// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { useState, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../../api/history';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { HistorySearchItem } from '../../../types/analysis';
import type { StockIndexItem } from '../../../types/stockIndex';
import { CommandPalette } from '../CommandPalette';
import { useCommandPaletteShortcut } from '../useCommandPaletteShortcut';

const { stockIndex } = vi.hoisted(() => ({
  stockIndex: [
    {
      canonicalCode: '600519.SH',
      displayCode: '600519',
      nameZh: '贵州茅台',
      pinyinFull: 'guizhoumaotai',
      pinyinAbbr: 'gzmt',
      aliases: ['茅台'],
      market: 'CN',
      assetType: 'stock',
      active: true,
      popularity: 100,
    },
    {
      canonicalCode: '00700.HK',
      displayCode: '00700',
      nameZh: 'Analysis Holdings',
      market: 'HK',
      assetType: 'stock',
      active: true,
      popularity: 90,
    },
    {
      canonicalCode: 'ANLY',
      displayCode: 'ANLY',
      nameZh: 'Analysis Holdings',
      market: 'US',
      assetType: 'stock',
      active: true,
      popularity: 80,
    },
  ] as StockIndexItem[],
}));

const report: HistorySearchItem = {
  id: 42,
  stockCode: '600519.SH',
  stockName: '贵州茅台',
  reportType: 'detailed',
  summary: 'Long-term analysis remains constructive',
  createdAt: '2026-08-10T09:30:00+08:00',
};

vi.mock('../../../hooks/useStockIndex', () => ({
  useStockIndex: () => ({
    index: stockIndex,
    loading: false,
    error: null,
    fallback: false,
    loaded: true,
  }),
}));

vi.mock('../../../api/history', () => ({
  historyApi: { search: vi.fn() },
}));

const searchHistory = vi.mocked(historyApi.search);
const onClose = vi.fn();
const onNavigate = vi.fn();

function PaletteProviders({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter>
      <UiLanguageProvider initialLanguage="zh">
        {children}
      </UiLanguageProvider>
    </MemoryRouter>
  );
}

function renderPalette(analysisHref: string | null = '/research/analysis') {
  return render(
    <PaletteProviders>
      <CommandPalette
        isOpen
        onClose={onClose}
        onNavigate={onNavigate}
        analysisHref={analysisHref ?? undefined}
      />
    </PaletteProviders>,
  );
}

function ShortcutHarness() {
  const [open, setOpen] = useState(false);
  useCommandPaletteShortcut(() => setOpen(true));
  return (
    <>
      <button type="button">Workspace</button>
      <CommandPalette
        isOpen={open}
        onClose={() => setOpen(false)}
        onNavigate={onNavigate}
      />
    </>
  );
}

