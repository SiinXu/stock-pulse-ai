// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { watchlistScoresApi } from '../../api/watchlistScores';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { WatchlistScoreItem, WatchlistScoreResponse } from '../../types/watchlistScore';
import {
  WATCHLIST_SCORES_CANCEL,
  WATCHLIST_SCORES_QUERY_SCHEDULE,
  buildWatchlistScoresQueryKey,
  createUnanalyzedWatchlistScore,
  fetchWatchlistScores,
  useWatchlistScores,
} from '../useWatchlistScores';

vi.mock('../../api/watchlistScores', () => ({
  watchlistScoresApi: {
    score: vi.fn(),
  },
}));

const score = vi.mocked(watchlistScoresApi.score);

const CODES = ['600519', 'AAPL'] as const;
const CODES_KEY = JSON.stringify(['600519', 'AAPL']);
const NEXT_CODES = ['00700'] as const;
const NEXT_CODES_KEY = JSON.stringify(['00700']);

const scoreItem = (stockCode: string, itemScore: number): WatchlistScoreItem => ({
  stockCode,
  status: 'scored',
  score: itemScore,
  asOf: '2026-08-09T00:00:00Z',
  ageDays: 0,
  analysisId: itemScore,
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

function createWrapper(client?: QueryClient) {
  const queryClient = client ?? createAppQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return { client: queryClient, wrapper: Wrapper };
}

function scoresOptions(
  client: QueryClient,
  queryKey: readonly unknown[] = buildWatchlistScoresQueryKey(CODES_KEY, ''),
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertNoWatchlistPrefixOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'watchlist' && key.length === 1).toBe(false);
    expect([...key]).not.toEqual(['watchlist', 'codes']);
    if (key[0] === 'watchlist') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['watchlist', 'scores', key[2], key[3]]);
      expect(key).toHaveLength(4);
    }
  }
}

async function flushQueryMicrotasks(rounds = 2) {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
  }
}

