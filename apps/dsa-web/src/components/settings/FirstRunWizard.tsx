import type React from 'react';
import { useMemo, useState } from 'react';
import { Button, InlineAlert, Input, Modal, Select } from '../common';
import { systemConfigApi } from '../../api/systemConfig';
import type { LlmProviderCatalogEntry } from '../../types/systemConfig';
import { ModelMultiSelect } from './ModelMultiSelect';
import type { UiLang } from './settingsInformationArchitecture';
import {
  canonicalModelRoute,
  resolveConnectionRequirements,
  suggestConnectionName,
} from './llmConnectionContract';
import { formatUiText } from '../../i18n/uiText';
import { SETTINGS_WIZARD_TEXT } from '../../locales/settingsWizard';

export interface WizardDraftItem {
  key: string;
  value: string;
}

export interface WizardCompleteResult {
  success: boolean;
  error?: string;
}

interface FirstRunWizardProps {
  /**
   * Commit the collected minimal config through the unified Save & Apply
   * transaction. Returns whether the backend accepted it so the wizard can keep
   * the modal open and show the error in place on failure.
   */
  onComplete: (items: WizardDraftItem[]) => Promise<WizardCompleteResult>;
  onClose: () => void;
  isSaving: boolean;
  language: UiLang;
  /**
   * Names already present in LLM_CHANNELS. A new Connection is merged into this
   * list instead of replacing it, so the wizard never clobbers existing setups.
   */
  existingChannelNames?: string[];
  /**
   * Authoritative provider catalog from the backend. The wizard reads provider
   * metadata and credential/base-URL requirements from here — it does not keep a
   * second hardcoded business list.
   */
  providers: LlmProviderCatalogEntry[];
  emptyApiKeyHosts?: string[];
}

type WizardMode = 'cloud' | 'cli';
type StepId = 'mode' | 'connection' | 'models' | 'model' | 'review';

const CLI_BACKENDS: Array<{ value: string; label: string }> = [
  { value: 'claude_code_cli', label: 'Claude Code CLI' },
  { value: 'codex_cli', label: 'Codex CLI' },
  { value: 'opencode_cli', label: 'OpenCode CLI' },
];

const STEP_ORDER: Record<WizardMode, StepId[]> = {
  cloud: ['mode', 'connection', 'models', 'model', 'review'],
  cli: ['mode', 'connection', 'review'],
};

function parseModels(models: string): string[] {
  return models
    .split(',')
    .map((model) => model.trim())
    .filter((model) => model.length > 0);
}

/**
 * Minimal first-run configuration wizard. It only collects the smallest set of
 * fields needed for a runnable config (one enabled channel + models, or a local
 * CLI backend) and commits them to the unified draft via onComplete, then the
 * page runs the normal Save & Apply. Advanced fields never appear here.
 */
