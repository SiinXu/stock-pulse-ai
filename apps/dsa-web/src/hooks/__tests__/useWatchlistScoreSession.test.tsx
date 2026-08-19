// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { watchlistScoresApi } from '../../api/watchlistScores';
import { createDeferred } from '../../test-utils';
import type { WatchlistScoreItem, WatchlistScoreResponse } from '../../types/watchlistScore';
import { useWatchlistScoreSession } from '../useWatchlistScoreSession';

vi.mock('../../api/watchlistScores', () => ({
  watchlistScoresApi: { score: vi.fn() },
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

describe('useWatchlistScoreSession', () => {
  beforeEach(() => {
    vi.mocked(watchlistScoresApi.score).mockReset();
  });

  it('starts idle when the watchlist is empty', () => {
    const { result } = renderHook(() => useWatchlistScoreSession([]));
    expect(result.current.status).toBe('idle');
    expect(result.current.itemsByCode.size).toBe(0);
    expect(result.current.stale).toBe(false);
    expect(watchlistScoresApi.score).not.toHaveBeenCalled();
  });

  it('ignores a stale success after unmount', async () => {
    const first = createDeferred<WatchlistScoreResponse>();
    vi.mocked(watchlistScoresApi.score).mockReturnValueOnce(first.promise);
    const { unmount } = renderHook(() => useWatchlistScoreSession(['AAPL']));
    await waitFor(() => expect(watchlistScoresApi.score).toHaveBeenCalledTimes(1));
    unmount();
    await act(async () => {
      first.resolve(scoreResponse([scoreItem('AAPL', 80)]));
      await first.promise;
    });
    expect(watchlistScoresApi.score).toHaveBeenCalledTimes(1);
  });

  it('ignores a stale success after a newer request starts', async () => {
    const first = createDeferred<WatchlistScoreResponse>();
    const second = createDeferred<WatchlistScoreResponse>();
    vi.mocked(watchlistScoresApi.score)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const { result, rerender } = renderHook(
      ({ refreshKey }) => useWatchlistScoreSession(['AAPL', '600519'], refreshKey),
      { initialProps: { refreshKey: 'gen-1' } },
    );

    await waitFor(() => expect(watchlistScoresApi.score).toHaveBeenCalledTimes(1));
    rerender({ refreshKey: 'gen-2' });
    await waitFor(() => expect(watchlistScoresApi.score).toHaveBeenCalledTimes(2));

    await act(async () => {
      first.resolve(scoreResponse([scoreItem('AAPL', 11)]));
      await first.promise;
    });
    expect(result.current.status).toBe('loading');
    expect(result.current.itemsByCode.size).toBe(0);

    await act(async () => {
      second.resolve(scoreResponse([scoreItem('AAPL', 91), scoreItem('600519', 10)]));
      await second.promise;
    });
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.itemsByCode.get('AAPL')?.score).toBe(91);
    expect(result.current.stale).toBe(false);
  });

  it('does not treat an aborted first request as a settled error', async () => {
    const first = createDeferred<WatchlistScoreResponse>();
    vi.mocked(watchlistScoresApi.score)
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(scoreResponse([scoreItem('AAPL', 70)]));
    const { result, rerender } = renderHook(
      ({ refreshKey }) => useWatchlistScoreSession(['AAPL'], refreshKey),
      { initialProps: { refreshKey: 1 } },
    );
    await waitFor(() => expect(watchlistScoresApi.score).toHaveBeenCalledTimes(1));
    rerender({ refreshKey: 2 });
    await act(async () => {
      first.reject(Object.assign(new Error('canceled'), { name: 'CanceledError', code: 'ERR_CANCELED' }));
    });
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.itemsByCode.get('AAPL')?.score).toBe(70);
    expect(result.current.status).not.toBe('error');
  });

  it('keeps last-known ready items only while a same-signature retry is in flight', async () => {
    const retryRequest = createDeferred<WatchlistScoreResponse>();
    vi.mocked(watchlistScoresApi.score)
      .mockResolvedValueOnce(scoreResponse([scoreItem('AAPL', 82)]))
      .mockReturnValueOnce(retryRequest.promise);
    const { result } = renderHook(() => useWatchlistScoreSession(['AAPL'], 'same-gen'));
    await waitFor(() => expect(result.current.status).toBe('ready'));

    act(() => {
      result.current.retry();
    });
    await waitFor(() => expect(result.current.status).toBe('retrying'));
    expect(result.current.stale).toBe(true);
    expect(result.current.itemsByCode.get('AAPL')?.score).toBe(82);

    await act(async () => {
      retryRequest.reject(new Error('provider unavailable'));
    });
    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.stale).toBe(false);
    expect(result.current.itemsByCode.size).toBe(0);
  });

  it('recovers from a provider failure without presenting the failed request as empty success', async () => {
    vi.mocked(watchlistScoresApi.score)
      .mockRejectedValueOnce(new Error('provider unavailable'))
      .mockResolvedValueOnce(scoreResponse([scoreItem('AAPL', 64)]));
    const { result } = renderHook(() => useWatchlistScoreSession(['AAPL']));
    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.itemsByCode.size).toBe(0);

    act(() => {
      result.current.retry();
    });
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.itemsByCode.get('AAPL')?.score).toBe(64);
    expect(result.current.stale).toBe(false);
  });

  it('fail-closes when a new lifecycle request fails instead of keeping the previous generation', async () => {
    vi.mocked(watchlistScoresApi.score)
      .mockResolvedValueOnce(scoreResponse([scoreItem('AAPL', 82)]))
      .mockRejectedValueOnce(new Error('score refresh failed'));
    const { result, rerender } = renderHook(
      ({ refreshKey }) => useWatchlistScoreSession(['AAPL'], refreshKey),
      { initialProps: { refreshKey: 'analysis-1' } },
    );
    await waitFor(() => expect(result.current.status).toBe('ready'));
    rerender({ refreshKey: 'analysis-2' });
    expect(result.current.status).toBe('loading');
    expect(result.current.itemsByCode.size).toBe(0);
    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.itemsByCode.size).toBe(0);
    expect(result.current.stale).toBe(false);
  });
});
