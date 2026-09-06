// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { scorecardApi } from '../../api/scorecard';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { SignalScorecardResponse } from '../../types/scorecard';
import {
  SCORECARD_CANCEL,
  SCORECARD_PUBLIC_QUERY_KEY,
  SCORECARD_QUERY_SCHEDULE,
  fetchPublicScorecard,
  useSignalScorecardQuery,
} from '../useSignalScorecardQuery';

vi.mock('../../api/scorecard', () => ({
  scorecardApi: {
    getPublic: vi.fn(),
  },
}));

const getPublic = vi.mocked(scorecardApi.getPublic);

function payload(hitRatePct: number): SignalScorecardResponse {
  return {
    minSamples: 5,
    overall: {
      status: 'ok',
      sampleSize: 12,
      completed: 14,
      hitRatePct,
      avgReturnPct: 1.2,
    },
    bySignalTypeHorizon: [],
    returnDistribution: [],
    recentMisses: [],
  };
}

function notFoundError(): Error {
  return Object.assign(new Error('Public scorecard is not enabled'), {
    response: {
      status: 404,
      data: { error: 'not_found', message: 'Public scorecard is not enabled' },
    },
    parsedError: {
      title: 'Not found',
      message: 'Public scorecard is not enabled',
      rawMessage: 'Public scorecard is not enabled',
      status: 404,
      category: 'http_error' as const,
      code: 'not_found',
    },
  });
}

function serverError(): Error {
  return Object.assign(new Error('server'), {
    response: {
      status: 500,
      data: { error: 'internal', message: 'scorecard unavailable' },
    },
  });
}

function createWrapper(client?: QueryClient) {
  const queryClient = client ?? createAppQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return { client: queryClient, wrapper: Wrapper };
}

function queryOptions(
  client: QueryClient,
  queryKey: readonly unknown[] = SCORECARD_PUBLIC_QUERY_KEY,
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertExactScorecardPublicOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'scorecard' && key.length === 1).toBe(false);
    if (key[0] === 'scorecard') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['scorecard', 'public']);
      expect(key).toHaveLength(2);
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

