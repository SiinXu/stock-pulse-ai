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

describe('FirstRunWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('walks the cloud path and emits a runnable channel config', () => {
    const onComplete = vi.fn();
    render(<FirstRunWizard onComplete={onComplete} onClose={() => {}} isSaving={false} language="zh" />);

    // Step 1: choose Cloud API.
    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    // Step 2: pick DeepSeek and enter an API key (Base URL prefilled).
    chooseOption(screen.getByLabelText('服务商'), 'deepseek');
    fireEvent.change(screen.getByLabelText('API Key'), { target: { value: 'sk-test-123' } });
    expect(screen.getByLabelText('Base URL')).toHaveValue('https://api.deepseek.com');
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    // Step 3: models are prefilled from the provider template.
    expect(screen.getByLabelText('模型（逗号分隔）')).toHaveValue('deepseek-v4-flash,deepseek-v4-pro');
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    // Step 4: report primary model defaults to the first model.
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    // Step 5: review + apply.
    fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));

    expect(onComplete).toHaveBeenCalledTimes(1);
    const items: Array<{ key: string; value: string }> = onComplete.mock.calls[0][0];
    const byKey = new Map(items.map((item) => [item.key, item.value]));
    expect(byKey.get('GENERATION_BACKEND')).toBe('litellm');
    expect(byKey.get('LLM_CHANNELS')).toBe('deepseek');
    expect(byKey.get('LLM_DEEPSEEK_PROTOCOL')).toBe('deepseek');
    expect(byKey.get('LLM_DEEPSEEK_BASE_URL')).toBe('https://api.deepseek.com');
    expect(byKey.get('LLM_DEEPSEEK_API_KEY')).toBe('sk-test-123');
    expect(byKey.get('LLM_DEEPSEEK_MODELS')).toBe('deepseek-v4-flash,deepseek-v4-pro');
    expect(byKey.get('LLM_DEEPSEEK_ENABLED')).toBe('true');
    expect(byKey.get('LITELLM_MODEL')).toBe('deepseek-v4-flash');
  });

  it('walks the local CLI path in fewer steps and emits the backend choice', () => {
    const onComplete = vi.fn();
    render(<FirstRunWizard onComplete={onComplete} onClose={() => {}} isSaving={false} language="zh" />);

    fireEvent.click(screen.getByRole('button', { name: /本机 CLI/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    // CLI path skips the models/model steps, so this is the last input step.
    chooseOption(screen.getByLabelText('选择本机 CLI 后端'), 'claude_code_cli');
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));
    expect(onComplete).toHaveBeenCalledWith([{ key: 'GENERATION_BACKEND', value: 'claude_code_cli' }]);
  });

  it('auto-discovers models and fills them into the models field', async () => {
    discoverLLMChannelModels.mockResolvedValue({ success: true, message: 'ok', models: ['model-a', 'model-b'] });
    render(<FirstRunWizard onComplete={() => {}} onClose={() => {}} isSaving={false} language="zh" />);

    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    chooseOption(screen.getByLabelText('服务商'), 'deepseek');
    fireEvent.change(screen.getByLabelText('API Key'), { target: { value: 'sk-test' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    fireEvent.click(screen.getByRole('button', { name: '自动发现模型' }));
    await waitFor(() => expect(screen.getByLabelText('模型（逗号分隔）')).toHaveValue('model-a,model-b'));
    expect(discoverLLMChannelModels).toHaveBeenCalledWith(expect.objectContaining({
      name: 'deepseek',
      protocol: 'deepseek',
      apiKey: 'sk-test',
    }));
  });

  it('blocks advancing until required fields are provided', () => {
    render(<FirstRunWizard onComplete={() => {}} onClose={() => {}} isSaving={false} language="zh" />);
    // No mode chosen yet.
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /云 API/ }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    // Cloud connection requires an API key.
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('API Key'), { target: { value: 'sk' } });
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
  });
});
