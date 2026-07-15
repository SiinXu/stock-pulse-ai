import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LlmProviderCatalogEntry } from '../../../types/systemConfig';
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
    id: 'custom',
    label: '自定义兼容服务',
    protocol: 'openai',
    requiresBaseUrl: true,
    supportsDiscovery: true,
    isCustom: true,
  }),
];

const OPENAI_ITEMS = [
  { key: 'LLM_CHANNELS', value: 'openai' },
  { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
  { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' },
  { key: 'LLM_OPENAI_ENABLED', value: 'true' },
  { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' },
  { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' },
  { key: 'LITELLM_MODEL', value: 'openai/gpt-4o-mini' },
];

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

function openAddModal(): HTMLElement {
  fireEvent.click(screen.getByRole('button', { name: '+ 添加模型服务' }));
  return screen.getByRole('dialog', { name: '添加模型服务' });
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

describe('LLMChannelEditor', () => {
  beforeEach(() => {
    testLLMChannel.mockReset();
    discoverLLMChannelModels.mockReset();
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
    expect(within(listbox).getByRole('option', { name: /自定义服务.*自定义模型服务/ })).toBeInTheDocument();
  });

  function openAddAfterRender(props: Partial<React.ComponentProps<typeof LLMChannelEditor>> = {}): HTMLElement {
    render(
      <LLMChannelEditor
        items={[]}
        providers={PROVIDERS}
        maskToken="******"
        {...props}
      />,
    );
    return openAddModal();
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

  it('allows multiple connections for one provider and suggests a unique name', () => {
    const { rerender } = render(
      <LLMChannelEditor items={OPENAI_ITEMS} providers={PROVIDERS} maskToken="******" addSignal={0} />,
    );
    rerender(
      <LLMChannelEditor items={OPENAI_ITEMS} providers={PROVIDERS} maskToken="******" addSignal={1} />,
    );
    selectProvider('openai');
    expect(screen.getByLabelText('连接名称')).toHaveValue('openai2');
  });

  it('shows protocol and service address controls only for custom services', () => {
    const dialog = openAddAfterRender();
    selectProvider('custom');
    expect(within(dialog).getByLabelText('协议')).toHaveAttribute('role', 'combobox');
    expect(within(dialog).getByLabelText('服务地址')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('API 密钥')).toBeInTheDocument();
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

  it('uses the backend-provided localhost exemption for custom OpenAI-compatible services', () => {
    const dialog = openAddAfterRender({ emptyApiKeyHosts: ['localhost', '127.0.0.1'] });
    selectProvider('custom');
    fireEvent.change(within(dialog).getByLabelText('服务地址'), { target: { value: 'http://localhost:9000/v1' } });
    addManualModels(['local-model']);
    expect(within(dialog).getByLabelText('API 密钥')).toHaveAttribute('placeholder', '本地服务可留空');
    expect(within(dialog).getByRole('button', { name: '添加到配置' })).toBeEnabled();
  });

  it('requires a key and service address for a remote custom enabled connection', () => {
    const dialog = openAddAfterRender();
    selectProvider('custom');
    addManualModels(['remote-model']);
    expect(within(dialog).getByText('缺少 API 密钥')).toBeInTheDocument();
    expect(within(dialog).getByText('缺少服务地址')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: '添加到配置' })).toBeDisabled();
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

  it('blocks the empty-state add action while the provider catalog is unavailable', () => {
    render(
      <LLMChannelEditor
        items={[]}
        providers={[]}
        maskToken="******"
        catalogUnavailable
      />,
    );
    expect(screen.getByRole('button', { name: '+ 添加模型服务' })).toBeDisabled();
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
    fireEvent.change(within(dialog).getByLabelText('搜索模型'), { target: { value: '5.5' } });
    expect(within(dialog).queryByText('gpt-5.4-mini')).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('checkbox', { name: 'gpt-5.5' }));
    expect(within(dialog).getByRole('button', { name: '移除模型 gpt-5.5' })).toBeInTheDocument();
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
