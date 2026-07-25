import { localModelsApi } from '../../api/localModels';
import { modelPacksApi } from '../../api/modelPacks';
import { getParsedApiError } from '../../api/error';
import type {
  LocalModelAssignment,
  LocalModelMutationResponse,
  LocalModelProgress,
  LocalModelPullResult,
  LocalModelRuntimeState,
  ModelPackImportResult,
} from '../../types/localModels';


const WEB_PULL_POLL_INTERVAL_MS = 750;
const WEB_PULL_TIMEOUT_MS = 31 * 60 * 1000;
const WEB_MODEL_PACK_POLL_INTERVAL_MS = 750;
const OLLAMA_INSTALL_GUIDE_URL = 'https://ollama.com/download';

interface DesktopLocalModelState {
  runtime?: unknown;
  status?: unknown;
  installedModels?: unknown;
  managed?: unknown;
  operation?: unknown;
  progress?: unknown;
  totalMemoryGb?: unknown;
  runtimeIdentity?: unknown;
}

interface DesktopOperationResult {
  ok?: unknown;
  modelId?: unknown;
  error?: unknown;
  runtimeIdentity?: unknown;
  weightsMutationAttempted?: unknown;
  canceled?: unknown;
  message?: unknown;
  displayName?: unknown;
  minimumMemoryGb?: unknown;
  licenseId?: unknown;
  warnings?: unknown;
  desktopAttestation?: unknown;
}

export interface DesktopLocalModelBridge {
  getState: () => Promise<DesktopLocalModelState>;
  detect: () => Promise<DesktopLocalModelState>;
  start: () => Promise<DesktopLocalModelState>;
  stop: () => Promise<DesktopLocalModelState>;
  pull: (modelId: string) => Promise<DesktopOperationResult>;
  remove: (modelId: string, expectedRuntimeIdentity: string) => Promise<DesktopOperationResult>;
  importPack: (expectedConfigVersion: string) => Promise<DesktopOperationResult>;
  openInstallGuide: () => Promise<boolean>;
  onStateChange: (listener: (state: DesktopLocalModelState) => void) => (() => void) | void;
}

declare global {
  interface Window {
    stockPulseLocalModels?: DesktopLocalModelBridge;
  }
}

export class LocalModelTransportError extends Error {
  code: string;
  manualCommand?: string;

  constructor(code: string, message: string, manualCommand?: string) {
    super(message);
    this.name = 'LocalModelTransportError';
    this.code = code;
    this.manualCommand = manualCommand;
  }
}

export interface LocalModelTransport {
  kind: 'desktop' | 'web';
  canControlRuntime: boolean;
  getRuntime(): Promise<LocalModelRuntimeState>;
  pull(
    modelId: string,
    onProgress: (progress: LocalModelProgress) => void,
    signal?: AbortSignal,
  ): Promise<LocalModelPullResult>;
  remove(modelId: string): Promise<LocalModelMutationResponse>;
  importPack(
    file: File | null,
    onProgress: (progress: LocalModelProgress) => void,
    signal?: AbortSignal,
  ): Promise<ModelPackImportResult | null>;
  assign(modelId: string, assignment: LocalModelAssignment): Promise<LocalModelMutationResponse>;
  start?(): Promise<LocalModelRuntimeState>;
  stop?(): Promise<LocalModelRuntimeState>;
  openInstallGuide(): Promise<void>;
  subscribe?(listener: (state: LocalModelRuntimeState) => void): () => void;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object';
}

function normalizeProgress(value: unknown): LocalModelProgress | null {
  if (!isRecord(value) || typeof value.modelId !== 'string') return null;
  return {
    modelId: value.modelId,
    percent: typeof value.percent === 'number' ? value.percent : null,
    status: typeof value.status === 'string' ? value.status : '',
  };
}

function normalizeDesktopState(
  value: DesktopLocalModelState,
  configuration: LocalModelRuntimeState['configuration'],
): LocalModelRuntimeState {
  const installedModels = Array.isArray(value.installedModels)
    ? value.installedModels.filter((model): model is string => typeof model === 'string')
    : [];
  const allowedStatuses = new Set<LocalModelRuntimeState['status']>([
    'unknown',
    'running',
    'unavailable',
    'not-installed',
    'stopped',
    'starting',
    'error',
  ]);
  const status = typeof value.status === 'string'
    && allowedStatuses.has(value.status as LocalModelRuntimeState['status'])
    ? value.status as LocalModelRuntimeState['status']
    : 'unknown';
  return {
    runtime: 'ollama',
    status,
    installedModels,
    manualPullSupported: status !== 'running',
    configuration,
    managed: value.managed === true,
    operation: typeof value.operation === 'string' ? value.operation : null,
    progress: normalizeProgress(value.progress),
    totalMemoryGb: typeof value.totalMemoryGb === 'number' ? value.totalMemoryGb : null,
  };
}

