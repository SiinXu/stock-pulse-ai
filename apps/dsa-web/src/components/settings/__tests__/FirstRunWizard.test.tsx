// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FirstRunWizard } from '../FirstRunWizard';
import type { LlmConnectionFieldSchema } from '../../../types/systemConfig';

const { discoverLLMChannelModels, testLLMChannel } = vi.hoisted(() => ({
  discoverLLMChannelModels: vi.fn(),
  testLLMChannel: vi.fn(),
}));

vi.mock('../../../api/systemConfig', () => ({
  systemConfigApi: {
    discoverLLMChannelModels: (...args: unknown[]) => discoverLLMChannelModels(...args),
    testLLMChannel: (...args: unknown[]) => testLLMChannel(...args),
  },
}));

if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

function openListbox(trigger: HTMLElement) {
  fireEvent.click(trigger);
  return document.getElementById(trigger.getAttribute('aria-controls')!)!;
}

function chooseOption(trigger: HTMLElement, value: string) {
  const listbox = openListbox(trigger);
  const option = within(listbox)
    .getAllByRole('option')
    .find((item) => item.getAttribute('data-value') === value)!;
  fireEvent.click(option);
}


const CATALOG = [
  { id: 'aihubmix', label: 'AIHubmix', protocol: 'openai', defaultBaseUrl: 'https://aihubmix.com/v1', capabilities: ['openai-compatible'], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
  { id: 'openai', label: 'OpenAI 官方', protocol: 'openai', defaultBaseUrl: 'https://api.openai.com/v1', capabilities: ['official-api'], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
  { id: 'deepseek', label: 'DeepSeek 官方', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: ['official-api'], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
  { id: 'gemini', label: 'Gemini 官方', protocol: 'gemini', defaultBaseUrl: '', capabilities: ['official-api', 'vision'], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: false, isLocal: false, isCustom: false },
  { id: 'ollama', label: 'Ollama（本地）', protocol: 'ollama', defaultBaseUrl: 'http://127.0.0.1:11434', capabilities: ['local-runtime'], requiresApiKey: false, requiresBaseUrl: false, supportsDiscovery: true, isLocal: true, isCustom: false },
  { id: 'custom', label: '自定义兼容服务', protocol: 'openai', defaultBaseUrl: '', capabilities: [], requiresApiKey: true, requiresBaseUrl: true, supportsDiscovery: true, isLocal: false, isCustom: true },
];

const ENGLISH_PROVIDER_LABELS: Record<string, string> = {
  aihubmix: 'AIHubmix (Aggregator)',
  openai: 'OpenAI Official',
  deepseek: 'DeepSeek Official',
  gemini: 'Gemini Official',
  ollama: 'Ollama (Local)',
  custom: 'Custom compatible service',
};

const BILINGUAL_CATALOG = CATALOG.map((entry) => ({
  ...entry,
  labelZh: entry.label,
  labelEn: ENGLISH_PROVIDER_LABELS[entry.id],
}));

const okComplete = () => vi.fn().mockResolvedValue({ success: true });

const CONNECTION_NAME_FIELD: LlmConnectionFieldSchema = {
  key: 'connection_name',
  dataType: 'string',
  isSensitive: false,
  isRequired: true,
  contract: { requirement: 'required' },
};

const PROVIDER_ID_FIELD: LlmConnectionFieldSchema = {
  key: 'provider_id',
  dataType: 'string',
  isSensitive: false,
  isRequired: true,
  contract: { requirement: 'required' },
};

const CONNECTION_IDENTITY_FIELDS = [CONNECTION_NAME_FIELD, PROVIDER_ID_FIELD];

const HIDDEN_INHERITED_CONTRACT: LlmConnectionFieldSchema['contract'] = {
  requirement: 'inherited',
  visibleWhen: [{ key: '__test_hidden', operator: 'equals', value: 'true' }],
};

const CONNECTION_CORE_FIELDS: LlmConnectionFieldSchema[] = [
  CONNECTION_NAME_FIELD,
  { key: 'display_name', dataType: 'string', isSensitive: false, isRequired: false, contract: HIDDEN_INHERITED_CONTRACT },
  PROVIDER_ID_FIELD,
  { key: 'protocol', dataType: 'string', isSensitive: false, isRequired: false, contract: HIDDEN_INHERITED_CONTRACT },
  { key: 'base_url', dataType: 'string', isSensitive: false, isRequired: false, contract: HIDDEN_INHERITED_CONTRACT },
  { key: 'api_key', dataType: 'string', isSensitive: true, isRequired: false, contract: HIDDEN_INHERITED_CONTRACT },
  { key: 'api_keys', dataType: 'array', isSensitive: true, isRequired: false, contract: HIDDEN_INHERITED_CONTRACT },
  { key: 'models', dataType: 'array', isSensitive: false, isRequired: false, contract: HIDDEN_INHERITED_CONTRACT },
  { key: 'extra_headers', dataType: 'json', isSensitive: true, isRequired: false, contract: HIDDEN_INHERITED_CONTRACT },
  { key: 'enabled', dataType: 'boolean', isSensitive: false, isRequired: false, contract: HIDDEN_INHERITED_CONTRACT },
];

function withCoreFields(fields: LlmConnectionFieldSchema[]): LlmConnectionFieldSchema[] {
  const byKey = new Map(
    [...CONNECTION_CORE_FIELDS, ...fields].map((field) => [field.key, field]),
  );
  return Array.from(byKey.values());
}

// The wizard no longer prefills example models; add them via the token editor
// (mirrors the real discover / manual-add flow) on the models step.
function addWizardModels(models: string[]): void {
  const input = screen.getByLabelText('添加模型');
  const addButton = screen.getByRole('button', { name: '添加' });
  for (const model of models) {
    fireEvent.change(input, { target: { value: model } });
    fireEvent.click(addButton);
  }
}

function expectCloudSetupReadOnlyForSchema(connectionFields: LlmConnectionFieldSchema[]): void {
  const onComplete = okComplete();
  render(
    <FirstRunWizard
      onComplete={onComplete}
      onClose={() => {}}
      isSaving={false}
      language="zh"
      providers={[CATALOG.find((entry) => entry.id === 'openai')!]}
      connectionFields={connectionFields}
    />,
  );

  fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
  fireEvent.click(screen.getByRole('button', { name: '下一步' }));
  const next = screen.getByRole('button', { name: '下一步' });
  expect(screen.getByText('连接 Schema 不完整或不可用')).toBeInTheDocument();
  expect(next).toBeDisabled();
  next.removeAttribute('disabled');
  fireEvent.click(next);
  expect(screen.getByText('第 2 / 5 步')).toBeInTheDocument();
  expect(discoverLLMChannelModels).not.toHaveBeenCalled();
  expect(testLLMChannel).not.toHaveBeenCalled();
  expect(onComplete).not.toHaveBeenCalled();
}

describe('FirstRunWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders built-in Provider labels in the requested English UI language', () => {
    render(
      <FirstRunWizard
        onComplete={okComplete()}
        onClose={() => {}}
        isSaving={false}
        language="en"
        providers={BILINGUAL_CATALOG}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Cloud API/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    const options = within(openListbox(screen.getByLabelText('Provider'))).getAllByRole('option');
    expect(options.map((option) => option.textContent)).toEqual(expect.arrayContaining([
      expect.stringContaining('DeepSeek Official'),
      expect.stringContaining('OpenAI Official'),
      expect.stringContaining('Gemini Official'),
      expect.stringContaining('Ollama (Local)'),
      expect.stringContaining('Custom compatible service'),
    ]));
    expect(options.map((option) => option.textContent).join(' ')).not.toMatch(/[\u3400-\u9fff]/u);
  });

  it('isolates provider credentials and keeps autofill-like changes side-effect free', () => {
    const onComplete = okComplete();
    render(
      <FirstRunWizard
        onComplete={onComplete}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[CATALOG.find((entry) => entry.id === 'openai')!]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    const providerCredential = screen.getByLabelText('API 密钥');
    expect(providerCredential).toHaveAttribute('name', 'stockpulse-provider-api-key');
    expect(providerCredential).toHaveAttribute('autocomplete', 'off');
    expect(providerCredential).toHaveValue('');

    fireEvent.change(providerCredential, { target: { value: 'autofilled-admin-password' } });

    expect(providerCredential).toHaveValue('autofilled-admin-password');
    expect(discoverLLMChannelModels).not.toHaveBeenCalled();
    expect(testLLMChannel).not.toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('uses the schema API-key requirement when Catalog says the key is required', () => {
    render(
      <FirstRunWizard
        onComplete={okComplete()}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[CATALOG.find((entry) => entry.id === 'openai')!]}
        connectionFields={withCoreFields([
          ...CONNECTION_IDENTITY_FIELDS,
          {
            key: 'api_key',
            dataType: 'string',
            isSensitive: true,
            isRequired: false,
            contract: { requirement: 'optional' },
          },
        ])}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    expect(screen.getByLabelText('API 密钥（可选）')).toHaveValue('');
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
  });

  it('does not read legacy Catalog requirement flags when the schema is present', () => {
    const legacyRequirementRead = vi.fn(() => true);
    const catalogProvider = { ...CATALOG.find((entry) => entry.id === 'openai')! };
    Object.defineProperties(catalogProvider, {
      requiresApiKey: { configurable: true, get: legacyRequirementRead },
      requiresBaseUrl: { configurable: true, get: legacyRequirementRead },
    });

    render(
      <FirstRunWizard
        onComplete={okComplete()}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[catalogProvider]}
        connectionFields={withCoreFields([
          ...CONNECTION_IDENTITY_FIELDS,
          {
            key: 'api_key',
            dataType: 'string',
            isSensitive: true,
            isRequired: false,
            contract: { requirement: 'optional' },
          },
        ])}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    expect(screen.getByLabelText('API 密钥（可选）')).toBeInTheDocument();
    expect(legacyRequirementRead).not.toHaveBeenCalled();
  });

  it('treats an explicitly empty schema as present instead of using legacy Catalog requirements', () => {
    const legacyRequirementRead = vi.fn(() => true);
    const catalogProvider = { ...CATALOG.find((entry) => entry.id === 'openai')! };
    Object.defineProperties(catalogProvider, {
      requiresApiKey: { configurable: true, get: legacyRequirementRead },
      requiresBaseUrl: { configurable: true, get: legacyRequirementRead },
    });

    render(
      <FirstRunWizard
        onComplete={okComplete()}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[catalogProvider]}
        connectionFields={[]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    expect(screen.queryByLabelText(/API 密钥/)).not.toBeInTheDocument();
    expect(legacyRequirementRead).not.toHaveBeenCalled();
  });

  it('uses the schema API-key requirement when Catalog says the key is optional', () => {
    const catalogProvider = {
      ...CATALOG.find((entry) => entry.id === 'openai')!,
      requiresApiKey: false,
    };
    render(
      <FirstRunWizard
        onComplete={okComplete()}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[catalogProvider]}
        connectionFields={withCoreFields([
          ...CONNECTION_IDENTITY_FIELDS,
          {
            key: 'api_key',
            dataType: 'string',
            isSensitive: true,
            isRequired: true,
            contract: { requirement: 'required' },
          },
        ])}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    expect(screen.getByLabelText('API 密钥')).toHaveValue('');
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'schema-key' } });
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
  });

  it('keeps an unknown-condition field visible and read-only while blocking progress', () => {
    render(
      <FirstRunWizard
        onComplete={okComplete()}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[CATALOG.find((entry) => entry.id === 'openai')!]}
        connectionFields={withCoreFields([
          ...CONNECTION_IDENTITY_FIELDS,
          {
            key: 'base_url',
            dataType: 'string',
            isSensitive: false,
            isRequired: false,
            contract: {
              requirement: 'optional',
              visibleWhen: [{ key: 'provider_id', operator: 'futureOperator' as never, value: 'openai' }],
            },
          },
        ])}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    expect(screen.getByLabelText('服务地址')).toBeDisabled();
    expect(screen.getByText('连接字段契约包含不支持的条件，无法继续。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
  });

  it('blocks creating a Connection when the Provider identity field is read-only', () => {
    const disabledForThisProvider = [{
      key: 'provider_id',
      operator: 'equals' as const,
      value: 'other',
    }];
    render(
      <FirstRunWizard
        onComplete={okComplete()}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[CATALOG.find((entry) => entry.id === 'openai')!]}
        connectionFields={withCoreFields([
          CONNECTION_NAME_FIELD,
          {
            key: 'provider_id',
            dataType: 'string',
            isSensitive: false,
            isRequired: false,
            contract: { requirement: 'optional', enabledWhen: disabledForThisProvider },
          },
          {
            key: 'api_key',
            dataType: 'string',
            isSensitive: true,
            isRequired: false,
            contract: { requirement: 'optional' },
          },
        ])}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    expect(screen.queryByLabelText('服务商')).not.toBeInTheDocument();
    expect(screen.getByText('连接 Schema 不完整或不可用')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    expect(discoverLLMChannelModels).not.toHaveBeenCalled();
    expect(testLLMChannel).not.toHaveBeenCalled();
  });

  it('applies schema enabled state to every model writer', () => {
    const disabledForThisProvider = [{
      key: 'provider_id',
      operator: 'equals' as const,
      value: 'other',
    }];
    render(
      <FirstRunWizard
        onComplete={okComplete()}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[CATALOG.find((entry) => entry.id === 'openai')!]}
        connectionFields={withCoreFields([
          ...CONNECTION_IDENTITY_FIELDS,
          {
            key: 'api_key',
            dataType: 'string',
            isSensitive: true,
            isRequired: false,
            contract: { requirement: 'optional' },
          },
          {
            key: 'models',
            dataType: 'array',
            isSensitive: false,
            isRequired: false,
            contract: { requirement: 'optional', enabledWhen: disabledForThisProvider },
          },
        ])}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    expect(screen.getByRole('button', { name: '自动发现模型' })).toBeDisabled();
    expect(screen.getByLabelText('添加模型')).toBeDisabled();
    expect(screen.getByRole('button', { name: '添加' })).toBeDisabled();
  });

  it('does not render model writers when the schema hides the models field', () => {
    render(
      <FirstRunWizard
        onComplete={okComplete()}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[CATALOG.find((entry) => entry.id === 'openai')!]}
        connectionFields={withCoreFields([
          ...CONNECTION_IDENTITY_FIELDS,
          {
            key: 'api_key',
            dataType: 'string',
            isSensitive: true,
            isRequired: false,
            contract: { requirement: 'optional' },
          },
          {
            key: 'models',
            dataType: 'array',
            isSensitive: false,
            isRequired: false,
            contract: {
              requirement: 'optional',
              visibleWhen: [{ key: 'provider_id', operator: 'equals', value: 'other' }],
            },
          },
        ])}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    expect(screen.queryByRole('button', { name: '自动发现模型' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('添加模型')).not.toBeInTheDocument();
  });

  it('does not create a Connection when an explicitly empty schema authorizes no field writes', () => {
    const onComplete = okComplete();
    render(
      <FirstRunWizard
        onComplete={onComplete}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[CATALOG.find((entry) => entry.id === 'openai')!]}
        connectionFields={[]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    const nextButton = screen.getByRole('button', { name: '下一步' });
    expect(nextButton).toBeDisabled();
    nextButton.removeAttribute('disabled');
    fireEvent.click(nextButton);
    expect(screen.getByText('第 2 / 5 步')).toBeInTheDocument();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('keeps cloud setup read-only for a present empty schema', () => {
    expectCloudSetupReadOnlyForSchema([]);
  });

  it('keeps cloud setup read-only for a present models-only schema', () => {
    expectCloudSetupReadOnlyForSchema([{
      key: 'models',
      dataType: 'array',
      isSensitive: false,
      isRequired: false,
      contract: { requirement: 'optional' },
    }]);
  });

  it('keeps cloud setup read-only when connection_name is missing', () => {
    expectCloudSetupReadOnlyForSchema([PROVIDER_ID_FIELD]);
  });

  it('keeps cloud setup read-only when provider_id is missing', () => {
    expectCloudSetupReadOnlyForSchema([CONNECTION_NAME_FIELD]);
  });

  it('keeps cloud setup read-only for a read-only identity schema', () => {
    expectCloudSetupReadOnlyForSchema(withCoreFields([
      CONNECTION_NAME_FIELD,
      {
        ...PROVIDER_ID_FIELD,
        isRequired: false,
        contract: { requirement: 'inherited' },
      },
    ]));
  });

  it('keeps cloud setup read-only for an unknown condition operator', () => {
    expectCloudSetupReadOnlyForSchema(withCoreFields([
      ...CONNECTION_IDENTITY_FIELDS,
      {
        key: 'models',
        dataType: 'array',
        isSensitive: false,
        isRequired: false,
        contract: {
          requirement: 'optional',
          enabledWhen: [{ key: 'provider_id', operator: 'futureOperator' as never, value: 'openai' }],
        },
      },
    ]));
  });

  it('keeps cloud setup read-only when an unknown required field becomes visible', () => {
    expectCloudSetupReadOnlyForSchema(withCoreFields([
      ...CONNECTION_IDENTITY_FIELDS,
      {
        key: 'future_token',
        dataType: 'string',
        isSensitive: true,
        isRequired: true,
        contract: {
          requirement: 'required',
          visibleWhen: [{ key: 'provider_id', operator: 'equals', value: 'openai' }],
        },
      },
    ]));
  });

  it('does not authorize a new Connection when the schema omits connection_name', () => {
    const onComplete = okComplete();
    render(
      <FirstRunWizard
        onComplete={onComplete}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[CATALOG.find((entry) => entry.id === 'openai')!]}
        connectionFields={[PROVIDER_ID_FIELD]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: '自动发现模型' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /测试连接/ })).not.toBeInTheDocument();
    expect(discoverLLMChannelModels).not.toHaveBeenCalled();
    expect(testLLMChannel).not.toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('fails closed on discovery when an omitted legacy schema becomes partial', () => {
    const onComplete = okComplete();
    const { rerender } = render(
      <FirstRunWizard
        onComplete={onComplete}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[CATALOG.find((entry) => entry.id === 'openai')!]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'legacy-key' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    expect(screen.getByRole('button', { name: '自动发现模型' })).toBeEnabled();

    rerender(
      <FirstRunWizard
        onComplete={onComplete}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[CATALOG.find((entry) => entry.id === 'openai')!]}
        connectionFields={[
          PROVIDER_ID_FIELD,
          {
            key: 'models',
            dataType: 'array',
            isSensitive: false,
            isRequired: false,
            contract: { requirement: 'optional' },
          },
        ]}
      />,
    );

    expect(screen.queryByRole('button', { name: '自动发现模型' })).not.toBeInTheDocument();
    expect(screen.getByText('连接 Schema 不完整或不可用')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    expect(discoverLLMChannelModels).not.toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('fails closed on testing and saving when an omitted legacy schema becomes partial', () => {
    const onComplete = okComplete();
    const { rerender } = render(
      <FirstRunWizard
        onComplete={onComplete}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[CATALOG.find((entry) => entry.id === 'openai')!]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'legacy-key' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    addWizardModels(['gpt-4o-mini']);
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    rerender(
      <FirstRunWizard
        onComplete={onComplete}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[CATALOG.find((entry) => entry.id === 'openai')!]}
        connectionFields={[PROVIDER_ID_FIELD]}
      />,
    );

    const testButton = screen.getByRole('button', { name: /测试连接/ });
    const saveButton = screen.getByRole('button', { name: '保存并应用' });
    expect(testButton).toBeDisabled();
    expect(saveButton).toBeDisabled();
    testButton.removeAttribute('disabled');
    saveButton.removeAttribute('disabled');
    fireEvent.click(testButton);
    fireEvent.click(saveButton);
    expect(testLLMChannel).not.toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('persists the exact suggested identity and only the schema-writable credential sibling', async () => {
    const onComplete = okComplete();
    render(
      <FirstRunWizard
        onComplete={onComplete}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[CATALOG.find((entry) => entry.id === 'openai')!]}
        existingChannelNames={['openai']}
        connectionFields={withCoreFields([
          ...CONNECTION_IDENTITY_FIELDS,
          { key: 'display_name', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
          { key: 'protocol', dataType: 'string', isSensitive: false, isRequired: false, contract: { requirement: 'optional' } },
          { key: 'base_url', dataType: 'string', isSensitive: false, isRequired: false, contract: { requirement: 'optional' } },
          { key: 'api_keys', dataType: 'array', isSensitive: true, isRequired: true, contract: { requirement: 'required', requiresConnectionTest: true } },
          { key: 'models', dataType: 'array', isSensitive: false, isRequired: true, contract: { requirement: 'required', requiresConnectionTest: true } },
          { key: 'enabled', dataType: 'boolean', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
        ])}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'single-schema-key' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    addWizardModels(['gpt-4o-mini']);
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    const items: Array<{ key: string; value: string }> = onComplete.mock.calls[0][0];
    expect(items).toHaveLength(11);
    expect(new Set(items.map((item) => item.key)).size).toBe(items.length);
    const byKey = new Map(items.map((item) => [item.key, item.value]));
    expect(byKey.get('LLM_CONFIG_MODE')).toBe('channels');
    expect(byKey.get('GENERATION_BACKEND')).toBe('litellm');
    expect(byKey.get('LLM_CHANNELS')).toBe('openai,openai2');
    expect(byKey.get('LLM_OPENAI2_DISPLAY_NAME')).toBe('OpenAI 官方');
    expect(byKey.get('LLM_OPENAI2_PROVIDER')).toBe('openai');
    expect(byKey.get('LLM_OPENAI2_PROTOCOL')).toBe('openai');
    expect(byKey.get('LLM_OPENAI2_BASE_URL')).toBe('https://api.openai.com/v1');
    expect(byKey.get('LLM_OPENAI2_API_KEYS')).toBe('single-schema-key');
    expect(byKey.has('LLM_OPENAI2_API_KEY')).toBe(false);
    expect(byKey.get('LLM_OPENAI2_MODELS')).toBe('gpt-4o-mini');
    expect(byKey.get('LLM_OPENAI2_ENABLED')).toBe('true');
    expect(byKey.get('LITELLM_MODEL')).toBe('modelref:v1:openai2:openai%2Fgpt-4o-mini');
  });

  it('does not let a Provider selection rewrite schema-read-only transport fields', () => {
    const readOnly = [{ key: 'provider_id', operator: 'equals' as const, value: 'never' }];
    render(
      <FirstRunWizard
        onComplete={okComplete()}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={CATALOG}
        connectionFields={withCoreFields([
          { key: 'connection_name', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
          { key: 'provider_id', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
          { key: 'protocol', dataType: 'string', isSensitive: false, isRequired: false, contract: { requirement: 'optional', enabledWhen: readOnly } },
          { key: 'base_url', dataType: 'string', isSensitive: false, isRequired: false, contract: { requirement: 'optional', enabledWhen: readOnly } },
        ])}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    const protocolBefore = (screen.getByLabelText('协议') as HTMLButtonElement).textContent;
    const baseUrlBefore = (screen.getByLabelText('服务地址') as HTMLInputElement).value;
    chooseOption(screen.getByLabelText('服务商'), 'deepseek');

    expect(screen.getByLabelText('协议')).toHaveTextContent(protocolBefore ?? '');
    expect(screen.getByLabelText('服务地址')).toHaveValue(baseUrlBefore);
  });

  it('evaluates transport writers against the proposed Provider state', () => {
    const writableForDeepSeek = [{ key: 'provider_id', operator: 'equals' as const, value: 'deepseek' }];
    render(
      <FirstRunWizard
        onComplete={okComplete()}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={CATALOG}
        connectionFields={withCoreFields([
          { key: 'connection_name', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
          { key: 'provider_id', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
          { key: 'protocol', dataType: 'string', isSensitive: false, isRequired: false, contract: { requirement: 'optional', enabledWhen: writableForDeepSeek } },
          { key: 'base_url', dataType: 'string', isSensitive: false, isRequired: false, contract: { requirement: 'optional', enabledWhen: writableForDeepSeek } },
        ])}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('服务商'), 'deepseek');

    expect(screen.getByLabelText('协议')).toHaveTextContent('deepseek');
    expect(screen.getByLabelText('服务地址')).toHaveValue('https://api.deepseek.com');
  });

  it('uses the suggested duplicate identity for discovery and connection tests', async () => {
    discoverLLMChannelModels.mockResolvedValue({ success: true, models: ['gpt-4o-mini'] });
    testLLMChannel.mockResolvedValue({ success: true });
    render(
      <FirstRunWizard
        onComplete={okComplete()}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={[CATALOG.find((entry) => entry.id === 'openai')!]}
        existingChannelNames={['openai']}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'sk-test' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '自动发现模型' }));
    await waitFor(() => expect(discoverLLMChannelModels).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'openai2' }),
    ));
    addWizardModels(['gpt-4o-mini']);
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: /测试连接/ }));
    await waitFor(() => expect(testLLMChannel).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'openai2' }),
    ));
  });

  it('keeps the omitted-schema fallback and emits a backend-valid channel config', async () => {
    const onComplete = okComplete();
    render(
      <FirstRunWizard
        onComplete={onComplete}
        onClose={() => {}}
        isSaving={false}
        language="zh" providers={CATALOG}
        existingChannelNames={['openai']}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('服务商'), 'deepseek');
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'sk-test-123' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' })); // -> models
    // The preset seeds no models; add them explicitly (discovery / manual).
    addWizardModels(['deepseek-v4-flash', 'deepseek-v4-pro']);
    fireEvent.click(screen.getByRole('button', { name: '下一步' })); // -> model
    fireEvent.click(screen.getByRole('button', { name: '下一步' })); // -> review
    fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    const items: Array<{ key: string; value: string }> = onComplete.mock.calls[0][0];
    const byKey = new Map(items.map((item) => [item.key, item.value]));
    expect(byKey.get('LLM_CONFIG_MODE')).toBe('channels');
    expect(byKey.get('GENERATION_BACKEND')).toBe('litellm');
    // Existing "openai" channel is preserved, not overwritten.
    expect(byKey.get('LLM_CHANNELS')).toBe('openai,deepseek');
    expect(byKey.get('LLM_DEEPSEEK_PROTOCOL')).toBe('deepseek');
    expect(byKey.get('LLM_DEEPSEEK_BASE_URL')).toBe('https://api.deepseek.com');
    expect(byKey.get('LLM_DEEPSEEK_API_KEY')).toBe('sk-test-123');
    expect(byKey.get('LLM_DEEPSEEK_MODELS')).toBe('deepseek-v4-flash,deepseek-v4-pro');
    expect(byKey.get('LLM_DEEPSEEK_ENABLED')).toBe('true');
    expect(byKey.get('LITELLM_MODEL')).toBe(
      'modelref:v1:deepseek:deepseek%2Fdeepseek-v4-flash',
    );
  });

  it('creates a second connection for the same provider without overwriting the existing one', async () => {
    const onComplete = okComplete();
    render(
      <FirstRunWizard
        onComplete={onComplete}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={CATALOG}
        existingChannelNames={['deepseek']}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('服务商'), 'deepseek');
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'sk-second' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    addWizardModels(['deepseek-v4-flash']);
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    const items: Array<{ key: string; value: string }> = onComplete.mock.calls[0][0];
    const byKey = new Map(items.map((item) => [item.key, item.value]));
    expect(byKey.get('LLM_CHANNELS')).toBe('deepseek,deepseek2');
    expect(byKey.get('LLM_DEEPSEEK2_PROVIDER')).toBe('deepseek');
    expect(byKey.get('LLM_DEEPSEEK2_MODELS')).toBe('deepseek-v4-flash');
    expect(items.some((item) => item.key === 'LLM_DEEPSEEK_MODELS')).toBe(false);
    expect(byKey.get('LITELLM_MODEL')).toBe(
      'modelref:v1:deepseek2:deepseek%2Fdeepseek-v4-flash',
    );
  });

  it('does not require a Base URL for Gemini (SDK default endpoint)', () => {
    render(<FirstRunWizard onComplete={okComplete()} onClose={() => {}} isSaving={false} language="zh" providers={CATALOG} />);
    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('服务商'), 'gemini');
    // Official SDK endpoints stay out of the first-run form.
    expect(screen.queryByLabelText('服务地址')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'gm-key' } });
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
  });

  it('uses supportsDiscovery and goes straight to manual models when unsupported', () => {
    render(<FirstRunWizard onComplete={okComplete()} onClose={() => {}} isSaving={false} language="zh" providers={CATALOG} />);
    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('服务商'), 'gemini');
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'gm-key' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    expect(screen.queryByRole('button', { name: '自动发现模型' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('添加模型')).toBeInTheDocument();
    expect(screen.getByText(/不支持自动发现/)).toBeInTheDocument();
  });

  it('does not require an API key for Ollama (local runtime) and omits an empty key', async () => {
    const onComplete = okComplete();
    render(<FirstRunWizard onComplete={onComplete} onClose={() => {}} isSaving={false} language="zh" providers={CATALOG} />);
    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('服务商'), 'ollama');
    // Key-exempt providers do not expose a misleading credential field.
    expect(screen.queryByLabelText(/API 密钥/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '下一步' })); // -> models
    addWizardModels(['llama3.2']);
    fireEvent.click(screen.getByRole('button', { name: '下一步' })); // -> model
    fireEvent.click(screen.getByRole('button', { name: '下一步' })); // -> review
    fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    const items: Array<{ key: string; value: string }> = onComplete.mock.calls[0][0];
    const byKey = new Map(items.map((item) => [item.key, item.value]));
    expect(byKey.has('LLM_OLLAMA_API_KEY')).toBe(false);
    expect(byKey.get('LLM_OLLAMA_BASE_URL')).toBe('http://127.0.0.1:11434');
    expect(byKey.get('LITELLM_MODEL')).toBe('modelref:v1:ollama:ollama%2Fllama3.2');
  });

  it('blocks Custom until a Base URL is provided (backend requiresBaseUrl)', () => {
    render(<FirstRunWizard onComplete={okComplete()} onClose={() => {}} isSaving={false} language="zh" providers={CATALOG} />);
    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('服务商'), 'custom');
    expect(screen.getByLabelText('协议')).toHaveAttribute('role', 'combobox');
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'sk-custom' } });
    expect(screen.getByLabelText('服务地址')).toHaveValue('');
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('服务地址'), { target: { value: 'https://my-proxy.example.com/v1' } });
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
  });

  it('allows a Custom localhost connection with an empty API key when the backend exempts that host', () => {
    render(
      <FirstRunWizard
        onComplete={okComplete()}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={CATALOG}
        emptyApiKeyHosts={['localhost']}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('服务商'), 'custom');

    expect(screen.getByLabelText('API 密钥')).toHaveValue('');
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('服务地址'), {
      target: { value: 'http://localhost:8001/v1' },
    });
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
  });

  it('walks the local CLI path in fewer steps and emits the backend choice', async () => {
    const onComplete = okComplete();
    render(
      <FirstRunWizard
        onComplete={onComplete}
        onClose={() => {}}
        isSaving={false}
        language="zh"
        providers={CATALOG}
        connectionFields={[]}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /本机 CLI/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('选择本机 CLI 后端'), 'claude_code_cli');
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));
    await waitFor(() => expect(onComplete).toHaveBeenCalledWith([{ key: 'GENERATION_BACKEND', value: 'claude_code_cli' }]));
  });

  it('presents discovered models for confirmation instead of auto-selecting them all', async () => {
    discoverLLMChannelModels.mockResolvedValue({ success: true, message: 'ok', models: ['model-a', 'model-b'] });
    render(<FirstRunWizard onComplete={okComplete()} onClose={() => {}} isSaving={false} language="zh" providers={CATALOG} />);
    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('服务商'), 'deepseek');
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'sk-test' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '自动发现模型' }));
    // Candidates land in the searchable multi-select, unchecked — nothing is
    // enabled until the user confirms each model.
    fireEvent.click(await screen.findByRole('button', { name: '选择模型' }));
    const checkboxA = await screen.findByLabelText('model-a');
    expect(checkboxA).not.toBeChecked();
    expect(screen.getByLabelText('model-b')).not.toBeChecked();
    expect(screen.queryByLabelText('移除模型 model-a')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    fireEvent.click(checkboxA);
    // Only the confirmed model becomes an enabled token chip.
    expect(screen.getAllByLabelText('移除模型 model-a').length).toBeGreaterThan(0);
    expect(screen.queryByLabelText('移除模型 model-b')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
    // The candidate list is searchable.
    fireEvent.change(screen.getByLabelText('搜索模型'), { target: { value: 'model-b' } });
    expect(screen.queryByLabelText('model-a')).not.toBeInTheDocument();
    expect(screen.getByLabelText('model-b')).toBeInTheDocument();
    expect(discoverLLMChannelModels).toHaveBeenCalledWith(expect.objectContaining({
      name: 'deepseek',
      protocol: 'deepseek',
      apiKey: 'sk-test',
    }));
  });

  it('allows model discovery for key-exempt Ollama with an empty API key', async () => {
    discoverLLMChannelModels.mockResolvedValue({ success: true, message: 'ok', models: ['llama3.2'] });
    render(<FirstRunWizard onComplete={okComplete()} onClose={() => {}} isSaving={false} language="zh" providers={CATALOG} />);
    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('服务商'), 'ollama');
    expect(screen.queryByLabelText(/API 密钥/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '下一步' })); // -> models
    const discoverButton = screen.getByRole('button', { name: '自动发现模型' });
    expect(discoverButton).toBeEnabled();
    fireEvent.click(discoverButton);
    await waitFor(() => expect(discoverLLMChannelModels).toHaveBeenCalledWith(expect.objectContaining({
      name: 'ollama',
      protocol: 'ollama',
      baseUrl: 'http://127.0.0.1:11434',
      apiKey: '',
    })));
    fireEvent.click(await screen.findByRole('button', { name: '选择模型' }));
    expect(await screen.findByLabelText('llama3.2')).not.toBeChecked();
  });

  it('splits a pasted comma/whitespace-separated model list into deduped tokens', () => {
    render(<FirstRunWizard onComplete={okComplete()} onClose={() => {}} isSaving={false} language="zh" providers={CATALOG} />);
    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('服务商'), 'deepseek');
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'sk-test' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' })); // -> models
    fireEvent.paste(screen.getByLabelText('添加模型'), {
      clipboardData: { getData: () => ' model-a, model-b\nmodel-a ' },
    });
    expect(screen.getByLabelText('移除模型 model-a')).toBeInTheDocument();
    expect(screen.getByLabelText('移除模型 model-b')).toBeInTheDocument();
    expect(within(screen.getByTestId('wizard-model-chips')).getAllByRole('button')).toHaveLength(2);
    for (const removeButton of within(screen.getByTestId('wizard-model-chips')).getAllByRole('button')) {
      expect(removeButton).toHaveClass('h-11', 'w-11');
    }
  });

  it('shows a backend save error in the modal and keeps it open', async () => {
    const onComplete = vi.fn().mockResolvedValue({ success: false, error: '主模型未被启用渠道声明' });
    render(<FirstRunWizard onComplete={onComplete} onClose={() => {}} isSaving={false} language="zh" providers={CATALOG} />);
    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('服务商'), 'deepseek');
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'sk-test' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' })); // -> models
    addWizardModels(['deepseek-v4-flash']);
    fireEvent.click(screen.getByRole('button', { name: '下一步' })); // -> model
    fireEvent.click(screen.getByRole('button', { name: '下一步' })); // -> review
    fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));

    // The error is shown in place; the wizard is still mounted.
    await waitFor(() => expect(screen.getByText('主模型未被启用渠道声明')).toBeInTheDocument());
    expect(screen.getByTestId('first-run-wizard')).toBeInTheDocument();
  });

  it('blocks advancing until required fields are provided', () => {
    render(<FirstRunWizard onComplete={okComplete()} onClose={() => {}} isSaving={false} language="zh" providers={CATALOG} />);
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    // A cloud provider that needs a key (DeepSeek is preselected first template
    // may be key-exempt; explicitly pick DeepSeek) blocks until the key is set.
    chooseOption(screen.getByLabelText('服务商'), 'deepseek');
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'sk' } });
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
  });
});
