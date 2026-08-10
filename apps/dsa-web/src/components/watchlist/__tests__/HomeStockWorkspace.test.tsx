// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { watchlistScoresApi } from '../../../api/watchlistScores';
import { HomeStockWorkspace } from '../HomeStockWorkspace';
import type { HomeWorkspaceTab } from '../HomeStockWorkspace';

vi.mock('../../../api/watchlistScores', () => ({
  watchlistScoresApi: {
    score: vi.fn(),
  },
}));

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
  beforeEach(() => {
    vi.mocked(watchlistScoresApi.score).mockResolvedValue({
      formulaVersion: 'watchlist_score_v1',
      scoringMode: 'aggregate_existing',
      sort: 'manual',
      items: [
        {
          stockCode: '600519',
          status: 'scored',
          score: 82,
          asOf: '2026-08-09T00:00:00Z',
          ageDays: 0,
          analysisId: 11,
          operationAdvice: 'buy',
          factors: [],
          freshness: 'today',
          degradedReasons: [],
        },
      ],
      queryCount: { analysis: 1, signals: 1 },
      sourceRows: { analysis: 1, signals: 0 },
      disclaimerKey: 'watchlist_score.disclaimer',
    });
  });

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

    expect(screen.getByRole('combobox', { name: '工作台视图切换' })).toBeInTheDocument();
    expect(screen.getByRole('searchbox', { name: '搜索' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '添加代码，如 600519' })).toHaveAttribute('data-size', 'comfortable');
    expect(screen.getByRole('button', { name: '添加自选股' })).toHaveAttribute('data-size', 'comfortable');
    expect(screen.getByRole('button', { name: '从自选股移除 600519' })).toHaveAttribute('data-size', 'default');
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
    expect(addButton).toHaveAttribute('data-size', 'comfortable');
    expect(addButton).toHaveAttribute('aria-busy', 'true');
    expect(addButton.textContent).toBe('');
    expect(addButton.querySelector('svg.animate-spin')).toBeInTheDocument();
  });

  it.each<[HomeWorkspaceTab, string]>([
    ['history', '历史'],
    ['watchlist', '自选'],
    ['today', '今日'],
  ])(
    'keeps the workspace view switcher outside the switching panel on the %s view',
    (activeTab, activeLabel) => {
      render(<HomeStockWorkspace {...buildProps(activeTab)} />);

      const switcher = screen.getByRole('combobox', { name: '工作台视图切换' });
      const panel = screen.getByRole('region', { name: activeLabel });
      expect(panel.contains(switcher)).toBe(false);

      fireEvent.click(switcher);
      const listbox = document.getElementById(switcher.getAttribute('aria-controls')!)!;
      expect(within(listbox).getAllByRole('option')).toHaveLength(3);
    },
  );

  it('selects a workspace view from the view switcher', () => {
    const onTabChange = vi.fn();
    render(<HomeStockWorkspace {...buildProps('history', onTabChange)} />);

    const switcher = screen.getByRole('combobox', { name: '工作台视图切换' });
    expect(switcher).toHaveTextContent('历史');

    fireEvent.click(switcher);
    const listbox = document.getElementById(switcher.getAttribute('aria-controls')!)!;
    const watchlistOption = within(listbox)
      .getAllByRole('option')
      .find((option) => option.getAttribute('data-value') === 'watchlist')!;
    fireEvent.click(watchlistOption);

    expect(onTabChange).toHaveBeenCalledWith('watchlist');
  });

  it('mounts WatchlistScoreColumn from the live score API on the watchlist view', async () => {
    render(
      <HomeStockWorkspace
        activeTab="watchlist"
        onTabChange={vi.fn()}
        watchlistRows={[{ code: '600519', analyzedToday: true }]}
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
        watchlistAnalyzedTodayCount={1}
        historyItems={[]}
        isLoadingHistory={false}
        onHistoryItemClick={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(watchlistScoresApi.score).toHaveBeenCalledWith(
        expect.objectContaining({ stockCodes: ['600519'] }),
      );
    });
    expect(await screen.findByTestId('watchlist-score-column')).toBeInTheDocument();
    expect(screen.getByTestId('watchlist-score-value')).toHaveTextContent('82');
  });
});
