import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LocalModelConfiguration } from '../../../types/localModels';
import {
  __localModelTransportTest,
  createLocalModelTransport,
  LocalModelTransportError,
  type DesktopLocalModelBridge,
} from '../localModelTransport';

const api = vi.hoisted(() => ({
  getRuntime: vi.fn(),
  getConfiguration: vi.fn(),
  startPull: vi.fn(),
  getPull: vi.fn(),
  assign: vi.fn(),
  activateDesktop: vi.fn(),
  deleteModel: vi.fn(),
  unregister: vi.fn(),
  restoreRegistration: vi.fn(),
  finalizeUnregistration: vi.fn(),
}));
const packApi = vi.hoisted(() => ({
  startImport: vi.fn(),
  getImport: vi.fn(),
  activateDesktop: vi.fn(),
}));

vi.mock('../../../api/localModels', () => ({ localModelsApi: api }));
vi.mock('../../../api/modelPacks', () => ({ modelPacksApi: packApi }));

const RUNTIME_IDENTITY = 'b26993598dffd1f14aed97def57ef67f753518a9b773d8a12033c82b4fa545ca';

const CONFIGURATION: LocalModelConfiguration = {
  configVersion: 'config-1',
  registeredModels: [],
  primaryModel: '',
  agentModel: '',
};

function createDesktopBridge(): DesktopLocalModelBridge {
  return {
    getState: vi.fn().mockResolvedValue({ status: 'running' }),
    detect: vi.fn().mockResolvedValue({
      status: 'running',
      installedModels: ['qwen3:4b'],
      totalMemoryGb: 24,
      runtimeIdentity: RUNTIME_IDENTITY,
    }),
    start: vi.fn().mockResolvedValue({ status: 'running' }),
    stop: vi.fn().mockResolvedValue({ status: 'stopped' }),
    pull: vi.fn().mockResolvedValue({
      ok: true,
      modelId: 'qwen3:4b',
      runtimeIdentity: RUNTIME_IDENTITY,
    }),
    remove: vi.fn().mockResolvedValue({
      ok: true,
      modelId: 'qwen3:4b',
      weightsMutationAttempted: true,
    }),
    importPack: vi.fn().mockResolvedValue({
      ok: true,
      modelId: 'licensed/finance:q4',
      displayName: 'Licensed Finance Q4',
      minimumMemoryGb: 16,
      licenseId: 'LicenseRef-Finance',
      warnings: [],
      runtimeIdentity: RUNTIME_IDENTITY,
    }),
    openInstallGuide: vi.fn().mockResolvedValue(true),
    onStateChange: vi.fn().mockReturnValue(() => undefined),
  };
}

