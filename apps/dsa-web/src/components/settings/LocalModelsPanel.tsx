import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Bot,
  Check,
  Copy,
  Download,
  ExternalLink,
  Play,
  RefreshCw,
  Square,
  Star,
  Trash2,
} from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  IconButton,
  InlineAlert,
  Loading,
  Section,
  StatusDot,
  useClipboard,
} from '../common';
import { localModelsApi } from '../../api/localModels';
import { formatUiText } from '../../i18n/uiText';
import { UI_LANGUAGE_METADATA, prefersChineseContent } from '../../i18n/uiLanguages';
import { SETTINGS_LOCAL_MODELS_TEXT } from '../../locales/settingsLocalModels';
import type {
  LocalModelCatalogEntry,
  LocalModelConfiguration,
  LocalModelProgress,
  LocalModelRuntimeState,
  LocalModelSection,
} from '../../types/localModels';
import { decodeModelRef } from '../../utils/modelRef';
import type { UiLang } from './settingsInformationArchitecture';
import {
  createLocalModelTransport,
  LocalModelTransportError,
  type LocalModelTransport,
} from './localModelTransport';


interface LocalModelsPanelProps {
  language: UiLang;
  headingAs?: 'h2' | 'h3' | 'h4';
  onConfigurationChanged?: () => void | Promise<void>;
  onModelReady?: (modelId: string) => void;
}

type OperationKind = 'pull' | 'assign-primary' | 'assign-agent' | 'delete' | 'runtime';

interface ActiveOperation {
  kind: OperationKind;
  modelId?: string;
}

const EMPTY_CONFIGURATION: LocalModelConfiguration = {
  configVersion: '',
  registeredModels: [],
  primaryModel: '',
  agentModel: '',
};

const CAPABILITY_TEXT_KEYS = {
  general: 'capabilityGeneral',
  reasoning: 'capabilityReasoning',
  multilingual: 'capabilityMultilingual',
  multimodal: 'capabilityMultimodal',
  agentic: 'capabilityAgentic',
  finance: 'capabilityFinance',
  chinese: 'capabilityChinese',
  dialogue: 'capabilityDialogue',
} as const;

const MEMORY_TIER_TEXT_KEYS = {
  light: 'memoryTierLight',
  standard: 'memoryTierStandard',
  high: 'memoryTierHigh',
} as const;

function runtimeRoute(value: string): string {
  return decodeModelRef(value)?.runtimeRoute ?? value.trim();
}

function modelRoute(modelId: string): string {
  return `ollama/${modelId}`;
}

function modelIsAssigned(value: string, modelId: string): boolean {
  return runtimeRoute(value) === modelRoute(modelId);
}

function browserMemoryGb(): number | null {
  const memory = (navigator as Navigator & { deviceMemory?: unknown }).deviceMemory;
  return typeof memory === 'number' && Number.isFinite(memory) && memory > 0 ? memory : null;
}

function recommendedRamForSection(
  models: LocalModelCatalogEntry[],
  section: LocalModelSection,
  memoryGb: number | null,
): number | null {
  if (memoryGb === null) return null;
  const fitting = models
    .filter((model) => model.section === section && model.recommendedRamGb <= memoryGb)
    .map((model) => model.recommendedRamGb);
  return fitting.length > 0 ? Math.max(...fitting) : null;
}

function configurationFromMutation(
  mutation: LocalModelConfiguration,
): LocalModelConfiguration {
  return {
    configVersion: mutation.configVersion,
    registeredModels: mutation.registeredModels,
    primaryModel: mutation.primaryModel,
    agentModel: mutation.agentModel,
  };
}

