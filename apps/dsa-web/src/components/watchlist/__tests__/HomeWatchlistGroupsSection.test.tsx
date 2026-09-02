// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode, type ReactElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { systemConfigApi } from '../../../api/systemConfig';
import { watchlistScoresApi } from '../../../api/watchlistScores';
import { useWatchlistGroups } from '../../../hooks/useWatchlistGroups';
import type { WatchlistScoreItem, WatchlistScoreResponse } from '../../../types/watchlistScore';
import { HomeWatchlistGroupsSection } from '../HomeWatchlistGroupsSection';

vi.mock('../../../api/watchlistScores', () => ({
  watchlistScoresApi: { score: vi.fn() },
}));

vi.mock('../../../api/systemConfig', () => ({
  systemConfigApi: {
    getWatchlist: vi.fn(),
    addToWatchlist: vi.fn(),
    removeFromWatchlist: vi.fn(),
  },
}));

vi.mock('../../../hooks/useWatchlistGroups', () => ({
  useWatchlistGroups: vi.fn(),
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

function renderWithRealWatchlist(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <StrictMode>
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      </StrictMode>
    );
  }
  return render(ui, { wrapper: Wrapper });
}

describe('HomeWatchlistGroupsSection', () => {
  const refreshGroups = vi.fn(async () => true);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(systemConfigApi.getWatchlist).mockResolvedValue(['AAPL', '600519']);
    vi.mocked(systemConfigApi.addToWatchlist).mockResolvedValue(['AAPL', '600519']);
    vi.mocked(systemConfigApi.removeFromWatchlist).mockResolvedValue(['AAPL']);
    vi.mocked(useWatchlistGroups).mockReturnValue({
      groups: [{
        id: 'default',
        name: 'Default',
        nameKey: 'watchlist.default',
        sortOrder: 0,
        isDefault: true,
        createdAt: '2026-08-09T00:00:00Z',
        updatedAt: '2026-08-09T00:00:00Z',
        members: [
          { stockCode: 'AAPL', sortOrder: 0, attrs: { schemaVersion: 1 } },
          { stockCode: '600519', sortOrder: 1, attrs: { schemaVersion: 1 } },
        ],
      }],
      revision: 1,
      isLoading: false,
      isActioning: false,
      errorMessage: null,
      refresh: refreshGroups,
      createGroup: vi.fn(),
      deleteGroup: vi.fn(),
      restoreGroup: vi.fn(),
      reorderGroups: vi.fn(),
      reorderMembers: vi.fn(),
      moveMember: vi.fn(),
    });
  });

  it('mounts live scores on Home and refreshes score order with unchanged symbols', async () => {
    vi.mocked(watchlistScoresApi.score)
      .mockResolvedValueOnce(scoreResponse([
        scoreItem('AAPL', 20),
        scoreItem('600519', 82),
      ]))
      .mockResolvedValueOnce(scoreResponse([
        scoreItem('AAPL', 91),
        scoreItem('600519', 10),
      ]));
    const view = renderWithRealWatchlist(<HomeWatchlistGroupsSection scoreRefreshKey="analysis-1" />);

    expect(await screen.findAllByTestId('watchlist-score-column')).toHaveLength(2);
    expect(watchlistScoresApi.score).toHaveBeenCalledWith(expect.objectContaining({
      stockCodes: ['AAPL', '600519'],
      sort: 'manual',
    }));
    const sort = screen.getByRole('combobox', { name: '手动排序' });
    fireEvent.click(sort);
    const listbox = document.getElementById(sort.getAttribute('aria-controls')!)!;
    fireEvent.click(within(listbox).getByRole('option', { name: '按 AI 分从高到低' }));
    expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('600519');

    view.rerender(<HomeWatchlistGroupsSection scoreRefreshKey="analysis-2" />);

    await waitFor(() => expect(watchlistScoresApi.score).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('AAPL'));
    expect(systemConfigApi.getWatchlist).toHaveBeenCalledTimes(1);
    expect(refreshGroups).not.toHaveBeenCalled();
  });

  it('fails closed on Home when an explicit refresh cannot reload scores', async () => {
    vi.mocked(watchlistScoresApi.score)
      .mockResolvedValueOnce(scoreResponse([
        scoreItem('AAPL', 20),
        scoreItem('600519', 82),
      ]))
      .mockRejectedValueOnce(new Error('score refresh failed'));
    renderWithRealWatchlist(<HomeWatchlistGroupsSection />);

    await screen.findAllByTestId('watchlist-score-column');
    const sort = screen.getByRole('combobox', { name: '手动排序' });
    fireEvent.click(sort);
    const listbox = document.getElementById(sort.getAttribute('aria-controls')!)!;
    fireEvent.click(within(listbox).getByRole('option', { name: '按 AI 分从高到低' }));
    expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('600519');

    fireEvent.click(screen.getByRole('button', { name: '刷新自选股' }));

    expect(await screen.findByText('AI 评分暂时不可用；刷新成功前不会显示评分或按评分排序。')).toBeInTheDocument();
    expect(screen.queryByTestId('watchlist-score-column')).not.toBeInTheDocument();
    expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('AAPL');
    expect(screen.getByRole('combobox', { name: '手动排序' })).toBeDisabled();
    expect(systemConfigApi.getWatchlist).toHaveBeenCalledTimes(2);
    expect(refreshGroups).toHaveBeenCalledTimes(1);
  });

  it('retries the score provider from the error alert without hiding remaining cards', async () => {
    vi.mocked(watchlistScoresApi.score)
      .mockRejectedValueOnce(new Error('provider unavailable'))
      .mockResolvedValueOnce(scoreResponse([
        scoreItem('AAPL', 64),
        scoreItem('600519', 20),
      ]));
    renderWithRealWatchlist(<HomeWatchlistGroupsSection />);

    expect(await screen.findByText('AI 评分暂时不可用；刷新成功前不会显示评分或按评分排序。')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: '刷新自选股' }));

    await waitFor(() => expect(watchlistScoresApi.score).toHaveBeenCalledTimes(2));
    expect(await screen.findAllByTestId('watchlist-score-column')).toHaveLength(2);
    expect(screen.getByText('AI 64')).toBeInTheDocument();
    expect(systemConfigApi.getWatchlist).toHaveBeenCalledTimes(2);
    expect(refreshGroups).toHaveBeenCalledTimes(1);
  });
});