describe('localModelTransport', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete window.stockPulseLocalModels;
    api.getConfiguration.mockResolvedValue(CONFIGURATION);
    packApi.activateDesktop.mockResolvedValue({ selectedPrimary: false });
  });

  it('uploads and polls a Model Pack through the Web task contract', async () => {
    vi.useFakeTimers();
    try {
      packApi.startImport.mockImplementation(async (_file, options) => {
        options.onUploadProgress({ loaded: 5, total: 10 });
        return { taskId: 'pack-1', status: 'accepted' };
      });
      packApi.getImport
        .mockResolvedValueOnce({
          taskId: 'pack-1',
          status: 'processing',
          progress: 50,
          message: 'Creating model',
        })
        .mockResolvedValueOnce({
          taskId: 'pack-1',
          status: 'completed',
          progress: 100,
          result: {
            modelId: 'licensed/finance:q4',
            displayName: 'Licensed Finance Q4',
            minimumMemoryGb: 16,
            licenseId: 'LicenseRef-Finance',
            warnings: [],
            activated: true,
            selectedPrimary: false,
          },
        });
      const progress = vi.fn();
      const file = new File(['pack'], 'finance.modelpack');

      const resultPromise = __localModelTransportTest.createWebTransport()
        .importPack(file, progress);
      await vi.advanceTimersByTimeAsync(750);

      await expect(resultPromise).resolves.toMatchObject({
        modelId: 'licensed/finance:q4',
        activated: true,
      });
      expect(packApi.startImport).toHaveBeenCalledWith(file, expect.any(Object));
      expect(progress).toHaveBeenCalledWith({
        modelId: '',
        percent: 60,
        status: 'Creating model',
      });
    } finally {
      vi.useRealTimers();
    }
  });

  it('uses the backend task contract and emits polled progress in Web mode', async () => {
    vi.useFakeTimers();
    try {
      api.startPull.mockResolvedValue({ taskId: 'pull-1', status: 'pending' });
      api.getPull
        .mockResolvedValueOnce({
          taskId: 'pull-1',
          status: 'processing',
          progress: 41,
          modelId: 'qwen3:4b',
        })
        .mockResolvedValueOnce({
          taskId: 'pull-1',
          status: 'completed',
          progress: 100,
          modelId: 'qwen3:4b',
          result: { modelId: 'qwen3:4b', activated: true, selectedPrimary: true },
        });
      const progress = vi.fn();

      const resultPromise = __localModelTransportTest.createWebTransport()
        .pull('qwen3:4b', progress);
      await vi.advanceTimersByTimeAsync(750);

      await expect(resultPromise).resolves.toEqual({
        modelId: 'qwen3:4b',
        activated: true,
        selectedPrimary: true,
      });
      expect(api.startPull).toHaveBeenCalledWith('qwen3:4b');
      expect(progress).toHaveBeenCalledWith({
        modelId: 'qwen3:4b',
        percent: 41,
        status: 'processing',
      });
    } finally {
      vi.useRealTimers();
    }
  });

  it('returns a safe manual command only for an explicit Web runtime failure', async () => {
    const runtimeError = Object.assign(new Error('private runtime details'), {
      parsedError: {
        title: 'Request failed',
        message: 'Request failed',
        rawMessage: 'private runtime details',
        category: 'http_error',
        code: 'local_model_runtime_unavailable',
      },
    });
    api.startPull.mockRejectedValue(runtimeError);

    await expect(
      __localModelTransportTest.createWebTransport().pull('qwen3:4b', () => undefined),
    ).rejects.toMatchObject({
      code: 'local_model_runtime_unavailable',
      manualCommand: 'ollama pull qwen3:4b',
    } satisfies Partial<LocalModelTransportError>);
  });

  it('does not recommend another pull when Web download activation fails', async () => {
    api.startPull.mockResolvedValue({ taskId: 'pull-activation', status: 'pending' });
    api.getPull.mockResolvedValue({
      taskId: 'pull-activation',
      status: 'completed',
      progress: 100,
      modelId: 'qwen3:4b',
      result: {
        modelId: 'qwen3:4b',
        activated: false,
        selectedPrimary: false,
      },
    });

    await expect(
      __localModelTransportTest.createWebTransport().pull('qwen3:4b', () => undefined),
    ).rejects.toMatchObject({
      code: 'local_model_activation_failed',
      manualCommand: undefined,
    } satisfies Partial<LocalModelTransportError>);
  });

  it('does not mislabel a configuration conflict as an Ollama outage', async () => {
    const conflict = Object.assign(new Error('configuration conflict'), {
      parsedError: {
        title: 'Configuration conflict',
        message: 'Refresh and retry',
        rawMessage: 'configuration conflict',
        category: 'http_error',
        code: 'config_version_conflict',
      },
    });
    api.startPull.mockRejectedValue(conflict);

    await expect(
      __localModelTransportTest.createWebTransport().pull('qwen3:4b', () => undefined),
    ).rejects.toMatchObject({
      code: 'config_version_conflict',
      manualCommand: undefined,
    } satisfies Partial<LocalModelTransportError>);
  });

  it('selects desktop IPC, reports host memory, and activates through the backend authority', async () => {
    const bridge = createDesktopBridge();
    window.stockPulseLocalModels = bridge;
    api.activateDesktop.mockResolvedValue({ selectedPrimary: false });
    const transport = createLocalModelTransport();

    await expect(transport.getRuntime()).resolves.toMatchObject({
      status: 'running',
      installedModels: ['qwen3:4b'],
      totalMemoryGb: 24,
      configuration: CONFIGURATION,
    });
    await expect(transport.pull('qwen3:4b', () => undefined)).resolves.toEqual({
      modelId: 'qwen3:4b',
      activated: true,
      selectedPrimary: false,
    });
    expect(bridge.pull).toHaveBeenCalledWith('qwen3:4b');
    expect(api.activateDesktop).toHaveBeenCalledWith(
      'qwen3:4b',
      'config-1',
      RUNTIME_IDENTITY,
    );
  });

  it('activates Desktop-imported manifest metadata against the pre-import snapshot', async () => {
    const bridge = createDesktopBridge();
    const transport = __localModelTransportTest.createDesktopTransport(bridge);

    await expect(transport.importPack(null, () => undefined)).resolves.toMatchObject({
      modelId: 'licensed/finance:q4',
      displayName: 'Licensed Finance Q4',
      activated: true,
    });
    expect(bridge.importPack).toHaveBeenCalledTimes(1);
    expect(packApi.activateDesktop).toHaveBeenCalledWith(
      {
        modelId: 'licensed/finance:q4',
        displayName: 'Licensed Finance Q4',
        minimumMemoryGb: 16,
        licenseId: 'LicenseRef-Finance',
      },
      'config-1',
      RUNTIME_IDENTITY,
    );
    expect(api.getConfiguration.mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(bridge.importPack).mock.invocationCallOrder[0],
    );
  });

  it('does not activate when the Desktop native picker is cancelled', async () => {
    const bridge = createDesktopBridge();
    vi.mocked(bridge.importPack).mockResolvedValue({ ok: false, canceled: true });

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge)
        .importPack(null, () => undefined),
    ).resolves.toBeNull();
    expect(packApi.activateDesktop).not.toHaveBeenCalled();
  });

  it('does not recommend another pull when desktop activation fails after download', async () => {
    const bridge = createDesktopBridge();
    api.activateDesktop.mockRejectedValue(new Error('configuration conflict'));

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge).pull(
        'qwen3:4b',
        () => undefined,
      ),
    ).rejects.toMatchObject({
      code: 'local_model_activation_failed',
      manualCommand: undefined,
    } satisfies Partial<LocalModelTransportError>);
    expect(bridge.pull).toHaveBeenCalledWith('qwen3:4b');
  });

  it('validates and unregisters before asking desktop IPC to delete model weights', async () => {
    const bridge = createDesktopBridge();
    const mutation = {
      ...CONFIGURATION,
      success: true,
      modelId: 'qwen3:4b',
      selectedPrimary: false,
      selectedAgent: false,
      deleted: false,
      updatedKeys: ['LLM_OLLAMA_MODELS'],
      warnings: [],
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      recoveryToken: 'recovery-1',
    };
    api.unregister.mockResolvedValue(mutation);
    const finalized = { ...mutation, deleted: true };
    api.finalizeUnregistration.mockResolvedValue(finalized);

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge).remove('qwen3:4b'),
    ).resolves.toEqual(finalized);
    expect(api.unregister).toHaveBeenCalledWith(
      'qwen3:4b',
      'config-1',
      RUNTIME_IDENTITY,
    );
    expect(bridge.remove).toHaveBeenCalledWith(
      'qwen3:4b',
      RUNTIME_IDENTITY,
    );
    expect(api.finalizeUnregistration).toHaveBeenCalledWith(
      'qwen3:4b',
      'recovery-1',
    );
    expect(api.unregister.mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(bridge.remove).mock.invocationCallOrder[0],
    );
  });

  it('keeps successful weight deletion successful when recovery finalization fails', async () => {
    const bridge = createDesktopBridge();
    const mutation = {
      ...CONFIGURATION,
      success: true,
      modelId: 'qwen3:4b',
      selectedPrimary: false,
      selectedAgent: false,
      deleted: false,
      updatedKeys: ['LLM_OLLAMA_MODELS'],
      warnings: [],
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      recoveryToken: 'recovery-1',
    };
    api.unregister.mockResolvedValue(mutation);
    api.finalizeUnregistration.mockRejectedValue(new Error('network failure'));

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge).remove('qwen3:4b'),
    ).resolves.toEqual({
      ...mutation,
      deleted: true,
      warnings: ['local_model_delete_finalize_unconfirmed'],
    });
    expect(bridge.remove).toHaveBeenCalledWith(
      'qwen3:4b',
      RUNTIME_IDENTITY,
    );
    expect(api.restoreRegistration).not.toHaveBeenCalled();
    expect(api.finalizeUnregistration).toHaveBeenCalledTimes(2);
  });

  it('keeps confirmed deletion successful with a warning after a finalization conflict', async () => {
    const bridge = createDesktopBridge();
    const mutation = {
      ...CONFIGURATION,
      success: true,
      modelId: 'qwen3:4b',
      selectedPrimary: false,
      selectedAgent: false,
      deleted: false,
      updatedKeys: ['LLM_OLLAMA_MODELS'],
      warnings: [],
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      recoveryToken: 'recovery-1',
    };
    api.unregister.mockResolvedValue(mutation);
    api.finalizeUnregistration.mockRejectedValue(Object.assign(new Error('conflict'), {
      parsedError: {
        title: 'Configuration conflict',
        message: 'Refresh and retry',
        rawMessage: 'conflict',
        status: 409,
        category: 'http_error',
        code: 'config_version_conflict',
      },
    }));

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge).remove('qwen3:4b'),
    ).resolves.toEqual({
      ...mutation,
      deleted: true,
      warnings: ['local_model_delete_finalize_unconfirmed'],
    });
    expect(api.finalizeUnregistration).toHaveBeenCalledTimes(1);
    expect(api.restoreRegistration).not.toHaveBeenCalled();
  });

  it('does not mutate desktop weights when backend active-model validation fails', async () => {
    const bridge = createDesktopBridge();
    api.unregister.mockRejectedValue(new Error('model in use'));

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge).remove('qwen3:4b'),
    ).rejects.toThrow('model in use');
    expect(bridge.remove).not.toHaveBeenCalled();
  });

  it('restores registration when the runtime changes before weight mutation', async () => {
    const bridge = createDesktopBridge();
    const mutation = {
      ...CONFIGURATION,
      success: true,
      modelId: 'qwen3:4b',
      selectedPrimary: false,
      selectedAgent: false,
      deleted: false,
      updatedKeys: ['LLM_OLLAMA_MODELS'],
      warnings: [],
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      recoveryToken: 'recovery-1',
    };
    api.unregister.mockResolvedValue(mutation);
    api.restoreRegistration.mockResolvedValue({ ...mutation, deleted: false });
    vi.mocked(bridge.remove).mockResolvedValue({
      ok: false,
      error: 'runtime-changed',
      weightsMutationAttempted: false,
    });
    vi.mocked(bridge.detect).mockResolvedValue({
      status: 'running',
      installedModels: [],
      runtimeIdentity: RUNTIME_IDENTITY,
    });

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge).remove('qwen3:4b'),
    ).rejects.toMatchObject({ code: 'runtime-changed' });
    expect(bridge.detect).toHaveBeenCalledTimes(1);
    expect(api.restoreRegistration).toHaveBeenCalledWith('qwen3:4b', 'recovery-1');
  });

  it('classifies a missing rollback capability as deletion recovery failure', async () => {
    const bridge = createDesktopBridge();
    api.unregister.mockResolvedValue({
      ...CONFIGURATION,
      success: true,
      modelId: 'qwen3:4b',
      selectedPrimary: false,
      selectedAgent: false,
      deleted: false,
      updatedKeys: ['LLM_OLLAMA_MODELS'],
      warnings: [],
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
    });
    vi.mocked(bridge.remove).mockResolvedValue({
      ok: false,
      error: 'delete-failed',
      weightsMutationAttempted: false,
    });

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge).remove('qwen3:4b'),
    ).rejects.toMatchObject({ code: 'local_model_delete_recovery_failed' });
    expect(bridge.remove).not.toHaveBeenCalled();
    expect(api.restoreRegistration).not.toHaveBeenCalled();
  });

  it('classifies a rejected rollback as deletion recovery failure', async () => {
    const bridge = createDesktopBridge();
    api.unregister.mockResolvedValue({
      ...CONFIGURATION,
      success: true,
      modelId: 'qwen3:4b',
      selectedPrimary: false,
      selectedAgent: false,
      deleted: false,
      updatedKeys: ['LLM_OLLAMA_MODELS'],
      warnings: [],
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      recoveryToken: 'recovery-1',
    });
    api.restoreRegistration.mockRejectedValue(new Error('conflict'));
    vi.mocked(bridge.remove).mockResolvedValue({
      ok: false,
      error: 'delete-failed',
      weightsMutationAttempted: false,
    });

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge).remove('qwen3:4b'),
    ).rejects.toMatchObject({ code: 'local_model_delete_recovery_failed' });
  });

  it('treats a missing-weight recovery verdict as confirmed deletion', async () => {
    const bridge = createDesktopBridge();
    const mutation = {
      ...CONFIGURATION,
      success: true,
      modelId: 'qwen3:4b',
      selectedPrimary: false,
      selectedAgent: false,
      deleted: false,
      updatedKeys: ['LLM_OLLAMA_MODELS'],
      warnings: [],
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      recoveryToken: 'recovery-1',
    };
    api.unregister.mockResolvedValue(mutation);
    api.restoreRegistration.mockRejectedValue(Object.assign(new Error('weights missing'), {
      parsedError: {
        title: 'Request failed',
        message: 'Request failed',
        rawMessage: 'weights missing',
        status: 409,
        category: 'http_error',
        code: 'local_model_not_installed',
      },
    }));
    vi.mocked(bridge.remove).mockResolvedValue({
      ok: false,
      error: 'delete-failed',
      weightsMutationAttempted: true,
    });

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge).remove('qwen3:4b'),
    ).resolves.toEqual({ ...mutation, deleted: true });
    expect(bridge.detect).toHaveBeenCalledTimes(2);
    expect(api.restoreRegistration).toHaveBeenCalledWith('qwen3:4b', 'recovery-1');
    expect(api.finalizeUnregistration).not.toHaveBeenCalled();
  });

  it('restores registration when a stopped runtime cannot confirm weight state', async () => {
    const bridge = createDesktopBridge();
    const mutation = {
      ...CONFIGURATION,
      success: true,
      modelId: 'qwen3:4b',
      selectedPrimary: false,
      selectedAgent: false,
      deleted: false,
      updatedKeys: ['LLM_OLLAMA_MODELS'],
      warnings: [],
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      recoveryToken: 'recovery-1',
    };
    api.unregister.mockResolvedValue(mutation);
    api.restoreRegistration.mockResolvedValue({ ...mutation, deleted: false });
    vi.mocked(bridge.remove).mockResolvedValue({
      ok: false,
      error: 'delete-failed',
      weightsMutationAttempted: true,
    });
    vi.mocked(bridge.detect).mockResolvedValue({
      status: 'stopped',
      installedModels: [],
      runtimeIdentity: RUNTIME_IDENTITY,
    });

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge).remove('qwen3:4b'),
    ).rejects.toMatchObject({ code: 'delete-failed' });
    expect(api.restoreRegistration).toHaveBeenCalledWith('qwen3:4b', 'recovery-1');
  });

  it('releases the deletion reservation when Desktop IPC rejects ambiguously', async () => {
    const bridge = createDesktopBridge();
    const mutation = {
      ...CONFIGURATION,
      success: true,
      modelId: 'qwen3:4b',
      selectedPrimary: false,
      selectedAgent: false,
      deleted: false,
      updatedKeys: ['LLM_OLLAMA_MODELS'],
      warnings: [],
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      recoveryToken: 'recovery-1',
    };
    api.unregister.mockResolvedValue(mutation);
    api.restoreRegistration.mockResolvedValue({ ...mutation, deleted: false });
    vi.mocked(bridge.remove).mockRejectedValue(new Error('ipc disconnected'));

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge).remove('qwen3:4b'),
    ).rejects.toThrow('ipc disconnected');
    expect(bridge.detect).toHaveBeenCalledTimes(2);
    expect(api.restoreRegistration).toHaveBeenCalledWith('qwen3:4b', 'recovery-1');
  });

  it('finalizes confirmed deletion when Desktop IPC rejects after mutation', async () => {
    const bridge = createDesktopBridge();
    const mutation = {
      ...CONFIGURATION,
      success: true,
      modelId: 'qwen3:4b',
      selectedPrimary: false,
      selectedAgent: false,
      deleted: false,
      updatedKeys: [],
      warnings: [],
      appliedCount: 0,
      skippedMaskedCount: 0,
      reloadTriggered: false,
      recoveryToken: 'recovery-1',
    };
    const finalized = { ...mutation, deleted: true };
    api.unregister.mockResolvedValue(mutation);
    api.finalizeUnregistration.mockResolvedValue(finalized);
    vi.mocked(bridge.remove).mockRejectedValue(new Error('response lost'));
    vi.mocked(bridge.detect)
      .mockResolvedValueOnce({
        status: 'running',
        installedModels: ['qwen3:4b'],
        runtimeIdentity: RUNTIME_IDENTITY,
      })
      .mockResolvedValueOnce({
        status: 'running',
        installedModels: [],
        runtimeIdentity: RUNTIME_IDENTITY,
      });

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge).remove('qwen3:4b'),
    ).resolves.toEqual(finalized);
    expect(api.restoreRegistration).not.toHaveBeenCalled();
    expect(api.finalizeUnregistration).toHaveBeenCalledWith(
      'qwen3:4b',
      'recovery-1',
    );
  });

  it('keeps registration removed when the running runtime confirms weights are gone', async () => {
    const bridge = createDesktopBridge();
    const mutation = {
      ...CONFIGURATION,
      success: true,
      modelId: 'qwen3:4b',
      selectedPrimary: false,
      selectedAgent: false,
      deleted: false,
      updatedKeys: ['LLM_OLLAMA_MODELS'],
      warnings: [],
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      recoveryToken: 'recovery-1',
    };
    api.unregister.mockResolvedValue(mutation);
    const finalized = { ...mutation, deleted: true };
    api.finalizeUnregistration.mockResolvedValue(finalized);
    vi.mocked(bridge.remove).mockResolvedValue({
      ok: false,
      error: 'delete-failed',
      weightsMutationAttempted: true,
    });
    vi.mocked(bridge.detect).mockResolvedValue({
      status: 'running',
      installedModels: [],
      runtimeIdentity: RUNTIME_IDENTITY,
    });

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge).remove('qwen3:4b'),
    ).resolves.toEqual(finalized);
    expect(api.restoreRegistration).not.toHaveBeenCalled();
    expect(api.finalizeUnregistration).toHaveBeenCalledWith(
      'qwen3:4b',
      'recovery-1',
    );
  });

  it('does not create registration while recovering an externally installed model', async () => {
    const bridge = createDesktopBridge();
    const mutation = {
      ...CONFIGURATION,
      success: true,
      modelId: 'qwen3:4b',
      selectedPrimary: false,
      selectedAgent: false,
      deleted: false,
      updatedKeys: [],
      warnings: [],
      appliedCount: 0,
      skippedMaskedCount: 0,
      reloadTriggered: false,
      recoveryToken: 'recovery-1',
    };
    api.unregister.mockResolvedValue(mutation);
    vi.mocked(bridge.remove).mockResolvedValue({
      ok: false,
      error: 'delete-failed',
      weightsMutationAttempted: false,
    });

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge).remove('qwen3:4b'),
    ).rejects.toMatchObject({ code: 'delete-failed' });
    expect(bridge.detect).toHaveBeenCalledTimes(1);
    expect(api.restoreRegistration).toHaveBeenCalledWith('qwen3:4b', 'recovery-1');
  });
});
