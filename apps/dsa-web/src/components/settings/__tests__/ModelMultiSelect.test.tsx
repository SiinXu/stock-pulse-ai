import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ModelMultiSelect } from '../ModelMultiSelect';

const OPTIONS = ['deepseek-v4-flash', 'deepseek-v4-pro', 'gpt-5.5'];

describe('ModelMultiSelect', () => {
  it('stays collapsed until the user opens an accessible multi-select listbox', () => {
    const selected = new Set(['deepseek-v4-pro']);
    render(
      <ModelMultiSelect
        options={OPTIONS}
        isSelected={(model) => selected.has(model)}
        onToggle={() => {}}
        language="zh"
      />,
    );
    const trigger = screen.getByRole('button', { name: '选择模型' });
    expect(trigger).toHaveClass('min-h-11');
    expect(trigger).toHaveTextContent('已选 1 / 3');
    expect(screen.getByTestId('model-multi-select')).toHaveTextContent('deepseek-v4-pro');
    expect(screen.queryByLabelText('搜索模型')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('gpt-5.5')).not.toBeInTheDocument();

    fireEvent.click(trigger);
    expect(screen.getByRole('listbox')).toHaveAttribute('aria-multiselectable', 'true');
    expect(screen.getByLabelText('搜索模型')).toHaveClass('min-h-11');
    expect(screen.getByLabelText('deepseek-v4-flash').closest('label')).toHaveClass('min-h-11');
    expect(screen.getByLabelText('deepseek-v4-flash')).not.toBeChecked();
    expect(screen.getByLabelText('deepseek-v4-pro')).toBeChecked();
    expect(screen.getByLabelText('gpt-5.5')).not.toBeChecked();
  });

  it('filters the candidate list by the search query', () => {
    render(
      <ModelMultiSelect options={OPTIONS} isSelected={() => false} onToggle={() => {}} language="zh" />,
    );
    fireEvent.click(screen.getByRole('button', { name: '选择模型' }));
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
    fireEvent.click(screen.getByRole('button', { name: '选择模型' }));
    fireEvent.click(screen.getByLabelText('gpt-5.5'));
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle).toHaveBeenCalledWith('gpt-5.5');
    // There is no select-all control: enabling models stays per-model opt-in.
    const container = screen.getByTestId('model-multi-select');
    expect(within(container).queryByText(/全选/)).not.toBeInTheDocument();
  });

  it('lets the user remove a selected trigger chip without opening the listbox', () => {
    const onToggle = vi.fn();
    render(
      <ModelMultiSelect
        options={OPTIONS}
        isSelected={(model) => model === 'deepseek-v4-pro'}
        onToggle={onToggle}
        language="zh"
      />,
    );

    const removeButton = screen.getByRole('button', { name: '移除模型 deepseek-v4-pro' });
    expect(removeButton).toHaveClass('h-11', 'w-11');
    fireEvent.click(removeButton);
    expect(onToggle).toHaveBeenCalledWith('deepseek-v4-pro');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('disables the checkboxes and search when disabled', () => {
    render(
      <ModelMultiSelect options={OPTIONS} isSelected={() => false} onToggle={() => {}} disabled language="zh" />,
    );
    const trigger = screen.getByRole('button', { name: '选择模型' });
    expect(trigger).toBeDisabled();
    fireEvent.click(trigger);
    expect(screen.queryByLabelText('搜索模型')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('gpt-5.5')).not.toBeInTheDocument();
  });

  it('closes on Escape and restores focus to the trigger', () => {
    render(<ModelMultiSelect options={OPTIONS} isSelected={() => false} onToggle={() => {}} language="zh" />);
    const trigger = screen.getByRole('button', { name: '选择模型' });
    fireEvent.click(trigger);
    const search = screen.getByLabelText('搜索模型');
    expect(search).toHaveFocus();
    fireEvent.keyDown(search, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
