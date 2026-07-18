import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LlmConnectionFieldSchema, LlmProviderCatalogEntry } from '../../../types/systemConfig';
import { UiLanguageProvider, useUiLanguage } from '../../../contexts/UiLanguageContext';
import { LLMChannelEditor } from '../LLMChannelEditor';

function provider(
  overrides: Partial<LlmProviderCatalogEntry> & Pick<LlmProviderCatalogEntry, 'id' | 'label' | 'protocol'>,
): LlmProviderCatalogEntry {
  return {
    defaultBaseUrl: '',
    capabilities: [],
    requiresApiKey: true,
    requiresBaseUrl: false,
    supportsDiscovery: false,
    isLocal: false,
    isCustom: false,
    ...overrides,
  };
}

const PROVIDERS: LlmProviderCatalogEntry[] = [
  provider({
    id: 'openai',
    label: 'OpenAI 官方',
    protocol: 'openai',
    defaultBaseUrl: 'https://api.openai.com/v1',
    capabilities: ['official-api', 'openai-compatible', 'model-discovery'],
    supportsDiscovery: true,
  }),
  provider({
    id: 'deepseek',
    label: 'DeepSeek 官方',
    protocol: 'deepseek',
    defaultBaseUrl: 'https://api.deepseek.com',
    capabilities: ['official-api', 'openai-compatible'],
    supportsDiscovery: true,
  }),
  provider({
    id: 'dashscope',
    label: '通义千问（Dashscope）',
    protocol: 'openai',
    defaultBaseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    capabilities: ['openai-compatible', 'model-discovery'],
    supportsDiscovery: true,
  }),
  provider({
    id: 'ollama',
    label: 'Ollama（本地）',
    protocol: 'ollama',
    defaultBaseUrl: 'http://127.0.0.1:11434',
    capabilities: ['local-runtime'],
    requiresApiKey: false,
    supportsDiscovery: true,
    isLocal: true,
  }),
  provider({
    id: 'anthropic',
    label: 'Anthropic 官方',
    protocol: 'anthropic',
    capabilities: ['official-api'],
    supportsDiscovery: false,
  }),
  provider({
    id: 'custom',
    label: '自定义兼容服务',
    protocol: 'openai',
    requiresBaseUrl: true,
    supportsDiscovery: true,
    isCustom: true,
  }),
];

const ENGLISH_PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI Official',
  deepseek: 'DeepSeek Official',
  dashscope: 'Qwen (DashScope)',
  ollama: 'Ollama (Local)',
  anthropic: 'Anthropic Official',
  custom: 'Custom compatible service',
};

const BILINGUAL_PROVIDERS = PROVIDERS.map((entry) => ({
  ...entry,
  labelZh: entry.label,
  labelEn: ENGLISH_PROVIDER_LABELS[entry.id],
}));

function RuntimeLanguageSwitch() {
  const { language, setLanguage } = useUiLanguage();
  return <button type="button" onClick={() => setLanguage(language === 'en' ? 'zh' : 'en')}>switch-language</button>;
}

