// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { watchlistScoresApi } from '../../../api/watchlistScores';
import { HomeStockWorkspace } from '../HomeStockWorkspace';
import type { HomeWorkspaceTab } from '../HomeStockWorkspace';
import type { WatchlistScoreItem, WatchlistScoreResponse } from '../../../types/watchlistScore';

vi.mock('../../../api/watchlistScores', () => ({
  watchlistScoresApi: {
    score: vi.fn(),
  },
}));

const scoreItem = (stockCode: string, score: number): WatchlistScoreItem => ({
  stockCode,
  status: 'scored',
  score,
  asOf: '2026-08-09T00:00:00Z',
  ageDays: 0,
  analysisId: score,
  operationAdvice: 'buy',
  factors: [],
  freshness: 'today',
  degradedReasons: [],
});

const scoreResponse = (items: WatchlistScoreItem[]): WatchlistScoreResponse => ({
  formulaVersion: 'watchlist_score_v1',
  scoringMode: 'aggregate_existing',
  sort: 'manual',
  items,
  queryCount: { analysis: 1, signals: 1 },
  sourceRows: { analysis: items.length, signals: 0 },
  disclaimerKey: 'watchlist_score.disclaimer',
});

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
    vi.mocked(watchlistScoresApi.score).mockReset();
    vi.mocked(watchlistScoresApi.score).mockResolvedValue(
      scoreResponse([scoreItem('600519', 82)]),
    );
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

  it('refetches and reorders scores when analysis state changes with the same symbols', async () => {
    vi.mocked(watchlistScoresApi.score)
      .mockResolvedValueOnce(scoreResponse([
        scoreItem('600519', 82),
        scoreItem('AAPL', 20),
      ]))
      .mockResolvedValueOnce(scoreResponse([
        scoreItem('600519', 10),
        scoreItem('AAPL', 91),
      ]));
    const props = {
      ...buildProps('watchlist'),
      watchlistRows: [
        { code: 'AAPL', analyzedToday: false },
        { code: '600519', analyzedToday: false },
      ],
    };
    const view = render(<HomeStockWorkspace {...props} />);

    await waitFor(() => expect(watchlistScoresApi.score).toHaveBeenCalledTimes(1));
    await screen.findAllByTestId('watchlist-score-column');
    const sort = screen.getByRole('combobox', { name: '手动排序' });
    fireEvent.click(sort);
    const sortListbox = document.getElementById(sort.getAttribute('aria-controls')!)!;
    fireEvent.click(within(sortListbox).getByRole('option', { name: '按 AI 分从高到低' }));
    expect(screen.getAllByTestId('watchlist-row')[0]).toHaveTextContent('600519');

    view.rerender(
      <HomeStockWorkspace
        {...props}
        watchlistRows={[
          { code: 'AAPL', analyzedToday: true },
          { code: '600519', analyzedToday: true },
        ]}
      />,
    );

    await waitFor(() => expect(watchlistScoresApi.score).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getAllByTestId('watchlist-row')[0]).toHaveTextContent('AAPL'));
    expect(screen.getByText('AI 91')).toBeInTheDocument();
    expect(screen.getByText('AI 10')).toBeInTheDocument();
  });

  it('fails closed after a follow-up score request instead of displaying or sorting by old scores', async () => {
    vi.mocked(watchlistScoresApi.score)
      .mockResolvedValueOnce(scoreResponse([
        scoreItem('600519', 82),
        scoreItem('AAPL', 20),
      ]))
      .mockRejectedValueOnce(new Error('score refresh failed'));
    const props = {
      ...buildProps('watchlist'),
      watchlistRows: [
        { code: 'AAPL', analyzedToday: false },
        { code: '600519', analyzedToday: false },
      ],
    };
    const view = render(<HomeStockWorkspace {...props} />);

    await screen.findAllByTestId('watchlist-score-column');
    const sort = screen.getByRole('combobox', { name: '手动排序' });
    fireEvent.click(sort);
    const sortListbox = document.getElementById(sort.getAttribute('aria-controls')!)!;
    fireEvent.click(within(sortListbox).getByRole('option', { name: '按 AI 分从高到低' }));
    expect(screen.getAllByTestId('watchlist-row')[0]).toHaveTextContent('600519');

    view.rerender(
      <HomeStockWorkspace
        {...props}
        watchlistRows={[
          { code: 'AAPL', analyzedToday: true },
          { code: '600519', analyzedToday: true },
        ]}
      />,
    );

    expect(await screen.findByText('AI 评分暂时不可用；刷新成功前不会显示评分或按评分排序。')).toBeInTheDocument();
    expect(screen.queryByTestId('watchlist-score-column')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('watchlist-row')[0]).toHaveTextContent('AAPL');
    expect(screen.getByRole('combobox', { name: '手动排序' })).toBeDisabled();
  });

  it('retries a failed score provider and restores cards without treating the failure as empty', async () => {
    vi.mocked(watchlistScoresApi.score)
      .mockRejectedValueOnce(new Error('provider unavailable'))
      .mockResolvedValueOnce(scoreResponse([
        scoreItem('AAPL', 64),
        scoreItem('600519', 20),
      ]));
    render(
      <HomeStockWorkspace
        {...buildProps('watchlist')}
        watchlistRows={[
          { code: 'AAPL', analyzedToday: false },
          { code: '600519', analyzedToday: false },
        ]}
      />,
    );

    expect(await screen.findByText('AI 评分暂时不可用；刷新成功前不会显示评分或按评分排序。')).toBeInTheDocument();
    expect(screen.queryByTestId('watchlist-score-column')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('watchlist-row')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: '重试' }));

    expect(await screen.findAllByTestId('watchlist-score-column')).toHaveLength(2);
    expect(screen.getByText('AI 64')).toBeInTheDocument();
    expect(screen.queryByText('AI 评分暂时不可用；刷新成功前不会显示评分或按评分排序。')).not.toBeInTheDocument();
  });

  it.each<[HomeWorkspaceTab, string]>([
    ['history', 'home-stock-bar-scroll'],
    ['watchlist', 'home-stock-workspace-scroll'],
    ['today', 'home-stock-workspace-scroll'],
  ])(
    'applies the home-stock-scroll-shell contract on the %s view',
    (activeTab, viewportTestId) => {
      render(
        <HomeStockWorkspace
          {...buildProps(activeTab)}
          historyItems={activeTab === 'history' ? [{
            id: 1,
            stockCode: '600519',
            stockName: '贵州茅台',
            sentimentScore: 62,
            operationAdvice: '观望',
            analysisCount: 1,
            lastAnalysisTime: '2026-07-15T08:00:00Z',
          }] : []}
          todayItems={activeTab === 'today' ? [{
            id: 2,
            stockCode: 'AAPL',
            stockName: 'Apple',
            sentimentScore: 70,
            operationAdvice: '买入',
            analysisCount: 1,
            lastAnalysisTime: '2026-07-15T08:00:00Z',
          }] : []}
          watchlistRows={activeTab === 'watchlist' ? [{ code: '600519', analyzedToday: false }] : []}
        />,
      );

      const workspace = screen.getByTestId('home-stock-workspace');
      expect(workspace).toHaveClass('home-stock-scroll-shell');
      expect(workspace).not.toHaveClass('overflow-hidden');

      const panel = screen.getByRole('region');
      expect(panel).not.toHaveClass('overflow-hidden');
      expect(workspace.contains(panel)).toBe(true);

      const viewport = screen.getByTestId(viewportTestId);
      expect(viewport).toHaveClass('min-h-0', 'overflow-y-auto');
      expect(viewport.parentElement).toHaveClass('overflow-hidden');
      expect(viewport.className.split(/\s+/)).not.toContain('touch-pan-y');

      if (activeTab === 'history') {
        const stockBar = screen.getByTestId('home-stock-bar');
        expect(stockBar.tagName).toBe('ASIDE');
        expect(stockBar).toHaveClass('home-stock-scroll-shell');
        expect(stockBar).not.toHaveClass('overflow-hidden');
        expect(stockBar.contains(viewport)).toBe(true);
        expect(screen.queryByTestId('home-stock-workspace-scroll')).not.toBeInTheDocument();
      } else {
        const surface = viewport.parentElement?.parentElement;
        expect(surface?.tagName).toBe('ASIDE');
        expect(surface).toHaveClass('home-stock-scroll-shell');
        expect(surface).not.toHaveClass('overflow-hidden');
        expect(screen.queryByTestId('home-stock-bar')).not.toBeInTheDocument();
      }
    },
  );
});
