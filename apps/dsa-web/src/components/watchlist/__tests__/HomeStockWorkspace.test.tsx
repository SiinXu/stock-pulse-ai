// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HomeStockWorkspace } from '../HomeStockWorkspace';
import type { HomeWorkspaceTab } from '../HomeStockWorkspace';

const buildProps = (activeTab: HomeWorkspaceTab, onTabChange = vi.fn()) => ({
  activeTab,
  onTabChange,
  watchlistRows: [],
  watchlistLoading: false,
  watchlistActioning: false,
  watchlistMessage: null,
  onAddToWatchlist: vi.fn(async () => undefined),
  onRemoveFromWatchlist: vi.fn(async () => undefined),
  onRefreshWatchlist: vi.fn(async () => undefined),
  onAnalyzeWatchlist: vi.fn(async () => undefined),
  isBatchAnalyzing: false,
  batchStatus: null,
  todayItems: [],
  isLoadingTodayItems: false,
  todayLoadError: false,
  watchlistAnalyzedTodayCount: 0,
  historyItems: [],
  isLoadingHistory: false,
  onHistoryItemClick: vi.fn(),
});

describe('HomeStockWorkspace', () => {
  it('keeps the workspace controls compact', () => {
    render(
      <HomeStockWorkspace
        activeTab="watchlist"
        onTabChange={vi.fn()}
        watchlistRows={[{ code: '600519', analyzedToday: false }]}
        watchlistLoading={false}
        watchlistActioning={false}
        watchlistMessage={null}
        onAddToWatchlist={vi.fn(async () => undefined)}
        onRemoveFromWatchlist={vi.fn(async () => undefined)}
        onRefreshWatchlist={vi.fn(async () => undefined)}
        onAnalyzeWatchlist={vi.fn(async () => undefined)}
        isBatchAnalyzing={false}
        batchStatus={null}
        todayItems={[]}
        isLoadingTodayItems={false}
        todayLoadError={false}
        watchlistAnalyzedTodayCount={0}
        historyItems={[]}
        isLoadingHistory={false}
        onHistoryItemClick={vi.fn()}
      />,
    );

    expect(screen.getByRole('combobox', { name: '工作台视图切换' })).toHaveClass('rounded-lg');
    expect(screen.getByRole('searchbox', { name: '搜索' }).parentElement).toHaveClass('h-11', 'sm:h-7');
    expect(screen.getByRole('textbox', { name: '添加代码，如 600519' })).toHaveClass('h-9');
    expect(screen.getByRole('button', { name: '添加自选股' })).toHaveClass('h-9', 'w-9');
    expect(screen.getByRole('button', { name: '从自选股移除 600519' })).toHaveClass('h-9', 'w-9');
  });

  it('keeps the busy add action spinner-only inside its fixed icon target', () => {
    render(
      <HomeStockWorkspace
        activeTab="watchlist"
        onTabChange={vi.fn()}
        watchlistRows={[]}
        watchlistLoading={false}
        watchlistActioning
        watchlistMessage={null}
        onAddToWatchlist={vi.fn(async () => undefined)}
        onRemoveFromWatchlist={vi.fn(async () => undefined)}
        onRefreshWatchlist={vi.fn(async () => undefined)}
        onAnalyzeWatchlist={vi.fn(async () => undefined)}
        isBatchAnalyzing={false}
        batchStatus={null}
        todayItems={[]}
        isLoadingTodayItems={false}
        todayLoadError={false}
        watchlistAnalyzedTodayCount={0}
        historyItems={[]}
        isLoadingHistory={false}
        onHistoryItemClick={vi.fn()}
      />,
    );

    const addButton = screen.getByRole('button', { name: '添加自选股' });
    expect(addButton).toHaveClass('h-9', 'w-9');
    expect(addButton).toHaveAttribute('aria-busy', 'true');
    expect(addButton.textContent).toBe('');
    expect(addButton.querySelector('svg.animate-spin')).toBeInTheDocument();
  });

  it.each<HomeWorkspaceTab>(['history', 'watchlist', 'today'])(
    'keeps the view selector outside the switching panel on the %s view',
    (activeTab) => {
      render(<HomeStockWorkspace {...buildProps(activeTab)} />);

      const selector = screen.getByRole('combobox', { name: '工作台视图切换' });
      const panel = screen.getByRole('region');
      expect(panel).toHaveAccessibleName(selector.textContent ?? '');

      expect(panel.contains(selector)).toBe(false);
    },
  );

  it('selects a workspace view from the shared dropdown', () => {
    const onTabChange = vi.fn();
    render(<HomeStockWorkspace {...buildProps('history', onTabChange)} />);

    const selector = screen.getByRole('combobox', { name: '工作台视图切换' });
    expect(selector).toHaveAttribute('data-value', 'history');
    fireEvent.click(selector);
    fireEvent.click(screen.getByRole('option', { name: '自选' }));

    expect(onTabChange).toHaveBeenCalledWith('watchlist');
  });
});
