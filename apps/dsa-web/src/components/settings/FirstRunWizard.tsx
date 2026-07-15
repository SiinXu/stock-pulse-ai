import type React from 'react';
import { useMemo, useState } from 'react';
import { Button, InlineAlert, Input, Modal, Select } from '../common';
import { systemConfigApi } from '../../api/systemConfig';
import type { LlmProviderCatalogEntry } from '../../types/systemConfig';
import { ModelMultiSelect } from './ModelMultiSelect';
import type { UiLang } from './settingsInformationArchitecture';

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

function tx(language: UiLang, zh: string, en: string): string {
  return language === 'en' ? en : zh;
}

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
}) => {
  const [step, setStep] = useState<StepId>('mode');
  const [mode, setMode] = useState<WizardMode | null>(null);
  const [providerId, setProviderId] = useState<string>(providers[0]?.id ?? '');
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
    setBaseUrl(nextProvider?.defaultBaseUrl ?? '');
    // Do not seed example model IDs: models come from discovery or manual entry.
    setModels('');
    setReportModel('');
    setDiscoveredModels([]);
    setDiscoverNote(null);
    setTestResult(null);
  };

  const handleDiscover = async () => {
    if (!provider) {
      return;
    }
    setIsDiscovering(true);
    setDiscoverNote(null);
    try {
      const result = await systemConfigApi.discoverLLMChannelModels({
        name: provider.id,
        protocol: provider.protocol,
        baseUrl: baseUrl.trim(),
        apiKey: apiKey.trim(),
      });
      if (result.success && result.models.length > 0) {
        // Present the results for explicit confirmation — never enable all of
        // them automatically.
        setDiscoveredModels(result.models);
        setDiscoverNote({
          ok: true,
          message: tx(
            language,
            `发现 ${result.models.length} 个模型，请勾选要启用的模型`,
            `Found ${result.models.length} models — pick the ones to enable`,
          ),
        });
      } else {
        setDiscoverNote({ ok: false, message: result.message || tx(language, '未发现模型，可手动逐个添加。', 'No models found — add them manually.') });
      }
    } catch {
      setDiscoverNote({ ok: false, message: tx(language, '发现失败，可手动逐个添加。', 'Discovery failed — add them manually.') });
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
        protocol: provider.protocol,
        baseUrl: baseUrl.trim(),
        apiKey: apiKey.trim(),
        models: modelOptions,
      });
      setTestResult({ ok: result.success, message: result.message });
    } catch {
      setTestResult({ ok: false, message: tx(language, '连接测试失败。', 'Connection test failed.') });
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
        const keyOk = !provider?.requiresApiKey || apiKey.trim().length > 0;
        const baseUrlOk = !provider?.requiresBaseUrl || baseUrl.trim().length > 0;
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
      setSaveError(result.error || tx(language, '保存失败，请检查配置后重试。', 'Save failed. Check the config and try again.'));
    }
  };

  const buildItems = (): WizardDraftItem[] => {
    if (mode === 'cli') {
      return [{ key: 'GENERATION_BACKEND', value: cliBackend }];
    }
    if (!provider) {
      return [];
    }
    const name = provider.id;
    const up = name.toUpperCase();
    const primaryModel = reportModel || modelOptions[0] || '';
    // The backend routes channel models as `<protocol>/<model>` and rejects a
    // bare model name; the user only ever sees/selects the display model.
    const primaryRoute = primaryModel ? `${provider.protocol}/${primaryModel}` : '';
    // Merge into any existing channels instead of replacing the whole list.
    const mergedChannels = Array.from(new Set([...existingChannelNames, name])).filter(Boolean).join(',');
    const items: WizardDraftItem[] = [
      // Make the configured channels the active source so a co-existing YAML /
      // Legacy config doesn't silently shadow the wizard result.
      { key: 'LLM_CONFIG_MODE', value: 'channels' },
      { key: 'GENERATION_BACKEND', value: 'litellm' },
      { key: 'LLM_CHANNELS', value: mergedChannels },
      { key: `LLM_${up}_PROTOCOL`, value: provider.protocol },
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

  const stepLabel = tx(
    language,
    `第 ${stepIndex + 1} / ${order.length} 步`,
    `Step ${stepIndex + 1} of ${order.length}`,
  );

  return (
    <Modal isOpen onClose={onClose} title={tx(language, '快速配置向导', 'Quick setup wizard')}>
      <div data-testid="first-run-wizard" className="space-y-5">
        <p className="text-xs text-muted-text">{stepLabel}</p>

        {step === 'mode' ? (
          <div className="space-y-3">
            <p className="text-sm text-foreground">
              {tx(language, '选择模型的运行方式：', 'How do you want to run the model?')}
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
                    {value === 'cloud' ? tx(language, '云 API', 'Cloud API') : tx(language, '本机 CLI', 'Local CLI')}
                  </span>
                  <span className="mt-1 block text-xs text-muted-text">
                    {value === 'cloud'
                      ? tx(language, '使用云端模型服务（OpenAI 兼容等）。', 'Use a cloud model service (OpenAI-compatible, etc.).')
                      : tx(language, '使用本机命令行后端（实验性）。', 'Use a local CLI backend (experimental).')}
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
                {tx(language, '服务商', 'Provider')}
              </label>
              <Select
                id="wizard-provider"
                value={providerId}
                onChange={applyProvider}
                options={providers.map((entry) => ({ value: entry.id, label: entry.label }))}
              />
            </div>
            <div>
              <label htmlFor="wizard-api-key" className="mb-1 block text-sm text-foreground">
                {provider && !provider.requiresApiKey
                  ? tx(language, 'API 密钥（可选）', 'API Key (optional)')
                  : tx(language, 'API 密钥', 'API Key')}
              </label>
              <Input
                id="wizard-api-key"
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder={provider && !provider.requiresApiKey
                  ? tx(language, '该服务无需密钥，可留空', 'This service needs no key — leave blank')
                  : tx(language, '填写服务商密钥', 'Enter the provider API key')}
              />
            </div>
            <div>
              <label htmlFor="wizard-base-url" className="mb-1 block text-sm text-foreground">
                {tx(language, '服务地址', 'Base URL')}
              </label>
              <Input
                id="wizard-base-url"
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
              />
            </div>
          </div>
        ) : null}

        {step === 'connection' && mode === 'cli' ? (
          <div className="space-y-2">
            <label htmlFor="wizard-cli" className="block text-sm text-foreground">
              {tx(language, '选择本机 CLI 后端', 'Choose a local CLI backend')}
            </label>
            <Select
              id="wizard-cli"
              value={cliBackend}
              onChange={setCliBackend}
              options={CLI_BACKENDS}
              placeholder={tx(language, '请选择', 'Select…')}
            />
          </div>
        ) : null}

        {step === 'models' ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="block text-sm text-foreground">
                {tx(language, '可用模型', 'Available models')}
              </span>
              <Button
                type="button"
                variant="settings-secondary"
                size="xsm"
                onClick={() => void handleDiscover()}
                // Key-exempt providers (e.g. Ollama) can discover with an empty
                // key; only key-required providers gate on it.
                disabled={isDiscovering || (Boolean(provider?.requiresApiKey) && !apiKey.trim())}
                isLoading={isDiscovering}
              >
                {tx(language, '自动发现模型', 'Discover models')}
              </Button>
            </div>
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
                      aria-label={tx(language, `移除模型 ${model}`, `Remove model ${model}`)}
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
                {tx(language, '尚未添加模型，请自动发现或逐个手动添加。', 'No models yet — discover them or add each manually.')}
              </p>
            )}
            <div className="flex items-center gap-2">
              <Input
                id="wizard-models"
                value={modelDraft}
                aria-label={tx(language, '添加模型', 'Add model')}
                placeholder={tx(language, '输入模型 ID 后回车或点“添加”', 'Enter a model ID, then press Enter or “Add”')}
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
                {tx(language, '添加', 'Add')}
              </Button>
            </div>
            {discoverNote ? (
              <p className={`text-xs ${discoverNote.ok ? 'text-success' : 'text-warning'}`}>{discoverNote.message}</p>
            ) : null}
            <p className="text-xs text-muted-text">
              {tx(
                language,
                '模型来自自动发现或手动逐个添加；不预填示例模型。发现失败时可手动添加。',
                'Models come from auto-discovery or manual entry — no example models are prefilled. Add them manually if discovery fails.',
              )}
            </p>
          </div>
        ) : null}

        {step === 'model' ? (
          <div className="space-y-2">
            <label htmlFor="wizard-report-model" className="block text-sm text-foreground">
              {tx(language, '报告主要模型', 'Report primary model')}
            </label>
            <Select
              id="wizard-report-model"
              value={reportModel || modelOptions[0] || ''}
              onChange={setReportModel}
              options={modelOptions.map((model) => ({ value: model, label: model }))}
            />
            <p className="text-xs text-muted-text">
              {tx(
                language,
                'Agent、Vision 与备用模型默认继承报告主要模型，可稍后在任务路由与可靠性中单独调整。',
                'Agent, Vision and fallback models inherit this by default; adjust them later in Task Routing and Reliability.',
              )}
            </p>
          </div>
        ) : null}

        {step === 'review' ? (
          <div className="space-y-3">
            <InlineAlert
              variant="info"
              message={tx(
                language,
                '将应用以下最小可运行配置，保存后可继续在设置中完善。',
                'The following minimal runnable config will be applied. You can refine it later in Settings.',
              )}
            />
            {/* User-facing summary only — no internal keys such as LLM_CHANNELS. */}
            <dl className="space-y-1.5 rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] p-3 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-muted-text">{tx(language, '执行方式', 'Execution')}</dt>
                <dd className="font-medium text-foreground">
                  {mode === 'cli'
                    ? CLI_BACKENDS.find((entry) => entry.value === cliBackend)?.label ?? tx(language, '本机 CLI', 'Local CLI')
                    : tx(language, '云 API', 'Cloud API')}
                </dd>
              </div>
              {mode === 'cloud' ? (
                <>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted-text">{tx(language, '模型服务', 'Model service')}</dt>
                    <dd className="min-w-0 truncate font-medium text-foreground">{provider?.label ?? '—'}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted-text">{tx(language, '可用模型', 'Available models')}</dt>
                    <dd className="min-w-0 truncate font-medium text-foreground">
                      {tx(language, `${modelOptions.length} 个`, `${modelOptions.length}`)}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted-text">{tx(language, '报告主要模型', 'Report primary model')}</dt>
                    <dd className="min-w-0 truncate font-medium text-foreground">{reportModel || modelOptions[0] || '—'}</dd>
                  </div>
                </>
              ) : null}
            </dl>
            {saveError ? <InlineAlert variant="danger" title={tx(language, '保存失败', 'Save failed')} message={saveError} /> : null}
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
                  {tx(language, '测试连接（可选）', 'Test connection (optional)')}
                </Button>
                <p className="text-xs text-muted-text">
                  {tx(
                    language,
                    '连接测试为可选诊断，可能访问外部服务或产生费用，不影响保存。',
                    'The connection test is an optional diagnostic that may reach external services or incur costs; it does not gate saving.',
                  )}
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
            {tx(language, '取消', 'Cancel')}
          </Button>
          <div className="flex items-center gap-2">
            {stepIndex > 0 ? (
              <Button type="button" variant="settings-secondary" size="sm" onClick={goBack} disabled={isSaving}>
                {tx(language, '上一步', 'Back')}
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
                {tx(language, '保存并应用', 'Save & Apply')}
              </Button>
            ) : (
              <Button
                type="button"
                variant="settings-primary"
                size="sm"
                onClick={goNext}
                disabled={!canAdvance}
              >
                {tx(language, '下一步', 'Next')}
              </Button>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
};
