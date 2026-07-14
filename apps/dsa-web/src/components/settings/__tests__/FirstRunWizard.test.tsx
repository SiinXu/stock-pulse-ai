import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FirstRunWizard } from '../FirstRunWizard';

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
  { id: 'deepseek', label: 'DeepSeek 官方', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: ['official-api'], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
  { id: 'gemini', label: 'Gemini 官方', protocol: 'gemini', defaultBaseUrl: '', capabilities: ['official-api', 'vision'], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: false, isLocal: false, isCustom: false },
  { id: 'ollama', label: 'Ollama（本地）', protocol: 'ollama', defaultBaseUrl: 'http://127.0.0.1:11434', capabilities: ['local-runtime'], requiresApiKey: false, requiresBaseUrl: false, supportsDiscovery: true, isLocal: true, isCustom: false },
  { id: 'custom', label: '自定义兼容服务', protocol: 'openai', defaultBaseUrl: '', capabilities: [], requiresApiKey: true, requiresBaseUrl: true, supportsDiscovery: true, isLocal: false, isCustom: false },
];

const okComplete = () => vi.fn().mockResolvedValue({ success: true });

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

describe('FirstRunWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('emits a backend-valid channel config: canonical route, channels mode, merged channels', async () => {
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
    // Canonical provider/model route, not a bare model name (backend rejects bare).
    expect(byKey.get('LITELLM_MODEL')).toBe('deepseek/deepseek-v4-flash');
  });

  it('does not require a Base URL for Gemini (SDK default endpoint)', () => {
    render(<FirstRunWizard onComplete={okComplete()} onClose={() => {}} isSaving={false} language="zh" providers={CATALOG} />);
    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('服务商'), 'gemini');
    // Gemini template has a blank Base URL; entering only the key must be enough.
    expect(screen.getByLabelText('服务地址')).toHaveValue('');
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'gm-key' } });
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
  });

  it('does not require an API key for Ollama (local runtime) and omits an empty key', async () => {
    const onComplete = okComplete();
    render(<FirstRunWizard onComplete={onComplete} onClose={() => {}} isSaving={false} language="zh" providers={CATALOG} />);
    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('服务商'), 'ollama');
    // No API key entered, but Ollama is key-exempt so we can proceed.
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
    expect(byKey.get('LITELLM_MODEL')).toBe('ollama/llama3.2');
  });

  it('blocks Custom until a Base URL is provided (backend requiresBaseUrl)', () => {
    render(<FirstRunWizard onComplete={okComplete()} onClose={() => {}} isSaving={false} language="zh" providers={CATALOG} />);
    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('服务商'), 'custom');
    fireEvent.change(screen.getByLabelText('API 密钥'), { target: { value: 'sk-custom' } });
    expect(screen.getByLabelText('服务地址')).toHaveValue('');
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('服务地址'), { target: { value: 'https://my-proxy.example.com/v1' } });
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
  });

  it('walks the local CLI path in fewer steps and emits the backend choice', async () => {
    const onComplete = okComplete();
    render(<FirstRunWizard onComplete={onComplete} onClose={() => {}} isSaving={false} language="zh" providers={CATALOG} />);
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
    const checkboxA = await screen.findByLabelText('model-a');
    expect(checkboxA).not.toBeChecked();
    expect(screen.getByLabelText('model-b')).not.toBeChecked();
    expect(screen.queryByLabelText('移除模型 model-a')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    fireEvent.click(checkboxA);
    // Only the confirmed model becomes an enabled token chip.
    expect(screen.getByLabelText('移除模型 model-a')).toBeInTheDocument();
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
    // The key field is explicitly marked optional for key-exempt providers.
    expect(screen.getByLabelText('API 密钥（可选）')).toBeInTheDocument();
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
