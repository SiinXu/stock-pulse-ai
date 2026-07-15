import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Modal } from '../Modal';
import { SearchableSelect, type SearchableSelectOption } from '../SearchableSelect';

const options: SearchableSelectOption[] = [
  {
    value: 'openai/gpt-5.5',
    label: 'GPT-5.5',
    sublabel: 'OpenAI · 生产连接',
    keywords: ['openai', 'production'],
  },
  {
    value: 'deepseek/deepseek-v4',
    label: 'DeepSeek V4',
    sublabel: 'DeepSeek · 备用连接',
    keywords: ['deepseek', 'backup'],
  },
];

describe('SearchableSelect', () => {
  it('opens an accessible listbox and commits only a catalog option', () => {
    const onChange = vi.fn();
    render(
      <SearchableSelect
        value=""
        onChange={onChange}
        options={options}
        ariaLabel="主要模型"
      />,
    );
    const trigger = screen.getByRole('button', { name: '主要模型' });
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    const listbox = screen.getByRole('listbox', { name: '主要模型' });
    fireEvent.click(within(listbox).getByRole('option', { name: /GPT-5.5/ }));
    expect(onChange).toHaveBeenCalledWith('openai/gpt-5.5');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('searches label, id, provider, connection, and extra keywords', () => {
    render(
      <SearchableSelect value="" onChange={() => {}} options={options} ariaLabel="主要模型" />,
    );
    fireEvent.click(screen.getByRole('button', { name: '主要模型' }));
    const search = screen.getByRole('combobox', { name: '搜索选项: 主要模型' });
    fireEvent.change(search, { target: { value: 'backup' } });
    const listbox = screen.getByRole('listbox');
    expect(within(listbox).getByRole('option', { name: /DeepSeek V4/ })).toBeInTheDocument();
    expect(within(listbox).queryByRole('option', { name: /GPT-5.5/ })).not.toBeInTheDocument();
  });

  it('supports Arrow keys, aria-activedescendant, Enter, and Escape', () => {
    const onChange = vi.fn();
    render(
      <SearchableSelect value="" onChange={onChange} options={options} ariaLabel="主要模型" />,
    );
    const trigger = screen.getByRole('button', { name: '主要模型' });
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });
    const search = screen.getByRole('combobox');
    fireEvent.keyDown(search, { key: 'ArrowDown' });
    expect(search.getAttribute('aria-activedescendant')).toMatch(/option-1$/);
    fireEvent.keyDown(search, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith('deepseek/deepseek-v4');

    fireEvent.keyDown(trigger, { key: 'Enter' });
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Escape' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('keeps and marks a stale value instead of clearing it', () => {
    const onChange = vi.fn();
    render(
      <SearchableSelect
        value="legacy/retired-model"
        onChange={onChange}
        options={options}
        ariaLabel="主要模型"
        staleValueLabel="当前配置不可用"
      />,
    );
    const trigger = screen.getByRole('button', { name: '主要模型' });
    const staleMessage = screen.getByText('当前配置不可用');
    expect(trigger).toHaveTextContent('legacy/retired-model');
    expect(trigger).toHaveAttribute('aria-describedby', staleMessage.id);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('associates validation errors with the trigger', () => {
    render(
      <>
        <SearchableSelect
          value=""
          onChange={() => {}}
          options={options}
          ariaLabel="主要模型"
          ariaDescribedBy="primary-model-error"
          error
        />
        <p id="primary-model-error">请选择主要模型</p>
      </>,
    );

    const trigger = screen.getByRole('button', { name: '主要模型' });
    expect(trigger).toHaveAttribute('aria-invalid', 'true');
    expect(trigger).toHaveAttribute('aria-describedby', 'primary-model-error');
  });

  it('renders the popup inside a modal so focus stays within the focus trap', () => {
    render(
      <Modal isOpen title="配置连接" onClose={() => {}}>
        <SearchableSelect value="" onChange={() => {}} options={options} ariaLabel="主要模型" />
      </Modal>,
    );
    const dialog = screen.getByRole('dialog', { name: '配置连接' });
    fireEvent.click(within(dialog).getByRole('button', { name: '主要模型' }));
    expect(within(dialog).getByRole('listbox')).toBeInTheDocument();
    expect(within(dialog).getByRole('combobox')).toHaveFocus();
  });

  it('lets Escape close the popup without dismissing its parent modal', () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen title="配置连接" onClose={onClose}>
        <SearchableSelect value="" onChange={() => {}} options={options} ariaLabel="主要模型" />
      </Modal>,
    );
    fireEvent.click(screen.getByRole('button', { name: '主要模型' }));
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Escape' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: '配置连接' })).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