export const LocalModelsPanel: React.FC<LocalModelsPanelProps> = ({
  language,
  headingAs = 'h2',
  onConfigurationChanged,
  onModelReady,
}) => {
  const text = SETTINGS_LOCAL_MODELS_TEXT[language];
  const transport = useMemo<LocalModelTransport>(() => createLocalModelTransport(), []);
  const { copyText, copyError, clearCopyError } = useClipboard();
  const [models, setModels] = useState<LocalModelCatalogEntry[]>([]);
  const [runtime, setRuntime] = useState<LocalModelRuntimeState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [catalogFailed, setCatalogFailed] = useState(false);
  const [activeOperation, setActiveOperation] = useState<ActiveOperation | null>(null);
  const [progress, setProgress] = useState<LocalModelProgress | null>(null);
  const [actionError, setActionError] = useState('');
  const [manualCommand, setManualCommand] = useState('');
  const [copiedModel, setCopiedModel] = useState('');
  const [readyModel, setReadyModel] = useState('');
  const [primaryPromptModel, setPrimaryPromptModel] = useState('');
  const [deleteModel, setDeleteModel] = useState<LocalModelCatalogEntry | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const readyNotifiedRef = useRef('');

  const load = useCallback(async () => {
    setIsLoading(true);
    setCatalogFailed(false);
    setActionError('');
    try {
      const [catalog, nextRuntime] = await Promise.all([
        localModelsApi.getCatalog(),
        transport.getRuntime(),
      ]);
      setModels(catalog.models);
      setRuntime(nextRuntime);
    } catch {
      setCatalogFailed(true);
    } finally {
      setIsLoading(false);
    }
  }, [transport]);

  const refreshRuntime = useCallback(async () => {
    setActionError('');
    try {
      const nextRuntime = await transport.getRuntime();
      setRuntime(nextRuntime);
      return nextRuntime;
    } catch {
      setActionError(text.actionFailed);
      return null;
    }
  }, [text.actionFailed, transport]);

  useEffect(() => {
    void load();
    return () => abortRef.current?.abort();
  }, [load]);

  useEffect(() => {
    if (!transport.subscribe) return undefined;
    let active = true;
    const unsubscribe = transport.subscribe((state) => {
      if (!active) return;
      setRuntime(state);
      if (state.progress) setProgress(state.progress);
    });
    return () => {
      active = false;
      unsubscribe();
    };
  }, [transport]);

  const installedModels = useMemo(
    () => new Set(runtime?.installedModels.map((model) => model.toLowerCase()) ?? []),
    [runtime?.installedModels],
  );
  const configuration = runtime?.configuration ?? EMPTY_CONFIGURATION;
  const registeredModels = useMemo(
    () => new Set(configuration.registeredModels.map((model) => model.toLowerCase())),
    [configuration.registeredModels],
  );
  const memoryGb = runtime?.totalMemoryGb ?? browserMemoryGb();
  const recommendedBySection = useMemo(() => ({
    general: recommendedRamForSection(models, 'general', memoryGb),
    finance: recommendedRamForSection(models, 'finance', memoryGb),
  }), [memoryGb, models]);

  useEffect(() => {
    const ready = models.find((model) => {
      const tag = model.install.ollamaTag;
      return Boolean(
        tag
        && installedModels.has(tag.toLowerCase())
        && (
          registeredModels.has(tag.toLowerCase())
          || modelIsAssigned(configuration.primaryModel, tag)
          || modelIsAssigned(configuration.agentModel, tag)
        ),
      );
    });
    if (!ready?.install.ollamaTag) {
      if (readyNotifiedRef.current) {
        readyNotifiedRef.current = '';
        onModelReady?.('');
      }
      return;
    }
    if (readyNotifiedRef.current === ready.install.ollamaTag) return;
    readyNotifiedRef.current = ready.install.ollamaTag;
    onModelReady?.(ready.install.ollamaTag);
  }, [configuration.agentModel, configuration.primaryModel, installedModels, models, onModelReady, registeredModels]);

  const updateConfiguration = useCallback(async (next: LocalModelConfiguration) => {
    setRuntime((current) => current ? {
      ...current,
      configuration: configurationFromMutation(next),
    } : current);
    await onConfigurationChanged?.();
  }, [onConfigurationChanged]);

  const handlePull = async (model: LocalModelCatalogEntry) => {
    const modelId = model.install.ollamaTag;
    if (!modelId) return;
    const controller = new AbortController();
    abortRef.current?.abort();
    abortRef.current = controller;
    setActiveOperation({ kind: 'pull', modelId });
    setProgress({ modelId, percent: 0, status: 'pending' });
    setActionError('');
    setManualCommand('');
    setReadyModel('');
    setPrimaryPromptModel('');
    try {
      const result = await transport.pull(modelId, setProgress, controller.signal);
      const nextRuntime = await refreshRuntime();
      await onConfigurationChanged?.();
      setReadyModel(modelId);
      readyNotifiedRef.current = modelId;
      onModelReady?.(modelId);
      if (
        result.selectedPrimary
        || Boolean(nextRuntime && modelIsAssigned(nextRuntime.configuration.primaryModel, modelId))
      ) {
        setPrimaryPromptModel('');
      } else {
        setPrimaryPromptModel(modelId);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      setActionError(
        error instanceof LocalModelTransportError && error.code === 'local_model_activation_failed'
          ? text.actionFailed
          : text.pullFailed,
      );
      if (error instanceof LocalModelTransportError && error.manualCommand) {
        setManualCommand(error.manualCommand);
      } else {
        setManualCommand('');
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setActiveOperation(null);
    }
  };

  const handleAssignment = async (modelId: string, assignment: 'primary' | 'agent') => {
    setActiveOperation({
      kind: assignment === 'primary' ? 'assign-primary' : 'assign-agent',
      modelId,
    });
    setActionError('');
    try {
      const result = await transport.assign(modelId, assignment);
      await updateConfiguration(result);
      if (assignment === 'primary') {
        setPrimaryPromptModel('');
        readyNotifiedRef.current = modelId;
        onModelReady?.(modelId);
      }
    } catch {
      setActionError(text.actionFailed);
    } finally {
      setActiveOperation(null);
    }
  };

  const handleDelete = async () => {
    const modelId = deleteModel?.install.ollamaTag;
    if (!modelId) return;
    setDeleteModel(null);
    setActiveOperation({ kind: 'delete', modelId });
    setActionError('');
    try {
      const result = await transport.remove(modelId);
      await updateConfiguration(result);
      await refreshRuntime();
      setReadyModel('');
      readyNotifiedRef.current = '';
      onModelReady?.('');
    } catch {
      setActionError(text.actionFailed);
    } finally {
      setActiveOperation(null);
    }
  };

  const handleRuntimeAction = async (action: 'start' | 'stop') => {
    const operation = action === 'start' ? transport.start : transport.stop;
    if (!operation) return;
    setActiveOperation({ kind: 'runtime' });
    setActionError('');
    try {
      setRuntime(await operation());
    } catch {
      setActionError(text.actionFailed);
    } finally {
      setActiveOperation(null);
    }
  };

  const openDownloadGuide = (model: LocalModelCatalogEntry) => {
    window.open(model.install.downloadUrl, '_blank', 'noopener,noreferrer');
  };

  const copyCommand = async (modelId: string) => {
    clearCopyError();
    if (await copyText(formatUiText(text.manualPullCommand, { model: modelId }))) {
      setCopiedModel(modelId);
    }
  };

  const copyManualCommand = async () => {
    clearCopyError();
    await copyText(manualCommand);
  };

  const runtimeCopy = (() => {
    switch (runtime?.status) {
      case 'running': return { label: text.runtimeRunning, tone: 'success' as const };
      case 'stopped': return { label: text.runtimeStopped, tone: 'warning' as const };
      case 'starting': return { label: text.runtimeStarting, tone: 'info' as const };
      case 'not-installed': return { label: text.runtimeMissing, tone: 'danger' as const };
      case 'unavailable':
      case 'error': return { label: text.runtimeUnavailable, tone: 'danger' as const };
      default: return { label: text.runtimeUnknown, tone: 'neutral' as const };
    }
  })();

  if (isLoading) return <Loading label={text.runtimeUnknown} />;
  if (catalogFailed) {
    return (
      <EmptyState
        title={text.catalogFailed}
        action={<Button variant="secondary" onClick={() => void load()}>{text.refresh}</Button>}
      />
    );
  }

  const sectionCards = (section: LocalModelSection) => {
    const sectionModels = models.filter((model) => model.section === section);
    if (sectionModels.length === 0) return <EmptyState title={text.noModels} compact />;
    return sectionModels.map((model) => {
      const modelId = model.install.ollamaTag;
      const installed = Boolean(modelId && installedModels.has(modelId.toLowerCase()));
      const registered = Boolean(modelId && registeredModels.has(modelId.toLowerCase()));
      const primary = Boolean(modelId && modelIsAssigned(configuration.primaryModel, modelId));
      const agent = Boolean(modelId && modelIsAssigned(configuration.agentModel, modelId));
      const recommended = recommendedBySection[section] === model.recommendedRamGb;
      const pulling = activeOperation?.kind === 'pull' && activeOperation.modelId === modelId;
      const busy = activeOperation !== null;
      const directPull = model.install.method === 'ollama_pull'
        && model.install.status === 'available'
        && Boolean(modelId);
      const localizedName = prefersChineseContent(language) ? model.displayName.zh : model.displayName.en;
      const localizedSummary = prefersChineseContent(language)
        ? model.capabilitySummary.zh
        : model.capabilitySummary.en;
      const size = new Intl.NumberFormat(UI_LANGUAGE_METADATA[language].intlLocale, {
        maximumFractionDigits: 1,
      }).format(model.q4.sizeBytes / 1_000_000_000);
      const inUse = primary || agent;

      return (
        <Card
          key={model.id}
          variant="bordered"
          padding="sm"
          title={localizedName}
          headerRight={recommended ? <Badge variant="info"><Star aria-hidden="true" />{text.recommended}</Badge> : null}
          data-testid={`local-model-${model.id}`}
        >
          <div className="space-y-3">
            <p className="text-sm leading-6 text-secondary-text">{localizedSummary}</p>
            <div className="flex flex-wrap gap-1.5">
              <Badge>{formatUiText(text.size, { size: `${size} GB` })}</Badge>
              <Badge>{formatUiText(text.memory, { ram: model.recommendedRamGb })}</Badge>
              <Badge>{text[MEMORY_TIER_TEXT_KEYS[model.memoryTier]]}</Badge>
              <Badge>{model.license.identifier}</Badge>
              {installed ? <Badge variant="success"><Check aria-hidden="true" />{text.installed}</Badge> : null}
              {registered && !primary && !agent ? <Badge variant="info">{text.registered}</Badge> : null}
              {primary ? <Badge variant="success">{text.primary}</Badge> : null}
              {agent ? <Badge variant="info"><Bot aria-hidden="true" />{text.agent}</Badge> : null}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {model.capabilities.map((capability) => {
                const key = CAPABILITY_TEXT_KEYS[capability as keyof typeof CAPABILITY_TEXT_KEYS];
                return <Badge key={capability} variant="history">{key ? text[key] : capability}</Badge>;
              })}
            </div>

            {pulling ? (
              <div className="space-y-1.5" data-testid={`local-model-progress-${model.id}`}>
                <div
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={progress?.percent ?? undefined}
                  aria-label={`${localizedName} ${text.downloading}`}
                  className="h-1.5 overflow-hidden rounded-full bg-hover"
                >
                  <div
                    className="h-full rounded-full bg-primary transition-[width] duration-200"
                    style={{ width: `${progress?.percent ?? 4}%` }}
                  />
                </div>
                <p className="text-xs text-muted-text">
                  {progress?.percent === null ? text.downloading : `${progress?.percent ?? 0}%`}
                </p>
              </div>
            ) : null}

            {directPull && runtime?.status !== 'running' && !installed ? (
              <div className="flex min-w-0 items-center gap-2 rounded-lg bg-hover px-3 py-2">
                <code className="min-w-0 flex-1 truncate text-xs text-secondary-text">
                  {formatUiText(text.manualPullCommand, { model: modelId ?? '' })}
                </code>
                <Button variant="ghost" size="compact" onClick={() => void copyCommand(modelId ?? '')}>
                  {copiedModel === modelId ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
                  {copiedModel === modelId ? text.copied : text.copyCommand}
                </Button>
              </div>
            ) : null}

            {!directPull ? (
              <InlineAlert
                variant={model.install.status === 'license_review_required' ? 'warning' : 'info'}
                size="compact"
                message={model.install.status === 'license_review_required'
                  ? text.licenseReviewRequired
                  : text.conversionRequired}
              />
            ) : null}

            <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
              {directPull && !installed ? (
                <Button
                  variant="primary"
                  size="default"
                  disabled={busy || runtime?.status !== 'running'}
                  isLoading={pulling}
                  loadingText={text.downloading}
                  onClick={() => void handlePull(model)}
                >
                  <Download aria-hidden="true" />
                  {text.download}
                </Button>
              ) : null}
              {!directPull ? (
                <Button variant="secondary" size="default" onClick={() => openDownloadGuide(model)}>
                  <ExternalLink aria-hidden="true" />
                  {text.downloadGuide}
                </Button>
              ) : null}
              {installed && modelId && !primary ? (
                <Button
                  variant="secondary"
                  size="default"
                  disabled={busy}
                  onClick={() => void handleAssignment(modelId, 'primary')}
                >
                  <Star aria-hidden="true" />
                  {text.setPrimary}
                </Button>
              ) : null}
              {installed && modelId && !agent ? (
                <Button
                  variant="secondary"
                  size="default"
                  disabled={busy}
                  onClick={() => void handleAssignment(modelId, 'agent')}
                >
                  <Bot aria-hidden="true" />
                  {text.setAgent}
                </Button>
              ) : null}
              {installed && modelId ? (
                <IconButton
                  variant="danger"
                  size="default"
                  aria-label={text.deleteModel}
                  disabled={busy || inUse}
                  onClick={() => setDeleteModel(model)}
                >
                  <Trash2 aria-hidden="true" />
                </IconButton>
              ) : null}
            </div>
          </div>
        </Card>
      );
    });
  };

  return (
    <Section
      title={text.title}
      headingAs={headingAs}
      actions={(
        <IconButton
          variant="outline"
          size="default"
          aria-label={text.refresh}
          isLoading={activeOperation?.kind === 'runtime'}
          disabled={activeOperation !== null}
          onClick={() => void refreshRuntime()}
        >
          <RefreshCw aria-hidden="true" />
        </IconButton>
      )}
      data-testid="local-models-panel"
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-y border-border py-3">
          <div className="flex items-center gap-2 text-sm text-foreground">
            <StatusDot tone={runtimeCopy.tone} pulse={runtime?.status === 'starting'} />
            <span className="font-medium">{text.runtime}</span>
            <span className="text-secondary-text">{runtimeCopy.label}</span>
            {memoryGb !== null ? (
              <span className="text-muted-text">
                {formatUiText(text.detectedMemory, { ram: memoryGb })}
              </span>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            {transport.canControlRuntime && runtime?.status === 'stopped' ? (
              <Button
                variant="secondary"
                disabled={activeOperation !== null}
                onClick={() => void handleRuntimeAction('start')}
              >
                <Play aria-hidden="true" />{text.start}
              </Button>
            ) : null}
            {transport.canControlRuntime && runtime?.status === 'running' && runtime.managed ? (
              <Button
                variant="secondary"
                disabled={activeOperation !== null}
                onClick={() => void handleRuntimeAction('stop')}
              >
                <Square aria-hidden="true" />{text.stop}
              </Button>
            ) : null}
            {runtime?.status === 'not-installed' || runtime?.status === 'unavailable' ? (
              <Button
                variant="secondary"
                disabled={activeOperation !== null}
                onClick={() => void transport.openInstallGuide()}
              >
                <ExternalLink aria-hidden="true" />{text.installRuntime}
              </Button>
            ) : null}
          </div>
        </div>

        {runtime?.status === 'unavailable' || runtime?.status === 'not-installed' || runtime?.status === 'error' ? (
          <InlineAlert
            variant="warning"
            title={text.unavailableTitle}
            message={text.unavailableMessage}
          />
        ) : null}
        {readyModel ? (
          <InlineAlert
            variant="success"
            title={text.readyTitle}
            message={formatUiText(text.readyMessage, { model: readyModel })}
          />
        ) : null}
        {primaryPromptModel ? (
          <InlineAlert
            variant="info"
            message={formatUiText(text.keepPrimaryMessage, { model: primaryPromptModel })}
            action={(
              <Button
                variant="secondary"
                size="compact"
                onClick={() => void handleAssignment(primaryPromptModel, 'primary')}
              >
                <Star aria-hidden="true" />{text.setPrimary}
              </Button>
            )}
          />
        ) : null}
        {actionError ? <InlineAlert variant="danger" message={actionError} /> : null}
        {manualCommand ? (
          <InlineAlert
            variant="warning"
            message={<code>{manualCommand}</code>}
            action={(
              <Button variant="secondary" size="compact" onClick={() => void copyManualCommand()}>
                <Copy aria-hidden="true" />{text.copyCommand}
              </Button>
            )}
          />
        ) : null}
        {copyError ? <InlineAlert variant="danger" message={copyError} /> : null}

        <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          {(['general', 'finance'] as LocalModelSection[]).map((section) => (
            <section key={section} aria-labelledby={`local-models-${section}`}>
              <h3 id={`local-models-${section}`} className="mb-3 text-sm font-semibold text-foreground">
                {section === 'general' ? text.general : text.finance}
              </h3>
              <div className="space-y-3">{sectionCards(section)}</div>
            </section>
          ))}
        </div>
      </div>

      <ConfirmDialog
        isOpen={deleteModel !== null}
        title={text.deleteTitle}
        message={formatUiText(text.deleteMessage, {
          model: deleteModel?.displayName[prefersChineseContent(language) ? 'zh' : 'en'] ?? '',
        })}
        confirmText={text.deleteConfirm}
        isDanger
        onConfirm={() => void handleDelete()}
        onCancel={() => setDeleteModel(null)}
      />
    </Section>
  );
};
