// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { usageApi } from '../../api/usage';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { UsageDashboard, UsagePeriod } from '../../api/usage';
import {
  TOKEN_USAGE_CANCEL,
  TOKEN_USAGE_DASHBOARD_LIMIT,
  TOKEN_USAGE_QUERY_SCHEDULE,
  buildTokenUsageDashboardQueryKey,
  fetchTokenUsageDashboard,
  useTokenUsageQuery,
} from '../useTokenUsageQuery';

vi.mock('../../api/usage', () => ({
  usageApi: {
    getDashboard: vi.fn(),
  },
}));

const getDashboard = vi.mocked(usageApi.getDashboard);

function payload(period: UsagePeriod, totalTokens: number): UsageDashboard {
  return {
    period,
    fromDate: '2026-06-01',
    toDate: '2026-06-11',
    totalCalls: totalTokens === 0 ? 0 : 3,
    totalPromptTokens: 120,
    totalCompletionTokens: 280,
    totalTokens,
    byCallType: [],
    byModel: [],
    recentCalls: [],
  };
}

function createWrapper(client?: QueryClient) {
  const queryClient = client ?? createAppQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return { client: queryClient, wrapper: Wrapper };
}

function dashboardOptions(
  client: QueryClient,
  queryKey: readonly unknown[] = buildTokenUsageDashboardQueryKey('month'),
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertNoUsagePrefixOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'usage' && key.length === 1).toBe(false);
    if (key[0] === 'usage') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['usage', 'dashboard', key[2]]);
      expect(key).toHaveLength(3);
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