describe('useSignalScorecardQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    getPublic.mockResolvedValue(payload(58.3));
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

  it('pins the exact public key, schedule, and getPublic() with no signal', async () => {
    expect([...SCORECARD_PUBLIC_QUERY_KEY]).toEqual(['scorecard', 'public']);
    expect(SCORECARD_PUBLIC_QUERY_KEY).toHaveLength(2);
    expect(SCORECARD_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(SCORECARD_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchPublicScorecard({ signal: controller.signal });
    expect(getPublic).toHaveBeenCalledTimes(1);
    expect(getPublic.mock.calls[0]).toEqual([]);
  });

  it('is not barrel-exported and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useSignalScorecardQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useSignalScorecardQuery(true), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['scorecard', 'public']);
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
    }
    expect(
      client.getQueryCache().find({
        queryKey: SCORECARD_PUBLIC_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(getPublic.mock.calls[0]).toEqual([]);
  });

  it('skips getPublic while publicEnabled is false and leaves no query row', async () => {
    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useSignalScorecardQuery(false), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getPublic).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.current.data).toBeNull();
    expect(result.current.loadError).toBeNull();
    expect(result.current.isRefreshing).toBe(false);
    expect(client.getQueryState(SCORECARD_PUBLIC_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['scorecard'] })).toHaveLength(0);
    expect(cancelSpy).toHaveBeenCalled();
    expect(removeSpy).toHaveBeenCalled();
    assertExactScorecardPublicOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactScorecardPublicOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('disables in flight with exact-key silent cancel+remove and ignores a late 200', async () => {
    const pending = createDeferred<SignalScorecardResponse>();
    getPublic.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result, rerender } = renderHook(
      ({ publicEnabled }: { publicEnabled: boolean }) => useSignalScorecardQuery(publicEnabled),
      { wrapper, initialProps: { publicEnabled: true } },
    );

    await waitFor(() => expect(getPublic).toHaveBeenCalledTimes(1));
    expect(result.current.isLoading).toBe(true);
    expect(result.current.isRefreshing).toBe(false);

    rerender({ publicEnabled: false });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data).toBeNull();
    expect(result.current.loadError).toBeNull();
    expect(result.current.isRefreshing).toBe(false);
    expect(getPublic).toHaveBeenCalledTimes(1);
    expect(client.getQueryState(SCORECARD_PUBLIC_QUERY_KEY)).toBeUndefined();

    await act(async () => {
      pending.resolve(payload(99));
      await pending.promise.catch(() => undefined);
    });

    expect(result.current.data).toBeNull();
    expect(result.current.loadError).toBeNull();
    expect(getPublic).toHaveBeenCalledTimes(1);
    expect(cancelSpy).toHaveBeenCalledWith(
      { queryKey: SCORECARD_PUBLIC_QUERY_KEY, exact: true },
      SCORECARD_CANCEL,
    );
    expect(removeSpy).toHaveBeenCalledWith(
      { queryKey: SCORECARD_PUBLIC_QUERY_KEY, exact: true },
    );
    assertExactScorecardPublicOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactScorecardPublicOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('removes the exact public key on unmount and ignores a late 500', async () => {
    const pending = createDeferred<SignalScorecardResponse>();
    getPublic.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useSignalScorecardQuery(true), { wrapper });

    await waitFor(() => expect(getPublic).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.loadError).toBeNull();
    expect(result.current.data).toBeNull();
    expect(client.getQueryState(SCORECARD_PUBLIC_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['scorecard'] })).toHaveLength(0);
    expect(queryFetchStatus(client, SCORECARD_PUBLIC_QUERY_KEY)).toBeUndefined();
  });

  it('lets a newer 404 win over a stale 200 so stats cannot resurrect', async () => {
    const first = createDeferred<SignalScorecardResponse>();
    getPublic
      .mockReturnValueOnce(first.promise)
      .mockRejectedValueOnce(notFoundError());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useSignalScorecardQuery(true), { wrapper });

    await waitFor(() => expect(getPublic).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(getPublic).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.loadError?.status).toBe(404));

    expect(result.current.data).toBeNull();
    expect(result.current.loadError?.code).toBe('not_found');
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);

    await act(async () => {
      first.resolve(payload(58.3));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.data).toBeNull();
    expect(result.current.loadError?.status).toBe(404);
    expect(result.current.loadError?.code).toBe('not_found');
  });

  it('fails closed on a 500 even when the test client default would retry', async () => {
    getPublic.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useSignalScorecardQuery(true), { wrapper });

    await waitFor(() => expect(result.current.loadError).not.toBeNull());
    expect(getPublic).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(result.current.data).toBeNull();
    expect(result.current.loadError?.status).toBe(500);
    expect(result.current.loadError?.code).not.toBe('not_found');
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);
  });

  it('does not set loadError when getPublic settles as CancelledError', async () => {
    getPublic.mockRejectedValue(new CancelledError(SCORECARD_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useSignalScorecardQuery(true), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.loadError).toBeNull();
    expect(result.current.data).toBeNull();
    expect(result.current.loadError?.status).not.toBe(404);
  });

  it('same-key refresh cancel+remove then fetchQuery and clears data on failure', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useSignalScorecardQuery(true), { wrapper });

    await waitFor(() => expect(result.current.data?.overall.hitRatePct).toBe(58.3));
    expect(getPublic).toHaveBeenCalledTimes(1);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);

    const pending = createDeferred<SignalScorecardResponse>();
    getPublic.mockReturnValueOnce(pending.promise);
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    expect(result.current.isLoading).toBe(false);

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.loadError).not.toBeNull());

    expect(result.current.data).toBeNull();
    expect(result.current.loadError?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);
    expect(fetchSpy).toHaveBeenCalled();
    expect(cancelSpy).toHaveBeenCalled();
    expect(removeSpy).toHaveBeenCalled();

    const cancelOrders = cancelSpy.mock.invocationCallOrder;
    const removeOrders = removeSpy.mock.invocationCallOrder;
    const fetchOrders = fetchSpy.mock.invocationCallOrder;
    expect(Math.min(...cancelOrders)).toBeLessThan(Math.min(...fetchOrders));
    expect(Math.min(...removeOrders)).toBeLessThan(Math.min(...fetchOrders));
    assertExactScorecardPublicOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactScorecardPublicOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('never prefix-cancels or prefix-removes ["scorecard"]', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useSignalScorecardQuery(true), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.load('refresh');
    });

    const allOps = [
      ...cancelSpy.mock.calls,
      ...removeSpy.mock.calls,
    ] as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>;
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey.length === 1
      && filters.queryKey[0] === 'scorecard'
    ))).toBe(false);
    assertExactScorecardPublicOps(allOps);
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useSignalScorecardQuery(true), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(queryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(queryOptions(client)?.staleTime).toBe(0);
    expect(getPublic).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(getPublic).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call getPublic again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useSignalScorecardQuery(true), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getPublic).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.refetchInterval).toBeUndefined();

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

    expect(getPublic).toHaveBeenCalledTimes(1);
  });

  it('issues getPublic while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useSignalScorecardQuery(true), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getPublic).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.networkMode).toBe('always');
    expect(result.current.data?.overall.hitRatePct).toBe(58.3);
  });
});
