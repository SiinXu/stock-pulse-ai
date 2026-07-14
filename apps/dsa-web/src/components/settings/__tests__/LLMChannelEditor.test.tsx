import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LLMChannelEditor } from '../LLMChannelEditor';
import type { LlmProviderCatalogEntry } from '../../../types/systemConfig';

// Mirrors the backend provider catalog (GET /system/config/llm/providers); the
// editor sources provider business metadata from this prop.
function provider(overrides: Partial<LlmProviderCatalogEntry> & Pick<LlmProviderCatalogEntry, 'id' | 'label' | 'protocol'>): LlmProviderCatalogEntry {
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

const PROVIDER_CATALOG: LlmProviderCatalogEntry[] = [
  provider({ id: 'aihubmix', label: 'AIHubmix（聚合平台）', protocol: 'openai', defaultBaseUrl: 'https://aihubmix.com/v1', capabilities: ['openai-compatible', 'aggregator'], supportsDiscovery: true }),
  provider({ id: 'anspire', label: 'Anspire Open（一站式模型+搜索）', protocol: 'openai', defaultBaseUrl: 'https://open-gateway.anspire.cn/v6', capabilities: ['openai-compatible'], supportsDiscovery: true }),
  provider({ id: 'deepseek', label: 'DeepSeek 官方', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: ['official-api', 'openai-compatible'], supportsDiscovery: true }),
  provider({ id: 'dashscope', label: '通义千问（Dashscope）', protocol: 'openai', defaultBaseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', capabilities: ['openai-compatible', 'model-discovery'], supportsDiscovery: true }),
  provider({ id: 'zhipu', label: '智谱 GLM', protocol: 'openai', defaultBaseUrl: 'https://open.bigmodel.cn/api/paas/v4', capabilities: ['openai-compatible'], supportsDiscovery: true }),
  provider({ id: 'moonshot', label: 'Moonshot（月之暗面）', protocol: 'openai', defaultBaseUrl: 'https://api.moonshot.cn/v1', capabilities: ['openai-compatible'], supportsDiscovery: true }),
  provider({ id: 'minimax', label: 'MiniMax 官方', protocol: 'openai', defaultBaseUrl: 'https://api.minimax.io/v1', capabilities: ['openai-compatible'], supportsDiscovery: true }),
  provider({ id: 'volcengine', label: '火山方舟（豆包）', protocol: 'openai', defaultBaseUrl: 'https://ark.cn-beijing.volces.com/api/v3', capabilities: ['openai-compatible'], supportsDiscovery: true }),
  provider({ id: 'siliconflow', label: '硅基流动（SiliconFlow）', protocol: 'openai', defaultBaseUrl: 'https://api.siliconflow.cn/v1', capabilities: ['openai-compatible', 'model-discovery'], supportsDiscovery: true }),
  provider({ id: 'openrouter', label: 'OpenRouter', protocol: 'openai', defaultBaseUrl: 'https://openrouter.ai/api/v1', capabilities: ['openai-compatible', 'aggregator', 'model-discovery'], supportsDiscovery: true }),
  provider({ id: 'gemini', label: 'Gemini 官方', protocol: 'gemini', defaultBaseUrl: '', capabilities: ['official-api', 'vision'] }),
  provider({ id: 'anthropic', label: 'Anthropic 官方', protocol: 'anthropic', defaultBaseUrl: '', capabilities: ['official-api'] }),
  provider({ id: 'openai', label: 'OpenAI 官方', protocol: 'openai', defaultBaseUrl: 'https://api.openai.com/v1', capabilities: ['official-api', 'openai-compatible', 'model-discovery'], supportsDiscovery: true }),
  provider({ id: 'ollama', label: 'Ollama（本地）', protocol: 'ollama', defaultBaseUrl: 'http://127.0.0.1:11434', capabilities: ['local-runtime'], requiresApiKey: false, supportsDiscovery: true, isLocal: true }),
  provider({ id: 'custom', label: '自定义兼容服务', protocol: 'openai', defaultBaseUrl: '', capabilities: [], requiresBaseUrl: true, supportsDiscovery: true, isCustom: true }),
];

// Set an expanded connection's models via the token editor (clear existing
// chips, then add each model one at a time), mirroring the real user flow that
// replaced the comma-separated input.
function setConnectionModels(models: string[]): void {
  let removeButtons = screen.queryAllByRole('button', { name: /^移除模型/ });
  while (removeButtons.length > 0) {
    fireEvent.click(removeButtons[0]);
    removeButtons = screen.queryAllByRole('button', { name: /^移除模型/ });
  }
  const addInput = screen.getByLabelText('添加模型');
  const addButton = screen.getByRole('button', { name: '添加' });
  for (const model of models) {
    fireEvent.change(addInput, { target: { value: model } });
    fireEvent.click(addButton);
  }
}

// The models a (single) expanded connection currently shows as removable chips.
function modelChipNames(): string[] {
  return screen
    .queryAllByRole('button', { name: /^移除模型 / })
    .map((button) => (button.getAttribute('aria-label') || '').replace('移除模型 ', ''));
}

const {
  update,
  testLLMChannel,
  discoverLLMChannelModels,
} = vi.hoisted(() => ({
  update: vi.fn(),
  testLLMChannel: vi.fn(),
  discoverLLMChannelModels: vi.fn(),
}));

vi.mock('../../../api/systemConfig', () => ({
  systemConfigApi: {
    update: (...args: unknown[]) => update(...args),
    testLLMChannel: (...args: unknown[]) => testLLMChannel(...args),
    discoverLLMChannelModels: (...args: unknown[]) => discoverLLMChannelModels(...args),
  },
}));

// jsdom 未实现 scrollIntoView，而 Select 打开下拉时会调用它保持活动项可见。
if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

describe('LLMChannelEditor', () => {
  beforeEach(() => {
    update.mockReset();
    testLLMChannel.mockReset();
    discoverLLMChannelModels.mockReset();
  });

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

  function selectOptionValues(label: string): string[] {
    const trigger = screen.getByLabelText(label);
    const listbox = openListbox(trigger);
    const values = within(listbox)
      .getAllByRole('option')
      .map((option) => option.getAttribute('data-value') ?? '');
    fireEvent.click(trigger);
    return values;
  }

  const openAiItems = [
    { key: 'LLM_CHANNELS', value: 'openai' },
    { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
    { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' },
    { key: 'LLM_OPENAI_ENABLED', value: 'true' },
    { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' },
    { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' },
    { key: 'LITELLM_MODEL', value: 'openai/gpt-4o-mini' },
  ];

  function lastDraftCall(onDraftItemsChange: ReturnType<typeof vi.fn>) {
    const calls = onDraftItemsChange.mock.calls;
    return calls[calls.length - 1]?.[0] || [];
  }

  it('reports an empty generation backend draft when channel settings are unchanged', async () => {
    const onDraftItemsChange = vi.fn();
    const { rerender } = render(
      <LLMChannelEditor
        items={openAiItems}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />
    );

    await waitFor(() => expect(onDraftItemsChange).toHaveBeenCalledWith([]));
    expect(onDraftItemsChange).toHaveBeenCalledTimes(1);

    rerender(
      <LLMChannelEditor
        items={openAiItems}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />
    );

    expect(onDraftItemsChange).toHaveBeenCalledTimes(1);
  });

  it('confirms before deleting an unreferenced channel and removes it only on confirm', async () => {
    const onDraftItemsChange = vi.fn();
    // No LITELLM_MODEL -> the connection is not referenced by any task, so direct
    // deletion is allowed after confirmation.
    const unreferencedItems = openAiItems.filter((item) => item.key !== 'LITELLM_MODEL');
    render(
      <LLMChannelEditor
        items={unreferencedItems}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />
    );

    expect(screen.getByRole('button', { name: /OpenAI 官方/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '删除连接' }));

    const dialog = await screen.findByRole('dialog', { name: '删除连接？' });
    // The channel stays until the deletion is confirmed.
    expect(screen.getByRole('button', { name: /OpenAI 官方/i })).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: '删除连接' }));

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /OpenAI 官方/i })).not.toBeInTheDocument();
    });
  });

  it('blocks direct deletion of a task-referenced connection and routes to replacement', async () => {
    const onManageModels = vi.fn();
    // openAiItems declares LITELLM_MODEL=openai/gpt-4o-mini, so the openai
    // connection is referenced by the report task.
    render(
      <LLMChannelEditor
        items={openAiItems}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        onManageModels={onManageModels}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '删除连接' }));

    const dialog = await screen.findByRole('dialog', { name: '无法直接删除连接' });
    expect(within(dialog).getByText(/正被以下任务引用/)).toBeInTheDocument();
    // No destructive "删除连接" confirm — only a jump to Task Routing.
    expect(within(dialog).queryByRole('button', { name: '删除连接' })).not.toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: '前往任务路由替换' }));
    expect(onManageModels).toHaveBeenCalledTimes(1);
    // The connection is NOT removed by the block dialog.
    expect(screen.getByRole('button', { name: /OpenAI 官方/i })).toBeInTheDocument();
  });

  it('reports unsaved channel edits as generation backend draft items', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={openAiItems}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.change(await screen.findByLabelText('服务地址'), {
      target: { value: 'https://proxy.example.com/v1' },
    });
    fireEvent.change(screen.getByLabelText('API 密钥'), {
      target: { value: 'sk-draft' },
    });
    setConnectionModels(['gpt-4o-mini', 'gpt-4o']);

    await waitFor(() => {
      const draft = lastDraftCall(onDraftItemsChange);
      expect(draft).toContainEqual({ key: 'LLM_OPENAI_BASE_URL', value: 'https://proxy.example.com/v1' });
      expect(draft).toContainEqual({ key: 'LLM_OPENAI_API_KEY', value: 'sk-draft' });
      expect(draft).toContainEqual({ key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini,gpt-4o' });
    });
  });

  it('returns to an empty generation backend draft after channel edits are restored', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={openAiItems}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    const baseUrlInput = await screen.findByLabelText('服务地址');
    fireEvent.change(baseUrlInput, { target: { value: 'https://proxy.example.com/v1' } });
    await waitFor(() => expect(lastDraftCall(onDraftItemsChange)).toContainEqual({
      key: 'LLM_OPENAI_BASE_URL',
      value: 'https://proxy.example.com/v1',
    }));

    fireEvent.change(baseUrlInput, { target: { value: 'https://api.openai.com/v1' } });

    await waitFor(() => {
      expect(lastDraftCall(onDraftItemsChange)).toEqual([]);
    });
  });

  it('does not emit invalid channel env keys while the channel name is empty', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={openAiItems}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.change(await screen.findByLabelText('连接名称'), { target: { value: '' } });

    await waitFor(() => {
      expect(lastDraftCall(onDraftItemsChange)).toEqual([]);
    });
    expect(onDraftItemsChange.mock.calls.flatMap((call) => call[0]).some((item) => item.key.startsWith('LLM__'))).toBe(false);
  });

  it('renders API Key input with controlled visibility', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openai' },
          { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' },
          { key: 'LLM_OPENAI_ENABLED', value: 'true' },
          { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' },
          { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));

    const input = await screen.findByLabelText('API 密钥');
    expect(input).toHaveAttribute('type', 'password');

    fireEvent.click(screen.getByRole('button', { name: '显示内容' }));
    expect(input).toHaveAttribute('type', 'text');
  });

  it('shows help dialogs for channel editor fields', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-v4-flash' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    fireEvent.click(await screen.findByRole('button', { name: '查看 服务地址 配置说明' }));

    expect(screen.getByRole('dialog', { name: '服务地址' })).toBeInTheDocument();
    expect(screen.getByText('该连接的接口根地址。')).toBeInTheDocument();
    // Examples are plain user-facing values; env-var syntax stays out of the normal page.
    expect(screen.getByText('https://openrouter.ai/api/v1')).toBeInTheDocument();
    expect(screen.queryByText(/LLM_[A-Z0-9_]+=/)).not.toBeInTheDocument();
    expect(screen.queryByText('LLM_CHANNEL_BASE_URL')).not.toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.click(await screen.findByRole('button', { name: '查看 Temperature 配置说明' }));

    expect(screen.getByRole('dialog', { name: 'Temperature' })).toBeInTheDocument();
    expect(screen.getByText('运行时统一采样温度。')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.click(await screen.findByRole('button', { name: '查看 运行时能力检测 配置说明' }));

    expect(screen.getByRole('dialog', { name: '运行时能力检测' })).toBeInTheDocument();
    expect(screen.getByText('选择能力后点击检测；检测会发起真实 LLM 请求。')).toBeInTheDocument();
  });

  it('hides LiteLLM wording when advanced YAML routing is enabled', () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openai' },
          { key: 'LITELLM_CONFIG', value: './litellm_config.yaml' },
          { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' },
          { key: 'LLM_OPENAI_ENABLED', value: 'true' },
          { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' },
          { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    expect(screen.getByText(/检测到已配置高级模型路由 YAML/i)).toBeInTheDocument();
    expect(screen.getByText(/运行时主要模型 \/ 备用模型 \/ Vision \/ Temperature 仍由下方通用字段决定/i)).toBeInTheDocument();
    expect(screen.queryByText(/LiteLLM/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/LITELLM_CONFIG/i)).not.toBeInTheDocument();
  });

  it('excludes Hermes-only route from Agent and Vision runtime selects', () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'hermes' },
          { key: 'LLM_HERMES_PROTOCOL', value: 'openai' },
          { key: 'LLM_HERMES_BASE_URL', value: 'http://127.0.0.1:8642/v1' },
          { key: 'LLM_HERMES_ENABLED', value: 'true' },
          { key: 'LLM_HERMES_API_KEY', value: '******' },
          { key: 'LLM_HERMES_MODELS', value: 'hermes-agent' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    expect(selectOptionValues('主要模型')).toContain('openai/hermes-agent');
    expect(selectOptionValues('Agent 主要模型')).not.toContain('openai/hermes-agent');
    expect(selectOptionValues('Vision 模型')).not.toContain('openai/hermes-agent');
  });

  it('keeps mixed Hermes route for Agent but excludes it from Vision', () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'hermes,remote,pure' },
          { key: 'LLM_HERMES_PROTOCOL', value: 'openai' },
          { key: 'LLM_HERMES_BASE_URL', value: 'http://127.0.0.1:8642/v1' },
          { key: 'LLM_HERMES_ENABLED', value: 'true' },
          { key: 'LLM_HERMES_API_KEY', value: '******' },
          { key: 'LLM_HERMES_MODELS', value: 'shared-route' },
          { key: 'LLM_REMOTE_PROTOCOL', value: 'openai' },
          { key: 'LLM_REMOTE_BASE_URL', value: 'https://api.example.com/v1' },
          { key: 'LLM_REMOTE_ENABLED', value: 'true' },
          { key: 'LLM_REMOTE_API_KEY', value: 'sk-remote' },
          { key: 'LLM_REMOTE_MODELS', value: 'shared-route' },
          { key: 'LLM_PURE_PROTOCOL', value: 'openai' },
          { key: 'LLM_PURE_BASE_URL', value: 'https://api.example.com/v1' },
          { key: 'LLM_PURE_ENABLED', value: 'true' },
          { key: 'LLM_PURE_API_KEY', value: 'sk-pure' },
          { key: 'LLM_PURE_MODELS', value: 'pure-route' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    expect(selectOptionValues('主要模型')).not.toContain('openai/shared-route');
    expect(selectOptionValues('主要模型')).toContain('openai/pure-route');
    expect(selectOptionValues('Agent 主要模型')).toContain('openai/shared-route');
    expect(selectOptionValues('Vision 模型')).not.toContain('openai/shared-route');
  });

  it('does not test runtime-only masked Hermes secrets from the settings UI', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'hermes' },
          { key: 'LLM_HERMES_PROTOCOL', value: 'openai' },
          { key: 'LLM_HERMES_BASE_URL', value: 'http://127.0.0.1:8642/v1' },
          { key: 'LLM_HERMES_ENABLED', value: 'true' },
          { key: 'LLM_HERMES_API_KEY', value: '******', rawValueExists: false },
          { key: 'LLM_HERMES_MODELS', value: 'hermes-agent' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Hermes/i }));
    fireEvent.click(screen.getByRole('button', { name: '测试连接' }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));
    fireEvent.click(screen.getByLabelText('JSON'));
    fireEvent.click(screen.getByRole('button', { name: '检测能力' }));

    const messages = await screen.findAllByText(/运行时注入的 Hermes Key 不会回传/i);
    expect(messages.length).toBeGreaterThanOrEqual(3);
    expect(testLLMChannel).not.toHaveBeenCalled();
    expect(discoverLLMChannelModels).not.toHaveBeenCalled();
  });

  it('keeps pure non-Hermes route in Agent and Vision runtime selects', () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'remote' },
          { key: 'LLM_REMOTE_PROTOCOL', value: 'openai' },
          { key: 'LLM_REMOTE_BASE_URL', value: 'https://api.example.com/v1' },
          { key: 'LLM_REMOTE_ENABLED', value: 'true' },
          { key: 'LLM_REMOTE_API_KEY', value: 'sk-remote' },
          { key: 'LLM_REMOTE_MODELS', value: 'gpt-4o-mini' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    expect(selectOptionValues('主要模型')).toContain('openai/gpt-4o-mini');
    expect(selectOptionValues('Agent 主要模型')).toContain('openai/gpt-4o-mini');
    expect(selectOptionValues('Vision 模型')).toContain('openai/gpt-4o-mini');
  });

  it('keeps minimax-prefixed models in runtime selections', () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openai' },
          { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.example.com/v1' },
          { key: 'LLM_OPENAI_ENABLED', value: 'true' },
          { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' },
          { key: 'LLM_OPENAI_MODELS', value: 'minimax/MiniMax-M1' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    for (const label of ['主要模型', 'Agent 主要模型', 'Vision 模型']) {
      const trigger = screen.getByLabelText(label);
      const listbox = openListbox(trigger);
      expect(within(listbox).getByRole('option', { name: 'minimax/MiniMax-M1' })).toBeInTheDocument();
      fireEvent.click(trigger);
    }
  });

  it('hides the runtime routing block and never emits runtime keys when showRuntimeConfig is false', () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={openAiItems}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        showRuntimeConfig={false}
        onDraftItemsChange={onDraftItemsChange}
      />
    );

    // Runtime routing controls belong to Task Routing / Reliability now.
    for (const label of ['主要模型', 'Agent 主要模型', 'Vision 模型']) {
      expect(screen.queryByLabelText(label)).not.toBeInTheDocument();
    }
    expect(screen.queryByText('运行时参数')).not.toBeInTheDocument();

    // Editing a channel still produces a channel draft, but it must not carry
    // any runtime routing keys (LITELLM_MODEL etc.) since this view no longer
    // owns them.
    fireEvent.click(screen.getByRole('button', { expanded: false }));
    setConnectionModels(['gpt-4o-mini', 'gpt-4o']);
    const draftKeys = new Set(
      lastDraftCall(onDraftItemsChange).map((item: { key: string }) => item.key.toUpperCase()),
    );
    expect(draftKeys.has('LLM_OPENAI_MODELS')).toBe(true);
    for (const runtimeKey of ['LITELLM_MODEL', 'AGENT_LITELLM_MODEL', 'VISION_MODEL', 'LITELLM_FALLBACK_MODELS', 'LLM_TEMPERATURE']) {
      expect(draftKeys.has(runtimeKey)).toBe(false);
    }
  });

  it('uses the DeepSeek endpoint/protocol but seeds no models when adding the official preset', async () => {
    render(
      <LLMChannelEditor
        items={[]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    chooseOption(screen.getByRole('combobox'), 'deepseek');
    fireEvent.click(screen.getByRole('button', { name: '+ 添加模型服务' }));

    await screen.findByRole('button', { name: /DeepSeek 官方/i });
    expect(screen.getByLabelText('服务地址')).toHaveValue('https://api.deepseek.com');
    // No concrete model IDs are seeded from the provider catalog: a new
    // connection starts explicitly with no models (discover or add manually).
    expect(modelChipNames()).toEqual([]);
    expect(screen.getByText(/尚未添加模型/)).toBeInTheDocument();
  });

  it.each([
    ['minimax', /MiniMax 官方/i, 'https://api.minimax.io/v1'],
    ['volcengine', /火山方舟/i, 'https://ark.cn-beijing.volces.com/api/v3'],
  ])('uses %s OpenAI-compatible endpoint but seeds no models when adding the official preset', async (preset, buttonName, baseUrl) => {
    render(
      <LLMChannelEditor
        items={[]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    chooseOption(screen.getByRole('combobox'), preset);
    fireEvent.click(screen.getByRole('button', { name: '+ 添加模型服务' }));

    await screen.findByRole('button', { name: buttonName });
    expect(screen.getAllByRole('combobox').some((select) => (
      select.getAttribute('data-value') === 'openai'
    ))).toBe(true);
    expect(screen.getByLabelText('服务地址')).toHaveValue(baseUrl);
    expect(modelChipNames()).toEqual([]);
  });

  it('shows provider capability badges, official sources, and config hints', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openrouter' },
          { key: 'LLM_OPENROUTER_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENROUTER_BASE_URL', value: 'https://openrouter.ai/api/v1' },
          { key: 'LLM_OPENROUTER_ENABLED', value: 'true' },
          { key: 'LLM_OPENROUTER_API_KEY', value: 'sk-or-test' },
          { key: 'LLM_OPENROUTER_MODELS', value: '~anthropic/claude-sonnet-latest' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenRouter/i }));

    expect(await screen.findByText('配置参考')).toBeInTheDocument();
    expect(screen.getByText('OpenAI 兼容')).toBeInTheDocument();
    expect(screen.getByText('聚合平台')).toBeInTheDocument();
    expect(screen.getByText('可获取模型')).toBeInTheDocument();
    expect(screen.getByText(/模型列表和模型可见性依赖账号权限与 API 密钥/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'OpenRouter Models API' })).toHaveAttribute(
      'href',
      'https://openrouter.ai/docs/api/api-reference/models/get-models',
    );
    expect(screen.getByText(/能力标签仅用于配置参考，不代表运行时能力已验证通过/i)).toBeInTheDocument();
  });

  it('shows model-discovery capability for SiliconFlow provider hints', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'siliconflow' },
          { key: 'LLM_SILICONFLOW_PROTOCOL', value: 'openai' },
          { key: 'LLM_SILICONFLOW_BASE_URL', value: 'https://api.siliconflow.cn/v1' },
          { key: 'LLM_SILICONFLOW_ENABLED', value: 'true' },
          { key: 'LLM_SILICONFLOW_API_KEY', value: 'sk-test' },
          { key: 'LLM_SILICONFLOW_MODELS', value: 'deepseek-ai/DeepSeek-V3.2' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /SiliconFlow/i }));

    expect(await screen.findByText('可获取模型')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'SiliconFlow Models' })).toBeInTheDocument();
  });

  it('does not show provider metadata for custom or unknown channels', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'my_proxy' },
          { key: 'LLM_MY_PROXY_PROTOCOL', value: 'openai' },
          { key: 'LLM_MY_PROXY_BASE_URL', value: 'https://proxy.example.com/v1' },
          { key: 'LLM_MY_PROXY_ENABLED', value: 'true' },
          { key: 'LLM_MY_PROXY_API_KEY', value: 'sk-test' },
          { key: 'LLM_MY_PROXY_MODELS', value: 'custom-model' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /my_proxy/i }));

    expect(screen.queryByText('配置参考')).not.toBeInTheDocument();
    expect(screen.queryByText(/官方来源/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/能力标签仅用于配置参考/i)).not.toBeInTheDocument();
  });

  it('preserves manually edited base URL and models when switching preset names', async () => {
    render(
      <LLMChannelEditor
        items={[]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    chooseOption(screen.getByRole('combobox'), 'deepseek');
    fireEvent.click(screen.getByRole('button', { name: '+ 添加模型服务' }));

    await screen.findByRole('button', { name: /DeepSeek 官方/i });
    fireEvent.change(screen.getByLabelText('服务地址'), {
      target: { value: 'https://proxy.example.com/v1' },
    });
    setConnectionModels(['custom-model-a', 'custom-model-b']);
    fireEvent.change(screen.getByLabelText('连接名称'), {
      target: { value: 'minimax' },
    });

    await screen.findByRole('button', { name: /MiniMax 官方/i });
    expect(screen.getByLabelText('服务地址')).toHaveValue('https://proxy.example.com/v1');
    expect(modelChipNames()).toEqual(['custom-model-a', 'custom-model-b']);
  });

  it('uses the selected preset defaults when adding a duplicate provider channel', async () => {
    render(
      <LLMChannelEditor
        items={[]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    chooseOption(screen.getByRole('combobox'), 'minimax');
    fireEvent.click(screen.getByRole('button', { name: '+ 添加模型服务' }));
    await screen.findByRole('button', { name: /MiniMax 官方/i });
    fireEvent.click(screen.getByRole('button', { name: '+ 添加模型服务' }));

    await screen.findByRole('button', { name: /minimax2/i });
    expect(screen.getAllByLabelText('连接名称').map((input) => (input as HTMLInputElement).value)).toEqual([
      'minimax',
      'minimax2',
    ]);
    expect(screen.getAllByLabelText('服务地址').map((input) => (input as HTMLInputElement).value)).toEqual([
      'https://api.minimax.io/v1',
      'https://api.minimax.io/v1',
    ]);
    // Neither connection carries seed models: the preset only fills the shared
    // endpoint/protocol, models are added per connection afterwards.
    expect(modelChipNames()).toEqual([]);
    expect(screen.getAllByRole('link', { name: 'MiniMax OpenAI API' })).toHaveLength(1);
  });

  it('reports the MiniMax preset as channel draft env keys', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={[]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />
    );

    chooseOption(screen.getByRole('combobox'), 'minimax');
    fireEvent.click(screen.getByRole('button', { name: '+ 添加模型服务' }));
    await screen.findByRole('button', { name: /MiniMax 官方/i });
    // An enabled channel must be complete (credential + models) before saving.
    // The preset seeds no models, so the user supplies both explicitly.
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'sk-minimax' } });
    setConnectionModels(['minimax-user-model']);

    await waitFor(() => {
      expect(lastDraftCall(onDraftItemsChange)).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ key: 'LLM_CHANNELS', value: 'minimax' }),
          expect.objectContaining({ key: 'LLM_MINIMAX_PROTOCOL', value: 'openai' }),
          expect.objectContaining({ key: 'LLM_MINIMAX_BASE_URL', value: 'https://api.minimax.io/v1' }),
          expect.objectContaining({ key: 'LLM_MINIMAX_MODELS', value: 'minimax-user-model' }),
        ]),
      );
    });
    expect(update).not.toHaveBeenCalled();
  });

  it('reports an enabled but incomplete channel as invalid until it is completed', async () => {
    const onValidityChange = vi.fn();
    render(<LLMChannelEditor items={[]} providers={PROVIDER_CATALOG} maskToken="******" onValidityChange={onValidityChange} />);

    chooseOption(screen.getByRole('combobox'), 'minimax');
    fireEvent.click(screen.getByRole('button', { name: '+ 添加模型服务' }));
    await screen.findByRole('button', { name: /MiniMax 官方/i });

    // Enabled + missing credential -> draft reported invalid with the missing item shown.
    await waitFor(() => {
      expect(onValidityChange).toHaveBeenLastCalledWith(false);
    });
    expect(screen.getAllByText(/缺少 API 密钥/).length).toBeGreaterThan(0);

    // Supplying the key alone is not enough: the preset seeds no models, so the
    // enabled connection stays incomplete until a model is added.
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'sk-minimax' } });
    await waitFor(() => {
      expect(onValidityChange).toHaveBeenLastCalledWith(false);
    });

    setConnectionModels(['minimax-user-model']);
    await waitFor(() => {
      expect(onValidityChange).toHaveBeenLastCalledWith(true);
    });
  });

  it('still adds a blank channel when the provider catalog failed to load', async () => {
    // Degraded mode: an empty catalog must not make the editor unable to add a
    // channel (the provider dropdown is empty but "add" still yields a row).
    render(<LLMChannelEditor items={[]} providers={[]} maskToken="******" />);

    expect(screen.queryByLabelText('服务地址')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '+ 添加模型服务' }));

    // A new channel row is created; its Base URL field is present (blank).
    expect(await screen.findByLabelText('服务地址')).toHaveValue('');
    expect(screen.getByText('已配置的连接')).toBeInTheDocument();
  });

  it('reports an incomplete channel as a valid draft once it is disabled', async () => {
    const onValidityChange = vi.fn();
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={[]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        onValidityChange={onValidityChange}
        onDraftItemsChange={onDraftItemsChange}
      />
    );

    chooseOption(screen.getByRole('combobox'), 'minimax');
    fireEvent.click(screen.getByRole('button', { name: '+ 添加模型服务' }));
    await screen.findByRole('button', { name: /MiniMax 官方/i });
    await waitFor(() => expect(onValidityChange).toHaveBeenLastCalledWith(false));

    // Disabling the incomplete channel makes it a saveable draft.
    fireEvent.click(screen.getByRole('checkbox', { name: /启用连接/ }));
    await waitFor(() => {
      expect(onValidityChange).toHaveBeenLastCalledWith(true);
    });
    expect(lastDraftCall(onDraftItemsChange).length).toBeGreaterThan(0);
    expect(update).not.toHaveBeenCalled();
  });

  it('treats an enabled ollama channel as complete without an API key', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'ollama' },
          { key: 'LLM_OLLAMA_PROTOCOL', value: 'ollama' },
          { key: 'LLM_OLLAMA_BASE_URL', value: 'http://localhost:11434/v1' },
          { key: 'LLM_OLLAMA_ENABLED', value: 'true' },
          { key: 'LLM_OLLAMA_MODELS', value: 'llama3' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    expect(screen.queryByText('草稿 · 未完成')).not.toBeInTheDocument();
    expect(screen.queryByText(/缺少 API 密钥/)).not.toBeInTheDocument();
  });

  it('renders read-only when a non-channels config mode is effective', async () => {
    render(
      <LLMChannelEditor
        items={openAiItems}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        overriddenByMode="legacy"
      />
    );

    expect(await screen.findByText('模型连接当前只读')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '+ 添加模型服务' })).toBeDisabled();
  });

  it('treats an enabled custom ollama channel as complete without a base URL', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'mylocal' },
          { key: 'LLM_MYLOCAL_PROTOCOL', value: 'ollama' },
          { key: 'LLM_MYLOCAL_ENABLED', value: 'true' },
          { key: 'LLM_MYLOCAL_MODELS', value: 'llama3' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    expect(screen.queryByText('草稿 · 未完成')).not.toBeInTheDocument();
    expect(screen.queryByText(/缺少服务地址/)).not.toBeInTheDocument();
  });

  it('treats a known provider with a blank base URL as complete (official default)', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openai' },
          { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENAI_BASE_URL', value: '' },
          { key: 'LLM_OPENAI_ENABLED', value: 'true' },
          { key: 'LLM_OPENAI_API_KEY', value: 'sk-openai' },
          { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    expect(screen.queryByText('草稿 · 未完成')).not.toBeInTheDocument();
    expect(screen.queryByText(/缺少服务地址/)).not.toBeInTheDocument();
  });

  it('reports cleared Hermes unsupported multi-key and extra-header env keys in the draft', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'hermes' },
          { key: 'LLM_HERMES_PROTOCOL', value: 'openai' },
          { key: 'LLM_HERMES_BASE_URL', value: 'http://127.0.0.1:8642/v1' },
          { key: 'LLM_HERMES_ENABLED', value: 'true' },
          { key: 'LLM_HERMES_API_KEY', value: 'sk-hermes-test-value' },
          { key: 'LLM_HERMES_API_KEYS', value: 'sk-old-a,sk-old-b' },
          { key: 'LLM_HERMES_EXTRA_HEADERS', value: '{"X":"Y"}' },
          { key: 'LLM_HERMES_MODELS', value: 'hermes-agent' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Hermes/i }));
    setConnectionModels(['hermes-agent', 'hermes-agent-2']);

    await waitFor(() => {
      const draftMap = new Map(lastDraftCall(onDraftItemsChange).map((item: { key: string; value: string }) => [item.key, item.value]));
      expect(draftMap.get('LLM_HERMES_API_KEY')).toBe('sk-hermes-test-value');
      expect(draftMap.get('LLM_HERMES_API_KEYS')).toBe('');
      expect(draftMap.get('LLM_HERMES_EXTRA_HEADERS')).toBe('');
    });
    expect(update).not.toHaveBeenCalled();
  });

  it('only reports edited values for runtime-only channel keys in the draft', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'my_proxy', rawValueExists: false },
          { key: 'LITELLM_MODEL', value: 'openai/gpt-4o', rawValueExists: false },
          { key: 'LLM_MY_PROXY_PROTOCOL', value: 'openai', rawValueExists: false },
          { key: 'LLM_MY_PROXY_BASE_URL', value: 'https://proxy.example.com/v1', rawValueExists: false },
          { key: 'LLM_MY_PROXY_ENABLED', value: 'true', rawValueExists: false },
          { key: 'LLM_MY_PROXY_API_KEYS', value: 'sk-runtime-only', rawValueExists: false },
          { key: 'LLM_MY_PROXY_MODELS', value: 'gpt-4o-mini', rawValueExists: false },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /my_proxy/i }));
    setConnectionModels(['gpt-4o-mini', 'gpt-4o']);

    await waitFor(() => {
      const draftMap = new Map(lastDraftCall(onDraftItemsChange).map((item: { key: string; value: string }) => [item.key, item.value]));
      expect(draftMap.get('LLM_MY_PROXY_MODELS')).toBe('gpt-4o-mini,gpt-4o');
      expect(draftMap.has('LITELLM_MODEL')).toBe(false);
      expect(draftMap.has('LLM_MY_PROXY_PROTOCOL')).toBe(false);
      expect(draftMap.has('LLM_MY_PROXY_BASE_URL')).toBe(false);
      expect(draftMap.has('LLM_MY_PROXY_API_KEY')).toBe(false);
      expect(draftMap.has('LLM_MY_PROXY_API_KEYS')).toBe(false);
    });
  });

  it('renames a mixed raw/runtime channel and clears persisted API key field in the draft', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'my_proxy' },
          { key: 'LLM_MY_PROXY_PROTOCOL', value: 'openai', rawValueExists: false },
          { key: 'LLM_MY_PROXY_BASE_URL', value: 'https://proxy.example.com/v1', rawValueExists: false },
          { key: 'LLM_MY_PROXY_ENABLED', value: 'true', rawValueExists: false },
          { key: 'LLM_MY_PROXY_API_KEY', value: 'sk-saved' },
          { key: 'LLM_MY_PROXY_MODELS', value: 'gpt-4o-mini', rawValueExists: false },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /my_proxy/i }));
    fireEvent.change(screen.getByLabelText('连接名称'), { target: { value: 'my_proxy2' } });

    await waitFor(() => {
      const draftMap = new Map(lastDraftCall(onDraftItemsChange).map((item: { key: string; value: string }) => [item.key, item.value]));
      expect(draftMap.get('LLM_MY_PROXY_API_KEY')).toBe('');
      expect(draftMap.has('LLM_MY_PROXY_API_KEYS')).toBe(false);
      expect(draftMap.has('LLM_MY_PROXY_PROTOCOL')).toBe(false);
      expect(draftMap.has('LLM_MY_PROXY_BASE_URL')).toBe(false);
      expect(draftMap.has('LLM_MY_PROXY_MODELS')).toBe(false);
      expect(draftMap.get('LLM_MY_PROXY2_API_KEY')).toBe('sk-saved');
      expect(draftMap.get('LLM_MY_PROXY2_BASE_URL')).toBe('https://proxy.example.com/v1');
      expect(draftMap.get('LLM_MY_PROXY2_MODELS')).toBe('gpt-4o-mini');
    });
  });

  it('uses runtime API_KEYS when both API_KEY and API_KEYS coexist', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'my_proxy', rawValueExists: false },
          { key: 'LLM_MY_PROXY_PROTOCOL', value: 'openai', rawValueExists: false },
          { key: 'LLM_MY_PROXY_BASE_URL', value: 'https://proxy.example.com/v1', rawValueExists: false },
          { key: 'LLM_MY_PROXY_ENABLED', value: 'true', rawValueExists: false },
          { key: 'LLM_MY_PROXY_API_KEY', value: 'sk-saved' },
          { key: 'LLM_MY_PROXY_API_KEYS', value: 'sk-runtime-only', rawValueExists: false },
          { key: 'LLM_MY_PROXY_MODELS', value: 'gpt-4o-mini', rawValueExists: false },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /my_proxy/i }));
    expect(screen.getByLabelText('API 密钥')).toHaveValue('sk-runtime-only');
  });

  it('does not migrate conflicted API key data as API_KEY when renaming a channel', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'my_proxy', rawValueExists: false },
          { key: 'LLM_MY_PROXY_PROTOCOL', value: 'openai', rawValueExists: false },
          { key: 'LLM_MY_PROXY_BASE_URL', value: 'https://proxy.example.com/v1', rawValueExists: false },
          { key: 'LLM_MY_PROXY_ENABLED', value: 'true', rawValueExists: false },
          { key: 'LLM_MY_PROXY_API_KEY', value: 'sk-saved' },
          { key: 'LLM_MY_PROXY_API_KEYS', value: 'sk-runtime-only', rawValueExists: false },
          { key: 'LLM_MY_PROXY_MODELS', value: 'gpt-4o-mini', rawValueExists: false },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /my_proxy/i }));
    fireEvent.change(screen.getByLabelText('连接名称'), { target: { value: 'my_proxy2' } });

    await waitFor(() => {
      const draftItems = lastDraftCall(onDraftItemsChange);
      const draftMap = new Map(draftItems.map((item: { key: string; value: string }) => [item.key, item.value]));
      expect(draftMap.get('LLM_CHANNELS')).toBe('my_proxy2');
      expect(draftMap.has('LLM_MY_PROXY2_API_KEY')).toBe(false);
      expect(draftMap.has('LLM_MY_PROXY2_API_KEYS')).toBe(false);
      expect(draftItems.map((item: { value: string }) => item.value)).not.toContain('sk-runtime-only');
      expect(draftItems.map((item: { value: string }) => item.value)).not.toContain('sk-saved');
      expect(draftMap.get('LLM_MY_PROXY_API_KEY')).toBe('');
      expect(draftMap.get('LLM_MY_PROXY2_BASE_URL')).toBe('https://proxy.example.com/v1');
      expect(draftMap.get('LLM_MY_PROXY2_MODELS')).toBe('gpt-4o-mini');
    });
  });

  it('does not migrate runtime-only API keys when renaming a startup-env channel', async () => {
    const onDraftItemsChange = vi.fn();
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'my_proxy', rawValueExists: false },
          { key: 'LLM_MY_PROXY_PROTOCOL', value: 'openai', rawValueExists: false },
          { key: 'LLM_MY_PROXY_BASE_URL', value: 'https://proxy.example.com/v1', rawValueExists: false },
          { key: 'LLM_MY_PROXY_ENABLED', value: 'true', rawValueExists: false },
          { key: 'LLM_MY_PROXY_API_KEYS', value: 'sk-runtime-only', rawValueExists: false },
          { key: 'LLM_MY_PROXY_MODELS', value: 'gpt-4o-mini', rawValueExists: false },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /my_proxy/i }));
    fireEvent.change(screen.getByLabelText('连接名称'), { target: { value: 'my_proxy2' } });

    await waitFor(() => {
      const draftItems = lastDraftCall(onDraftItemsChange);
      const draftMap = new Map(draftItems.map((item: { key: string; value: string }) => [item.key, item.value]));
      expect(draftMap.get('LLM_CHANNELS')).toBe('my_proxy2');
      expect(draftMap.has('LLM_MY_PROXY_API_KEY')).toBe(false);
      expect(draftMap.has('LLM_MY_PROXY_API_KEYS')).toBe(false);
      expect(draftMap.has('LLM_MY_PROXY2_API_KEY')).toBe(false);
      expect(draftMap.has('LLM_MY_PROXY2_API_KEYS')).toBe(false);
      expect(draftItems.map((item: { value: string }) => item.value)).not.toContain('sk-runtime-only');
    });
  });

  it('keeps runtime selections while channel models are edited temporarily', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROTOCOL', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://api.deepseek.com' },
          { key: 'LLM_DEEPSEEK_ENABLED', value: 'true' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-test' },
          { key: 'LLM_DEEPSEEK_MODELS', value: 'deepseek-chat,deepseek-reasoner,deepseek-v4-pro' },
          { key: 'LITELLM_MODEL', value: 'deepseek/deepseek-chat' },
          { key: 'AGENT_LITELLM_MODEL', value: 'deepseek/deepseek-reasoner' },
          { key: 'LITELLM_FALLBACK_MODELS', value: 'deepseek/deepseek-v4-pro' },
          { key: 'VISION_MODEL', value: 'deepseek/deepseek-reasoner' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    const primaryModelSelect = screen.getByRole('combobox', { name: '主要模型' });
    const agentModelSelect = screen.getByRole('combobox', { name: 'Agent 主要模型' });
    const visionModelSelect = screen.getByRole('combobox', { name: 'Vision 模型' });

    fireEvent.click(screen.getByRole('button', { name: /DeepSeek 官方/i }));
    setConnectionModels(['deepseek-v4-flash']);

    await waitFor(() => {
      expect(primaryModelSelect).toHaveAttribute('data-value', 'deepseek/deepseek-chat');
      expect(agentModelSelect).toHaveAttribute('data-value', 'deepseek/deepseek-reasoner');
      expect(visionModelSelect).toHaveAttribute('data-value', 'deepseek/deepseek-reasoner');
    });

    setConnectionModels(['deepseek-chat', 'deepseek-reasoner', 'deepseek-v4-pro']);

    await waitFor(() => {
      expect(primaryModelSelect).toHaveAttribute('data-value', 'deepseek/deepseek-chat');
      expect(agentModelSelect).toHaveAttribute('data-value', 'deepseek/deepseek-reasoner');
      expect(visionModelSelect).toHaveAttribute('data-value', 'deepseek/deepseek-reasoner');
      expect(screen.getByLabelText('deepseek/deepseek-v4-pro')).toBeChecked();
    });
  });

  it('checks protocol-prefixed selected model when discovery returns bare id', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: true,
      message: 'LLM channel model discovery succeeded',
      error: null,
      resolvedProtocol: 'openai',
      models: ['MiniMax-M1'],
      latencyMs: 80,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'dashscope' },
          { key: 'LLM_DASHSCOPE_PROTOCOL', value: 'openai' },
          { key: 'LLM_DASHSCOPE_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_DASHSCOPE_ENABLED', value: 'true' },
          { key: 'LLM_DASHSCOPE_API_KEY', value: 'sk-test' },
          { key: 'LLM_DASHSCOPE_MODELS', value: 'openai/MiniMax-M1' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /通义千问/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    const checkbox = await screen.findByLabelText('MiniMax-M1');
    expect(checkbox).toBeChecked();

    fireEvent.click(checkbox);
    await waitFor(() => {
      expect(modelChipNames()).toEqual([]);
    });
  });

  it('does not treat unknown-prefixed selected model as equivalent to bare discovered id', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: true,
      message: 'LLM channel model discovery succeeded',
      error: null,
      resolvedProtocol: 'openai',
      models: ['MiniMax-M1'],
      latencyMs: 80,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'dashscope' },
          { key: 'LLM_DASHSCOPE_PROTOCOL', value: 'openai' },
          { key: 'LLM_DASHSCOPE_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_DASHSCOPE_ENABLED', value: 'true' },
          { key: 'LLM_DASHSCOPE_API_KEY', value: 'sk-test' },
          { key: 'LLM_DASHSCOPE_MODELS', value: 'minimax/MiniMax-M1' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /通义千问/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    const checkbox = await screen.findByLabelText('MiniMax-M1');
    expect(checkbox).not.toBeChecked();
    expect(modelChipNames()).toEqual(['minimax/MiniMax-M1']);
  });

  it('discovers models and writes selected values into the channel draft', async () => {
    const onDraftItemsChange = vi.fn();
    discoverLLMChannelModels.mockResolvedValue({
      success: true,
      message: 'LLM channel model discovery succeeded',
      error: null,
      resolvedProtocol: 'openai',
      models: ['qwen-plus', 'qwen-turbo'],
      latencyMs: 88,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'dashscope' },
          { key: 'LLM_DASHSCOPE_PROTOCOL', value: 'openai' },
          { key: 'LLM_DASHSCOPE_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_DASHSCOPE_ENABLED', value: 'true' },
          { key: 'LLM_DASHSCOPE_API_KEY', value: 'sk-test' },
          { key: 'LLM_DASHSCOPE_MODELS', value: 'qwen-old' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
        onDraftItemsChange={onDraftItemsChange}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Dashscope/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    const qwenPlusCheckbox = await screen.findByLabelText('qwen-plus');
    fireEvent.click(qwenPlusCheckbox);

    await waitFor(() => {
      expect(modelChipNames()).toEqual(['qwen-old', 'qwen-plus']);
    });

    expect(discoverLLMChannelModels).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'dashscope',
        protocol: 'openai',
        baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        apiKey: 'sk-test',
        models: ['qwen-old'],
      }),
    );

    // Discovery only updates the local draft; it never triggers a save request.
    await waitFor(() => {
      expect(lastDraftCall(onDraftItemsChange)).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ key: 'LLM_DASHSCOPE_MODELS', value: 'qwen-old,qwen-plus' }),
        ]),
      );
    });
    expect(update).not.toHaveBeenCalled();
  });

  it('shows structured troubleshooting hint when channel auth fails', async () => {
    testLLMChannel.mockResolvedValue({ success: false, message: 'LLM authentication failed', error: '401 Unauthorized · Bearer [REDACTED]', errorCode: 'auth', stage: 'chat_completion', retryable: false, details: {}, resolvedProtocol: 'openai', resolvedModel: 'openai/gpt-4o-mini', latencyMs: null });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'openai' }, { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' }, { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' }, { key: 'LLM_OPENAI_ENABLED', value: 'true' }, { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' }, { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' }]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '测试连接' }));

    expect(await screen.findByText(/聊天调用 · 鉴权失败：LLM authentication failed/i)).toBeInTheDocument();
    expect(screen.getByText(/请检查 API 密钥是否正确/i)).toBeInTheDocument();
    expect(screen.queryByText(/调整模型顺序或移除不可用模型/i)).not.toBeInTheDocument();
  });

  it('shows tested model and model-availability hints when a model is disabled', async () => {
    testLLMChannel.mockResolvedValue({
      success: false,
      message: 'LLM channel test failed',
      error: 'litellm.APIError: APIError: OpenAIException - Model disabled.',
      errorCode: 'model_not_found',
      stage: 'chat_completion',
      retryable: false,
      details: { reason: 'model_access_denied', model: 'openai/deepseek-ai/DeepSeek-V3' },
      resolvedProtocol: 'openai',
      resolvedModel: 'openai/deepseek-ai/DeepSeek-V3',
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'siliconflow' },
          { key: 'LLM_SILICONFLOW_PROTOCOL', value: 'openai' },
          { key: 'LLM_SILICONFLOW_BASE_URL', value: 'https://api.siliconflow.cn/v1' },
          { key: 'LLM_SILICONFLOW_ENABLED', value: 'true' },
          { key: 'LLM_SILICONFLOW_API_KEY', value: 'secret-key' },
          { key: 'LLM_SILICONFLOW_MODELS', value: 'deepseek-ai/DeepSeek-V3,Qwen/Qwen3-Coder' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /SiliconFlow/i }));
    fireEvent.click(screen.getByRole('button', { name: '测试连接' }));

    expect(await screen.findByText(/聊天调用 · 模型不可用：LLM channel test failed/i)).toBeInTheDocument();
    expect(screen.getByText(/本次测试模型：openai\/deepseek-ai\/DeepSeek-V3/i)).toBeInTheDocument();
    expect(screen.getByText(/基础连接测试默认使用模型列表首项：deepseek-ai\/DeepSeek-V3/i)).toBeInTheDocument();
    expect(screen.getByText(/基础连接测试默认只测试模型列表中的第一个模型/i)).toBeInTheDocument();
    expect(screen.getByText(/调整模型顺序或移除不可用模型/i)).toBeInTheDocument();
    expect(screen.getByText(/模型是否已开通、账号是否可见/i)).toBeInTheDocument();
    expect(screen.queryByText(/服务地址、代理、TLS/i)).not.toBeInTheDocument();
    expect(testLLMChannel).toHaveBeenCalledWith(expect.objectContaining({
      models: ['deepseek-ai/DeepSeek-V3', 'Qwen/Qwen3-Coder'],
    }));
  });

  it('shows provider blocked troubleshooting without network or model-list hints', async () => {
    testLLMChannel.mockResolvedValue({
      success: false,
      message: 'LLM request was blocked by provider or gateway policy',
      error: 'litellm.APIError: APIError: OpenAIException - Your request was blocked.',
      errorCode: 'request_blocked',
      stage: 'chat_completion',
      retryable: false,
      details: { reason: 'provider_blocked', model: 'openai/gpt-5.5' },
      resolvedProtocol: 'openai',
      resolvedModel: 'openai/gpt-5.5',
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'proxy' },
          { key: 'LLM_PROXY_PROTOCOL', value: 'openai' },
          { key: 'LLM_PROXY_BASE_URL', value: 'https://gateway.example.com/v1' },
          { key: 'LLM_PROXY_ENABLED', value: 'true' },
          { key: 'LLM_PROXY_API_KEY', value: 'secret-key' },
          { key: 'LLM_PROXY_MODELS', value: 'gpt-5.5,gpt-4o-mini' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /proxy/i }));
    fireEvent.click(screen.getByRole('button', { name: '测试连接' }));

    expect(await screen.findByText(/聊天调用 · 请求被拦截/i)).toBeInTheDocument();
    expect(screen.getByText(/本次测试模型：openai\/gpt-5\.5/i)).toBeInTheDocument();
    expect(screen.getByText(/账号风控、地域限制、模型权限/i)).toBeInTheDocument();
    expect(screen.queryByText(/服务地址、代理、TLS/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/调整模型顺序或移除不可用模型/i)).not.toBeInTheDocument();
  });

  it('shows focused quota exceeded troubleshooting hints', async () => {
    testLLMChannel.mockResolvedValue({
      success: false,
      message: 'LLM request was rejected by quota or rate limiting',
      error: 'quota exceeded',
      errorCode: 'quota',
      stage: 'chat_completion',
      retryable: true,
      details: { reason: 'quota_exceeded' },
      resolvedProtocol: 'openai',
      resolvedModel: 'openai/gpt-4o-mini',
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'openai' }, { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' }, { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' }, { key: 'LLM_OPENAI_ENABLED', value: 'true' }, { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' }, { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' }]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '测试连接' }));

    expect(await screen.findByText(/服务商返回配额已耗尽/i)).toBeInTheDocument();
    expect(screen.queryByText(/调整模型顺序或移除不可用模型/i)).not.toBeInTheDocument();
  });

  it('does not show model-list action hints for network failures', async () => {
    testLLMChannel.mockResolvedValue({
      success: false,
      message: 'LLM request failed before a valid response was returned',
      error: 'DNS lookup failed',
      errorCode: 'network_error',
      stage: 'chat_completion',
      retryable: true,
      details: { reason: 'dns_error' },
      resolvedProtocol: 'openai',
      resolvedModel: 'openai/gpt-4o-mini',
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'openai' }, { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' }, { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' }, { key: 'LLM_OPENAI_ENABLED', value: 'true' }, { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' }, { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' }]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '测试连接' }));

    expect(await screen.findByText(/域名解析失败/i)).toBeInTheDocument();
    expect(screen.queryByText(/调整模型顺序或移除不可用模型/i)).not.toBeInTheDocument();
  });

  it('does not request runtime capabilities during the basic connection test', async () => {
    testLLMChannel.mockResolvedValue({
      success: true,
      message: 'LLM channel test succeeded',
      error: null,
      errorCode: null,
      stage: 'chat_completion',
      retryable: false,
      details: {},
      resolvedProtocol: 'openai',
      resolvedModel: 'openai/gpt-4o-mini',
      latencyMs: 80,
      capabilityResults: {},
    });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'openai' }, { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' }, { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' }, { key: 'LLM_OPENAI_ENABLED', value: 'true' }, { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' }, { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' }]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '测试连接' }));

    await screen.findByText(/连接成功 · openai\/gpt-4o-mini/i);
    expect(testLLMChannel).toHaveBeenCalledWith(expect.not.objectContaining({ capabilityChecks: expect.anything() }));
  });

  it('runs explicit runtime capability checks and shows detailed hints', async () => {
    testLLMChannel.mockResolvedValue({
      success: true,
      message: 'LLM channel test succeeded',
      error: null,
      errorCode: null,
      stage: 'chat_completion',
      retryable: false,
      details: {},
      resolvedProtocol: 'openai',
      resolvedModel: 'openai/gpt-4o-mini',
      latencyMs: 80,
      capabilityResults: {
        json: {
          status: 'passed',
          message: 'JSON output capability check passed',
          errorCode: null,
          stage: 'capability_json',
          retryable: false,
          details: { reason: 'json_valid' },
        },
        tools: {
          status: 'failed',
          message: 'LLM channel does not support tools capability',
          errorCode: 'capability_unsupported',
          stage: 'capability_tools',
          retryable: false,
          details: { reason: 'capability_unsupported' },
        },
      },
    });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'openai' }, { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' }, { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' }, { key: 'LLM_OPENAI_ENABLED', value: 'true' }, { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' }, { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' }]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByLabelText('JSON'));
    fireEvent.click(screen.getByLabelText('Tools'));
    fireEvent.click(screen.getByRole('button', { name: '检测能力' }));

    expect(await screen.findByText(/能力检测完成：1 通过 \/ 1 失败 \/ 0 跳过/i)).toBeInTheDocument();
    expect(screen.getByText('JSON 通过')).toBeInTheDocument();
    expect(screen.getByText('Tools 失败')).toBeInTheDocument();
    expect(screen.getByText(/当前模型或兼容层不支持该能力/i)).toBeInTheDocument();
    expect(testLLMChannel).toHaveBeenCalledWith(expect.objectContaining({ capabilityChecks: ['json', 'tools'] }));
  });

  it('shows skipped runtime capabilities when the base test fails', async () => {
    testLLMChannel.mockResolvedValue({
      success: false,
      message: 'LLM authentication failed',
      error: '401 Unauthorized',
      errorCode: 'auth',
      stage: 'chat_completion',
      retryable: false,
      details: { reason: 'api_key_rejected' },
      resolvedProtocol: 'openai',
      resolvedModel: 'openai/gpt-4o-mini',
      latencyMs: null,
      capabilityResults: {
        json: {
          status: 'skipped',
          message: 'Skipped because the base channel test did not pass',
          errorCode: 'skipped',
          stage: 'capability_json',
          retryable: false,
          details: { reason: 'base_test_failed' },
        },
      },
    });

    render(
      <LLMChannelEditor
        items={[{ key: 'LLM_CHANNELS', value: 'openai' }, { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' }, { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' }, { key: 'LLM_OPENAI_ENABLED', value: 'true' }, { key: 'LLM_OPENAI_API_KEY', value: 'bad-key' }, { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' }]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByLabelText('JSON'));
    fireEvent.click(screen.getByRole('button', { name: '检测能力' }));

    expect(await screen.findByText(/能力检测完成：0 通过 \/ 0 失败 \/ 1 跳过/i)).toBeInTheDocument();
    expect(screen.getByText('JSON 跳过')).toBeInTheDocument();
    expect(screen.getByText(/服务商拒绝了当前 API 密钥/i)).toBeInTheDocument();
    expect(screen.getByLabelText('添加模型')).toBeEnabled();
  });

  it('keeps manual model input available when discovery fails', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: false,
      message: 'Model discovery is not supported for this protocol',
      error: 'LLM channel does not support /models discovery yet',
      errorCode: 'unsupported_protocol',
      stage: 'model_discovery',
      retryable: false,
      details: {},
      resolvedProtocol: 'gemini',
      models: [],
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'gemini' },
          { key: 'LLM_GEMINI_PROTOCOL', value: 'gemini' },
          { key: 'LLM_GEMINI_BASE_URL', value: '' },
          { key: 'LLM_GEMINI_ENABLED', value: 'true' },
          { key: 'LLM_GEMINI_API_KEY', value: 'sk-test' },
          { key: 'LLM_GEMINI_MODELS', value: '' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Gemini 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    await screen.findByText(/模型发现 · 协议暂不支持：Model discovery is not supported for this protocol/i);
    expect(screen.getByText(/当前仅对 OpenAI Compatible \/ DeepSeek 连接提供自动模型发现/i)).toBeInTheDocument();

    const manualInput = screen.getByLabelText('添加模型');
    fireEvent.change(manualInput, { target: { value: 'gemini-2.5-flash' } });
    expect(manualInput).toHaveValue('gemini-2.5-flash');
    fireEvent.click(screen.getByRole('button', { name: '添加' }));
    expect(modelChipNames()).toEqual(['gemini-2.5-flash']);
  });

  it('maps discovery format errors to the /models troubleshooting hint', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: false,
      message: 'Failed to parse /models response',
      error: 'Unexpected discovery payload',
      errorCode: 'format_error',
      stage: 'response_parse',
      retryable: false,
      details: {},
      resolvedProtocol: 'openai',
      models: [],
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openai' },
          { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' },
          { key: 'LLM_OPENAI_ENABLED', value: 'true' },
          { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' },
          { key: 'LLM_OPENAI_MODELS', value: '' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    expect(await screen.findByText(/响应解析 · 格式异常：Failed to parse \/models response/i)).toBeInTheDocument();
    expect(screen.getByText(/该连接返回的 \/models 响应格式不兼容，请改为手动填写模型列表。/i)).toBeInTheDocument();
  });

  it('maps discovery empty responses to the /models troubleshooting hint', async () => {
    discoverLLMChannelModels.mockResolvedValue({
      success: false,
      message: 'No model IDs returned from /models response',
      error: 'Empty model discovery response',
      errorCode: 'empty_response',
      stage: 'model_discovery',
      retryable: false,
      details: {},
      resolvedProtocol: 'openai',
      models: [],
      latencyMs: null,
    });

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openai' },
          { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' },
          { key: 'LLM_OPENAI_ENABLED', value: 'true' },
          { key: 'LLM_OPENAI_API_KEY', value: 'secret-key' },
          { key: 'LLM_OPENAI_MODELS', value: '' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    expect(await screen.findByText(/模型发现 · 空响应：No model IDs returned from \/models response/i)).toBeInTheDocument();
    expect(screen.getByText(/该连接的 \/models 接口未返回可用模型 ID/i)).toBeInTheDocument();
    expect(screen.queryByText(/切换兼容模型、关闭额外响应模式/i)).not.toBeInTheDocument();
  });

  it('does not apply stale discovery response after channel list re-sync', async () => {
    let resolvePendingFirst!: (value: unknown) => void;
    const pendingFirst = new Promise((resolve) => {
      resolvePendingFirst = resolve;
    });

    discoverLLMChannelModels
      .mockImplementationOnce(() => pendingFirst)
      .mockResolvedValueOnce({
        success: true,
        message: 'LLM channel model discovery succeeded',
        error: null,
        resolvedProtocol: 'openai',
        models: ['dashscope-plus'],
        latencyMs: 30,
      });

    const renderResult = render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openai' },
          { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' },
          { key: 'LLM_OPENAI_ENABLED', value: 'true' },
          { key: 'LLM_OPENAI_API_KEY', value: 'open-key' },
          { key: 'LLM_OPENAI_MODELS', value: 'gpt-old' },
          { key: 'LLM_DASHSCOPE_PROTOCOL', value: 'openai' },
          { key: 'LLM_DASHSCOPE_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_DASHSCOPE_ENABLED', value: 'true' },
          { key: 'LLM_DASHSCOPE_API_KEY', value: 'dash-key' },
          { key: 'LLM_DASHSCOPE_MODELS', value: 'dash-old' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    renderResult.rerender(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'dashscope' },
          { key: 'LLM_DASHSCOPE_PROTOCOL', value: 'openai' },
          { key: 'LLM_DASHSCOPE_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_DASHSCOPE_ENABLED', value: 'true' },
          { key: 'LLM_DASHSCOPE_API_KEY', value: 'dash-key' },
          { key: 'LLM_DASHSCOPE_MODELS', value: 'dash-old' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /通义千问/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    const dashModelCheckbox = await screen.findByLabelText('dashscope-plus');
    fireEvent.click(dashModelCheckbox);

    expect(modelChipNames()).toEqual(['dash-old', 'dashscope-plus']);

    resolvePendingFirst({
      success: true,
      message: 'LLM channel model discovery succeeded',
      error: null,
      resolvedProtocol: 'openai',
      models: ['stale-openai'],
      latencyMs: 20,
    });

    await waitFor(() => {
      expect(modelChipNames()).toEqual(['dash-old', 'dashscope-plus']);
    });
    expect(screen.queryByLabelText('stale-openai')).not.toBeInTheDocument();
  });

  it('does not apply stale discovery response after inline channel edit', async () => {
    let resolvePendingFirst!: (value: unknown) => void;
    const pendingFirst = new Promise((resolve) => {
      resolvePendingFirst = resolve;
    });

    discoverLLMChannelModels.mockImplementationOnce(() => pendingFirst);

    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'dashscope' },
          { key: 'LLM_DASHSCOPE_PROTOCOL', value: 'openai' },
          { key: 'LLM_DASHSCOPE_BASE_URL', value: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
          { key: 'LLM_DASHSCOPE_ENABLED', value: 'true' },
          { key: 'LLM_DASHSCOPE_API_KEY', value: 'dash-key' },
          { key: 'LLM_DASHSCOPE_MODELS', value: 'qwen-old' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Dashscope/i }));
    fireEvent.click(screen.getByRole('button', { name: '获取模型' }));

    const baseUrlInput = screen.getByLabelText('服务地址');
    fireEvent.change(baseUrlInput, {
      target: { value: 'https://dashscope.aliyuncs.com/compatible-mode/v2' },
    });

    resolvePendingFirst({
      success: true,
      message: 'LLM channel model discovery succeeded',
      error: null,
      resolvedProtocol: 'openai',
      models: ['stale-openai'],
      latencyMs: 20,
    });

    await waitFor(() => {
      expect(modelChipNames()).toEqual(['qwen-old']);
      expect(screen.queryByLabelText('stale-openai')).not.toBeInTheDocument();
    });
  });

  it('never surfaces the legacy "渠道" wording anywhere in the rendered model-access UI', async () => {
    const { container } = render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openai' },
          { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' },
          { key: 'LLM_OPENAI_ENABLED', value: 'true' },
          { key: 'LLM_OPENAI_API_KEY', value: 'sk-existing' },
          { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    // Negative assertion over ALL user-visible text (collapsed card, add flow,
    // and the fully expanded editor: labels, hints, buttons, status copy).
    expect(container.textContent || '').not.toMatch(/渠道/);

    // Add a second connection so the add-flow copy is included, then expand the
    // first connection so the full field editor (labels/hints/buttons) renders.
    fireEvent.click(screen.getByRole('button', { name: '+ 添加模型服务' }));
    await screen.findByRole('button', { name: /AIHubmix/i });
    expect(container.textContent || '').not.toMatch(/渠道/);

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    await screen.findAllByLabelText('添加模型');
    expect(container.textContent || '').not.toMatch(/渠道/);
  });

  it('deduplicates model tokens and removes them individually', async () => {
    render(
      <LLMChannelEditor
        items={[
          { key: 'LLM_CHANNELS', value: 'openai' },
          { key: 'LLM_OPENAI_PROTOCOL', value: 'openai' },
          { key: 'LLM_OPENAI_BASE_URL', value: 'https://api.openai.com/v1' },
          { key: 'LLM_OPENAI_ENABLED', value: 'true' },
          { key: 'LLM_OPENAI_API_KEY', value: 'sk-existing' },
          { key: 'LLM_OPENAI_MODELS', value: 'gpt-4o-mini' },
        ]}
        providers={PROVIDER_CATALOG}
        maskToken="******"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /OpenAI 官方/i }));
    const addInput = await screen.findByLabelText('添加模型');
    const addButton = screen.getByRole('button', { name: '添加' });

    // Adding an existing model is a no-op (dedup); adding a new one appends.
    fireEvent.change(addInput, { target: { value: 'gpt-4o-mini' } });
    fireEvent.click(addButton);
    expect(modelChipNames()).toEqual(['gpt-4o-mini']);

    fireEvent.change(addInput, { target: { value: 'gpt-4o' } });
    fireEvent.click(addButton);
    expect(modelChipNames()).toEqual(['gpt-4o-mini', 'gpt-4o']);

    // Individual removal.
    fireEvent.click(screen.getByRole('button', { name: '移除模型 gpt-4o-mini' }));
    expect(modelChipNames()).toEqual(['gpt-4o']);
  });
});