export const FirstRunWizard: React.FC<FirstRunWizardProps> = ({
  onComplete,
  onClose,
  isSaving,
  language,
  existingChannelNames = [],
  providers,
  emptyApiKeyHosts = [],
}) => {
  const text = SETTINGS_WIZARD_TEXT[language];
  const [step, setStep] = useState<StepId>('mode');
  const [mode, setMode] = useState<WizardMode | null>(null);
  const [providerId, setProviderId] = useState<string>(providers[0]?.id ?? '');
  const [protocol, setProtocol] = useState(providers[0]?.protocol ?? 'openai');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [models, setModels] = useState('');
  const [modelDraft, setModelDraft] = useState('');
  const [reportModel, setReportModel] = useState('');
  const [cliBackend, setCliBackend] = useState('');
  // Discovery results are candidates only: the user confirms which ones to
  // enable via the multi-select — never auto-selected wholesale.
  const [discoveredModels, setDiscoveredModels] = useState<string[]>([]);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoverNote, setDiscoverNote] = useState<{ ok: boolean; message: string } | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Resolve the selected provider against the backend catalog. If the stored id
  // is stale (catalog re-loaded), fall back to the first available provider.
  const provider = useMemo(
    () => providers.find((entry) => entry.id === providerId) ?? providers[0],
    [providers, providerId],
  );
  const modelOptions = useMemo(() => parseModels(models), [models]);
  const requirements = useMemo(() => provider ? resolveConnectionRequirements({
    provider,
    protocol,
    baseUrl,
    emptyApiKeyHosts,
  }) : null, [provider, protocol, baseUrl, emptyApiKeyHosts]);
  const protocolOptions = useMemo(() => Array.from(
    new Map(providers.map((entry) => [entry.protocol, entry.protocol])).entries(),
  ).map(([value, label]) => ({ value, label })), [providers]);

  // One model per Enter/click, but pasted comma/whitespace-separated lists are
  // split, trimmed and deduped in one pass.
  const addModelToken = (raw: string) => {
    const tokens = raw.split(/[,\s]+/).map((token) => token.trim()).filter(Boolean);
    if (tokens.length === 0) return;
    setModels(Array.from(new Set([...modelOptions, ...tokens])).join(','));
    setModelDraft('');
  };
  const removeModelToken = (model: string) => {
    setModels(modelOptions.filter((entry) => entry !== model).join(','));
  };

  const order = mode ? STEP_ORDER[mode] : STEP_ORDER.cloud;
  const stepIndex = order.indexOf(step);

  const applyProvider = (nextProviderId: string) => {
    setProviderId(nextProviderId);
    const nextProvider = providers.find((entry) => entry.id === nextProviderId);
    setProtocol(nextProvider?.protocol ?? 'openai');
    setBaseUrl(nextProvider?.defaultBaseUrl ?? '');
    setApiKey('');
    // Do not seed example model IDs: models come from discovery or manual entry.
    setModels('');
    setReportModel('');
    setDiscoveredModels([]);
    setDiscoverNote(null);
    setTestResult(null);
  };

  const handleDiscover = async () => {
    if (!provider || requirements?.supportsDiscovery === false) {
      return;
    }
    setIsDiscovering(true);
    setDiscoverNote(null);
    try {
      const result = await systemConfigApi.discoverLLMChannelModels({
        name: provider.id,
        providerId: provider.id,
        protocol,
        baseUrl: baseUrl.trim(),
        apiKey: apiKey.trim(),
      });
      if (result.success && result.models.length > 0) {
        // Present the results for explicit confirmation — never enable all of
        // them automatically.
        setDiscoveredModels(result.models);
        setDiscoverNote({ ok: true, message: formatUiText(text.discovered, { count: result.models.length }) });
      } else {
        setDiscoverNote({ ok: false, message: text.noDiscovered });
      }
    } catch {
      setDiscoverNote({ ok: false, message: text.discoveryFailed });
    } finally {
      setIsDiscovering(false);
    }
  };

  const handleTestConnection = async () => {
    if (!provider) {
      return;
    }
    setIsTesting(true);
    setTestResult(null);
    try {
      const result = await systemConfigApi.testLLMChannel({
        name: provider.id,
        providerId: provider.id,
        protocol,
        baseUrl: baseUrl.trim(),
        apiKey: apiKey.trim(),
        models: modelOptions,
      });
      setTestResult({ ok: result.success, message: result.success ? text.testSucceeded : text.testFailed });
    } catch {
      setTestResult({ ok: false, message: text.testFailed });
    } finally {
      setIsTesting(false);
    }
  };

  const chooseMode = (nextMode: WizardMode) => {
    setMode(nextMode);
    if (nextMode === 'cloud' && !baseUrl) {
      applyProvider(providerId);
    }
  };

  const canAdvance = (() => {
    switch (step) {
      case 'mode':
        return mode !== null;
      case 'connection': {
        if (mode === 'cli') {
          return Boolean(cliBackend);
        }
        // Official providers use their SDK default / prefilled endpoint, so Base
        // URL is never a blocker here; the API key is required unless the
        // provider is key-exempt (e.g. Ollama).
        const keyOk = !requirements?.apiKeyRequired || apiKey.trim().length > 0;
        const baseUrlOk = !requirements?.baseUrlRequired || baseUrl.trim().length > 0;
        return Boolean(provider && keyOk && baseUrlOk);
      }
      case 'models':
        return modelOptions.length > 0;
      case 'model':
        return true; // defaults to the first model
      default:
        return true;
    }
  })();

  const goNext = () => {
    if (step === 'model' && !reportModel && modelOptions.length > 0) {
      setReportModel(modelOptions[0]);
    }
    const next = order[stepIndex + 1];
    if (next) {
      setStep(next);
    }
  };
  const goBack = () => {
    const prev = order[stepIndex - 1];
    if (prev) {
      setStep(prev);
    }
  };

  const handleSave = async () => {
    setSaveError(null);
    const result = await onComplete(buildItems());
    if (!result.success) {
      // Keep the modal open and surface the failure in place.
      setSaveError(language === 'zh' && result.error ? result.error : text.saveFailedMessage);
    }
  };

  const buildItems = (): WizardDraftItem[] => {
    if (mode === 'cli') {
      return [{ key: 'GENERATION_BACKEND', value: cliBackend }];
    }
    if (!provider) {
      return [];
    }
    const name = suggestConnectionName(existingChannelNames, provider.id);
    const up = name.toUpperCase();
    const primaryModel = reportModel || modelOptions[0] || '';
    // The backend routes channel models as `<protocol>/<model>` and rejects a
    // bare model name; the user only ever sees/selects the display model.
    const primaryRoute = canonicalModelRoute(protocol, primaryModel);
    // Merge into any existing channels instead of replacing the whole list.
    const mergedChannels = Array.from(new Set([...existingChannelNames, name])).filter(Boolean).join(',');
    const items: WizardDraftItem[] = [
      // Make the configured channels the active source so a co-existing YAML /
      // Legacy config doesn't silently shadow the wizard result.
      { key: 'LLM_CONFIG_MODE', value: 'channels' },
      { key: 'GENERATION_BACKEND', value: 'litellm' },
      { key: 'LLM_CHANNELS', value: mergedChannels },
      { key: `LLM_${up}_PROVIDER`, value: provider.id },
      { key: `LLM_${up}_PROTOCOL`, value: protocol },
      { key: `LLM_${up}_MODELS`, value: modelOptions.join(',') },
      { key: `LLM_${up}_ENABLED`, value: 'true' },
      { key: 'LITELLM_MODEL', value: primaryRoute },
    ];
    // Base URL: official providers with a blank template endpoint use the SDK
    // default; only emit an explicit endpoint when one is provided.
    if (baseUrl.trim()) {
      items.push({ key: `LLM_${up}_BASE_URL`, value: baseUrl.trim() });
    }
    // API key: omit for key-exempt local runtimes (e.g. Ollama).
    if (apiKey.trim()) {
      items.push({ key: `LLM_${up}_API_KEY`, value: apiKey.trim() });
    }
    return items;
  };

  const stepLabel = formatUiText(text.step, { current: stepIndex + 1, total: order.length });

  return (
    <Modal isOpen onClose={onClose} title={text.title}>
      <div data-testid="first-run-wizard" className="space-y-5">
        <p className="text-xs text-muted-text">{stepLabel}</p>

        {step === 'mode' ? (
          <div className="space-y-3">
            <p className="text-sm text-foreground">
              {text.chooseMode}
            </p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {(['cloud', 'cli'] as WizardMode[]).map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={mode === value}
                  onClick={() => chooseMode(value)}
                  className={`rounded-lg border px-4 py-3 text-left text-sm transition-colors ${
                    mode === value
                      ? 'border-[var(--nav-active-border)] bg-[var(--nav-active-bg)] text-foreground'
                      : 'border-[var(--settings-border)] bg-[var(--settings-surface)] text-secondary-text hover:bg-[var(--settings-surface-hover)]'
                  }`}
                >
                  <span className="block font-medium text-foreground">
                    {value === 'cloud' ? text.cloudApi : text.localCli}
                  </span>
                  <span className="mt-1 block text-xs text-muted-text">
                    {value === 'cloud'
                      ? text.cloudDescription
                      : text.cliDescription}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {step === 'connection' && mode === 'cloud' ? (
          <div className="space-y-3">
            <div>
              <label htmlFor="wizard-provider" className="mb-1 block text-sm text-foreground">
                {text.provider}
              </label>
              <Select
                id="wizard-provider"
                value={providerId}
                onChange={applyProvider}
                options={providers.map((entry) => ({ value: entry.id, label: entry.label }))}
              />
            </div>
            {requirements?.showProtocol ? (
              <div>
                <label htmlFor="wizard-protocol" className="mb-1 block text-sm text-foreground">
                  {text.protocol}
                </label>
                <Select
                  id="wizard-protocol"
                  value={protocol}
                  onChange={setProtocol}
                  options={protocolOptions}
                />
              </div>
            ) : null}
            {requirements?.showApiKey ? (
              <div>
                <label htmlFor="wizard-api-key" className="mb-1 block text-sm text-foreground">
                  {requirements.apiKeyRequired
                    ? text.apiKey
                    : text.apiKeyOptional}
                </label>
                <Input
                  id="wizard-api-key"
                  type="password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder={requirements.apiKeyRequired
                    ? text.apiKeyPlaceholder
                    : text.localKeyPlaceholder}
                />
              </div>
            ) : null}
            {requirements?.showBaseUrl ? (
              <div>
                <label htmlFor="wizard-base-url" className="mb-1 block text-sm text-foreground">
                  {text.baseUrl}
                </label>
                <Input
                  id="wizard-base-url"
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                />
              </div>
            ) : null}
          </div>
        ) : null}

        {step === 'connection' && mode === 'cli' ? (
          <div className="space-y-2">
            <label htmlFor="wizard-cli" className="block text-sm text-foreground">
              {text.chooseCli}
            </label>
            <Select
              id="wizard-cli"
              value={cliBackend}
              onChange={setCliBackend}
              options={CLI_BACKENDS}
              placeholder={text.select}
            />
          </div>
        ) : null}

        {step === 'models' ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="block text-sm text-foreground">
                {text.availableModels}
              </span>
              {requirements?.supportsDiscovery !== false ? (
                <Button
                  type="button"
                  variant="settings-secondary"
                  size="xsm"
                  onClick={() => void handleDiscover()}
                  disabled={isDiscovering || (Boolean(requirements?.apiKeyRequired) && !apiKey.trim())}
                  isLoading={isDiscovering}
                >
                  {text.discoverModels}
                </Button>
              ) : null}
            </div>
            {requirements?.supportsDiscovery === false ? (
              <p className="text-xs text-muted-text">
                {text.discoveryUnsupported}
              </p>
            ) : null}
            {discoveredModels.length > 0 ? (
              <ModelMultiSelect
                options={discoveredModels}
                isSelected={(model) => modelOptions.includes(model)}
                onToggle={(model) => (modelOptions.includes(model) ? removeModelToken(model) : addModelToken(model))}
                language={language}
              />
            ) : null}
            {modelOptions.length > 0 ? (
              <div className="flex flex-wrap gap-1.5" data-testid="wizard-model-chips">
                {modelOptions.map((model) => (
                  <span
                    key={model}
                    className="inline-flex max-w-full items-center gap-1 rounded-md border border-[var(--settings-border)] bg-[var(--settings-surface)] px-1.5 py-0.5 text-xs text-secondary-text"
                  >
                    <span className="truncate">{model}</span>
                    <button
                      type="button"
                      aria-label={formatUiText(text.removeModel, { model })}
                      onClick={() => removeModelToken(model)}
                      className="shrink-0 text-muted-text hover:text-danger"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-text">
                {text.noModels}
              </p>
            )}
            <div className="flex items-center gap-2">
              <Input
                id="wizard-models"
                value={modelDraft}
                aria-label={text.addModel}
                placeholder={text.addModelPlaceholder}
                onChange={(event) => setModelDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    addModelToken(modelDraft);
                  }
                }}
                onPaste={(event) => {
                  const text = event.clipboardData.getData('text');
                  // A pasted list (comma/whitespace separated) becomes tokens
                  // immediately; a single id falls through to the normal input.
                  if (/[,\s]/.test(text.trim())) {
                    event.preventDefault();
                    addModelToken(`${modelDraft} ${text}`);
                  }
                }}
              />
              <Button
                type="button"
                variant="settings-secondary"
                size="xsm"
                className="shrink-0"
                disabled={!modelDraft.trim()}
                onClick={() => addModelToken(modelDraft)}
              >
                {text.add}
              </Button>
            </div>
            {discoverNote ? (
              <p className={`text-xs ${discoverNote.ok ? 'text-success' : 'text-warning'}`}>{discoverNote.message}</p>
            ) : null}
            <p className="text-xs text-muted-text">
              {text.modelSourceHint}
            </p>
          </div>
        ) : null}

        {step === 'model' ? (
          <div className="space-y-2">
            <label htmlFor="wizard-report-model" className="block text-sm text-foreground">
              {text.reportModel}
            </label>
            <Select
              id="wizard-report-model"
              value={reportModel || modelOptions[0] || ''}
              onChange={setReportModel}
              options={modelOptions.map((model) => ({ value: model, label: model }))}
            />
            <p className="text-xs text-muted-text">
              {text.inheritanceHint}
            </p>
          </div>
        ) : null}

        {step === 'review' ? (
          <div className="space-y-3">
            <InlineAlert
              variant="info"
              message={text.reviewDescription}
            />
            {/* User-facing summary only — no internal keys such as LLM_CHANNELS. */}
            <dl className="space-y-1.5 rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] p-3 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-muted-text">{text.execution}</dt>
                <dd className="font-medium text-foreground">
                  {mode === 'cli'
                    ? CLI_BACKENDS.find((entry) => entry.value === cliBackend)?.label ?? text.localCli
                    : text.cloudApi}
                </dd>
              </div>
              {mode === 'cloud' ? (
                <>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted-text">{text.modelService}</dt>
                    <dd className="min-w-0 truncate font-medium text-foreground">{provider?.label ?? '—'}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted-text">{text.availableModels}</dt>
                    <dd className="min-w-0 truncate font-medium text-foreground">
                      {formatUiText(text.modelCount, { count: modelOptions.length })}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted-text">{text.reportModel}</dt>
                    <dd className="min-w-0 truncate font-medium text-foreground">{reportModel || modelOptions[0] || '—'}</dd>
                  </div>
                </>
              ) : null}
            </dl>
            {saveError ? <InlineAlert variant="danger" title={text.saveFailedTitle} message={saveError} /> : null}
            {mode === 'cloud' ? (
              <div className="space-y-1.5">
                <Button
                  type="button"
                  variant="settings-secondary"
                  size="xsm"
                  onClick={() => void handleTestConnection()}
                  disabled={isTesting}
                  isLoading={isTesting}
                >
                  {text.testOptional}
                </Button>
                <p className="text-xs text-muted-text">
                  {text.testHint}
                </p>
                {testResult ? (
                  <p className={`text-xs ${testResult.ok ? 'text-success' : 'text-warning'}`}>{testResult.message}</p>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="flex items-center justify-between gap-2 border-t border-[var(--settings-border)] pt-4">
          <Button type="button" variant="settings-secondary" size="sm" onClick={onClose}>
            {text.cancel}
          </Button>
          <div className="flex items-center gap-2">
            {stepIndex > 0 ? (
              <Button type="button" variant="settings-secondary" size="sm" onClick={goBack} disabled={isSaving}>
                {text.back}
              </Button>
            ) : null}
            {step === 'review' ? (
              <Button
                type="button"
                variant="settings-primary"
                size="sm"
                onClick={() => void handleSave()}
                disabled={isSaving}
                isLoading={isSaving}
              >
                {text.saveApply}
              </Button>
            ) : (
              <Button
                type="button"
                variant="settings-primary"
                size="sm"
                onClick={goNext}
                disabled={!canAdvance}
              >
                {text.next}
              </Button>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
};
