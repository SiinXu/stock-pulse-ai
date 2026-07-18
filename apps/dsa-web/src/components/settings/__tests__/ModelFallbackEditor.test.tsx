// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ModelFallbackEditor } from '../ModelFallbackEditor';
import type { SearchableSelectOption } from '../../common';

const options: SearchableSelectOption[] = [
  { value: 'deepseek/deepseek-v4-flash', label: 'deepseek-v4-flash', group: 'deepseek' },
  { value: 'deepseek/deepseek-v4-pro', label: 'deepseek-v4-pro', group: 'deepseek' },
  { value: 'openai/gpt-5.5', label: 'gpt-5.5', group: 'openai' },
];

const personalGptRef = 'modelref:v1:personal:openai%2Fgpt-4o';
const workGptRef = 'modelref:v1:work:openai%2Fgpt-4o';
const backupRef = 'modelref:v1:personal:openai%2Fgpt-4o-mini';
const connectionAwareOptions: SearchableSelectOption[] = [
  {
    value: personalGptRef,
    label: 'gpt-4o',
    sublabel: 'OpenAI · Personal',
    group: 'Personal',
  },
  {
    value: backupRef,
    label: 'gpt-4o-mini',
    sublabel: 'OpenAI · Personal',
    group: 'Personal',
  },
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
    expect(screen.getAllByText('deepseek-v4-pro').length).toBeGreaterThan(0);
    expect(screen.getAllByText('gpt-5.5').length).toBeGreaterThan(0);
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
    fireEvent.click(screen.getByRole('button', { name: '选择备用模型' }));
    const listbox = screen.getByRole('listbox');
    // The primary model is excluded; selected fallbacks remain visible and
    // checked so the same collapsed control can add and remove values.
    expect(within(listbox).queryByText('deepseek-v4-flash')).not.toBeInTheDocument();
    expect(within(listbox).getByRole('checkbox', { name: 'deepseek-v4-pro' })).toBeChecked();
    fireEvent.click(within(listbox).getByRole('checkbox', { name: 'gpt-5.5' }));
    expect(onChange).toHaveBeenCalledWith('deepseek/deepseek-v4-pro,openai/gpt-5.5');
  });

  it('filters the add list by search query', () => {
    render(
      <ModelFallbackEditor value="" onChange={() => {}} options={options} language="zh" />,
    );
    fireEvent.click(screen.getByRole('button', { name: '选择备用模型' }));
    fireEvent.change(screen.getByLabelText('搜索模型'), { target: { value: 'gpt' } });
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
    for (const button of screen.getAllByRole('button', { name: /^(上移|下移|移除) / })) {
      expect(button).toHaveClass('h-11', 'w-11');
    }
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

  it('resolves a unique legacy route for display and selection without changing it on load', () => {
    const onChange = vi.fn();
    render(
      <ModelFallbackEditor
        value="openai/gpt-4o"
        onChange={onChange}
        options={connectionAwareOptions}
        resolveConfiguredModelRef={(value) => (
          value === 'openai/gpt-4o' ? personalGptRef : value
        )}
        language="zh"
      />,
    );

    expect(screen.getAllByText('gpt-4o · OpenAI · Personal').length).toBeGreaterThan(0);
    expect(screen.queryByText('当前配置不可用')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '选择备用模型' }));
    expect(screen.getByRole('checkbox', { name: 'gpt-4o · OpenAI · Personal' })).toBeChecked();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('keeps an ambiguous legacy route stale until a Connection is explicitly chosen', () => {
    const onChange = vi.fn();
    const ambiguousOptions: SearchableSelectOption[] = [
      connectionAwareOptions[0],
      {
        value: workGptRef,
        label: 'gpt-4o',
        sublabel: 'OpenAI · Work',
        group: 'Work',
      },
    ];
    render(
      <ModelFallbackEditor
        value="openai/gpt-4o"
        onChange={onChange}
        options={ambiguousOptions}
        resolveConfiguredModelRef={(value) => value}
        language="zh"
      />,
    );

    expect(screen.getByText('openai/gpt-4o')).toBeInTheDocument();
    expect(screen.getByText('当前配置不可用')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '选择备用模型' }));
    for (const checkbox of screen.getAllByRole('checkbox', { name: /gpt-4o · OpenAI/ })) {
      expect(checkbox).not.toBeChecked();
    }
    expect(onChange).not.toHaveBeenCalled();
  });

  it('replaces an ambiguous legacy route with the explicitly selected Connection ModelRef', () => {
    const onChange = vi.fn();
    const ambiguousOptions: SearchableSelectOption[] = [
      connectionAwareOptions[0],
      {
        value: workGptRef,
        label: 'gpt-4o',
        sublabel: 'OpenAI · Work',
        group: 'Work',
      },
    ];
    render(
      <ModelFallbackEditor
        value="openai/gpt-4o"
        onChange={onChange}
        options={ambiguousOptions}
        resolveConfiguredModelRef={(value) => value}
        language="zh"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '选择备用模型' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'gpt-4o · OpenAI · Personal' }));

    expect(onChange).toHaveBeenCalledWith(personalGptRef);
  });

  it('canonicalizes and deduplicates legacy identities when another model is selected', () => {
    const onChange = vi.fn();
    render(
      <ModelFallbackEditor
        value={`openai/gpt-4o,${personalGptRef}`}
        onChange={onChange}
        options={connectionAwareOptions}
        resolveConfiguredModelRef={(value) => (
          value === 'openai/gpt-4o' ? personalGptRef : value
        )}
        language="zh"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '选择备用模型' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'gpt-4o-mini · OpenAI · Personal' }));

    expect(onChange).toHaveBeenCalledWith(`${personalGptRef},${backupRef}`);
  });
});
