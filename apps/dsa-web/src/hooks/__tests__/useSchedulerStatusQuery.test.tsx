// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { systemConfigApi } from '../../api/systemConfig';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { SchedulerStatusResponse } from '../../types/systemConfig';
import {
  SCHEDULER_STATUS_CANCEL,
  SCHEDULER_STATUS_QUERY_KEY,
  SCHEDULER_STATUS_QUERY_SCHEDULE,
  fetchSchedulerStatus,
  useSchedulerStatusQuery,
} from '../useSchedulerStatusQuery';

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getSchedulerStatus: vi.fn(),
  },
}));

const getSchedulerStatus = vi.mocked(systemConfigApi.getSchedulerStatus);

function idleStatus(overrides: Partial<SchedulerStatusResponse> = {}): SchedulerStatusResponse {
  return {
    track: 'legacy_day_batch',
    enabled: true,
    running: false,
    attached: true,
    processMode: 'serve+schedule',
    scheduleTimezone: 'Asia/Shanghai',
    runNowAvailable: true,
    runNowBlockReason: null,
    scheduleTimes: ['09:20', '15:10'],
    nextRunAt: '2026-06-21T09:20:00+08:00',
    lastRunAt: null,
    lastSuccessAt: '2026-06-20T15:10:00+08:00',
    lastError: null,
    lastSkippedAt: null,
    lastSkipReason: null,
    activeRunId: null,
    lastRunId: null,
    lastRunOutcome: null,
    ...overrides,
  };
}

