// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Modal } from '../Modal';
import { SearchableSelect, type SearchableSelectOption } from '../SearchableSelect';
import { FIXED_POPUP_VIEWPORT_MARGIN_PX } from '../useFixedPopup';

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

  it('keeps the trigger, clear action, search, and options at least 44px at every breakpoint', () => {
    render(
      <SearchableSelect
        value="openai/gpt-5.5"
        onChange={() => {}}
        options={options}
        ariaLabel="主要模型"
        clearable
      />,
    );

    const trigger = screen.getByRole('button', { name: '主要模型' });
    expect(trigger).toHaveClass('h-11', 'min-h-11');
    expect(trigger).not.toHaveClass('sm:min-h-0');
    expect(screen.getByRole('button', { name: '清除 主要模型' })).toHaveClass('h-11', 'w-11');

    fireEvent.click(trigger);
    expect(screen.getByRole('combobox', { name: '搜索选项: 主要模型' })).toHaveClass('h-11', 'min-h-11');
    for (const option of screen.getAllByRole('option')) {
      expect(option).toHaveClass('min-h-11');
      expect(option).not.toHaveClass('sm:min-h-0');
    }
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
        staleValueText="retired-model · retired-connection"
      />,
    );
    const trigger = screen.getByRole('button', { name: '主要模型' });
    const staleMessage = screen.getByText('当前配置不可用');
    expect(trigger).toHaveTextContent('retired-model · retired-connection');
    expect(trigger).toHaveAttribute('data-value', 'legacy/retired-model');
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

  it('opens above a bottom-anchored trigger so the popup stays in the viewport', async () => {
    const triggerRect = new DOMRect(21, 706, 348, 44);
    const popupRect = new DOMRect(21, 754, 348, 299);
    const rectSpy = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockImplementation(function getBoundingClientRect(this: HTMLElement) {
        if (this.getAttribute('aria-label') === '主要模型') {
          return triggerRect;
        }
        if (this.getAttribute('data-dialog-popup') === 'true') {
          return popupRect;
        }
        return new DOMRect();
      });
    vi.stubGlobal('innerHeight', 844);
    vi.stubGlobal('innerWidth', 390);

    try {
      render(
        <Modal isOpen title="配置连接" onClose={() => {}}>
          <SearchableSelect value="" onChange={() => {}} options={options} ariaLabel="主要模型" />
        </Modal>,
      );
      fireEvent.click(screen.getByRole('button', { name: '主要模型' }));
      const popup = screen.getByRole('listbox', { name: '主要模型' }).parentElement;
      expect(popup).not.toBeNull();

      await waitFor(() => {
        expect(popup?.style.maxWidth).toBe(
          `calc(100vw - ${FIXED_POPUP_VIEWPORT_MARGIN_PX * 2}px)`,
        );
        const popupTop = Number.parseFloat(popup?.style.top ?? '');
        expect(popupTop).toBeLessThan(triggerRect.top);
        expect(popupTop + popupRect.height).toBeLessThanOrEqual(
          window.innerHeight - FIXED_POPUP_VIEWPORT_MARGIN_PX,
        );
      });
    } finally {
      rectSpy.mockRestore();
      vi.unstubAllGlobals();
    }
  });

  it('portals to document.body and remeasures the trigger after a window resize', async () => {
    let triggerTop = 100;
    const triggerWidth = 240;
    const triggerHeight = 44;
    const popupHeight = 180;
    const rectSpy = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockImplementation(function getBoundingClientRect(this: HTMLElement) {
        if (this.getAttribute('aria-label') === '主要模型') {
          return new DOMRect(80, triggerTop, triggerWidth, triggerHeight);
        }
        if (this.getAttribute('data-dialog-popup') === 'true') {
          return new DOMRect(80, 0, triggerWidth, popupHeight);
        }
        return new DOMRect();
      });
    vi.stubGlobal('innerWidth', 1024);
    vi.stubGlobal('innerHeight', 844);

    try {
      render(
        <SearchableSelect value="" onChange={() => {}} options={options} ariaLabel="主要模型" />,
      );
      fireEvent.click(screen.getByRole('button', { name: '主要模型' }));
      const popup = screen.getByRole('listbox', { name: '主要模型' }).parentElement;
      expect(popup).not.toBeNull();
      expect(popup?.parentElement).toBe(document.body);

      let initialTop = Number.NaN;
      await waitFor(() => {
        initialTop = Number.parseFloat(popup?.style.top ?? '');
        expect(initialTop).toBeGreaterThan(triggerTop + triggerHeight);
      });

      triggerTop = 360;
      fireEvent.resize(window);

      await waitFor(() => {
        expect(Number.parseFloat(popup?.style.top ?? '')).toBeGreaterThan(initialTop);
      });
    } finally {
      rectSpy.mockRestore();
      vi.unstubAllGlobals();
    }
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