describe('CommandPalette', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    searchHistory.mockResolvedValue({ query: '', limit: 5, items: [] });
  });

  it('filters localized navigation and executes canonical actions', async () => {
    renderPalette();
    const input = screen.getByRole('combobox', { name: '搜索股票、报告、页面或操作' });
    await waitFor(() => expect(input).toHaveFocus());

    fireEvent.change(input, { target: { value: '持仓' } });
    expect(screen.getByRole('option', { name: '持仓' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: '分析工作台' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('option', { name: '持仓' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onNavigate).toHaveBeenCalledWith('/signals?scope=holdings');
  });

  it('keeps focus in the combobox while arrows select and Enter executes', async () => {
    renderPalette();
    const input = screen.getByRole('combobox', { name: '搜索股票、报告、页面或操作' });
    await waitFor(() => expect(input).toHaveFocus());

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(input).toHaveAttribute('aria-activedescendant', 'command-palette-option-page-home');
    expect(screen.getByRole('option', { name: '首页' })).toHaveAttribute('aria-selected', 'true');

    fireEvent.keyDown(input, { key: 'ArrowUp' });
    expect(screen.getByRole('option', { name: '再评估与统计' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onNavigate).toHaveBeenCalledWith('/signals?tab=review');
  });

  it('groups bounded multi-market stock, report, page, and action results', async () => {
    searchHistory.mockResolvedValue({ query: 'analysis', limit: 5, items: [report] });
    renderPalette();
    const input = screen.getByRole('combobox', { name: '搜索股票、报告、页面或操作' });
    await waitFor(() => expect(input).toHaveFocus());
    expect(screen.getByRole('group', { name: '页面' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: '操作' })).toBeInTheDocument();

    fireEvent.change(input, { target: { value: 'analysis' } });

    await waitFor(() => expect(searchHistory).toHaveBeenCalledWith(
      'analysis',
      expect.objectContaining({ limit: 5, signal: expect.any(AbortSignal) }),
    ));
    expect(screen.getByRole('group', { name: '股票' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: '报告' })).toBeInTheDocument();
    expect(screen.getAllByRole('option', { name: /Analysis Holdings/ })).toHaveLength(2);
    expect(screen.getByRole('option', { name: /贵州茅台.*Long-term analysis/ })).toBeInTheDocument();
  });

  it('runs the full shortcut, query, keyboard selection, report navigation, and close flow', async () => {
    searchHistory.mockResolvedValue({ query: 'long-term', limit: 5, items: [report] });
    render(
      <PaletteProviders>
        <ShortcutHarness />
      </PaletteProviders>,
    );
    const trigger = screen.getByRole('button', { name: 'Workspace' });
    trigger.focus();

    fireEvent.keyDown(document, { key: 'k', metaKey: true });
    const dialog = await screen.findByRole('dialog', { name: '快速前往' });
    const input = within(dialog).getByRole('combobox', { name: '搜索股票、报告、页面或操作' });
    await waitFor(() => expect(input).toHaveFocus());
    fireEvent.change(input, { target: { value: 'long-term' } });
    await waitFor(() => expect(within(dialog).getByRole('group', { name: '报告' })).toBeInTheDocument());

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(within(dialog).getByRole('option', { name: /贵州茅台/ })).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onNavigate).toHaveBeenCalledWith(
      '/research/analysis?segment=history&recordId=42&stock=600519.SH',
    );
    expect(screen.queryByRole('dialog', { name: '快速前往' })).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it('announces loading separately from the settled empty state', async () => {
    let resolveSearch: ((value: Awaited<ReturnType<typeof historyApi.search>>) => void) | undefined;
    searchHistory.mockImplementation(() => new Promise((resolve) => {
      resolveSearch = resolve;
    }));
    renderPalette();
    const input = screen.getByRole('combobox', { name: '搜索股票、报告、页面或操作' });
    await waitFor(() => expect(input).toHaveFocus());

    fireEvent.change(input, { target: { value: 'no-match-term' } });
    expect(screen.getByRole('status')).toHaveTextContent('正在加载');
    await waitFor(() => expect(searchHistory).toHaveBeenCalledTimes(1));

    await act(async () => {
      resolveSearch?.({ query: 'no-match-term', limit: 5, items: [] });
    });
    await waitFor(() => expect(screen.getByText('没有匹配的结果')).toBeInTheDocument());
    expect(screen.queryByText('正在加载')).not.toBeInTheDocument();
  });

  it('keeps stock search available when report search fails', async () => {
    searchHistory.mockRejectedValue(new Error('offline'));
    renderPalette();
    const input = screen.getByRole('combobox', { name: '搜索股票、报告、页面或操作' });
    await waitFor(() => expect(input).toHaveFocus());
    fireEvent.change(input, { target: { value: 'maotai' } });

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('报告搜索暂时不可用'));
    expect(screen.getByRole('option', { name: /贵州茅台.*600519.*CN/ })).toBeInTheDocument();
  });

  it('ignores an older report response after the query changes', async () => {
    const pending = new Map<
      string,
      (value: Awaited<ReturnType<typeof historyApi.search>>) => void
    >();
    searchHistory.mockImplementation((query) => new Promise((resolve) => {
      pending.set(query, resolve);
    }));
    renderPalette();
    const input = screen.getByRole('combobox', { name: '搜索股票、报告、页面或操作' });
    await waitFor(() => expect(input).toHaveFocus());

    fireEvent.change(input, { target: { value: 'older-query' } });
    await waitFor(() => expect(searchHistory).toHaveBeenCalledWith(
      'older-query',
      expect.any(Object),
    ));
    fireEvent.change(input, { target: { value: 'newer-query' } });
    await waitFor(() => expect(searchHistory).toHaveBeenCalledWith(
      'newer-query',
      expect.any(Object),
    ));

    await act(async () => {
      pending.get('newer-query')?.({
        query: 'newer-query',
        limit: 5,
        items: [{ ...report, id: 43, summary: 'Newer report result' }],
      });
    });
    expect(await screen.findByRole('option', { name: /Newer report result/ })).toBeInTheDocument();

    await act(async () => {
      pending.get('older-query')?.({ query: 'older-query', limit: 5, items: [report] });
    });
    expect(screen.queryByRole('option', { name: /Long-term analysis/ })).not.toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Newer report result/ })).toBeInTheDocument();
  });

  it('preserves canonical page, analysis, and one-shot market-review routes', () => {
    renderPalette(null);

    fireEvent.click(screen.getByRole('option', { name: '首页' }));
    expect(onNavigate).toHaveBeenLastCalledWith('/');
    fireEvent.click(screen.getByRole('option', { name: '分析工作台' }));
    expect(onNavigate).toHaveBeenLastCalledWith('/research/analysis');
    fireEvent.click(screen.getByRole('option', { name: '运行大盘复盘' }));
    expect(onNavigate).toHaveBeenLastCalledWith('/research/market?action=run');
  });
});
