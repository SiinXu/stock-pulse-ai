// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { CommandPalette } from '../CommandPalette';

vi.mock('../../StockAutocomplete', () => ({
  StockAutocomplete: ({
    value,
    onChange,
    onSubmit,
    ariaLabel,
  }: {
    value: string;
    onChange: (value: string) => void;
    onSubmit: (value: string) => void;
    ariaLabel: string;
  }) => (
    <input
      aria-label={ariaLabel}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === 'Enter') onSubmit(value);
      }}
    />
  ),
}));

const onClose = vi.fn();
const onNavigate = vi.fn();

function renderPalette() {
  return render(
    <MemoryRouter>
      <UiLanguageProvider initialLanguage="zh">
        <CommandPalette
          isOpen
          onClose={onClose}
          onNavigate={onNavigate}
          analysisHref="/research/analysis"
        />
      </UiLanguageProvider>
    </MemoryRouter>,
  );
}

describe('CommandPalette', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('filters localized page and action commands and navigates to canonical routes', async () => {
    renderPalette();
    const search = screen.getByRole('searchbox', { name: '搜索页面或操作' });
    await waitFor(() => expect(search).toHaveFocus());

    fireEvent.change(search, { target: { value: '持仓' } });
    expect(screen.getByRole('button', { name: '持仓' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '分析' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '持仓' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onNavigate).toHaveBeenCalledWith('/signals?scope=holdings');
  });

  it('moves from search into commands with arrow keys and wraps through the list', async () => {
    renderPalette();
    const search = screen.getByRole('searchbox', { name: '搜索页面或操作' });
    await waitFor(() => expect(search).toHaveFocus());

    fireEvent.keyDown(search, { key: 'ArrowDown' });
    expect(screen.getByRole('button', { name: '开始分析' })).toHaveFocus();

    fireEvent.keyDown(screen.getByRole('button', { name: '开始分析' }), { key: 'ArrowUp' });
    expect(screen.getByRole('button', { name: '再评估与统计' })).toHaveFocus();
  });

  it('reuses stock autocomplete and opens the selected stock detail route', () => {
    renderPalette();
    const stockSearch = screen.getByRole('textbox', { name: '股票' });

    fireEvent.change(stockSearch, { target: { value: 'AAPL' } });
    fireEvent.keyDown(stockSearch, { key: 'Enter' });

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onNavigate).toHaveBeenCalledWith('/stocks/AAPL');
  });

  it('does not navigate when stock autocomplete submits an empty value', () => {
    renderPalette();
    fireEvent.keyDown(screen.getByRole('textbox', { name: '股票' }), { key: 'Enter' });

    expect(onClose).not.toHaveBeenCalled();
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it('shows a bounded empty result while keeping stock lookup available', () => {
    renderPalette();
    fireEvent.change(screen.getByRole('searchbox', { name: '搜索页面或操作' }), {
      target: { value: 'not-a-command' },
    });

    expect(screen.getByText('没有匹配的页面或操作')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '股票' })).toBeInTheDocument();
  });
});