const OPENAI_ITEMS = [
  { key: 'LLM_CHANNELS', value: 'openai' },
  { key: 'LLM_OPENAI_PROVIDER', value: 'openai' },
  { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
  { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' },
  { key: 'LLM_OPENAI_ENABLED', value: 'true' },
  { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' },
  { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' },
  { key: 'LITELLM_MODEL', value: 'openai/gpt-4o-mini' },
];

const CONNECTION_IDENTITY_FIELDS: LlmConnectionFieldSchema[] = [
  { key: 'connection_name', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'provider_id', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
];

const HIDDEN_INHERITED_CONTRACT: LlmConnectionFieldSchema['contract'] = {
  requirement: 'inherited',
  visibleWhen: [{ key: '__test_hidden', operator: 'equals', value: 'true' }],
};

const CONNECTION_CORE_FIELDS: LlmConnectionFieldSchema[] = [
  CONNECTION_IDENTITY_FIELDS[0],
  { key: 'display_name', dataType: 'string', isSensitive: false, isRequired: false, contract: HIDDEN_INHERITED_CONTRACT },
  CONNECTION_IDENTITY_FIELDS[1],
  { key: 'protocol', dataType: 'string', isSensitive: false, isRequired: false, contract: HIDDEN_INHERITED_CONTRACT },
  { key: 'base_url', dataType: 'string', isSensitive: false, isRequired: false, contract: HIDDEN_INHERITED_CONTRACT },
  { key: 'api_key', dataType: 'string', isSensitive: true, isRequired: false, contract: HIDDEN_INHERITED_CONTRACT },
  { key: 'api_keys', dataType: 'array', isSensitive: true, isRequired: false, contract: HIDDEN_INHERITED_CONTRACT },
  { key: 'models', dataType: 'array', isSensitive: false, isRequired: false, contract: HIDDEN_INHERITED_CONTRACT },
  { key: 'extra_headers', dataType: 'json', isSensitive: true, isRequired: false, contract: HIDDEN_INHERITED_CONTRACT },
  { key: 'enabled', dataType: 'boolean', isSensitive: false, isRequired: false, contract: HIDDEN_INHERITED_CONTRACT },
];

const MODELS_SCHEMA_FIELD: LlmConnectionFieldSchema = {
  key: 'models',
  dataType: 'array',
  isSensitive: false,
  isRequired: false,
  contract: { requirement: 'optional' },
};

const REQUIRED_SAVED_CONNECTION_FIELDS: LlmConnectionFieldSchema[] = [
  { key: 'connection_name', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'display_name', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'provider_id', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'protocol', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'enabled', dataType: 'boolean', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
];

const COMPLETE_SAVED_CONNECTION_ITEMS = [
  { key: 'LLM_CHANNELS', value: 'openai' },
  { key: 'LLM_OPENAI_DISPLAY_NAME', value: 'OpenAI' },
  { key: 'LLM_OPENAI_PROVIDER', value: 'openai' },
  { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
  { key: 'LLM_OPENAI_ENABLED', value: 'false' },
];

function withIdentity(fields: LlmConnectionFieldSchema[]): LlmConnectionFieldSchema[] {
  const byKey = new Map(
    [...CONNECTION_CORE_FIELDS, ...fields].map((field) => [field.key, field]),
  );
  return Array.from(byKey.values());
}

function officialItemsWithoutBaseUrl(providerId: 'gemini' | 'anthropic') {
  const upper = providerId.toUpperCase();
  return [
    { key: 'LLM_CHANNELS', value: providerId },
    { key: `LLM_${upper}_PROVIDER`, value: providerId },
    { key: `LLM_${upper}_PROTOCOL`, value: providerId },
    { key: `LLM_${upper}_BASE_URL`, value: '' },
    { key: `LLM_${upper}_ENABLED`, value: 'true' },
    { key: `LLM_${upper}_API_KEY`, value: 'secret-key' },
    { key: `LLM_${upper}_MODELS`, value: `${providerId}-model` },
  ];
}

const { testLLMChannel, discoverLLMChannelModels } = vi.hoisted(() => ({
  testLLMChannel: vi.fn(),
  discoverLLMChannelModels: vi.fn(),
}));

vi.mock('../../../api/systemConfig', () => ({
  systemConfigApi: {
    testLLMChannel: (...args: unknown[]) => testLLMChannel(...args),
    discoverLLMChannelModels: (...args: unknown[]) => discoverLLMChannelModels(...args),
  },
}));

if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

function connectionCard(name = 'openai'): HTMLElement {
  return screen.getByTestId(`connection-card-${name}`);
}

function editConnection(name = 'openai'): HTMLElement {
  fireEvent.click(within(connectionCard(name)).getByRole('button', { name: '编辑' }));
  return screen.getByRole('dialog', { name: '编辑模型服务' });
}

function openConnectionMenu(name = 'openai'): HTMLElement {
  fireEvent.click(within(connectionCard(name)).getByRole('button', { name: `更多操作 ${name}` }));
  return screen.getByRole('menu');
}

function selectProvider(value: string): void {
  const trigger = screen.getByLabelText('选择模型服务商');
  fireEvent.click(trigger);
  const listbox = screen.getByRole('listbox');
  const option = within(listbox)
    .getAllByRole('option')
    .find((item) => item.getAttribute('data-value') === value);
  expect(option).toBeDefined();
  fireEvent.click(option!);
  const next = screen.queryByRole('button', { name: '下一步' });
  if (next) {
    fireEvent.click(next);
  }
}

function revealManualModelInput(): HTMLInputElement {
  const existing = screen.queryByLabelText('手动添加模型');
  if (existing) {
    return existing as HTMLInputElement;
  }
  fireEvent.click(screen.getByRole('button', { name: /手动添加模型/ }));
  return screen.getByLabelText('手动添加模型') as HTMLInputElement;
}

function addManualModels(models: string[]): void {
  const input = revealManualModelInput();
  for (const model of models) {
    fireEvent.change(input, { target: { value: model } });
    fireEvent.keyDown(input, { key: 'Enter' });
  }
}

function replaceModels(models: string[]): void {
  for (const remove of screen.queryAllByRole('button', { name: /^移除模型 / })) {
    fireEvent.click(remove);
  }
  addManualModels(models);
}

function lastDraft(onDraftItemsChange: ReturnType<typeof vi.fn>): Array<{ key: string; value: string }> {
  return onDraftItemsChange.mock.calls.at(-1)?.[0] ?? [];
}

async function expectUnavailableConnectionSchema(connectionFields: LlmConnectionFieldSchema[]) {
  const onDraftItemsChange = vi.fn();
  const onValidityChange = vi.fn();
  render(
    <LLMChannelEditor
      items={OPENAI_ITEMS}
      providers={PROVIDERS}
      connectionFields={connectionFields}
      maskToken="******"
      onDraftItemsChange={onDraftItemsChange}
      onValidityChange={onValidityChange}
    />,
  );

  await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(false));
  const card = connectionCard();
  const test = within(card).getByRole('button', { name: '测试' });
  const edit = within(card).getByRole('button', { name: '编辑' });
  const more = within(card).getByRole('button', { name: '更多操作 openai' });
  expect(test).toBeDisabled();
  expect(edit).toBeDisabled();
  expect(more).toBeDisabled();
  fireEvent.click(test);
  fireEvent.click(edit);
  fireEvent.click(more);
  expect(screen.getAllByText(/连接 Schema 不完整或不可用/).length).toBeGreaterThan(0);
  expect(screen.queryByRole('dialog', { name: '编辑模型服务' })).not.toBeInTheDocument();
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  expect(testLLMChannel).not.toHaveBeenCalled();
  expect(discoverLLMChannelModels).not.toHaveBeenCalled();
  await waitFor(() => expect(lastDraft(onDraftItemsChange)).toEqual([]));
}

describe('LLMChannelEditor', () => {
  beforeEach(() => {
    testLLMChannel.mockReset();
    discoverLLMChannelModels.mockReset();
    localStorage.clear();
  });

  it('updates cards and an open Connection modal immediately when UI language changes', () => {
    localStorage.setItem('dsa.uiLanguage', 'en');
    render(
      <UiLanguageProvider>
        <RuntimeLanguageSwitch />
        <LLMChannelEditor items={OPENAI_ITEMS} providers={BILINGUAL_PROVIDERS} maskToken="******" />
      </UiLanguageProvider>,
    );
    const languageSwitch = screen.getByRole('button', { name: 'switch-language' });
    expect(connectionCard()).toHaveTextContent('OpenAI Official');
    fireEvent.click(within(connectionCard()).getByRole('button', { name: 'Edit' }));
    const dialog = screen.getByRole('dialog', { name: 'Edit model service' });
    expect(within(dialog).getByRole('button', { name: 'Choose model provider' })).toHaveTextContent('OpenAI Official');

    fireEvent.click(languageSwitch);

    expect(connectionCard()).toHaveTextContent('OpenAI 官方');
    expect(within(dialog).getByRole('button', { name: '选择模型服务商' })).toHaveTextContent('OpenAI 官方');
    expect(OPENAI_ITEMS.find((item) => item.key === 'LLM_OPENAI_PROVIDER')?.value).toBe('openai');
  });

  it('renders saved connections as compact cards without flat credential fields', () => {
    const { container } = render(
      <LLMChannelEditor items={OPENAI_ITEMS} providers={PROVIDERS} maskToken="******" />,
    );

    expect(connectionCard()).toHaveTextContent('OpenAI 官方');
    expect(connectionCard()).toHaveTextContent('gpt-4o-mini');
    expect(screen.queryByLabelText('API 密钥')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('服务地址')).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/生成后端状态|主后端|备用后端|运行时能力检测/);
  });

  it.each([
    'LLM_OPENAI_DISPLAY_NAME',
    'LLM_OPENAI_PROVIDER',
    'LLM_OPENAI_PROTOCOL',
    'LLM_OPENAI_ENABLED',
  ])('does not synthesize %s when a Connection Schema is present', async (missingKey) => {
    const onValidityChange = vi.fn();
    render(
      <LLMChannelEditor
        items={COMPLETE_SAVED_CONNECTION_ITEMS.filter((item) => item.key !== missingKey)}
        providers={PROVIDERS}
        connectionFields={withIdentity(REQUIRED_SAVED_CONNECTION_FIELDS)}
        maskToken="******"
        onValidityChange={onValidityChange}
      />,
    );

    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(false));
  });

  it.each([
    'LLM_OPENAI_DISPLAY_NAME',
    'LLM_OPENAI_PROVIDER',
    'LLM_OPENAI_PROTOCOL',
    'LLM_OPENAI_ENABLED',
  ])('does not treat the effective %s fallback as persisted when rawValueExists is false', async (missingKey) => {
    const onValidityChange = vi.fn();
    render(
      <LLMChannelEditor
        items={COMPLETE_SAVED_CONNECTION_ITEMS.map((item) => (
          item.key === missingKey ? { ...item, rawValueExists: false } : item
        ))}
        providers={PROVIDERS}
        connectionFields={withIdentity(REQUIRED_SAVED_CONNECTION_FIELDS)}
        maskToken="******"
        onValidityChange={onValidityChange}
      />,
    );

    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(false));
  });

  it('treats an explicit false enabled value as present under a Connection Schema', async () => {
    const onValidityChange = vi.fn();
    render(
      <LLMChannelEditor
        items={COMPLETE_SAVED_CONNECTION_ITEMS}
        providers={PROVIDERS}
        connectionFields={withIdentity(REQUIRED_SAVED_CONNECTION_FIELDS)}
        maskToken="******"
        onValidityChange={onValidityChange}
      />,
    );

    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(true));
  });

  it('keeps legacy fallback for the same sparse payload only when the Schema is omitted', async () => {
    const onValidityChange = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS.filter((item) => (
          !['LLM_OPENAI_PROVIDER', 'LLM_OPENAI_PROTOCOL', 'LLM_OPENAI_ENABLED'].includes(item.key)
        ))}
        providers={PROVIDERS}
        maskToken="******"
        onValidityChange={onValidityChange}
      />,
    );

    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(true));
  });

  it('fails closed across card actions and drafts for a present empty schema', async () => {
    await expectUnavailableConnectionSchema([]);
  });

  it('fails closed across card actions and drafts for a present partial schema', async () => {
    await expectUnavailableConnectionSchema([MODELS_SCHEMA_FIELD]);
  });

  it('fails closed across card actions and drafts for an identity-only schema', async () => {
    await expectUnavailableConnectionSchema(CONNECTION_IDENTITY_FIELDS);
  });

  it('blocks actions and drafts when an unknown field is visible and required', async () => {
    await expectUnavailableConnectionSchema(withIdentity([{
      key: 'future_token',
      dataType: 'string',
      isSensitive: false,
      isRequired: true,
      contract: {
        requirement: 'required',
        visibleWhen: [{ key: 'provider_id', operator: 'equals', value: 'openai' }],
      },
    }]));
  });

  it('fails closed across card actions and drafts when connection_name is missing', async () => {
    await expectUnavailableConnectionSchema([
      CONNECTION_IDENTITY_FIELDS[1],
      MODELS_SCHEMA_FIELD,
    ]);
  });

  it('fails closed across card actions and drafts when provider_id is missing', async () => {
    await expectUnavailableConnectionSchema([
      CONNECTION_IDENTITY_FIELDS[0],
      MODELS_SCHEMA_FIELD,
    ]);
  });

  it('fails closed across card actions and drafts for a read-only identity schema', async () => {
    await expectUnavailableConnectionSchema([
      CONNECTION_IDENTITY_FIELDS[0],
      {
        ...CONNECTION_IDENTITY_FIELDS[1],
        isRequired: false,
        contract: { requirement: 'inherited' },
      },
      MODELS_SCHEMA_FIELD,
    ]);
  });

  it('keeps an unknown-condition field inspectable but read-only', async () => {
    const onDraftItemsChange = vi.fn();
    const onValidityChange = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        connectionFields={withIdentity([{
          key: 'base_url',
          dataType: 'string',
          isSensitive: false,
          isRequired: false,
          contract: {
            requirement: 'optional',
            visibleWhen: [{ key: 'provider_id', operator: 'futureOperator' as never, value: 'openai' }],
          },
        }])}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
        onValidityChange={onValidityChange}
      />,
    );

    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(false));
    expect(within(connectionCard()).getByRole('button', { name: '测试' })).toBeDisabled();
    const more = within(connectionCard()).getByRole('button', { name: '更多操作 openai' });
    expect(more).toBeEnabled();
    fireEvent.click(more);
    const menu = screen.getByRole('menu');
    for (const action of within(menu).getAllByRole('menuitem')) {
      expect(action).toBeDisabled();
      action.removeAttribute('disabled');
      fireEvent.click(action);
    }
    fireEvent.click(more);
    expect(within(connectionCard()).getByRole('button', { name: '编辑' })).toBeEnabled();
    const dialog = editConnection();
    expect(within(dialog).getByLabelText('服务地址')).toBeDisabled();
    expect(within(dialog).getByText('连接字段契约包含不支持的条件')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: '保存修改' })).toBeDisabled();
    expect(testLLMChannel).not.toHaveBeenCalled();
    expect(discoverLLMChannelModels).not.toHaveBeenCalled();
    await waitFor(() => expect(lastDraft(onDraftItemsChange)).toEqual([]));
  });

  it('localizes the unavailable-schema diagnostic in English', () => {
    localStorage.setItem('dsa.uiLanguage', 'en');
    render(
      <UiLanguageProvider>
        <LLMChannelEditor
          items={OPENAI_ITEMS}
          providers={BILINGUAL_PROVIDERS}
          connectionFields={[]}
          maskToken="******"
        />
      </UiLanguageProvider>,
    );

    expect(screen.getAllByText('Connection Schema is incomplete or unavailable').length).toBeGreaterThan(0);
  });

  it('rejects modal test, discovery and save when a loaded schema becomes partial', async () => {
    const onDraftItemsChange = vi.fn();
    const onValidityChange = vi.fn();
    const completeFields = withIdentity([MODELS_SCHEMA_FIELD]);
    const { rerender } = render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        connectionFields={completeFields}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
        onValidityChange={onValidityChange}
      />,
    );
    const dialog = editConnection();

    rerender(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        connectionFields={[MODELS_SCHEMA_FIELD]}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
        onValidityChange={onValidityChange}
      />,
    );

    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(false));
    const test = within(dialog).getByRole('button', { name: '测试连接' });
    const save = within(dialog).getByRole('button', { name: '保存修改' });
    expect(within(dialog).queryByRole('button', { name: '获取模型' })).not.toBeInTheDocument();
    for (const button of [test, save]) {
      expect(button).toBeDisabled();
      button.removeAttribute('disabled');
      fireEvent.click(button);
    }
    expect(within(dialog).getByText('连接 Schema 不完整或不可用')).toBeInTheDocument();
    expect(testLLMChannel).not.toHaveBeenCalled();
    expect(discoverLLMChannelModels).not.toHaveBeenCalled();
    await waitFor(() => expect(lastDraft(onDraftItemsChange)).toEqual([]));
  });

  it('uses the backend Connection field contract instead of a local models requirement', async () => {
    const onValidityChange = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS.filter((item) => item.key !== 'LLM_OPENAI_MODELS')}
        providers={PROVIDERS}
        connectionFields={withIdentity([{
          key: 'models',
          dataType: 'array',
          isSensitive: false,
          isRequired: false,
          contract: { requirement: 'optional' },
        }])}
        maskToken="******"
        onValidityChange={onValidityChange}
      />,
    );

    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(true));
    expect(connectionCard()).not.toHaveTextContent('草稿 · 未完成');
  });

  it('uses the schema API-key label when Catalog says the key is required', () => {
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        connectionFields={withIdentity([{
          key: 'api_key',
          dataType: 'string',
          isSensitive: true,
          isRequired: false,
          contract: { requirement: 'optional' },
        }])}
        maskToken="******"
      />,
    );

    const dialog = editConnection();
    expect(within(dialog).getByLabelText('API 密钥（可选）')).toHaveValue('secret-key');
  });

  it('does not read legacy Catalog requirements for an explicitly empty schema', () => {
    const legacyRequirementRead = vi.fn(() => true);
    const openai = { ...PROVIDERS.find((entry) => entry.id === 'openai')! };
    Object.defineProperties(openai, {
      requiresApiKey: { configurable: true, get: legacyRequirementRead },
      requiresBaseUrl: { configurable: true, get: legacyRequirementRead },
    });
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={[openai]}
        connectionFields={[]}
        maskToken="******"
      />,
    );

    expect(within(connectionCard()).getByRole('button', { name: '编辑' })).toBeDisabled();
    expect(screen.getAllByText('连接 Schema 不完整或不可用').length).toBeGreaterThan(0);
    expect(legacyRequirementRead).not.toHaveBeenCalled();
  });

  it('uses schema visibility and enabled state for protocol and Base URL fields', () => {
    const readOnlyForThisProvider = [{ key: 'provider_id', operator: 'equals' as const, value: 'other' }];
    const visibleForThisProvider = [{ key: 'provider_id', operator: 'equals' as const, value: 'openai' }];
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        connectionFields={withIdentity([
          {
            key: 'protocol',
            dataType: 'string',
            isSensitive: false,
            isRequired: false,
            contract: {
              requirement: 'optional',
              visibleWhen: visibleForThisProvider,
              enabledWhen: readOnlyForThisProvider,
            },
          },
          {
            key: 'base_url',
            dataType: 'string',
            isSensitive: false,
            isRequired: false,
            contract: {
              requirement: 'optional',
              visibleWhen: visibleForThisProvider,
              enabledWhen: readOnlyForThisProvider,
            },
          },
        ])}
        maskToken="******"
      />,
    );

    const dialog = editConnection();
    expect(within(dialog).getByLabelText('协议')).toBeDisabled();
    expect(within(dialog).getByLabelText('服务地址')).toBeDisabled();
  });

  it('does not expose legacy Base URL actions when the schema hides the field', () => {
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        connectionFields={withIdentity([{
          key: 'base_url',
          dataType: 'string',
          isSensitive: false,
          isRequired: false,
          contract: {
            requirement: 'optional',
            visibleWhen: [{ key: 'provider_id', operator: 'equals', value: 'other' }],
          },
        }])}
        maskToken="******"
      />,
    );

    const dialog = editConnection();
    expect(within(dialog).queryByLabelText('服务地址')).not.toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: '使用自定义服务地址' })).not.toBeInTheDocument();
    expect(within(dialog).queryByText('使用服务商官方地址')).not.toBeInTheDocument();
  });

  it('exposes the Base URL reveal only when the schema authorizes that UI context', () => {
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        connectionFields={withIdentity([{
          key: 'base_url',
          dataType: 'string',
          isSensitive: false,
          isRequired: false,
          contract: {
            requirement: 'optional',
            visibleWhen: [{ key: 'base_url_visible', operator: 'equals', value: 'true' }],
          },
        }])}
        maskToken="******"
      />,
    );

    const dialog = editConnection();
    expect(within(dialog).getByText('使用服务商官方地址')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: '使用自定义服务地址' }));
    expect(within(dialog).getByLabelText('服务地址')).toHaveValue('https://api.openai.com/v1');
  });

  it('does not restore a Base URL when the schema makes that field read-only', () => {
    const customUrlItems = OPENAI_ITEMS.map((item) => (
      item.key === 'LLM_OPENAI_BASE_URL'
        ? { ...item, value: 'https://proxy.example.com/v1' }
        : item
    ));
    render(
      <LLMChannelEditor
        items={customUrlItems}
        providers={PROVIDERS}
        connectionFields={withIdentity([{
          key: 'base_url',
          dataType: 'string',
          isSensitive: false,
          isRequired: false,
          contract: {
            requirement: 'optional',
            enabledWhen: [{ key: 'provider_id', operator: 'equals', value: 'other' }],
          },
        }])}
        maskToken="******"
      />,
    );

    const dialog = editConnection();
    const baseUrlInput = within(dialog).getByLabelText('服务地址');
    const restore = within(dialog).getByRole('button', { name: '恢复官方默认地址' });
    expect(restore).toBeDisabled();
    fireEvent.click(restore);
    expect(baseUrlInput).toHaveValue('https://proxy.example.com/v1');
  });

  it('does not mutate models through secondary controls when the schema is read-only', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        connectionFields={withIdentity([{
          key: 'models',
          dataType: 'array',
          isSensitive: false,
          isRequired: false,
          contract: {
            requirement: 'optional',
            enabledWhen: [{ key: 'provider_id', operator: 'equals', value: 'other' }],
          },
        }])}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    const dialog = editConnection();
    const remove = within(dialog).getByRole('button', { name: '移除模型 gpt-4o-mini' });
    const discover = within(dialog).getByRole('button', { name: '获取模型' });
    const manual = within(dialog).getByRole('button', { name: /手动添加模型/ });
    expect(remove).toBeDisabled();
    expect(discover).toBeDisabled();
    expect(manual).toBeDisabled();
    fireEvent.click(remove);
    fireEvent.click(manual);
    expect(within(dialog).queryByLabelText('手动添加模型')).not.toBeInTheDocument();
    expect(within(dialog).getByText('gpt-4o-mini')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: '保存修改' }));

    await waitFor(() => {
      const draft = lastDraft(onDraftItemsChange);
      expect(draft).not.toContainEqual({ key: 'LLM_OPENAI_MODELS', value: '' });
    });
  });

  it('disables model discovery when a schema-required connection-test field is missing', () => {
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS.filter((item) => item.key !== 'LLM_OPENAI_API_KEY')}
        providers={PROVIDERS}
        connectionFields={withIdentity([
          {
            key: 'api_key',
            dataType: 'string',
            isSensitive: true,
            isRequired: true,
            contract: { requirement: 'required', requiresConnectionTest: true },
          },
          {
            key: 'models',
            dataType: 'array',
            isSensitive: false,
            isRequired: false,
            contract: { requirement: 'optional', requiresConnectionTest: true },
          },
        ])}
        maskToken="******"
      />,
    );

    const dialog = editConnection();
    expect(within(dialog).getByRole('button', { name: '获取模型' })).toBeDisabled();
  });

  it('uses schema visibility and enabled state for the remaining editable fields', () => {
    const disabledHere = [{ key: 'provider_id', operator: 'equals' as const, value: 'other' }];
    const hiddenHere = [{ key: 'provider_id', operator: 'equals' as const, value: 'other' }];
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        connectionFields={withIdentity([
          { key: 'display_name', dataType: 'string', isSensitive: false, isRequired: false, contract: { requirement: 'optional', enabledWhen: disabledHere } },
          { key: 'api_key', dataType: 'string', isSensitive: true, isRequired: false, contract: { requirement: 'optional', visibleWhen: hiddenHere } },
          { key: 'extra_headers', dataType: 'json', isSensitive: true, isRequired: false, contract: { requirement: 'optional', enabledWhen: disabledHere } },
          { key: 'models', dataType: 'array', isSensitive: false, isRequired: false, contract: { requirement: 'optional', visibleWhen: hiddenHere } },
          { key: 'enabled', dataType: 'boolean', isSensitive: false, isRequired: false, contract: { requirement: 'optional', enabledWhen: disabledHere } },
        ])}
        maskToken="******"
      />,
    );

    const dialog = editConnection();
    expect(within(dialog).getByRole('button', { name: '选择模型服务商' })).toBeEnabled();
    expect(within(dialog).getByLabelText('连接名称')).toBeDisabled();
    expect(within(dialog).queryByLabelText(/API 密钥/)).not.toBeInTheDocument();
    expect(within(dialog).getByLabelText('附加请求头（JSON）')).toBeDisabled();
    expect(within(dialog).queryByLabelText('可用模型')).not.toBeInTheDocument();
    expect(within(dialog).getByRole('switch', { name: '启用此连接' })).toBeDisabled();
  });

  it('blocks saving a disabled draft when its schema contains an unknown operator', () => {
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS.map((item) => (
          item.key === 'LLM_OPENAI_ENABLED' ? { ...item, value: 'false' } : item
        ))}
        providers={PROVIDERS}
        connectionFields={withIdentity([{
          key: 'base_url',
          dataType: 'string',
          isSensitive: false,
          isRequired: false,
          contract: {
            requirement: 'optional',
            visibleWhen: [{ key: 'provider_id', operator: 'futureOperator' as never, value: 'openai' }],
          },
        }])}
        maskToken="******"
      />,
    );

    expect(within(connectionCard()).getByRole('button', { name: '编辑' })).toBeEnabled();
    const dialog = editConnection();
    expect(within(dialog).getByLabelText('服务地址')).toBeDisabled();
    expect(within(dialog).getByText('连接字段契约包含不支持的条件')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: '保存修改' })).toBeDisabled();
  });

  it('does not let the card shortcut toggle enabled when an empty schema authorizes no writes', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        connectionFields={[]}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    const menu = within(connectionCard()).getByRole('button', { name: '更多操作 openai' });
    expect(menu).toBeDisabled();
    fireEvent.click(menu);

    expect(connectionCard()).toHaveTextContent('已启用');
    await waitFor(() => expect(lastDraft(onDraftItemsChange)).toEqual([]));
  });

  it('does not expose the add-flow Provider writer under an empty schema', () => {
    const { rerender } = render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        connectionFields={[]}
        maskToken="******"
        addSignal={0}
      />,
    );
    rerender(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        connectionFields={[]}
        maskToken="******"
        addSignal={1}
      />,
    );

    expect(screen.queryByRole('dialog', { name: '添加模型服务' })).not.toBeInTheDocument();
    expect(screen.getAllByText('连接 Schema 不完整或不可用').length).toBeGreaterThan(0);
  });

  it('does not authorize a new Connection when the schema omits connection_name', () => {
    const connectionFields: LlmConnectionFieldSchema[] = [{
        key: 'provider_id',
        dataType: 'string',
        isSensitive: false,
        isRequired: true,
        contract: { requirement: 'required' },
    }];
    const { rerender } = render(
      <LLMChannelEditor items={[]} providers={PROVIDERS} connectionFields={connectionFields} maskToken="******" addSignal={0} />,
    );
    rerender(
      <LLMChannelEditor items={[]} providers={PROVIDERS} connectionFields={connectionFields} maskToken="******" addSignal={1} />,
    );

    expect(screen.queryByRole('dialog', { name: '添加模型服务' })).not.toBeInTheDocument();
    expect(screen.getByText('连接 Schema 不完整或不可用')).toBeInTheDocument();
  });

  it('does not let a Provider change rewrite schema-read-only transport fields', () => {
    const readOnly = [{ key: 'provider_id', operator: 'equals' as const, value: 'never' }];
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        connectionFields={withIdentity([
          { key: 'provider_id', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
          { key: 'protocol', dataType: 'string', isSensitive: false, isRequired: false, contract: { requirement: 'optional', enabledWhen: readOnly } },
          { key: 'base_url', dataType: 'string', isSensitive: false, isRequired: false, contract: { requirement: 'optional', enabledWhen: readOnly } },
        ])}
        maskToken="******"
      />,
    );

    const dialog = editConnection();
    const protocol = within(dialog).getByLabelText('协议');
    const baseUrl = within(dialog).getByLabelText('服务地址');
    const protocolBefore = protocol.textContent;
    const baseUrlBefore = (baseUrl as HTMLInputElement).value;
    selectProvider('deepseek');

    expect(protocol).toHaveTextContent(protocolBefore ?? '');
    expect(baseUrl).toHaveValue(baseUrlBefore);
  });

  it('writes a single credential only to the schema-visible API_KEYS sibling', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS.filter((item) => item.key !== 'LLM_OPENAI_API_KEY')}
        providers={PROVIDERS}
        connectionFields={withIdentity([{
          key: 'api_keys',
          dataType: 'array',
          isSensitive: true,
          isRequired: false,
          contract: { requirement: 'optional' },
        }])}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    const dialog = editConnection();
    fireEvent.change(within(dialog).getByLabelText('API 密钥（可选）'), {
      target: { value: 'single-schema-key' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: '保存修改' }));

    await waitFor(() => expect(lastDraft(onDraftItemsChange)).toEqual([
      { key: 'LLM_OPENAI_PROVIDER', value: 'openai' },
      { key: 'LLM_OPENAI_API_KEYS', value: 'single-schema-key' },
    ]));
  });

  it('does not serialize or mutate a draft under a present models-only schema', async () => {
    const onDraftItemsChange = vi.fn();
    const onValidityChange = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        connectionFields={[{
          key: 'models',
          dataType: 'array',
          isSensitive: false,
          isRequired: false,
          contract: { requirement: 'optional' },
        }]}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
        onValidityChange={onValidityChange}
      />,
    );

    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(false));
    expect(within(connectionCard()).getByRole('button', { name: '测试' })).toBeDisabled();
    expect(within(connectionCard()).getByRole('button', { name: '编辑' })).toBeDisabled();
    expect(within(connectionCard()).getByRole('button', { name: '更多操作 openai' })).toBeDisabled();
    expect(screen.getAllByText('连接 Schema 不完整或不可用').length).toBeGreaterThan(0);
    expect(testLLMChannel).not.toHaveBeenCalled();
    expect(discoverLLMChannelModels).not.toHaveBeenCalled();
    await waitFor(() => expect(lastDraft(onDraftItemsChange)).toEqual([]));
  });

  it('serializes a model edit when the final schema has writable identity authority', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        connectionFields={withIdentity([{
          key: 'models',
          dataType: 'array',
          isSensitive: false,
          isRequired: false,
          contract: { requirement: 'optional' },
        }])}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    const dialog = editConnection();
    replaceModels(['gpt-5.5']);
    fireEvent.click(within(dialog).getByRole('button', { name: '保存修改' }));

    await waitFor(() => expect(lastDraft(onDraftItemsChange)).toEqual([
      { key: 'LLM_OPENAI_PROVIDER', value: 'openai' },
      { key: 'LLM_OPENAI_MODELS', value: 'gpt-5.5' },
    ]));
  });

  it('blocks card Test/Delete and modal Test when the schema authorizes no operations', () => {
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        connectionFields={[]}
        maskToken="******"
      />,
    );

    const card = connectionCard();
    const cardTest = within(card).getByRole('button', { name: '测试' });
    expect(cardTest).toBeDisabled();
    const moreActions = within(card).getByRole('button', { name: '更多操作 openai' });
    expect(moreActions).toBeDisabled();
    const edit = within(card).getByRole('button', { name: '编辑' });
    expect(edit).toBeDisabled();
    fireEvent.click(cardTest);
    fireEvent.click(moreActions);
    fireEvent.click(edit);
    expect(testLLMChannel).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog', { name: '编辑模型服务' })).not.toBeInTheDocument();
  });

  it.each([
    ['Catalog loading', { catalogLoading: true }],
    ['Catalog failure', { catalogUnavailable: true }],
  ])('keeps the draft invalid and actions read-only during %s', async (_label, state) => {
    const onValidityChange = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        maskToken="******"
        onValidityChange={onValidityChange}
        {...state}
      />,
    );

    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(false));
    expect(within(connectionCard()).getByRole('button', { name: '测试' })).toBeDisabled();
    expect(within(connectionCard()).getByRole('button', { name: '编辑' })).toBeDisabled();
  });

  it('does not read legacy Base URL requirements when a schema is present', () => {
    const legacyRequirementRead = vi.fn(() => false);
    const anthropic = { ...PROVIDERS.find((entry) => entry.id === 'anthropic')! };
    Object.defineProperty(anthropic, 'requiresBaseUrl', {
      configurable: true,
      get: legacyRequirementRead,
    });
    render(
      <LLMChannelEditor
        items={officialItemsWithoutBaseUrl('anthropic')}
        providers={[anthropic]}
        connectionFields={withIdentity([{
          key: 'base_url',
          dataType: 'string',
          isSensitive: false,
          isRequired: false,
          contract: { requirement: 'optional' },
        }])}
        maskToken="******"
      />,
    );

    editConnection('anthropic');
    expect(legacyRequirementRead).not.toHaveBeenCalled();
  });

  it('fails closed without evaluating legacy completeness while the Catalog schema is still loading', async () => {
    const onValidityChange = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS.filter((item) => item.key !== 'LLM_OPENAI_MODELS')}
        providers={PROVIDERS}
        maskToken="******"
        catalogLoading
        onValidityChange={onValidityChange}
      />,
    );

    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(false));
    expect(within(connectionCard()).getByRole('button', { name: '编辑' })).toBeDisabled();
  });

  it('uses the backend Connection field contract instead of a local display-name requirement', async () => {
    const onValidityChange = vi.fn();
    render(
      <LLMChannelEditor
        items={[
          ...OPENAI_ITEMS,
          { key: 'LLM_OPENAI_DISPLAY_NAME', value: '' },
        ]}
        providers={PROVIDERS}
        connectionFields={withIdentity([{
          key: 'display_name',
          dataType: 'string',
          isSensitive: false,
          isRequired: false,
          contract: { requirement: 'optional' },
        }])}
        maskToken="******"
        onValidityChange={onValidityChange}
      />,
    );

    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(true));
    expect(connectionCard()).not.toHaveTextContent('草稿 · 未完成');
  });

  it('preserves legacy model-based local runtime inference only when the Schema is omitted', async () => {
    const onValidityChange = vi.fn();
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'lab' },
          { key: 'LLM_LAB_MODELS', value: 'ollama/llama3' },
          { key: 'LLM_LAB_ENABLED', value: 'true' },
        ]}
        providers={PROVIDERS}
        maskToken="******"
        onValidityChange={onValidityChange}
      />,
    );

    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(true));
  });

  it('shows provider identity plus independent enabled and untested states', () => {
    render(<LLMChannelEditor items={OPENAI_ITEMS} providers={PROVIDERS} maskToken="******" />);
    const card = connectionCard();
    expect(within(card).getByTestId('provider-avatar-openai')).toHaveTextContent('O');
    expect(within(card).getByText('已启用')).toBeInTheDocument();
    expect(within(card).getByText('未测试')).toBeInTheDocument();
  });

  it('keeps native connection actions on 44px targets with a compact switch visual', () => {
    render(<LLMChannelEditor items={OPENAI_ITEMS} providers={PROVIDERS} maskToken="******" />);

    const card = connectionCard();
    expect(within(card).getByRole('button', { name: '管理模型 openai' })).toHaveClass('min-h-11', 'min-w-11');
    const menu = openConnectionMenu();
    for (const menuItem of within(menu).getAllByRole('menuitem')) {
      expect(menuItem).toHaveClass('min-h-11');
    }

    const dialog = editConnection();
    expect(within(dialog).getByRole('button', { name: '移除模型 gpt-4o-mini' })).toHaveClass('h-11', 'w-11');
    expect(within(dialog).getByRole('button', { name: /手动添加模型/ })).toHaveClass('min-h-11', 'min-w-11');
    const enabledSwitch = within(dialog).getByRole('switch', { name: '启用此连接' });
    expect(enabledSwitch).toHaveClass('h-11', 'w-11');
    expect(within(dialog).getByTestId('connection-enabled-switch-visual')).toHaveClass('h-6', 'w-10');
  });

  it('keeps stable connection identity when its display name changes', async () => {
    const onDraftItemsChange = vi.fn();
    const renamedItems = OPENAI_ITEMS.map((item) => ({
      ...item,
      key: item.key.replace('LLM_OPENAI_', 'LLM_PRODUCTION_'),
      value: item.key === 'LLM_CHANNELS' ? 'production' : item.value,
    }));
    render(
      <LLMChannelEditor
        items={renamedItems}
        providers={PROVIDERS}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    expect(connectionCard('production')).toHaveTextContent('OpenAI 官方');
    const dialog = editConnection('production');
    fireEvent.change(within(dialog).getByLabelText('连接名称'), { target: { value: 'research' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '保存修改' }));

    await waitFor(() => {
      const draft = lastDraft(onDraftItemsChange);
      expect(draft).toContainEqual({ key: 'LLM_PRODUCTION_DISPLAY_NAME', value: 'research' });
      expect(draft).toContainEqual({ key: 'LLM_PRODUCTION_PROVIDER', value: 'openai' });
      expect(draft).not.toContainEqual({ key: 'LLM_RESEARCH_PROVIDER', value: 'openai' });
    });
    expect(connectionCard('production')).toHaveTextContent('OpenAI 官方');
    expect(connectionCard('production')).toHaveTextContent('research');
  });

  it('preserves an explicitly empty display name for contract validation', async () => {
    const onValidityChange = vi.fn();
    render(
      <LLMChannelEditor
        items={[
          ...OPENAI_ITEMS,
          { key: 'LLM_OPENAI_DISPLAY_NAME', value: '' },
        ]}
        providers={PROVIDERS}
        maskToken="******"
        onValidityChange={onValidityChange}
      />,
    );

    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(false));
    const dialog = editConnection();
    const displayNameInput = within(dialog).getByLabelText('连接名称');
    expect(displayNameInput).toHaveValue('');
    expect(displayNameInput).toHaveAccessibleDescription('连接名称必填');
    expect(within(dialog).getByRole('button', { name: '保存修改' })).toBeDisabled();
  });

  it('reports one stable empty draft while the saved connection is unchanged', async () => {
    const onDraftItemsChange = vi.fn();
    const { rerender } = render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );
    await waitFor(() => expect(onDraftItemsChange).toHaveBeenCalledWith([]));
    rerender(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );
    expect(onDraftItemsChange).toHaveBeenCalledTimes(1);
  });

  it('confirms before deleting an unreferenced connection', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    fireEvent.click(within(openConnectionMenu()).getByRole('menuitem', { name: '删除连接' }));
    const dialog = screen.getByRole('dialog', { name: '删除连接？' });
    expect(connectionCard()).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: '删除连接' }));

    await waitFor(() => expect(screen.queryByTestId('connection-card-openai')).not.toBeInTheDocument());
    expect(lastDraft(onDraftItemsChange)).toContainEqual({ key: 'LLM_CHANNELS', value: '' });
  });

  it('blocks deletion when a task still references the connection', () => {
    const onManageModels = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        maskToken="******"
        taskModelRefs={[{ label: '报告主要模型', route: 'openai/gpt-4o-mini' }]}
        onManageModels={onManageModels}
      />,
    );

    fireEvent.click(within(openConnectionMenu()).getByRole('menuitem', { name: '删除连接' }));
    const dialog = screen.getByRole('dialog', { name: '无法直接删除连接' });
    expect(dialog).toHaveTextContent('报告主要模型');
    expect(within(dialog).queryByRole('button', { name: '删除连接' })).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: '前往任务路由替换' }));
    expect(onManageModels).toHaveBeenCalledTimes(1);
    expect(connectionCard()).toBeInTheDocument();
  });

  it('blocks deleting one model in the modal and lists every task reference', () => {
    const onManageModels = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        maskToken="******"
        taskModelRefs={[
          { key: 'LITELLM_MODEL', label: '报告主要模型', route: 'openai/gpt-4o-mini' },
          { key: 'LITELLM_FALLBACK_MODELS', label: '备用模型', route: 'openai/gpt-4o-mini' },
        ]}
        onManageModels={onManageModels}
      />,
    );

    const dialog = editConnection();
    fireEvent.click(within(dialog).getByRole('button', { name: '移除模型 gpt-4o-mini' }));
    expect(within(dialog).getByText('无法直接删除模型')).toBeInTheDocument();
    expect(within(dialog).getByText(/报告主要模型/)).toBeInTheDocument();
    expect(within(dialog).getByText(/备用模型/)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: '移除模型 gpt-4o-mini' })).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: '前往任务路由' }));
    expect(onManageModels).toHaveBeenCalledTimes(1);
  });

  it('normalizes a historical bare Agent model before protecting its route', () => {
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        maskToken="******"
        taskModelRefs={[
          { key: 'AGENT_LITELLM_MODEL', label: 'Agent', route: 'gpt-4o-mini' },
        ]}
      />,
    );

    const dialog = editConnection();
    fireEvent.click(within(dialog).getByRole('button', { name: '移除模型 gpt-4o-mini' }));

    expect(within(dialog).getByText('无法直接删除模型')).toBeInTheDocument();
    expect(within(dialog).getByText('Agent')).toBeInTheDocument();
  });

  it('requires confirmation for an ambiguous legacy route before removing either owner', () => {
    const items = [
      { key: 'LLM_CHANNELS', value: 'openai,backup' },
      ...OPENAI_ITEMS.filter((item) => item.key !== 'LLM_CHANNELS' && item.key !== 'LITELLM_MODEL'),
      { key: 'LLM_BACKUP_PROVIDER', value: 'openai' },
      { key: 'LLM_BACKUP_PROTOCOL', value: 'openai' },
      { key: 'LLM_BACKUP_BASE_URL', value: 'https://api.openai.com/v1' },
      { key: 'LLM_BACKUP_ENABLED', value: 'true' },
      { key: 'LLM_BACKUP_API_KEY', value: 'backup-key' },
      { key: 'LLM_BACKUP_MODELS', value: 'gpt-4o-mini' },
      { key: 'LITELLM_MODEL', value: 'openai/gpt-4o-mini' },
    ];
    render(
      <LLMChannelEditor
        items={items}
        providers={PROVIDERS}
        maskToken="******"
        taskModelRefs={[
          { key: 'LITELLM_MODEL', label: '报告主要模型', route: 'openai/gpt-4o-mini' },
        ]}
      />,
    );

    const dialog = editConnection('openai');
    fireEvent.click(within(dialog).getByRole('button', { name: '移除模型 gpt-4o-mini' }));

    expect(within(dialog).getByText('无法直接删除模型')).toBeInTheDocument();
    expect(within(dialog).getByText('报告主要模型')).toBeInTheDocument();
  });

  it('allows deleting a same-name model only from the unreferenced Connection', () => {
    const items = [
      { key: 'LLM_CHANNELS', value: 'openai,backup' },
      ...OPENAI_ITEMS.filter((item) => item.key !== 'LLM_CHANNELS' && item.key !== 'LITELLM_MODEL'),
      { key: 'LLM_BACKUP_PROVIDER', value: 'openai' },
      { key: 'LLM_BACKUP_PROTOCOL', value: 'openai' },
      { key: 'LLM_BACKUP_BASE_URL', value: 'https://backup.example/v1' },
      { key: 'LLM_BACKUP_ENABLED', value: 'true' },
      { key: 'LLM_BACKUP_API_KEY', value: 'backup-key' },
      { key: 'LLM_BACKUP_MODELS', value: 'gpt-4o-mini' },
    ];
    const availableModels = [
      {
        modelRef: 'modelref:v1:openai:openai%2Fgpt-4o-mini',
        route: 'openai/gpt-4o-mini',
        display: 'gpt-4o-mini',
        connection: 'openai',
        connectionId: 'openai',
        connectionName: 'Personal',
        provider: 'openai',
        providerId: 'openai',
        providerLabel: 'OpenAI',
        available: true,
      },
      {
        modelRef: 'modelref:v1:backup:openai%2Fgpt-4o-mini',
        route: 'openai/gpt-4o-mini',
        display: 'gpt-4o-mini',
        connection: 'backup',
        connectionId: 'backup',
        connectionName: 'Work',
        provider: 'openai',
        providerId: 'openai',
        providerLabel: 'OpenAI',
        available: true,
      },
    ];
    render(
      <LLMChannelEditor
        items={items}
        providers={PROVIDERS}
        availableModels={availableModels}
        availableModelRoutes={availableModels.map((entry) => entry.route)}
        maskToken="******"
        taskModelRefs={[{
          key: 'LITELLM_MODEL',
          label: '报告主要模型',
          route: availableModels[0].modelRef,
        }]}
      />,
    );

    const backupDialog = editConnection('backup');
    fireEvent.click(within(backupDialog).getByRole('button', { name: '移除模型 gpt-4o-mini' }));
    expect(within(backupDialog).queryByText('无法直接删除模型')).not.toBeInTheDocument();
    expect(within(backupDialog).queryByRole('button', { name: '移除模型 gpt-4o-mini' })).not.toBeInTheDocument();
  });

  it('replaces task references and removes the model in the same page draft', () => {
    const onReplaceModelReferences = vi.fn();
    const items = OPENAI_ITEMS.map((item) => (
      item.key === 'LLM_OPENAI_MODELS' ? { ...item, value: 'gpt-4o-mini,gpt-5.5' } : item
    ));
    render(
      <LLMChannelEditor
        items={items}
        providers={PROVIDERS}
        maskToken="******"
        taskModelRefs={[{ key: 'LITELLM_MODEL', label: '报告主要模型', route: 'openai/gpt-4o-mini' }]}
        onReplaceModelReferences={onReplaceModelReferences}
      />,
    );

    const dialog = editConnection();
    fireEvent.click(within(dialog).getByRole('button', { name: '移除模型 gpt-4o-mini' }));
    const replacement = within(dialog).getByRole('button', { name: '替代模型' });
    fireEvent.click(replacement);
    fireEvent.click(within(dialog).getByRole('option', { name: /gpt-5.5/ }));
    fireEvent.click(within(dialog).getByRole('button', { name: '替换引用并删除' }));

    expect(onReplaceModelReferences).not.toHaveBeenCalled();
    expect(within(dialog).queryByRole('button', { name: '移除模型 gpt-4o-mini' })).not.toBeInTheDocument();
    expect(within(dialog).getAllByRole('button', { name: '移除模型 gpt-5.5' }).length).toBeGreaterThan(0);

    fireEvent.click(within(dialog).getByRole('button', { name: '保存修改' }));
    expect(onReplaceModelReferences).toHaveBeenCalledWith([{
      fromRoute: 'openai/gpt-4o-mini',
      toRoute: 'modelref:v1:openai:openai%2Fgpt-5.5',
      references: [{ key: 'LITELLM_MODEL', label: '报告主要模型', route: 'openai/gpt-4o-mini' }],
    }]);
  });

  it('discards a staged reference replacement and model deletion when the modal is cancelled', async () => {
    const onReplaceModelReferences = vi.fn();
    const onDraftItemsChange = vi.fn();
    const items = OPENAI_ITEMS.map((item) => (
      item.key === 'LLM_OPENAI_MODELS' ? { ...item, value: 'gpt-4o-mini,gpt-5.5' } : item
    ));
    render(
      <LLMChannelEditor
        items={items}
        providers={PROVIDERS}
        maskToken="******"
        taskModelRefs={[{ key: 'LITELLM_MODEL', label: '报告主要模型', route: 'openai/gpt-4o-mini' }]}
        onReplaceModelReferences={onReplaceModelReferences}
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    await waitFor(() => expect(onDraftItemsChange).toHaveBeenCalledWith([]));

    let dialog = editConnection();
    fireEvent.click(within(dialog).getByRole('button', { name: '移除模型 gpt-4o-mini' }));
    fireEvent.click(within(dialog).getByRole('button', { name: '替代模型' }));
    fireEvent.click(within(dialog).getByRole('option', { name: /gpt-5.5/ }));
    fireEvent.click(within(dialog).getByRole('button', { name: '替换引用并删除' }));
    fireEvent.click(within(dialog).getByRole('button', { name: '取消' }));

    expect(onReplaceModelReferences).not.toHaveBeenCalled();
    expect(lastDraft(onDraftItemsChange)).toEqual([]);
    dialog = editConnection();
    expect(within(dialog).getByRole('button', { name: '移除模型 gpt-4o-mini' })).toBeInTheDocument();
  });

  it('flushes multiple staged replacements as one batch only when modal changes are saved', () => {
    const onReplaceModelReferences = vi.fn();
    const items = OPENAI_ITEMS.map((item) => (
      item.key === 'LLM_OPENAI_MODELS'
        ? { ...item, value: 'gpt-4o-mini,gpt-4.1-mini,gpt-5.5' }
        : item
    ));
    render(
      <LLMChannelEditor
        items={items}
        providers={PROVIDERS}
        maskToken="******"
        taskModelRefs={[
          { key: 'LITELLM_MODEL', label: '报告主要模型', route: 'openai/gpt-4o-mini' },
          { key: 'LITELLM_FALLBACK_MODELS', label: '备用模型', route: 'openai/gpt-4.1-mini' },
        ]}
        onReplaceModelReferences={onReplaceModelReferences}
      />,
    );

    const dialog = editConnection();
    for (const model of ['gpt-4o-mini', 'gpt-4.1-mini']) {
      fireEvent.click(within(dialog).getByRole('button', { name: `移除模型 ${model}` }));
      fireEvent.click(within(dialog).getByRole('button', { name: '替代模型' }));
      fireEvent.click(within(dialog).getByRole('option', { name: /gpt-5.5/ }));
      fireEvent.click(within(dialog).getByRole('button', { name: '替换引用并删除' }));
    }

    expect(onReplaceModelReferences).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole('button', { name: '保存修改' }));
    expect(onReplaceModelReferences).toHaveBeenCalledTimes(1);
    expect(onReplaceModelReferences.mock.calls[0]?.[0]).toHaveLength(2);
  });

  it('opens and focuses the requested dynamic connection field through the editor signal', async () => {
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        maskToken="******"
        focusFieldRequest={{ requestId: 1, key: 'LLM_OPENAI_API_KEY' }}
      />,
    );

    const dialog = await screen.findByRole('dialog', { name: '编辑模型服务' });
    await waitFor(() => expect(within(dialog).getByLabelText('API 密钥')).toHaveFocus());
  });

  it('focuses an editable Provider recovery control and drafts the selected Catalog identity', async () => {
    const onDraftItemsChange = vi.fn();
    const items = OPENAI_ITEMS.map((item) => (
      item.key === 'LLM_OPENAI_PROVIDER' ? { ...item, value: 'missing-provider' } : item
    ));
    render(
      <LLMChannelEditor
        items={items}
        providers={PROVIDERS}
        maskToken="******"
        focusFieldRequest={{ requestId: 1, key: 'LLM_OPENAI_PROVIDER' }}
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    const dialog = await screen.findByRole('dialog', { name: '编辑模型服务' });
    await waitFor(() => expect(within(dialog).getByLabelText('选择模型服务商')).toHaveFocus());
    selectProvider('openai');
    fireEvent.click(within(dialog).getByRole('button', { name: '保存修改' }));
    await waitFor(() => expect(lastDraft(onDraftItemsChange)).toContainEqual({
      key: 'LLM_OPENAI_PROVIDER',
      value: 'openai',
    }));
  });

  it('reveals and focuses the authoritative protocol recovery control for an official Provider', async () => {
    const onDraftItemsChange = vi.fn();
    const items = OPENAI_ITEMS.map((item) => (
      item.key === 'LLM_OPENAI_PROTOCOL' ? { ...item, value: 'deepseek' } : item
    ));
    render(
      <LLMChannelEditor
        items={items}
        providers={PROVIDERS}
        maskToken="******"
        focusFieldRequest={{ requestId: 1, key: 'LLM_OPENAI_PROTOCOL' }}
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    const dialog = await screen.findByRole('dialog', { name: '编辑模型服务' });
    const protocol = within(dialog).getByLabelText('协议');
    await waitFor(() => expect(protocol).toHaveFocus());
    fireEvent.click(protocol);
    fireEvent.click(screen.getByRole('option', { name: 'OpenAI' }));
    fireEvent.click(within(dialog).getByRole('button', { name: '保存修改' }));
    await waitFor(() => expect(lastDraft(onDraftItemsChange)).toContainEqual({
      key: 'LLM_OPENAI_PROTOCOL',
      value: 'openai',
    }));
  });

  it('reveals and focuses Extra Headers so a backend field error can be corrected', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={[...OPENAI_ITEMS, { key: 'LLM_OPENAI_EXTRA_HEADERS', value: '{invalid' }]}
        providers={PROVIDERS}
        maskToken="******"
        focusFieldRequest={{ requestId: 1, key: 'LLM_OPENAI_EXTRA_HEADERS' }}
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    const dialog = await screen.findByRole('dialog', { name: '编辑模型服务' });
    const extraHeaders = within(dialog).getByLabelText('附加请求头（JSON）');
    await waitFor(() => expect(extraHeaders).toHaveFocus());
    fireEvent.change(extraHeaders, { target: { value: '' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '保存修改' }));
    await waitFor(() => expect(lastDraft(onDraftItemsChange)).toContainEqual({
      key: 'LLM_OPENAI_EXTRA_HEADERS',
      value: '',
    }));
  });

  it('edits credentials and models only inside the modal and emits the unified draft', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    const dialog = editConnection();
    fireEvent.change(within(dialog).getByLabelText('API 密钥'), { target: { value: 'new-secret' } });
    replaceModels(['gpt-5.5', 'gpt-5.4-mini']);
    fireEvent.click(within(dialog).getByRole('button', { name: '保存修改' }));

    expect(connectionCard()).toHaveTextContent('未保存');
    expect(connectionCard()).toHaveTextContent('gpt-5.5');
    await waitFor(() => {
      const draft = lastDraft(onDraftItemsChange);
      expect(draft).toContainEqual({ key: 'LLM_OPENAI_API_KEY', value: 'new-secret' });
      expect(draft).toContainEqual({ key: 'LLM_OPENAI_MODELS', value: 'gpt-5.5,gpt-5.4-mini' });
    });
  });

  it('does not submit an unchanged masked secret when only models change', async () => {
    const onDraftItemsChange = vi.fn();
    const maskedItems = OPENAI_ITEMS.map((item) => (
      item.key === 'LLM_OPENAI_API_KEY'
        ? { ...item, value: '******', rawValueExists: true }
        : item
    ));
    render(
      <LLMChannelEditor
        items={maskedItems}
        providers={PROVIDERS}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    const dialog = editConnection();
    replaceModels(['gpt-5.5']);
    fireEvent.click(within(dialog).getByRole('button', { name: '保存修改' }));

    await waitFor(() => {
      const draft = lastDraft(onDraftItemsChange);
      expect(draft).toContainEqual({ key: 'LLM_OPENAI_MODELS', value: 'gpt-5.5' });
      expect(draft).not.toContainEqual(expect.objectContaining({ key: 'LLM_OPENAI_API_KEY' }));
    });
  });

  it('returns to an empty draft when an edit is restored to the saved value', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    let dialog = editConnection();
    replaceModels(['gpt-5.5']);
    fireEvent.click(within(dialog).getByRole('button', { name: '保存修改' }));
    await waitFor(() => expect(lastDraft(onDraftItemsChange)).not.toEqual([]));

    dialog = editConnection();
    replaceModels(['gpt-4o-mini']);
    fireEvent.click(within(dialog).getByRole('button', { name: '保存修改' }));
    await waitFor(() => expect(lastDraft(onDraftItemsChange)).toEqual([]));
  });

  it('does not emit invalid env keys while the connection name is empty', () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );
    const dialog = editConnection();
    fireEvent.change(within(dialog).getByLabelText('连接名称'), { target: { value: '' } });
    expect(within(dialog).getByRole('button', { name: '保存修改' })).toBeDisabled();
    expect(lastDraft(onDraftItemsChange)).toEqual([]);
  });

  it('keeps the API key masked until the user requests visibility', () => {
    const dialog = editConnectionAfterRender();
    const input = within(dialog).getByLabelText('API 密钥');
    expect(input).toHaveAttribute('type', 'password');
    fireEvent.click(within(dialog).getByRole('button', { name: '显示内容' }));
    expect(input).toHaveAttribute('type', 'text');
  });

  function editConnectionAfterRender(): HTMLElement {
    render(<LLMChannelEditor items={OPENAI_ITEMS} providers={PROVIDERS} maskToken="******" />);
    return editConnection();
  }

  it('opens the provider picker in a modal and includes custom as a first-class option', () => {
    const dialog = openAddAfterRender();
    const trigger = within(dialog).getByLabelText('选择模型服务商');
    fireEvent.click(trigger);
    const listbox = screen.getByRole('listbox');
    expect(within(listbox).getByRole('option', { name: /OpenAI 官方.*云端模型服务/ })).toBeInTheDocument();
    expect(within(listbox).getByRole('option', { name: /自定义兼容服务.*自定义模型服务/ })).toBeInTheDocument();
  });

  it('offers only providers returned by the backend catalog', () => {
    const dialog = openAddAfterRender({ providers: PROVIDERS.filter((entry) => entry.id !== 'custom') });
    const trigger = within(dialog).getByLabelText('选择模型服务商');
    fireEvent.click(trigger);
    expect(within(screen.getByRole('listbox')).queryByRole('option', { name: /自定义服务/ })).not.toBeInTheDocument();
  });

  it('waits for an explicit Next action after provider selection', () => {
    const dialog = openAddAfterRender();
    const trigger = within(dialog).getByLabelText('选择模型服务商');
    fireEvent.click(trigger);
    fireEvent.click(within(screen.getByRole('listbox')).getByRole('option', { name: /OpenAI 官方/ }));

    expect(within(dialog).getByLabelText('选择模型服务商')).toBeInTheDocument();
    expect(within(dialog).queryByLabelText('连接名称')).not.toBeInTheDocument();
    const next = within(dialog).getByRole('button', { name: '下一步' });
    expect(next).toBeEnabled();
    fireEvent.click(next);
    expect(within(dialog).getByLabelText('连接名称')).toBeInTheDocument();
  });

  function openAddAfterRender(props: Partial<React.ComponentProps<typeof LLMChannelEditor>> = {}): HTMLElement {
    const { rerender } = render(
      <LLMChannelEditor
        items={[]}
        providers={PROVIDERS}
        maskToken="******"
        {...props}
        addSignal={0}
      />,
    );
    rerender(
      <LLMChannelEditor
        items={[]}
        providers={PROVIDERS}
        maskToken="******"
        {...props}
        addSignal={1}
      />,
    );
    return screen.getByRole('dialog', { name: '添加模型服务' });
  }

  it('uses official protocol and endpoint defaults without seeding or exposing them', () => {
    const dialog = openAddAfterRender();
    selectProvider('deepseek');
    expect(within(dialog).queryByLabelText('协议')).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText('服务地址')).not.toBeInTheDocument();
    expect(within(dialog).getByText('使用服务商官方地址')).toBeInTheDocument();
    expect(within(dialog).queryAllByRole('button', { name: /^移除模型 / })).toHaveLength(0);
    expect(within(dialog).getByRole('button', { name: '添加到配置' })).toBeDisabled();
  });

  it('returns to provider selection with the same modal when Back is pressed', () => {
    const dialog = openAddAfterRender();
    selectProvider('openai');
    fireEvent.click(within(dialog).getByRole('button', { name: '上一步' }));
    expect(within(dialog).getByLabelText('选择模型服务商')).toBeInTheDocument();
    expect(screen.getAllByRole('dialog', { name: '添加模型服务' })).toHaveLength(1);
  });

  it('adds an official connection to the parent draft without calling a save API', async () => {
    const onDraftItemsChange = vi.fn();
    const dialog = openAddAfterRender({ onDraftItemsChange });
    selectProvider('openai');
    fireEvent.change(within(dialog).getByLabelText('API 密钥'), { target: { value: 'sk-test' } });
    addManualModels(['gpt-5.5']);
    fireEvent.click(within(dialog).getByRole('button', { name: '添加到配置' }));

    expect(connectionCard()).toHaveTextContent('未保存');
    await waitFor(() => {
      const draft = lastDraft(onDraftItemsChange);
      expect(draft).toContainEqual({ key: 'LLM_CHANNELS', value: 'openai' });
      expect(draft).toContainEqual({ key: 'LLM_OPENAI_PROTOCOL', value: 'openai' });
      expect(draft).toContainEqual({ key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' });
      expect(draft).toContainEqual({ key: 'LLM_OPENAI_MODELS', value: 'gpt-5.5' });
    });
  });

  it('uses a stable unique id separately from the editable display name', () => {
    const { rerender } = render(
      <LLMChannelEditor items={OPENAI_ITEMS} providers={PROVIDERS} maskToken="******" addSignal={0} />,
    );
    rerender(
      <LLMChannelEditor items={OPENAI_ITEMS} providers={PROVIDERS} maskToken="******" addSignal={1} />,
    );
    selectProvider('openai');
    expect(screen.getByLabelText('连接名称')).toHaveValue('OpenAI 官方');
    expect(screen.getByLabelText('连接名称').closest('[data-connection-id]')).toHaveAttribute('data-connection-id', 'openai2');
  });

  it('shows protocol and service address controls only for custom services', () => {
    const dialog = openAddAfterRender();
    selectProvider('custom');
    expect(within(dialog).getByLabelText('协议')).toHaveAttribute('role', 'combobox');
    expect(within(dialog).getByLabelText('服务地址')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('API 密钥')).toBeInTheDocument();
  });

  it('derives custom protocol options from the Provider Catalog and preserves the current value', () => {
    const items = [
      { key: 'LLM_CHANNELS', value: 'local_custom' },
      { key: 'LLM_LOCAL_CUSTOM_PROVIDER', value: 'custom' },
      { key: 'LLM_LOCAL_CUSTOM_PROTOCOL', value: 'ollama' },
      { key: 'LLM_LOCAL_CUSTOM_BASE_URL', value: 'http://localhost:11434' },
      { key: 'LLM_LOCAL_CUSTOM_ENABLED', value: 'true' },
      { key: 'LLM_LOCAL_CUSTOM_API_KEY', value: '' },
      { key: 'LLM_LOCAL_CUSTOM_MODELS', value: 'qwen3:8b' },
    ];
    render(
      <LLMChannelEditor
        items={items}
        providers={PROVIDERS.filter((entry) => ['custom', 'anthropic'].includes(entry.id))}
        emptyApiKeyHosts={['localhost']}
        maskToken="******"
      />,
    );

    const dialog = editConnection('local_custom');
    fireEvent.click(within(dialog).getByLabelText('协议'));
    const values = screen.getAllByRole('option').map((option) => option.getAttribute('data-value'));
    expect(values).toEqual(['anthropic', 'openai', 'ollama']);
    expect(values).not.toContain('deepseek');
    expect(values).not.toContain('gemini');
  });

  it('allows Ollama discovery and drafts without an API key', async () => {
    const onDraftItemsChange = vi.fn();
    const dialog = openAddAfterRender({ onDraftItemsChange });
    selectProvider('ollama');
    expect(within(dialog).queryByLabelText('API 密钥')).not.toBeInTheDocument();
    addManualModels(['qwen3:8b']);
    expect(within(dialog).getByRole('button', { name: '添加到配置' })).toBeEnabled();
    fireEvent.click(within(dialog).getByRole('button', { name: '添加到配置' }));
    await waitFor(() => {
      expect(lastDraft(onDraftItemsChange)).toContainEqual({ key: 'LLM_OLLAMA_API_KEY', value: '' });
    });
  });

  it('uses supportsDiscovery to offer manual model entry instead of an unsupported action', () => {
    const dialog = openAddAfterRender();
    selectProvider('anthropic');
    expect(within(dialog).queryByRole('button', { name: '获取模型' })).not.toBeInTheDocument();
    expect(within(dialog).getByText('该服务暂不支持自动获取模型，请在下方手动添加模型 ID。')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('手动添加模型')).toBeInTheDocument();
  });

  it('uses the backend-provided localhost exemption for custom OpenAI-compatible services', () => {
    const dialog = openAddAfterRender({ emptyApiKeyHosts: ['localhost', '127.0.0.1'] });
    selectProvider('custom');
    fireEvent.change(within(dialog).getByLabelText('服务地址'), { target: { value: 'http://localhost:9000/v1' } });
    addManualModels(['local-model']);
    expect(within(dialog).getByLabelText('API 密钥')).toHaveAttribute('placeholder', '本地服务可留空');
    expect(within(dialog).getByRole('button', { name: '添加到配置' })).toBeEnabled();
  });

  it('keeps the schema-owned API Key control visible when a Custom endpoint becomes local', () => {
    const dialog = openAddAfterRender({
      emptyApiKeyHosts: ['localhost', '127.0.0.1'],
      connectionFields: withIdentity([
        { key: 'connection_name', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
        { key: 'display_name', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
        { key: 'provider_id', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
        { key: 'protocol', dataType: 'string', isSensitive: false, isRequired: false, contract: { requirement: 'optional', visibleWhen: [{ key: 'protocol_visible', operator: 'equals', value: 'true' }] } },
        { key: 'base_url', dataType: 'string', isSensitive: false, isRequired: false, contract: { requirement: 'optional', visibleWhen: [{ key: 'base_url_visible', operator: 'equals', value: 'true' }] } },
        { key: 'api_key', dataType: 'string', isSensitive: true, isRequired: false, contract: { requirement: 'optional', requiredWhen: [{ key: 'api_key_required', operator: 'equals', value: 'true' }], visibleWhen: [{ key: 'api_key_visible', operator: 'equals', value: 'true' }] } },
        { key: 'models', dataType: 'array', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
        { key: 'enabled', dataType: 'boolean', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
      ]),
    });
    selectProvider('custom');
    fireEvent.change(within(dialog).getByLabelText('服务地址'), {
      target: { value: 'http://localhost:9000/v1' },
    });

    expect(within(dialog).getByLabelText('API 密钥（可选）'))
      .toHaveAttribute('placeholder', '本地服务可留空');
  });

  it('requires a key and service address for a remote custom enabled connection', () => {
    const dialog = openAddAfterRender();
    selectProvider('custom');
    addManualModels(['remote-model']);
    expect(within(dialog).getAllByText('缺少 API 密钥').length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText('缺少服务地址').length).toBeGreaterThan(0);
    expect(within(dialog).getByRole('button', { name: '添加到配置' })).toBeDisabled();
  });

  it('associates connection field errors with their inputs', () => {
    const dialog = openAddAfterRender();
    selectProvider('custom');
    for (const label of ['API 密钥', '服务地址']) {
      const input = within(dialog).getByLabelText(label);
      expect(input).toHaveAttribute('aria-invalid', 'true');
      const describedBy = input.getAttribute('aria-describedby');
      expect(describedBy).toBeTruthy();
      expect(document.getElementById(describedBy!)).toBeInTheDocument();
    }
  });

  it('allows an incomplete connection to be added only as a disabled draft', async () => {
    const onDraftItemsChange = vi.fn();
    const onValidityChange = vi.fn();
    const dialog = openAddAfterRender({ onDraftItemsChange, onValidityChange });
    selectProvider('custom');
    fireEvent.click(within(dialog).getByRole('switch', { name: '启用此连接' }));
    expect(within(dialog).getByRole('button', { name: '添加到配置' })).toBeEnabled();
    fireEvent.click(within(dialog).getByRole('button', { name: '添加到配置' }));
    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(true));
    expect(connectionCard('custom')).toHaveTextContent('草稿 · 未完成');
    expect(connectionCard('custom')).toHaveTextContent('已停用');
    expect(connectionCard('custom')).toHaveTextContent('未测试');
    expect(lastDraft(onDraftItemsChange)).toContainEqual({ key: 'LLM_CUSTOM_ENABLED', value: 'false' });
  });

  it('keeps existing connections visible when the provider catalog fails', () => {
    const onReloadCatalog = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={[]}
        maskToken="******"
        catalogUnavailable
        onReloadCatalog={onReloadCatalog}
      />,
    );
    expect(connectionCard()).toBeInTheDocument();
    expect(screen.getByText('模型服务列表加载失败')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(onReloadCatalog).toHaveBeenCalledTimes(1);
  });

  it.each(['gemini', 'anthropic'] as const)(
    'preserves an explicit %s Provider and blank official Base URL during an initial catalog outage',
    async (providerId) => {
      const onValidityChange = vi.fn();
      render(
        <LLMChannelEditor
          items={officialItemsWithoutBaseUrl(providerId)}
          providers={[]}
          maskToken="******"
          catalogUnavailable
          onValidityChange={onValidityChange}
        />,
      );

      const card = connectionCard(providerId);
      expect(card).toHaveTextContent(providerId);
      expect(card).not.toHaveTextContent('草稿 · 未完成');
      await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(false));
      expect(within(card).getByRole('button', { name: '测试' })).toBeDisabled();
      expect(within(card).getByRole('button', { name: '编辑' })).toBeDisabled();
    },
  );

  it('keeps a failed-catalog empty state passive and ignores the page add signal', () => {
    const { rerender } = render(
      <LLMChannelEditor
        items={[]}
        providers={[]}
        maskToken="******"
        catalogUnavailable
        addSignal={0}
      />,
    );
    rerender(
      <LLMChannelEditor
        items={[]}
        providers={[]}
        maskToken="******"
        catalogUnavailable
        addSignal={1}
      />,
    );
    expect(screen.queryByRole('button', { name: /添加模型服务/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '添加模型服务' })).not.toBeInTheDocument();
    expect(screen.getByText('模型服务列表加载失败')).toBeInTheDocument();
  });

  it('renders a concise read-only notice for externally managed model config', () => {
    const onViewDiagnostics = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        maskToken="******"
        overriddenByMode="yaml"
        onViewDiagnostics={onViewDiagnostics}
      />,
    );
    expect(screen.getByText('当前模型配置由外部配置管理，网页暂时只读。')).toBeInTheDocument();
    expect(within(connectionCard()).getByRole('button', { name: '编辑' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '查看详情' }));
    expect(onViewDiagnostics).toHaveBeenCalledTimes(1);
  });

  it('does not auto-select models returned by discovery', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: true,
      message: 'ok',
      models: ['gpt-5.5', 'gpt-5.4-mini'],
      latencyMs: 12,
    });
    const dialog = editConnectionAfterRender();
    fireEvent.click(within(dialog).getByRole('button', { name: '获取模型' }));
    await within(dialog).findByText('已获取 2 个模型 · 12 ms');
    expect(within(dialog).getByText('已选 0 / 2')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: '保存修改' })).toBeEnabled();
  });

  it('searches and explicitly selects discovered models', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: true,
      message: 'ok',
      models: ['gpt-5.5', 'gpt-5.4-mini'],
    });
    const dialog = editConnectionAfterRender();
    replaceModels([]);
    fireEvent.click(within(dialog).getByRole('button', { name: '获取模型' }));
    await within(dialog).findByTestId('model-multi-select');
    fireEvent.click(within(dialog).getByRole('button', { name: '选择模型' }));
    fireEvent.change(within(dialog).getByLabelText('搜索模型'), { target: { value: '5.5' } });
    expect(within(dialog).queryByText('gpt-5.4-mini')).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('checkbox', { name: 'gpt-5.5' }));
    expect(within(dialog).getAllByRole('button', { name: '移除模型 gpt-5.5' }).length).toBeGreaterThan(0);
  });

  it('distinguishes an empty discovery result from a request error', async () => {
    discoverLLMChannelModels.mockResolvedValue({ success: true, message: 'ok', models: [] });
    const dialog = editConnectionAfterRender();
    fireEvent.click(within(dialog).getByRole('button', { name: '获取模型' }));
    expect(await within(dialog).findByText('服务已连通，但没有返回可用模型')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /手动添加模型/ })).toBeInTheDocument();
  });

  it('keeps manual model entry available when discovery fails', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: false,
      message: 'unauthorized',
      errorCode: 'auth',
      stage: 'model_discovery',
      details: { reason: 'api_key_rejected' },
      models: [],
    });
    const dialog = editConnectionAfterRender();
    fireEvent.click(within(dialog).getByRole('button', { name: '获取模型' }));
    expect(await within(dialog).findByText(/模型发现 · 鉴权失败/)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /手动添加模型/ })).toBeInTheDocument();
  });

  it('splits pasted model lists, trims, deduplicates, and removes one token', () => {
    const dialog = editConnectionAfterRender();
    replaceModels([]);
    const input = within(dialog).getByLabelText('手动添加模型');
    fireEvent.paste(input, {
      clipboardData: { getData: () => 'gpt-5.5, gpt-5.5\ngpt-5.4-mini' },
    });
    expect(within(dialog).getAllByRole('button', { name: /^移除模型 / })).toHaveLength(2);
    fireEvent.click(within(dialog).getByRole('button', { name: '移除模型 gpt-5.5' }));
    expect(within(dialog).queryByRole('button', { name: '移除模型 gpt-5.5' })).not.toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: '移除模型 gpt-5.4-mini' })).toBeInTheDocument();
  });

  it('runs a basic connection test without capability-check parameters', async () => {
    testLLMChannel.mockResolvedValue({
      success: true,
      message: 'ok',
      resolvedModel: 'openai/gpt-4o-mini',
      latencyMs: 21,
    });
    const dialog = editConnectionAfterRender();
    fireEvent.click(within(dialog).getByRole('button', { name: '测试连接' }));
    expect(await within(dialog).findByText('连接成功 · openai/gpt-4o-mini · 21 ms')).toBeInTheDocument();
    expect(testLLMChannel).toHaveBeenCalledWith(expect.not.objectContaining({ capabilityChecks: expect.anything() }));
  });

  it('shows focused authentication troubleshooting without closing the modal', async () => {
    testLLMChannel.mockResolvedValue({
      success: false,
      message: 'unauthorized',
      errorCode: 'auth',
      stage: 'chat_completion',
      details: { reason: 'api_key_rejected' },
      resolvedModel: 'openai/gpt-4o-mini',
    });
    const dialog = editConnectionAfterRender();
    fireEvent.click(within(dialog).getByRole('button', { name: '测试连接' }));
    expect(await within(dialog).findByText(/服务商拒绝了当前 API 密钥/)).toBeInTheDocument();
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByLabelText('API 密钥')).toHaveValue('secret-key');
  });

  it('discards stale discovery responses after connection parameters change', async () => {
    let resolveDiscovery!: (value: unknown) => void;
    discoverLLMChannelModels.mockReturnValue(new Promise((resolve) => { resolveDiscovery = resolve; }));
    const dialog = editConnectionAfterRender();
    fireEvent.click(within(dialog).getByRole('button', { name: '获取模型' }));
    fireEvent.click(within(dialog).getByRole('button', { name: '使用自定义服务地址' }));
    fireEvent.change(within(dialog).getByLabelText('服务地址'), { target: { value: 'https://proxy.example/v1' } });
    resolveDiscovery({ success: true, message: 'ok', models: ['stale-model'] });
    await waitFor(() => expect(within(dialog).queryByText('stale-model')).not.toBeInTheDocument());
  });

  it('uses a saved secret for card tests but refuses runtime-only masked Hermes secrets', async () => {
    testLLMChannel.mockResolvedValue({ success: true, message: 'ok' });
    const hermesItems = [
      { key: 'LLM_CHANNELS', value: 'hermes' },
      { key: 'LLM_HERMES_PROTOCOL', value: 'openai' },
      { key: 'LLM_HERMES_BASE_URL', value: 'http://localhost:8080/v1' },
      { key: 'LLM_HERMES_ENABLED', value: 'true' },
      { key: 'LLM_HERMES_API_KEY', value: '******', rawValueExists: false },
      { key: 'LLM_HERMES_MODELS', value: 'hermes-agent' },
    ];
    render(
      <LLMChannelEditor
        items={hermesItems}
        providers={PROVIDERS}
        emptyApiKeyHosts={['localhost']}
        maskToken="******"
      />,
    );
    fireEvent.click(within(connectionCard('hermes')).getByRole('button', { name: '测试' }));
    expect(await screen.findByText(/运行时注入的密钥不会显示/)).toBeInTheDocument();
    expect(testLLMChannel).not.toHaveBeenCalled();
  });

  it('resets local modal changes when the parent reset signal changes', () => {
    const { rerender } = render(
      <LLMChannelEditor items={OPENAI_ITEMS} providers={PROVIDERS} maskToken="******" resetSignal={0} />,
    );
    const dialog = editConnection();
    replaceModels(['gpt-5.5']);
    fireEvent.click(within(dialog).getByRole('button', { name: '保存修改' }));
    expect(connectionCard()).toHaveTextContent('gpt-5.5');

    rerender(
      <LLMChannelEditor items={OPENAI_ITEMS} providers={PROVIDERS} maskToken="******" resetSignal={1} />,
    );
    expect(connectionCard()).toHaveTextContent('gpt-4o-mini');
    expect(connectionCard()).not.toHaveTextContent('gpt-5.5');
  });

  it('rehydrates a parent-held channel draft after remount', () => {
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        maskToken="******"
        persistedDraftItems={[{ key: 'LLM_OPENAI_MODELS', value: 'gpt-5.5' }]}
      />,
    );
    expect(connectionCard()).toHaveTextContent('gpt-5.5');
    expect(connectionCard()).toHaveTextContent('未保存');
  });

  it('never emits runtime routing keys from model-access edits', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={OPENAI_ITEMS}
        providers={PROVIDERS}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );
    const dialog = editConnection();
    replaceModels(['gpt-5.5']);
    fireEvent.click(within(dialog).getByRole('button', { name: '保存修改' }));
    await waitFor(() => expect(lastDraft(onDraftItemsChange)).not.toEqual([]));
    const keys = lastDraft(onDraftItemsChange).map((item) => item.key);
    expect(keys).not.toEqual(expect.arrayContaining([
      'LITELLM_MODEL',
      'AGENT_LITELLM_MODEL',
      'VISION_MODEL',
      'LITELLM_FALLBACK_MODELS',
    ]));
  });

  it('prefers runtime API_KEYS when both key variants coexist', () => {
    const items = [
      ...OPENAI_ITEMS.filter((item) => item.key !== 'LLM_OPENAI_API_KEY'),
      { key: 'LLM_OPENAI_API_KEY', value: 'saved-single', rawValueExists: true },
      { key: 'LLM_OPENAI_API_KEYS', value: 'runtime-list', rawValueExists: false },
    ];
    render(<LLMChannelEditor items={items} providers={PROVIDERS} maskToken="******" />);
    const dialog = editConnection();
    expect(within(dialog).getByLabelText('API 密钥')).toHaveValue('runtime-list');
  });

  it('does not surface legacy channel terminology or internal config keys in normal UI', () => {
    const { container } = render(
      <LLMChannelEditor items={OPENAI_ITEMS} providers={PROVIDERS} maskToken="******" />,
    );
    const dialog = editConnection();
    expect(container.textContent).not.toMatch(/渠道|LLM_|LITELLM_|GENERATION_BACKEND|主后端|备用后端/);
    expect(dialog.textContent).not.toMatch(/JSON|Tools|Stream|运行时能力/);
  });
});
