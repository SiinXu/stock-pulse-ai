import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ModelMultiSelect } from '../ModelMultiSelect';

const OPTIONS = ['deepseek-v4-flash', 'deepseek-v4-pro', 'gpt-5.5'];

describe('ModelMultiSelect', () => {
  it('renders every option as an explicit opt-in checkbox with a selected counter', () => {
    const selected = new Set(['deepseek-v4-pro']);
    render(
      <ModelMultiSelect
        options={OPTIONS}
        isSelected={(model) => selected.has(model)}
        onToggle={() => {}}
        language="zh"
      />,
    );
    expect(screen.getByLabelText('deepseek-v4-flash')).not.toBeChecked();
    expect(screen.getByLabelText('deepseek-v4-pro')).toBeChecked();
    expect(screen.getByLabelText('gpt-5.5')).not.toBeChecked();
    expect(screen.getByText('已选 1 / 3')).toBeInTheDocument();
  });

  it('filters the candidate list by the search query', () => {
    render(
      <ModelMultiSelect options={OPTIONS} isSelected={() => false} onToggle={() => {}} language="zh" />,
    );
    fireEvent.change(screen.getByLabelText('搜索模型'), { target: { value: 'GPT' } });
    expect(screen.getByLabelText('gpt-5.5')).toBeInTheDocument();
    expect(screen.queryByLabelText('deepseek-v4-flash')).not.toBeInTheDocument();
    // No match state instead of an empty box.
    fireEvent.change(screen.getByLabelText('搜索模型'), { target: { value: 'zzz' } });
    expect(screen.getByText('无匹配模型')).toBeInTheDocument();
    // The counter still reflects all options, not just the filtered subset.
    expect(screen.getByText('已选 0 / 3')).toBeInTheDocument();
  });

  it('reports toggles for individual models only', () => {
    const onToggle = vi.fn();
    render(
      <ModelMultiSelect options={OPTIONS} isSelected={() => false} onToggle={onToggle} language="zh" />,
    );
    fireEvent.click(screen.getByLabelText('gpt-5.5'));
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle).toHaveBeenCalledWith('gpt-5.5');
    // There is no select-all control: enabling models stays per-model opt-in.
    const container = screen.getByTestId('model-multi-select');
    expect(within(container).queryByText(/全选/)).not.toBeInTheDocument();
  });

  it('disables the checkboxes and search when disabled', () => {
    render(
      <ModelMultiSelect options={OPTIONS} isSelected={() => false} onToggle={() => {}} disabled language="zh" />,
    );
    expect(screen.getByLabelText('搜索模型')).toBeDisabled();
    expect(screen.getByLabelText('gpt-5.5')).toBeDisabled();
  });
});