function waitForPoll(delayMs: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Operation aborted', 'AbortError'));
      return;
    }

    const handleAbort = () => {
      window.clearTimeout(timer);
      reject(new DOMException('Operation aborted', 'AbortError'));
    };
    const timer = window.setTimeout(() => {
      signal?.removeEventListener('abort', handleAbort);
      resolve();
    }, delayMs);
    signal?.addEventListener('abort', handleAbort, { once: true });
  });
}

async function pollWebPull(
  taskId: string,
  onProgress: (progress: LocalModelProgress) => void,
  signal?: AbortSignal,
): Promise<LocalModelPullResult> {
  const deadline = Date.now() + WEB_PULL_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const task = await localModelsApi.getPull(taskId);
    onProgress({ modelId: task.modelId, percent: task.progress, status: task.status });
    if (task.status === 'completed' && task.result) {
      if (!task.result.activated) {
        throw new LocalModelTransportError(
          'local_model_activation_failed',
          'Local model configuration failed',
        );
      }
      return task.result;
    }
    if (['failed', 'cancelled', 'interrupted'].includes(task.status)) {
      throw new LocalModelTransportError(
        task.error || 'local_model_pull_failed',
        'Local model download failed',
        `ollama pull ${task.modelId}`,
      );
    }
    await waitForPoll(WEB_PULL_POLL_INTERVAL_MS, signal);
  }
  throw new LocalModelTransportError('local_model_pull_timeout', 'Local model download timed out');
}

async function pollWebModelPackImport(
  taskId: string,
  onProgress: (progress: LocalModelProgress) => void,
  signal?: AbortSignal,
): Promise<ModelPackImportResult> {
  while (true) {
    const task = await modelPacksApi.getImport(taskId);
    onProgress({
      modelId: task.result?.modelId ?? '',
      percent: Math.min(100, 20 + Math.round(task.progress * 0.8)),
      status: task.message || task.status,
    });
    if (task.status === 'completed' && task.result) {
      if (!task.result.activated) {
        throw new LocalModelTransportError(
          'registration_failed',
          'The model was created but could not be registered',
        );
      }
      return task.result;
    }
    if (['failed', 'cancelled', 'interrupted'].includes(task.status)) {
      throw new LocalModelTransportError(
        task.error || 'model_pack_import_failed',
        task.message || 'Model Pack import failed',
      );
    }
    await waitForPoll(WEB_MODEL_PACK_POLL_INTERVAL_MS, signal);
  }
}

function createWebTransport(): LocalModelTransport {
  return {
    kind: 'web',
    canControlRuntime: false,
    getRuntime: () => localModelsApi.getRuntime(),
    async pull(modelId, onProgress, signal) {
      try {
        const accepted = await localModelsApi.startPull(modelId);
        onProgress({ modelId, percent: 0, status: accepted.status });
        return await pollWebPull(accepted.taskId, onProgress, signal);
      } catch (error) {
        if (error instanceof LocalModelTransportError || (error instanceof DOMException && error.name === 'AbortError')) {
          throw error;
        }
        const parsed = getParsedApiError(error, 'en');
        throw new LocalModelTransportError(
          parsed.code || 'local_model_pull_submit_failed',
          'Local model download failed',
          parsed.code === 'local_model_runtime_unavailable'
            ? `ollama pull ${modelId}`
            : undefined,
        );
      }
    },
    remove: (modelId) => localModelsApi.deleteModel(modelId),
    async importPack(file, onProgress, signal) {
      if (!(file instanceof File)) {
        throw new LocalModelTransportError(
          'model_pack_source_required',
          'Select a Model Pack file',
        );
      }
      try {
        const accepted = await modelPacksApi.startImport(file, {
          signal,
          onUploadProgress: ({ loaded, total }) => {
            const percent = total && total > 0
              ? Math.min(20, Math.round((loaded / total) * 20))
              : null;
            onProgress({ modelId: '', percent, status: 'uploading' });
          },
        });
        onProgress({ modelId: '', percent: 20, status: accepted.status });
        return await pollWebModelPackImport(accepted.taskId, onProgress, signal);
      } catch (error) {
        if (error instanceof LocalModelTransportError
          || (error instanceof DOMException && error.name === 'AbortError')) {
          throw error;
        }
        const parsed = getParsedApiError(error, 'en');
        throw new LocalModelTransportError(
          parsed.code || 'model_pack_import_failed',
          'Model Pack import failed',
        );
      }
    },
    assign: (modelId, assignment) => localModelsApi.assign(modelId, assignment),
    async openInstallGuide() {
      window.open(OLLAMA_INSTALL_GUIDE_URL, '_blank', 'noopener,noreferrer');
    },
  };
}

