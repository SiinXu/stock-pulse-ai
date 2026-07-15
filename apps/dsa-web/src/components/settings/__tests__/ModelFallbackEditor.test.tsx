import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ModelFallbackEditor } from '../ModelFallbackEditor';
import type { SearchableSelectOption } from '../../common';

const options: SearchableSelectOption[] = [
  { value: 'deepseek/deepseek-v4-flash', label: 'deepseek-v4-flash', group: 'deepseek' },
  { value: 'deepseek/deepseek-v4-pro', label: 'deepseek-v4-pro', group: 'deepseek' },
  { value: 'openai/gpt-5.5', label: 'gpt-5.5', group: 'openai' },
];

describe('ModelFallbackEditor', () => {
  it('shows the disabled/empty state when there are no fallbacks', () => {
    render(<ModelFallbackEditor value="" onChange={() => {}} options={options} language="zh" />);
    expect(screen.getByText('未启用备用模型')).toBeInTheDocument();
  });

  it('renders ordered removable tokens with display labels', () => {
    render(
      <ModelFallbackEditor
        value="deepseek/deepseek-v4-pro,openai/gpt-5.5"
        onChange={() => {}}
        options={options}
        language="zh"
      />,
    );
    expect(screen.getByText('deepseek-v4-pro')).toBeInTheDocument();
    expect(screen.getByText('gpt-5.5')).toBeInTheDocument();
  });

  it('appends a selected model to the list via the selector', () => {
    const onChange = vi.fn();
    render(
      <ModelFallbackEditor
        value="deepseek/deepseek-v4-pro"
        onChange={onChange}
        options={options}
        primaryRoute="deepseek/deepseek-v4-flash"
        language="zh"
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '添加备用模型' }));
    const listbox = screen.getByRole('listbox');
    // The primary model and already-picked model are excluded from the add list.
    expect(within(listbox).queryByText('deepseek-v4-flash')).not.toBeInTheDocument();
    expect(within(listbox).queryByText('deepseek-v4-pro')).not.toBeInTheDocument();
    fireEvent.click(within(listbox).getByText('gpt-5.5'));
    expect(onChange).toHaveBeenCalledWith('deepseek/deepseek-v4-pro,openai/gpt-5.5');
  });

  it('filters the add list by search query', () => {
    render(
      <ModelFallbackEditor value="" onChange={() => {}} options={options} language="zh" />,
    );
    fireEvent.click(screen.getByRole('button', { name: '添加备用模型' }));
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'gpt' } });
    const listbox = screen.getByRole('listbox');
    expect(within(listbox).getByText('gpt-5.5')).toBeInTheDocument();
    expect(within(listbox).queryByText('deepseek-v4-flash')).not.toBeInTheDocument();
  });

  it('removes and reorders tokens', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <ModelFallbackEditor
        value="deepseek/deepseek-v4-flash,openai/gpt-5.5"
        onChange={onChange}
        options={options}
        language="zh"
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '移除 gpt-5.5' }));
    expect(onChange).toHaveBeenCalledWith('deepseek/deepseek-v4-flash');

    onChange.mockClear();
    rerender(
      <ModelFallbackEditor
        value="deepseek/deepseek-v4-flash,openai/gpt-5.5"
        onChange={onChange}
        options={options}
        language="zh"
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '上移 gpt-5.5' }));
    expect(onChange).toHaveBeenCalledWith('openai/gpt-5.5,deepseek/deepseek-v4-flash');

    onChange.mockClear();
    rerender(
      <ModelFallbackEditor
        value="deepseek/deepseek-v4-flash,openai/gpt-5.5"
        onChange={onChange}
        options={options}
        language="zh"
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '下移 deepseek-v4-flash' }));
    expect(onChange).toHaveBeenCalledWith('openai/gpt-5.5,deepseek/deepseek-v4-flash');
    // Boundary moves are disabled instead of no-oping silently.
    expect(screen.getByRole('button', { name: '上移 deepseek-v4-flash' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '下移 gpt-5.5' })).toBeDisabled();
  });

  it('marks a configured route missing from the catalog as unavailable without clearing it', () => {
    render(
      <ModelFallbackEditor
        value="legacy/retired-model,openai/gpt-5.5"
        onChange={() => {}}
        options={options}
        language="zh"
      />,
    );
    // The stale route stays in the list (rendered by its raw route)…
    expect(screen.getByText('legacy/retired-model')).toBeInTheDocument();
    // …and is explicitly marked, while catalog-backed routes are not.
    expect(screen.getAllByText('当前配置不可用')).toHaveLength(1);
  });
});