describe('useWatchlistScores', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    score.mockResolvedValue(scoreResponse([
      scoreItem('600519', 80),
      scoreItem('AAPL', 70),
    ]));
  });

  afterEach(() => {
    vi.useRealTimers();
    onlineManager.setOnline(true);
    focusManager.setFocused(true);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    });
  });

  it('pins the exact scores key, schedule, and score({stockCodes,sort,signal})', async () => {
    expect(buildWatchlistScoresQueryKey(CODES_KEY, 'gen-1')).toEqual([
      'watchlist',
      'scores',
      CODES_KEY,
      'gen-1',
    ]);
    expect(WATCHLIST_SCORES_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    const signal = new AbortController().signal;
    await fetchWatchlistScores({ stockCodes: [...CODES], signal });
    expect(score).toHaveBeenCalledTimes(1);
    expect(score).toHaveBeenCalledWith({
      stockCodes: ['600519', 'AAPL'],
      sort: 'manual',
      signal,
    });
  });

  it('stays idle and does not fetch when codes are empty', async () => {
    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result, rerender } = renderHook(
      ({ codes, refreshKey }: { codes: readonly string[]; refreshKey: string }) => (
        useWatchlistScores(codes, refreshKey)
      ),
      { wrapper, initialProps: { codes: [] as readonly string[], refreshKey: '' } },
    );

    expect(result.current.status).toBe('idle');
    expect(result.current.itemsByCode.size).toBe(0);
    expect(score).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();

    rerender({ codes: [], refreshKey: 'later' });
    await flushQueryMicrotasks();
    expect(result.current.status).toBe('idle');
    expect(score).not.toHaveBeenCalled();
  });

  it('does not auto-retry a 5xx load when the QueryClient default would retry', async () => {
    score.mockRejectedValue(Object.assign(new Error('server'), { response: { status: 500 } }));
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useWatchlistScores(CODES), { wrapper });

    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(score).toHaveBeenCalledTimes(1);
    expect(scoresOptions(client)?.retry).toBe(false);
    expect(result.current.itemsByCode.size).toBe(0);
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useWatchlistScores(CODES), { wrapper });

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(scoresOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(scoresOptions(client)?.retry).toBe(false);
    expect(scoresOptions(client)?.staleTime).toBe(0);
    expect(score).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(score).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call score again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useWatchlistScores(CODES), { wrapper });
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(score).toHaveBeenCalledTimes(1);
    expect(scoresOptions(client)?.refetchInterval).toBeUndefined();

    vi.useFakeTimers();
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    await flushQueryMicrotasks();

    expect(score).toHaveBeenCalledTimes(1);
  });

  it('issues score while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlistScores(CODES), { wrapper });

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(score).toHaveBeenCalledTimes(1);
    expect(scoresOptions(client)?.networkMode).toBe('always');
    expect(result.current.itemsByCode.get('600519')?.score).toBe(80);
  });

  it('schedules through fetchQuery with no live observer', async () => {
    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useWatchlistScores(CODES), { wrapper });

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['watchlist', 'scores', CODES_KEY, '']);
    }
    const key = buildWatchlistScoresQueryKey(CODES_KEY, '');
    expect(client.getQueryCache().find({ queryKey: key, exact: true })?.getObserversCount()).toBe(0);
  });

  it('filters the response to the requested codes', async () => {
    score.mockResolvedValue(scoreResponse([
      scoreItem('600519', 80),
      scoreItem('AAPL', 70),
      scoreItem('EXTRA', 99),
    ]));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlistScores(CODES), { wrapper });

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect([...result.current.itemsByCode.keys()].sort()).toEqual(['600519', 'AAPL']);
    expect(result.current.itemsByCode.has('EXTRA')).toBe(false);
  });

  it('trims blank codes out of the exact query key', async () => {
    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(
      () => useWatchlistScores([' 600519 ', '', 'AAPL'], 4),
      { wrapper },
    );

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(fetchSpy.mock.calls[0]?.[0]?.queryKey).toEqual([
      'watchlist',
      'scores',
      CODES_KEY,
      '4',
    ]);
    expect(score).toHaveBeenCalledWith({
      stockCodes: ['600519', 'AAPL'],
      sort: 'manual',
      signal: expect.any(AbortSignal),
    });
  });

  it('treats number 1 and string 1 as one canonical refresh generation', async () => {
    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result, rerender } = renderHook(
      ({ refreshKey }: { refreshKey: string | number }) => useWatchlistScores(CODES, refreshKey),
      { wrapper, initialProps: { refreshKey: 1 as string | number } },
    );

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(score).toHaveBeenCalledTimes(1);
    expect(fetchSpy.mock.calls[0]?.[0]?.queryKey).toEqual([
      'watchlist',
      'scores',
      CODES_KEY,
      '1',
    ]);
    expect(result.current.itemsByCode.get('600519')?.score).toBe(80);

    rerender({ refreshKey: '1' });
    expect(result.current.status).toBe('ready');
    expect(result.current.itemsByCode.get('600519')?.score).toBe(80);
    await flushQueryMicrotasks(6);
    expect(score).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe('ready');
    expect(result.current.itemsByCode.get('600519')?.score).toBe(80);

    rerender({ refreshKey: 2 });
    expect(result.current.status).toBe('loading');
    expect(result.current.itemsByCode.size).toBe(0);
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(score).toHaveBeenCalledTimes(2);
    expect(fetchSpy.mock.calls[1]?.[0]?.queryKey).toEqual([
      'watchlist',
      'scores',
      CODES_KEY,
      '2',
    ]);
  });

  it('exposes loading plus empty immediately on refreshKey and lets the newest result win', async () => {
    const first = createDeferred<WatchlistScoreResponse>();
    score
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(scoreResponse([scoreItem('600519', 11), scoreItem('AAPL', 12)]));
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const abandoned = buildWatchlistScoresQueryKey(CODES_KEY, '');
    const nextKey = buildWatchlistScoresQueryKey(CODES_KEY, 'refresh-2');
    const { result, rerender } = renderHook(
      ({ refreshKey }: { refreshKey: string }) => useWatchlistScores(CODES, refreshKey),
      { wrapper, initialProps: { refreshKey: '' } },
    );

    await waitFor(() => expect(score).toHaveBeenCalledTimes(1));
    expect(result.current.status).toBe('loading');
    expect(result.current.itemsByCode.size).toBe(0);

    rerender({ refreshKey: 'refresh-2' });
    expect(result.current.status).toBe('loading');
    expect(result.current.itemsByCode.size).toBe(0);

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.itemsByCode.get('600519')?.score).toBe(11);
    expect(score.mock.calls[0]?.[0]?.signal?.aborted).toBe(true);
    expect(client.getQueryState(abandoned)).toBeUndefined();
    expect(client.getQueryState(nextKey)).toBeDefined();

    await act(async () => {
      first.resolve(scoreResponse([scoreItem('600519', 1), scoreItem('AAPL', 2)]));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.itemsByCode.get('600519')?.score).toBe(11);
    expect(result.current.status).toBe('ready');
    assertNoWatchlistPrefixOps(cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
    assertNoWatchlistPrefixOps(removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
  });

  it('cancels the previous codes key and ignores its late response', async () => {
    const first = createDeferred<WatchlistScoreResponse>();
    score
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(scoreResponse([scoreItem('00700', 55)]));
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const abandoned = buildWatchlistScoresQueryKey(CODES_KEY, '');
    const nextKey = buildWatchlistScoresQueryKey(NEXT_CODES_KEY, '');
    const { result, rerender } = renderHook(
      ({ codes }: { codes: readonly string[] }) => useWatchlistScores(codes),
      { wrapper, initialProps: { codes: CODES as readonly string[] } },
    );

    await waitFor(() => expect(score).toHaveBeenCalledTimes(1));
    rerender({ codes: NEXT_CODES });
    expect(result.current.status).toBe('loading');
    expect(result.current.itemsByCode.size).toBe(0);

    await waitFor(() => expect(result.current.itemsByCode.get('00700')?.score).toBe(55));
    expect(score.mock.calls[0]?.[0]?.signal?.aborted).toBe(true);
    expect(client.getQueryState(abandoned)).toBeUndefined();
    expect(client.getQueryState(nextKey)).toBeDefined();

    await act(async () => {
      first.resolve(scoreResponse([scoreItem('600519', 80), scoreItem('AAPL', 70)]));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.itemsByCode.get('00700')?.score).toBe(55);
    expect(result.current.itemsByCode.has('600519')).toBe(false);
    assertNoWatchlistPrefixOps(cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
    assertNoWatchlistPrefixOps(removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
  });

  it('exposes error plus empty data with no stale fallback', async () => {
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ refreshKey }: { refreshKey: string }) => useWatchlistScores(CODES, refreshKey),
      { wrapper, initialProps: { refreshKey: '' } },
    );

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.itemsByCode.get('600519')?.score).toBe(80);

    score.mockRejectedValueOnce(Object.assign(new Error('server'), { response: { status: 500 } }));
    rerender({ refreshKey: 'boom' });
    expect(result.current.status).toBe('loading');
    expect(result.current.itemsByCode.size).toBe(0);

    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.itemsByCode.size).toBe(0);
  });

  it('does not expose error when score settles as CancelledError', async () => {
    score.mockRejectedValue(new CancelledError(WATCHLIST_SCORES_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlistScores(CODES), { wrapper });

    await flushQueryMicrotasks(6);
    expect(result.current.status).not.toBe('error');
    expect(result.current.status).not.toBe('ready');
    expect(result.current.itemsByCode.size).toBe(0);
  });

  it('does not expose error or stale data when an aborted predecessor fails', async () => {
    const first = createDeferred<WatchlistScoreResponse>();
    score
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(scoreResponse([scoreItem('600519', 11), scoreItem('AAPL', 12)]));
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ refreshKey }: { refreshKey: string }) => useWatchlistScores(CODES, refreshKey),
      { wrapper, initialProps: { refreshKey: '' } },
    );

    await waitFor(() => expect(score).toHaveBeenCalledTimes(1));
    rerender({ refreshKey: 'next' });
    await waitFor(() => expect(result.current.itemsByCode.get('600519')?.score).toBe(11));

    await act(async () => {
      first.reject(Object.assign(new Error('server'), { response: { status: 500 } }));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.status).toBe('ready');
    expect(result.current.itemsByCode.get('600519')?.score).toBe(11);
  });

  it('fences a stale predecessor completion so it cannot overwrite a newer generation', async () => {
    const first = createDeferred<WatchlistScoreResponse>();
    const successor = createDeferred<WatchlistScoreResponse>();
    score
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(successor.promise);
    const { client, wrapper } = createWrapper();
    const firstKey = buildWatchlistScoresQueryKey(CODES_KEY, '');
    const nextKey = buildWatchlistScoresQueryKey(CODES_KEY, 'gen-2');
    const { result, rerender } = renderHook(
      ({ refreshKey }: { refreshKey: string }) => useWatchlistScores(CODES, refreshKey),
      { wrapper, initialProps: { refreshKey: '' } },
    );

    await waitFor(() => expect(score).toHaveBeenCalledTimes(1));
    rerender({ refreshKey: 'gen-2' });
    await waitFor(() => expect(score).toHaveBeenCalledTimes(2));

    await act(async () => {
      successor.resolve(scoreResponse([scoreItem('600519', 90), scoreItem('AAPL', 91)]));
    });
    await waitFor(() => expect(result.current.itemsByCode.get('600519')?.score).toBe(90));

    await act(async () => {
      first.resolve(scoreResponse([scoreItem('600519', 1), scoreItem('AAPL', 2)]));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.itemsByCode.get('600519')?.score).toBe(90);
    expect(result.current.status).toBe('ready');
    expect(queryFetchStatus(client, firstKey)).toBeUndefined();
    expect(queryFetchStatus(client, nextKey)).toBe('idle');
  });

  it('does not resurrect settled A while A→B(pending)→A starts a new A generation', async () => {
    const bPending = createDeferred<WatchlistScoreResponse>();
    const reusedA = createDeferred<WatchlistScoreResponse>();
    score
      .mockResolvedValueOnce(scoreResponse([scoreItem('600519', 80), scoreItem('AAPL', 70)]))
      .mockReturnValueOnce(bPending.promise)
      .mockReturnValueOnce(reusedA.promise);
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const aKey = buildWatchlistScoresQueryKey(CODES_KEY, '');
    const bKey = buildWatchlistScoresQueryKey(CODES_KEY, 'b');
    const { result, rerender } = renderHook(
      ({ refreshKey }: { refreshKey: string }) => useWatchlistScores(CODES, refreshKey),
      { wrapper, initialProps: { refreshKey: '' } },
    );

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.itemsByCode.get('600519')?.score).toBe(80);

    rerender({ refreshKey: 'b' });
    await waitFor(() => expect(score).toHaveBeenCalledTimes(2));
    expect(result.current.status).toBe('loading');
    expect(result.current.itemsByCode.size).toBe(0);

    rerender({ refreshKey: '' });
    expect(result.current.status).toBe('loading');
    expect(result.current.itemsByCode.size).toBe(0);
    expect(result.current.itemsByCode.get('600519')?.score).toBeUndefined();

    await waitFor(() => expect(score).toHaveBeenCalledTimes(3));
    expect(bPending.promise).toBeDefined();
    expect(score.mock.calls[1]?.[0]?.signal?.aborted).toBe(true);
    expect(client.getQueryState(bKey)).toBeUndefined();

    await act(async () => {
      reusedA.resolve(scoreResponse([scoreItem('600519', 11), scoreItem('AAPL', 12)]));
    });
    await waitFor(() => expect(result.current.itemsByCode.get('600519')?.score).toBe(11));

    await act(async () => {
      bPending.resolve(scoreResponse([scoreItem('600519', 99), scoreItem('AAPL', 98)]));
      await bPending.promise.catch(() => undefined);
    });

    expect(result.current.status).toBe('ready');
    expect(result.current.itemsByCode.get('600519')?.score).toBe(11);
    expect(queryFetchStatus(client, aKey)).toBe('idle');
    assertNoWatchlistPrefixOps(cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
    assertNoWatchlistPrefixOps(removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
  });

  it('does not resurrect settled A after A→empty→A', async () => {
    score
      .mockResolvedValueOnce(scoreResponse([scoreItem('600519', 80), scoreItem('AAPL', 70)]))
      .mockResolvedValueOnce(scoreResponse([scoreItem('600519', 11), scoreItem('AAPL', 12)]));
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const key = buildWatchlistScoresQueryKey(CODES_KEY, '');
    const { result, rerender } = renderHook(
      ({ codes }: { codes: readonly string[] }) => useWatchlistScores(codes),
      { wrapper, initialProps: { codes: CODES as readonly string[] } },
    );

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.itemsByCode.get('600519')?.score).toBe(80);

    rerender({ codes: [] });
    expect(result.current.status).toBe('idle');
    expect(result.current.itemsByCode.size).toBe(0);
    expect(client.getQueryState(key)).toBeUndefined();

    rerender({ codes: [...CODES] });
    expect(result.current.status).toBe('loading');
    expect(result.current.itemsByCode.size).toBe(0);
    expect(result.current.itemsByCode.get('600519')?.score).toBeUndefined();

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.itemsByCode.get('600519')?.score).toBe(11);
    expect(score).toHaveBeenCalledTimes(2);
    assertNoWatchlistPrefixOps(cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
    assertNoWatchlistPrefixOps(removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
  });

  it('does not resurrect a prior error signature while A→B(pending)→A reloads', async () => {
    const bPending = createDeferred<WatchlistScoreResponse>();
    score
      .mockRejectedValueOnce(Object.assign(new Error('server'), { response: { status: 500 } }))
      .mockReturnValueOnce(bPending.promise)
      .mockResolvedValueOnce(scoreResponse([scoreItem('600519', 11), scoreItem('AAPL', 12)]));
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ refreshKey }: { refreshKey: string }) => useWatchlistScores(CODES, refreshKey),
      { wrapper, initialProps: { refreshKey: '' } },
    );

    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.itemsByCode.size).toBe(0);

    rerender({ refreshKey: 'b' });
    await waitFor(() => expect(score).toHaveBeenCalledTimes(2));
    expect(result.current.status).toBe('loading');

    rerender({ refreshKey: '' });
    expect(result.current.status).toBe('loading');
    expect(result.current.itemsByCode.size).toBe(0);

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.itemsByCode.get('600519')?.score).toBe(11);
  });

  it('returns idle and cancels the previous fetch when codes become empty', async () => {
    const pending = createDeferred<WatchlistScoreResponse>();
    score.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const key = buildWatchlistScoresQueryKey(CODES_KEY, '');
    const { result, rerender } = renderHook(
      ({ codes }: { codes: readonly string[] }) => useWatchlistScores(codes),
      { wrapper, initialProps: { codes: CODES as readonly string[] } },
    );

    await waitFor(() => expect(score).toHaveBeenCalledTimes(1));
    rerender({ codes: [] });
    expect(result.current.status).toBe('idle');
    expect(result.current.itemsByCode.size).toBe(0);
    expect(score).toHaveBeenCalledTimes(1);
    expect(client.getQueryState(key)).toBeUndefined();

    await act(async () => {
      pending.resolve(scoreResponse([scoreItem('600519', 80), scoreItem('AAPL', 70)]));
      await pending.promise.catch(() => undefined);
    });
    expect(result.current.status).toBe('idle');
    expect(result.current.itemsByCode.size).toBe(0);
  });

  it('removes exact scores keys on unmount and ignores a late score failure', async () => {
    const pending = createDeferred<WatchlistScoreResponse>();
    score.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const key = buildWatchlistScoresQueryKey(CODES_KEY, '');
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result, unmount } = renderHook(() => useWatchlistScores(CODES), { wrapper });

    await waitFor(() => expect(score).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(Object.assign(new Error('server'), { response: { status: 500 } }));
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.status).toBe('loading');
    expect(client.getQueryState(key)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['watchlist', 'scores'] })).toHaveLength(0);
    expect(queryFetchStatus(client, key)).toBeUndefined();
    assertNoWatchlistPrefixOps(cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
    assertNoWatchlistPrefixOps(removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
  });

  it('keeps createUnanalyzedWatchlistScore as the unanalyzed placeholder', () => {
    expect(createUnanalyzedWatchlistScore('600519')).toEqual({
      stockCode: '600519',
      status: 'unanalyzed',
      score: null,
      asOf: null,
      ageDays: null,
      analysisId: null,
      operationAdvice: null,
      factors: [],
      freshness: 'none',
      degradedReasons: [],
    });
  });
});
