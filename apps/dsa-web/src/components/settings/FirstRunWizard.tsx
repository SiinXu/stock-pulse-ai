import type React from 'react';
import { useMemo, useState } from 'react';
import { Button, InlineAlert, Input, Modal, Select } from '../common';
import { systemConfigApi } from '../../api/systemConfig';
import { LLM_PROVIDER_TEMPLATES } from './llmProviderTemplates';
import type { UiLang } from './settingsInformationArchitecture';

export interface WizardDraftItem {
  key: string;
  value: string;
}

interface FirstRunWizardProps {
  /** Commit the collected minimal config into the unified draft and Save & Apply. */
  onComplete: (items: WizardDraftItem[]) => void;
  onClose: () => void;
  isSaving: boolean;
  language: UiLang;
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
}) => {
  const [step, setStep] = useState<StepId>('mode');
  const [mode, setMode] = useState<WizardMode | null>(null);
  const [providerId, setProviderId] = useState<string>(LLM_PROVIDER_TEMPLATES[0]?.channelId ?? '');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [models, setModels] = useState('');
  const [reportModel, setReportModel] = useState('');
  const [cliBackend, setCliBackend] = useState('');
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoverNote, setDiscoverNote] = useState<{ ok: boolean; message: string } | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  const template = useMemo(
    () => LLM_PROVIDER_TEMPLATES.find((entry) => entry.channelId === providerId),
    [providerId],
  );
  const modelOptions = useMemo(() => parseModels(models), [models]);

  const order = mode ? STEP_ORDER[mode] : STEP_ORDER.cloud;
  const stepIndex = order.indexOf(step);

  const applyProvider = (nextProviderId: string) => {
    setProviderId(nextProviderId);
    const nextTemplate = LLM_PROVIDER_TEMPLATES.find((entry) => entry.channelId === nextProviderId);
    setBaseUrl(nextTemplate?.baseUrl ?? '');
    setModels(nextTemplate?.placeholderModels ?? '');
    setReportModel('');
    setDiscoverNote(null);
    setTestResult(null);
  };

  const handleDiscover = async () => {
    if (!template) {
      return;
    }
    setIsDiscovering(true);
    setDiscoverNote(null);
    try {
      const result = await systemConfigApi.discoverLLMChannelModels({
        name: template.channelId,
        protocol: template.protocol,
        baseUrl: baseUrl.trim(),
        apiKey: apiKey.trim(),
      });
      if (result.success && result.models.length > 0) {
        setModels(result.models.join(','));
        setReportModel('');
        setDiscoverNote({ ok: true, message: tx(language, `发现 ${result.models.length} 个模型`, `Found ${result.models.length} models`) });
      } else {
        setDiscoverNote({ ok: false, message: result.message || tx(language, '未发现模型，可手动填写。', 'No models found — enter them manually.') });
      }
    } catch {
      setDiscoverNote({ ok: false, message: tx(language, '发现失败，可手动填写。', 'Discovery failed — enter them manually.') });
    } finally {
      setIsDiscovering(false);
    }
  };

  const handleTestConnection = async () => {
    if (!template) {
      return;
    }
    setIsTesting(true);
    setTestResult(null);
    try {
      const result = await systemConfigApi.testLLMChannel({
        name: template.channelId,
        protocol: template.protocol,
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
      case 'connection':
        return mode === 'cli' ? Boolean(cliBackend) : Boolean(providerId && apiKey.trim() && baseUrl.trim());
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

  const buildItems = (): WizardDraftItem[] => {
    if (mode === 'cli') {
      return [{ key: 'GENERATION_BACKEND', value: cliBackend }];
    }
    if (!template) {
      return [];
    }
    const name = template.channelId;
    const up = name.toUpperCase();
    const primary = reportModel || modelOptions[0] || '';
    return [
      { key: 'GENERATION_BACKEND', value: 'litellm' },
      { key: 'LLM_CHANNELS', value: name },
      { key: `LLM_${up}_PROTOCOL`, value: template.protocol },
      { key: `LLM_${up}_BASE_URL`, value: baseUrl.trim() },
      { key: `LLM_${up}_API_KEY`, value: apiKey.trim() },
      { key: `LLM_${up}_MODELS`, value: modelOptions.join(',') },
      { key: `LLM_${up}_ENABLED`, value: 'true' },
      { key: 'LITELLM_MODEL', value: primary },
    ];
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
                options={LLM_PROVIDER_TEMPLATES.map((entry) => ({ value: entry.channelId, label: entry.label }))}
              />
            </div>
            <div>
              <label htmlFor="wizard-api-key" className="mb-1 block text-sm text-foreground">
                {tx(language, 'API Key', 'API Key')}
              </label>
              <Input
                id="wizard-api-key"
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder={tx(language, '填写服务商密钥', 'Enter the provider API key')}
              />
            </div>
            <div>
              <label htmlFor="wizard-base-url" className="mb-1 block text-sm text-foreground">
                {tx(language, 'Base URL', 'Base URL')}
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
              <label htmlFor="wizard-models" className="block text-sm text-foreground">
                {tx(language, '模型（逗号分隔）', 'Models (comma separated)')}
              </label>
              <Button
                type="button"
                variant="settings-secondary"
                size="xsm"
                onClick={() => void handleDiscover()}
                disabled={isDiscovering || !apiKey.trim()}
                isLoading={isDiscovering}
              >
                {tx(language, '自动发现模型', 'Discover models')}
              </Button>
            </div>
            <Input
              id="wizard-models"
              value={models}
              onChange={(event) => setModels(event.target.value)}
            />
            {discoverNote ? (
              <p className={`text-xs ${discoverNote.ok ? 'text-success' : 'text-warning'}`}>{discoverNote.message}</p>
            ) : null}
            <p className="text-xs text-muted-text">
              {tx(
                language,
                '已用服务商默认模型预填，可按需修改，或用默认 Base URL 自动发现；发现失败时手动填写即可。',
                'Prefilled with the provider defaults. You can edit them, or auto-discover via the default Base URL; enter them manually if discovery fails.',
              )}
            </p>
          </div>
        ) : null}

        {step === 'model' ? (
          <div className="space-y-2">
            <label htmlFor="wizard-report-model" className="block text-sm text-foreground">
              {tx(language, '报告主模型', 'Report primary model')}
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
                'Agent、Vision 与备用模型默认继承报告主模型，可稍后在任务路由与可靠性中单独调整。',
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
            <dl className="space-y-1.5 rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] p-3 text-sm">
              {buildItems().map((item) => (
                <div key={item.key} className="flex justify-between gap-3">
                  <dt className="text-muted-text">{item.key}</dt>
                  <dd className="min-w-0 truncate font-medium text-foreground">
                    {item.key.includes('API_KEY') ? '••••••' : item.value || '—'}
                  </dd>
                </div>
              ))}
            </dl>
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
                onClick={() => onComplete(buildItems())}
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