describe('useTokenUsageQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    getDashboard.mockResolvedValue(payload('month', 400));
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

  it('pins the exact dashboard key, schedule, and getDashboard({period, limit: 50})', async () => {
    expect(buildTokenUsageDashboardQueryKey('month')).toEqual(['usage', 'dashboard', 'month']);
    expect(TOKEN_USAGE_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(TOKEN_USAGE_DASHBOARD_LIMIT).toBe(50);
    await fetchTokenUsageDashboard({ period: 'month' });
    expect(getDashboard).toHaveBeenCalledTimes(1);
    expect(getDashboard).toHaveBeenCalledWith({ period: 'month', limit: 50 });
  });

  it('does not auto-retry a 5xx load when the QueryClient default would retry', async () => {
    getDashboard.mockRejectedValue(Object.assign(new Error('server'), { response: { status: 500 } }));
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useTokenUsageQuery('month'), { wrapper });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(getDashboard).toHaveBeenCalledTimes(1);
    expect(dashboardOptions(client)?.retry).toBe(false);
    expect(result.current.dashboard).toBeNull();
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useTokenUsageQuery('month'), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(dashboardOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(dashboardOptions(client)?.retry).toBe(false);
    expect(dashboardOptions(client)?.staleTime).toBe(0);
    expect(getDashboard).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(getDashboard).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call getDashboard again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useTokenUsageQuery('month'), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getDashboard).toHaveBeenCalledTimes(1);
    expect(dashboardOptions(client)?.refetchInterval).toBeUndefined();

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

    expect(getDashboard).toHaveBeenCalledTimes(1);
  });

  it('issues getDashboard while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useTokenUsageQuery('month'), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getDashboard).toHaveBeenCalledTimes(1);
    expect(dashboardOptions(client)?.networkMode).toBe('always');
    expect(result.current.dashboard?.totalTokens).toBe(400);
  });

  it('schedules through fetchQuery with no live observer', async () => {
    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useTokenUsageQuery('month'), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['usage', 'dashboard', 'month']);
    }
    const key = buildTokenUsageDashboardQueryKey('month');
    expect(client.getQueryCache().find({ queryKey: key, exact: true })?.getObserversCount()).toBe(0);
  });

  it('cancels the previous period key and ignores its late response', async () => {
    const first = createDeferred<UsageDashboard>();
    getDashboard
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(payload('today', 900));
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const abandoned = buildTokenUsageDashboardQueryKey('month');
    const nextKey = buildTokenUsageDashboardQueryKey('today');
    const { result, rerender } = renderHook(
      ({ period }: { period: UsagePeriod }) => useTokenUsageQuery(period),
      { wrapper, initialProps: { period: 'month' } },
    );

    await waitFor(() => expect(getDashboard).toHaveBeenCalledTimes(1));
    rerender({ period: 'today' });

    await waitFor(() => expect(result.current.dashboard?.totalTokens).toBe(900));
    expect(client.getQueryState(abandoned)).toBeUndefined();
    expect(client.getQueryState(nextKey)).toBeDefined();
    expect(getDashboard).toHaveBeenLastCalledWith({ period: 'today', limit: 50 });

    await act(async () => {
      first.resolve(payload('month', 400));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.dashboard?.totalTokens).toBe(900);
    expect(result.current.error).toBeNull();
    assertNoUsagePrefixOps(cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
    assertNoUsagePrefixOps(removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
  });

  it('same-key refresh cancel+remove then fetchQuery keeps last-good on failure', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useTokenUsageQuery('month'), { wrapper });

    await waitFor(() => expect(result.current.dashboard?.totalTokens).toBe(400));
    expect(getDashboard).toHaveBeenCalledTimes(1);

    getDashboard.mockRejectedValueOnce(new Error('refresh unavailable'));
    await act(async () => {
      await result.current.load();
    });

    expect(result.current.error).not.toBeNull();
    expect(result.current.dashboard?.totalTokens).toBe(400);
    expect(result.current.loading).toBe(false);
    expect(fetchSpy).toHaveBeenCalled();
    expect(cancelSpy).toHaveBeenCalled();
    expect(removeSpy).toHaveBeenCalled();
    assertNoUsagePrefixOps(cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
  });

  it('hides the previous-period snapshot when the new period fails', async () => {
    getDashboard.mockResolvedValueOnce(payload('month', 400));
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ period }: { period: UsagePeriod }) => useTokenUsageQuery(period),
      { wrapper, initialProps: { period: 'month' } },
    );

    await waitFor(() => expect(result.current.dashboard?.totalTokens).toBe(400));

    getDashboard.mockRejectedValueOnce(new Error('today unavailable'));
    rerender({ period: 'today' });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.dashboard).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it('does not setError when getDashboard settles as CancelledError', async () => {
    getDashboard.mockRejectedValue(new CancelledError(TOKEN_USAGE_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useTokenUsageQuery('month'), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.dashboard).toBeNull();
  });

  it('fences a stale predecessor completion so it cannot overwrite a newer generation', async () => {
    const first = createDeferred<UsageDashboard>();
    const successor = createDeferred<UsageDashboard>();
    getDashboard
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(successor.promise);
    const { client, wrapper } = createWrapper();
    const key = buildTokenUsageDashboardQueryKey('month');
    const { result } = renderHook(() => useTokenUsageQuery('month'), { wrapper });

    await waitFor(() => expect(getDashboard).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load();
    });
    await waitFor(() => expect(getDashboard).toHaveBeenCalledTimes(2));

    await act(async () => {
      successor.resolve(payload('month', 900));
    });
    await waitFor(() => expect(result.current.dashboard?.totalTokens).toBe(900));

    await act(async () => {
      first.resolve(payload('month', 400));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.dashboard?.totalTokens).toBe(900);
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(queryFetchStatus(client, key)).toBe('idle');
  });

  it('uses the same load path for Refresh and period-key changes', async () => {
    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result, rerender } = renderHook(
      ({ period }: { period: UsagePeriod }) => useTokenUsageQuery(period),
      { wrapper, initialProps: { period: 'month' } },
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getDashboard).toHaveBeenCalledTimes(1);
    const firstLoad = result.current.load;

    await act(async () => {
      await result.current.load();
    });
    expect(result.current.load).toBe(firstLoad);
    expect(getDashboard).toHaveBeenCalledTimes(2);
    expect(getDashboard.mock.calls[1][0]).toEqual({ period: 'month', limit: 50 });

    getDashboard.mockResolvedValueOnce(payload('today', 900));
    rerender({ period: 'today' });
    await waitFor(() => expect(getDashboard).toHaveBeenCalledTimes(3));
    expect(result.current.load).toBe(firstLoad);
    expect(getDashboard.mock.calls[2][0]).toEqual({ period: 'today', limit: 50 });

    for (const [options] of fetchSpy.mock.calls) {
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.queryFn).toEqual(expect.any(Function));
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
    }
  });

  it('removes exact dashboard keys on unmount and ignores a late getDashboard failure', async () => {
    const pending = createDeferred<UsageDashboard>();
    getDashboard.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const key = buildTokenUsageDashboardQueryKey('month');
    const { result, unmount } = renderHook(() => useTokenUsageQuery('month'), { wrapper });

    await waitFor(() => expect(getDashboard).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(Object.assign(new Error('server'), { response: { status: 500 } }));
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.error).toBeNull();
    expect(client.getQueryState(key)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['usage', 'dashboard'] })).toHaveLength(0);
    expect(queryFetchStatus(client, key)).toBeUndefined();
  });
});