function serverError(): Error {
  return Object.assign(new Error('server'), {
    response: {
      status: 500,
      data: { error: 'internal', message: 'scheduler status unavailable' },
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
  queryKey: readonly unknown[] = SCHEDULER_STATUS_QUERY_KEY,
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertExactSchedulerOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'scheduler' && key.length === 1).toBe(false);
    expect(key[0] === 'settings').toBe(false);
    expect(key[0] === 'kronos').toBe(false);
    expect(key[0] === 'capabilities').toBe(false);
    if (key[0] === 'scheduler') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['scheduler', 'status']);
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

describe('useSchedulerStatusQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    getSchedulerStatus.mockResolvedValue(idleStatus());
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

  it('pins the exact scheduler key, schedule, and getSchedulerStatus() with no signal', async () => {
    expect([...SCHEDULER_STATUS_QUERY_KEY]).toEqual(['scheduler', 'status']);
    expect(SCHEDULER_STATUS_QUERY_KEY).toHaveLength(2);
    expect(SCHEDULER_STATUS_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(SCHEDULER_STATUS_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchSchedulerStatus({ signal: controller.signal });
    expect(getSchedulerStatus).toHaveBeenCalledTimes(1);
    expect(getSchedulerStatus.mock.calls[0]).toEqual([]);
  });

  it('is not barrel-exported and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useSchedulerStatusQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(
      () => useSchedulerStatusQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isRefreshingStatus).toBe(false));

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['scheduler', 'status']);
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
    }
    expect(
      client.getQueryCache().find({
        queryKey: SCHEDULER_STATUS_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(getSchedulerStatus.mock.calls[0]).toEqual([]);
    expect(result.current).not.toHaveProperty('isLoading');
    expect(result.current).not.toHaveProperty('isRefreshing');
  });

  it('fetches once on mount, sets status, and leaves zero live observers', async () => {
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(
      () => useSchedulerStatusQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isRefreshingStatus).toBe(false));
    expect(getSchedulerStatus).toHaveBeenCalledTimes(1);
    expect(result.current.status?.enabled).toBe(true);
    expect(result.current.status?.runNowAvailable).toBe(true);
    expect(result.current.statusError).toBeNull();
    expect(
      client.getQueryCache().find({
        queryKey: SCHEDULER_STATUS_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
  });

  it('skips GET when enabled is false and exact-removes the status key', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(
      () => useSchedulerStatusQuery({ enabled: false, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isRefreshingStatus).toBe(false));
    expect(getSchedulerStatus).not.toHaveBeenCalled();
    expect(result.current.status).toBeNull();
    expect(result.current.statusError).toBeNull();
    expect(client.getQueryState(SCHEDULER_STATUS_QUERY_KEY)).toBeUndefined();
    assertExactSchedulerOps(
      [...cancelSpy.mock.calls, ...removeSpy.mock.calls] as Array<
        [filters?: { queryKey?: readonly unknown[]; exact?: boolean }]
      >,
    );
  });

  it('shares one load path across mount, refreshToken change, and refresh()', async () => {
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ refreshToken }) => useSchedulerStatusQuery({ enabled: true, refreshToken }),
      { wrapper, initialProps: { refreshToken: 0 } },
    );

    await waitFor(() => expect(result.current.isRefreshingStatus).toBe(false));
    expect(getSchedulerStatus).toHaveBeenCalledTimes(1);

    rerender({ refreshToken: 1 });
    await waitFor(() => expect(getSchedulerStatus).toHaveBeenCalledTimes(2));

    await act(async () => {
      await result.current.refresh();
    });
    expect(getSchedulerStatus).toHaveBeenCalledTimes(3);
  });

  it('treats 200 running:false / runNowAvailable absent as a success payload', async () => {
    getSchedulerStatus.mockResolvedValueOnce(idleStatus({
      running: false,
      runNowAvailable: undefined,
      processMode: undefined,
    }));
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useSchedulerStatusQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isRefreshingStatus).toBe(false));
    expect(result.current.status?.running).toBe(false);
    expect(result.current.status?.runNowAvailable).toBeUndefined();
    expect(result.current.statusError).toBeNull();
  });

  it('removes the exact scheduler key on unmount and ignores a late 500', async () => {
    const pending = createDeferred<SchedulerStatusResponse>();
    getSchedulerStatus.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(
      () => useSchedulerStatusQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(getSchedulerStatus).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.statusError).toBeNull();
    expect(result.current.status).toBeNull();
    expect(client.getQueryState(SCHEDULER_STATUS_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['scheduler'] })).toHaveLength(0);
    expect(queryFetchStatus(client, SCHEDULER_STATUS_QUERY_KEY)).toBeUndefined();
  });

  it('lets a newer 500 win over a stale 200 so a later success cannot resurrect', async () => {
    const first = createDeferred<SchedulerStatusResponse>();
    getSchedulerStatus
      .mockReturnValueOnce(first.promise)
      .mockRejectedValueOnce(serverError());
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useSchedulerStatusQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(getSchedulerStatus).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.refresh();
    });
    await waitFor(() => expect(getSchedulerStatus).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.statusError?.status).toBe(500));

    expect(result.current.status).toBeNull();
    expect(result.current.isRefreshingStatus).toBe(false);

    await act(async () => {
      first.resolve(idleStatus({ enabled: true }));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.status).toBeNull();
    expect(result.current.statusError?.status).toBe(500);
  });

  it('lets a newer 200 disabled payload win over a stale 500', async () => {
    const first = createDeferred<SchedulerStatusResponse>();
    getSchedulerStatus
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(idleStatus({
        enabled: false,
        runNowAvailable: false,
        runNowBlockReason: 'scheduler_disabled',
      }));
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useSchedulerStatusQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(getSchedulerStatus).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.refresh();
    });
    await waitFor(() => expect(getSchedulerStatus).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.status?.enabled).toBe(false));

    expect(result.current.status?.runNowAvailable).toBe(false);
    expect(result.current.statusError).toBeNull();
    expect(result.current.isRefreshingStatus).toBe(false);

    await act(async () => {
      first.reject(serverError());
      await first.promise.catch(() => undefined);
    });

    expect(result.current.status?.enabled).toBe(false);
    expect(result.current.statusError).toBeNull();
  });

  it('keeps last-good status when a later refresh fails', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useSchedulerStatusQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.status?.enabled).toBe(true));

    getSchedulerStatus.mockRejectedValueOnce(serverError());
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.status?.enabled).toBe(true);
    expect(result.current.status?.runNowAvailable).toBe(true);
    expect(result.current.statusError?.status).toBe(500);
    expect(result.current.isRefreshingStatus).toBe(false);
  });

  it('fails closed on an initial 500 even when the test client default would retry', async () => {
    getSchedulerStatus.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(
      () => useSchedulerStatusQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.statusError).not.toBeNull());
    expect(getSchedulerStatus).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(result.current.status).toBeNull();
    expect(result.current.statusError?.status).toBe(500);
    expect(result.current.isRefreshingStatus).toBe(false);
  });

  it('does not set statusError when getSchedulerStatus settles as CancelledError', async () => {
    getSchedulerStatus.mockRejectedValue(new CancelledError(SCHEDULER_STATUS_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useSchedulerStatusQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isRefreshingStatus).toBe(false));
    expect(result.current.statusError).toBeNull();
    expect(result.current.status).toBeNull();
  });

  it('keeps empty classification false while a cancelled generation is still in flight', async () => {
    const pending = createDeferred<SchedulerStatusResponse>();
    getSchedulerStatus.mockReturnValueOnce(pending.promise);
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useSchedulerStatusQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(getSchedulerStatus).toHaveBeenCalledTimes(1));
    expect(result.current.isRefreshingStatus).toBe(true);
    expect(result.current.statusError).toBeNull();
    expect(result.current.status).toBeNull();
    const looksEmpty = !result.current.isRefreshingStatus
      && !result.current.statusError
      && !result.current.status;
    expect(looksEmpty).toBe(false);

    await act(async () => {
      pending.reject(new CancelledError(SCHEDULER_STATUS_CANCEL));
      await pending.promise.catch(() => undefined);
    });

    expect(result.current.statusError).toBeNull();
  });

  it('same-key refresh cancel+remove then fetchQuery and keeps last-good on failure', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(
      () => useSchedulerStatusQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.status?.enabled).toBe(true));
    expect(getSchedulerStatus).toHaveBeenCalledTimes(1);
    expect(result.current.isRefreshingStatus).toBe(false);

    const pending = createDeferred<SchedulerStatusResponse>();
    getSchedulerStatus.mockReturnValueOnce(pending.promise);
    await act(async () => {
      void result.current.refresh();
    });
    await waitFor(() => expect(result.current.isRefreshingStatus).toBe(true));
    expect(result.current).not.toHaveProperty('isLoading');

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.statusError).not.toBeNull());

    expect(result.current.status?.enabled).toBe(true);
    expect(result.current.statusError?.status).toBe(500);
    expect(result.current.isRefreshingStatus).toBe(false);
    expect(fetchSpy).toHaveBeenCalled();
    expect(cancelSpy).toHaveBeenCalled();
    expect(removeSpy).toHaveBeenCalled();

    const cancelOrders = cancelSpy.mock.invocationCallOrder;
    const removeOrders = removeSpy.mock.invocationCallOrder;
    const fetchOrders = fetchSpy.mock.invocationCallOrder;
    expect(Math.min(...cancelOrders)).toBeLessThan(Math.min(...fetchOrders));
    expect(Math.min(...removeOrders)).toBeLessThan(Math.min(...fetchOrders));
    assertExactSchedulerOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactSchedulerOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('never prefix-cancels or prefix-removes ["scheduler"] or ["settings"]', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(
      () => useSchedulerStatusQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isRefreshingStatus).toBe(false));
    await act(async () => {
      await result.current.refresh();
    });

    const allOps = [
      ...cancelSpy.mock.calls,
      ...removeSpy.mock.calls,
    ] as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>;
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey.length === 1
      && filters.queryKey[0] === 'scheduler'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'settings'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'kronos'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'capabilities'
    ))).toBe(false);
    assertExactSchedulerOps(allOps);
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(
      () => useSchedulerStatusQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isRefreshingStatus).toBe(false));
    expect(queryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(queryOptions(client)?.staleTime).toBe(0);
    expect(getSchedulerStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(getSchedulerStatus).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call getSchedulerStatus again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(
      () => useSchedulerStatusQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isRefreshingStatus).toBe(false));
    expect(getSchedulerStatus).toHaveBeenCalledTimes(1);
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

    expect(getSchedulerStatus).toHaveBeenCalledTimes(1);
  });

  it('issues getSchedulerStatus while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(
      () => useSchedulerStatusQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isRefreshingStatus).toBe(false));
    expect(getSchedulerStatus).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.networkMode).toBe('always');
    expect(result.current.status?.enabled).toBe(true);
  });
});