function createDesktopTransport(bridge: DesktopLocalModelBridge): LocalModelTransport {
  const loadState = async (source: () => Promise<DesktopLocalModelState>) => {
    const [state, configuration] = await Promise.all([
      source(),
      localModelsApi.getConfiguration(),
    ]);
    return normalizeDesktopState(state, configuration);
  };
  const confirmedDeletion = (
    unregistered: LocalModelMutationResponse,
  ): LocalModelMutationResponse => ({
    ...unregistered,
    deleted: true,
  });
  const finalizeDeletedRegistration = async (
    modelId: string,
    recoveryToken: string,
    unregistered: LocalModelMutationResponse,
  ): Promise<LocalModelMutationResponse> => {
    let finalizationWarning = false;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        return await localModelsApi.finalizeUnregistration(modelId, recoveryToken);
      } catch (error) {
        const parsed = getParsedApiError(error, 'en');
        finalizationWarning = true;
        if (parsed.status !== undefined || ![
          'local_connection_failed',
          'upstream_network',
          'upstream_timeout',
          'unknown',
        ].includes(parsed.category)) {
          break;
        }
        // Retry once because the first response may have been lost after revocation.
      }
    }
    return {
      ...confirmedDeletion(unregistered),
      warnings: finalizationWarning
        ? [...unregistered.warnings, 'local_model_delete_finalize_unconfirmed']
        : unregistered.warnings,
    };
  };
  const confirmWeightsRemain = async (modelId: string): Promise<boolean> => {
    try {
      const state = await bridge.detect();
      if (state.status === 'running' && Array.isArray(state.installedModels)) {
        return state.installedModels.some(
          (installed) => typeof installed === 'string'
            && installed.toLowerCase() === modelId.toLowerCase(),
        );
      }
    } catch {
      // Recover conservatively when Desktop cannot confirm deletion state.
    }
    return true;
  };
  const restoreDeletionReservation = async (
    modelId: string,
    recoveryToken: string,
  ): Promise<'restored' | 'deleted'> => {
    try {
      await localModelsApi.restoreRegistration(modelId, recoveryToken);
      return 'restored';
    } catch (error) {
      if (getParsedApiError(error, 'en').code === 'local_model_not_installed') {
        return 'deleted';
      }
      throw new LocalModelTransportError(
        'local_model_delete_recovery_failed',
        'Local model deletion failed and registration could not be restored',
      );
    }
  };
  return {
    kind: 'desktop',
    canControlRuntime: true,
    getRuntime: () => loadState(bridge.detect),
    async pull(modelId, onProgress) {
      const configuration = await localModelsApi.getConfiguration();
      const unsubscribe = bridge.onStateChange((state) => {
        const progress = normalizeProgress(state.progress);
        if (progress) onProgress(progress);
      });
      try {
        const result = await bridge.pull(modelId);
        if (result.ok !== true) {
          throw new LocalModelTransportError(
            typeof result.error === 'string' ? result.error : 'local_model_pull_failed',
            'Local model download failed',
            `ollama pull ${modelId}`,
          );
        }
        const runtimeIdentity = typeof result.runtimeIdentity === 'string'
          ? result.runtimeIdentity
          : '';
        if (!runtimeIdentity) {
          throw new LocalModelTransportError(
            'local_model_runtime_snapshot_missing',
            'Local model runtime identity was not returned',
          );
        }
        let activation: LocalModelMutationResponse;
        try {
          activation = await localModelsApi.activateDesktop(
            modelId,
            configuration.configVersion,
            runtimeIdentity,
          );
        } catch {
          throw new LocalModelTransportError(
            'local_model_activation_failed',
            'Local model configuration failed',
          );
        }
        return {
          modelId,
          activated: true,
          selectedPrimary: activation.selectedPrimary,
        };
      } finally {
        if (typeof unsubscribe === 'function') unsubscribe();
      }
    },
    async remove(modelId) {
      const [configurationSnapshot, runtimeSnapshot] = await Promise.all([
        localModelsApi.getConfiguration(),
        bridge.detect(),
      ]);
      const runtimeIdentity = typeof runtimeSnapshot.runtimeIdentity === 'string'
        ? runtimeSnapshot.runtimeIdentity
        : '';
      if (!runtimeIdentity) {
        throw new LocalModelTransportError(
          'local_model_runtime_snapshot_missing',
          'Local model runtime identity was not returned',
        );
      }
      const configuration = await localModelsApi.unregister(
        modelId,
        configurationSnapshot.configVersion,
        runtimeIdentity,
      );
      if (!configuration.recoveryToken) {
        throw new LocalModelTransportError(
          'local_model_delete_recovery_failed',
          'Local model deletion reservation was not issued',
        );
      }
      let result: DesktopOperationResult;
      try {
        result = await bridge.remove(modelId, runtimeIdentity);
      } catch (error) {
        if (!await confirmWeightsRemain(modelId)) {
          return finalizeDeletedRegistration(
            modelId,
            configuration.recoveryToken,
            configuration,
          );
        }
        const recovery = await restoreDeletionReservation(
          modelId,
          configuration.recoveryToken,
        );
        if (recovery === 'deleted') return confirmedDeletion(configuration);
        throw error;
      }
      if (result.ok !== true) {
        let weightsRemain = result.weightsMutationAttempted !== true;
        if (result.weightsMutationAttempted === true) {
          weightsRemain = await confirmWeightsRemain(modelId);
        }
        if (weightsRemain) {
          const recovery = await restoreDeletionReservation(
            modelId,
            configuration.recoveryToken,
          );
          if (recovery === 'deleted') return confirmedDeletion(configuration);
        } else {
          return finalizeDeletedRegistration(
            modelId,
            configuration.recoveryToken,
            configuration,
          );
        }
        throw new LocalModelTransportError(
          typeof result.error === 'string' ? result.error : 'local_model_delete_failed',
          'Local model deletion failed',
        );
      }
      return finalizeDeletedRegistration(
        modelId,
        configuration.recoveryToken,
        configuration,
      );
    },
    async importPack(_file, onProgress) {
      const configuration = await localModelsApi.getConfiguration();
      const unsubscribe = bridge.onStateChange((state) => {
        const nextProgress = normalizeProgress(state.progress);
        if (nextProgress && state.operation === 'import') onProgress(nextProgress);
      });
      try {
        const result = await bridge.importPack(configuration.configVersion);
        if (result.canceled === true) return null;
        if (result.ok !== true) {
          throw new LocalModelTransportError(
            typeof result.error === 'string' ? result.error : 'model_pack_import_failed',
            typeof result.message === 'string' ? result.message : 'Model Pack import failed',
          );
        }
        const modelId = typeof result.modelId === 'string' ? result.modelId : '';
        const displayName = typeof result.displayName === 'string' ? result.displayName : '';
        const minimumMemoryGb = typeof result.minimumMemoryGb === 'number'
          ? result.minimumMemoryGb
          : 0;
        const licenseId = typeof result.licenseId === 'string' ? result.licenseId : '';
        const runtimeIdentity = typeof result.runtimeIdentity === 'string'
          ? result.runtimeIdentity
          : '';
        const desktopAttestation = typeof result.desktopAttestation === 'string'
          ? result.desktopAttestation
          : '';
        if (!modelId || !displayName || !minimumMemoryGb || !licenseId
          || !runtimeIdentity || !desktopAttestation) {
          throw new LocalModelTransportError(
            'local_model_runtime_snapshot_missing',
            'Desktop did not return a complete validated Model Pack snapshot',
          );
        }
        const manifest = { modelId, displayName, minimumMemoryGb, licenseId };
        let activation: LocalModelMutationResponse;
        try {
          activation = await modelPacksApi.activateDesktop(
            manifest,
            configuration.configVersion,
            runtimeIdentity,
            desktopAttestation,
          );
        } catch (error) {
          const parsed = getParsedApiError(error, 'en');
          throw new LocalModelTransportError(
            parsed.code || 'registration_failed',
            'The model was created but could not be registered',
          );
        }
        return {
          ...manifest,
          warnings: Array.isArray(result.warnings)
            ? result.warnings.filter((warning): warning is string => typeof warning === 'string')
            : [],
          activated: true,
          selectedPrimary: activation.selectedPrimary,
        };
      } finally {
        if (typeof unsubscribe === 'function') unsubscribe();
      }
    },
    assign: (modelId, assignment) => localModelsApi.assign(modelId, assignment),
    start: () => loadState(bridge.start),
    stop: () => loadState(bridge.stop),
    async openInstallGuide() {
      await bridge.openInstallGuide();
    },
    subscribe(listener) {
      let active = true;
      const unsubscribe = bridge.onStateChange((state) => {
        void localModelsApi.getConfiguration().then((configuration) => {
          if (active) listener(normalizeDesktopState(state, configuration));
        }).catch(() => undefined);
      });
      return () => {
        active = false;
        if (typeof unsubscribe === 'function') unsubscribe();
      };
    },
  };
}

export function createLocalModelTransport(): LocalModelTransport {
  const bridge = window.stockPulseLocalModels;
  return bridge ? createDesktopTransport(bridge) : createWebTransport();
}

export const __localModelTransportTest = {
  createDesktopTransport,
  createWebTransport,
  normalizeDesktopState,
  pollWebPull,
  pollWebModelPackImport,
};
