import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CreatableCombobox, type ComboboxOption } from '../CreatableCombobox';

if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

const options: ComboboxOption[] = [
  { value: 'deepseek/deepseek-v4-flash', label: 'deepseek-v4-flash', group: 'DeepSeek', hint: 'tested' },
  { value: 'deepseek/deepseek-v4-pro', label: 'deepseek-v4-pro', group: 'DeepSeek' },
  { value: 'openai/gpt-5.5', label: 'gpt-5.5', group: 'OpenAI' },
];

function openList() {
  fireEvent.focus(screen.getByRole('combobox'));
  const listbox = document.getElementById(screen.getByRole('combobox').getAttribute('aria-controls')!);
  return listbox!;
}

describe('CreatableCombobox', () => {
  it('renders grouped options and selects by click', () => {
    const onChange = vi.fn();
    render(<CreatableCombobox value="" onChange={onChange} options={options} ariaLabel="模型" />);
    const listbox = openList();
    expect(within(listbox).getByText('DeepSeek')).toBeInTheDocument();
    expect(within(listbox).getByText('OpenAI')).toBeInTheDocument();
    fireEvent.click(within(listbox).getByText('gpt-5.5'));
    expect(onChange).toHaveBeenCalledWith('openai/gpt-5.5');
  });

  it('filters options by the typed query', () => {
    render(<CreatableCombobox value="" onChange={() => {}} options={options} ariaLabel="模型" />);
    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'pro' } });
    const listbox = document.getElementById(input.getAttribute('aria-controls')!)!;
    expect(within(listbox).getByText('deepseek-v4-pro')).toBeInTheDocument();
    expect(within(listbox).queryByText('gpt-5.5')).not.toBeInTheDocument();
  });

  it('searches across value, group (connection) and hint, not just the label', () => {
    render(<CreatableCombobox value="" onChange={() => {}} options={options} ariaLabel="模型" allowCustom={false} />);
    const input = screen.getByRole('combobox');
    // Group name (e.g. connection) matches.
    fireEvent.change(input, { target: { value: 'openai' } });
    let listbox = document.getElementById(input.getAttribute('aria-controls')!)!;
    expect(within(listbox).getByText('gpt-5.5')).toBeInTheDocument();
    expect(within(listbox).queryByText('deepseek-v4-pro')).not.toBeInTheDocument();
    // Hint matches.
    fireEvent.change(input, { target: { value: 'tested' } });
    listbox = document.getElementById(input.getAttribute('aria-controls')!)!;
    expect(within(listbox).getByText('deepseek-v4-flash')).toBeInTheDocument();
    expect(within(listbox).queryByText('deepseek-v4-pro')).not.toBeInTheDocument();
    // Stored value (model route) matches even when the label differs.
    fireEvent.change(input, { target: { value: 'deepseek/deepseek-v4-pro' } });
    listbox = document.getElementById(input.getAttribute('aria-controls')!)!;
    expect(within(listbox).getByText('deepseek-v4-pro')).toBeInTheDocument();
  });

  it('offers a custom value when the query is not in the list and allowCustom is on', () => {
    const onChange = vi.fn();
    render(
      <CreatableCombobox
        value=""
        onChange={onChange}
        options={options}
        ariaLabel="模型"
        customLabel={(v) => `自定义: ${v}`}
      />,
    );
    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'my/custom-model' } });
    const listbox = document.getElementById(input.getAttribute('aria-controls')!)!;
    fireEvent.click(within(listbox).getByText('自定义: my/custom-model'));
    expect(onChange).toHaveBeenCalledWith('my/custom-model');
  });

  it('does not offer a custom value when allowCustom is false', () => {
    render(
      <CreatableCombobox value="" onChange={() => {}} options={options} ariaLabel="模型" allowCustom={false} />,
    );
    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'zzz-none' } });
    const listbox = document.getElementById(input.getAttribute('aria-controls')!)!;
    expect(within(listbox).getByText('无匹配项')).toBeInTheDocument();
  });

  it('marks a current value that is not in the options as custom/unavailable', () => {
    render(
      <CreatableCombobox
        value="legacy/old-model"
        onChange={() => {}}
        options={options}
        ariaLabel="模型"
        unavailableLabel="当前配置不可用：legacy/old-model"
      />,
    );
    expect(screen.getByText('当前配置不可用：legacy/old-model')).toBeInTheDocument();
    // The value is still shown in the input, not silently dropped.
    expect(screen.getByRole('combobox')).toHaveValue('legacy/old-model');
  });

  it('supports keyboard selection and clearing', () => {
    const onChange = vi.fn();
    render(<CreatableCombobox value="openai/gpt-5.5" onChange={onChange} options={options} ariaLabel="模型" />);
    const input = screen.getByRole('combobox');
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith('deepseek/deepseek-v4-pro');
    // Clear button resets the value.
    fireEvent.click(screen.getByRole('button', { name: '模型 clear' }));
    expect(onChange).toHaveBeenCalledWith('');
  });
});
