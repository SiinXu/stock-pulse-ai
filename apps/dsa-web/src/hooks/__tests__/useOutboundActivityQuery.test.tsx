// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { outboundActivityApi } from '../../api/outboundActivity';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { LocalOnlyModeStatus, OutboundActivityItem, OutboundActivityPage } from '../../types/outboundActivity';
import {
  OUTBOUND_ACTIVITY_CANCEL,
  OUTBOUND_ACTIVITY_LIMIT,
  OUTBOUND_ACTIVITY_QUERY_KEY,
  OUTBOUND_ACTIVITY_QUERY_SCHEDULE,
  fetchOutboundActivity,
  useOutboundActivityQuery,
} from '../useOutboundActivityQuery';

vi.mock('../../api/outboundActivity', () => ({
  outboundActivityApi: {
    getLocalOnlyStatus: vi.fn(),
    listActivity: vi.fn(),
  },
}));

const getLocalOnlyStatus = vi.mocked(outboundActivityApi.getLocalOnlyStatus);
const listActivity = vi.mocked(outboundActivityApi.listActivity);

function localOnlyStatus(enabled = true): LocalOnlyModeStatus {
  return {
    enabled,
    envKey: 'LOCAL_ONLY_MODE',
    policy: 'non_loopback_denied',
    allowedDestinationClasses: ['loopback'],
    blockedErrorReason: 'local_only_mode_blocked',
  };
}

function activityItem(correlationId: string): OutboundActivityItem {
  return {
    occurredAt: '2026-08-06T12:00:00Z',
    decision: 'blocked',
    destinationClass: 'public_hostname',
    scheme: 'https',
    hostType: 'hostname',
    reason: 'local_only_mode_blocked',
    correlationId,
    localOnlyMode: true,
    allowlisted: false,
  };
}

function activityPage(items: OutboundActivityItem[]): OutboundActivityPage {
  return {
    localOnlyMode: true,
    limit: 50,
    returned: items.length,
    maxRetained: 100,
    items,
  };
}

function serverError(): Error {
  return Object.assign(new Error('server'), {
    response: {
      status: 500,
      data: { error: 'internal', message: 'outbound activity unavailable' },
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
  queryKey: readonly unknown[] = OUTBOUND_ACTIVITY_QUERY_KEY,
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertExactOutboundOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'outbound-activity' && key.length === 1).toBe(false);
    expect(key[0] === 'settings').toBe(false);
    expect(key[0] === 'kronos').toBe(false);
    expect(key[0] === 'data-providers').toBe(false);
    expect(key[0] === 'scorecard').toBe(false);
    if (key[0] === 'outbound-activity') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['outbound-activity', 'load']);
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

function mockSettledPair(
  status: LocalOnlyModeStatus = localOnlyStatus(),
  items: OutboundActivityItem[] = [activityItem('abcdef0123456789')],
) {
  getLocalOnlyStatus.mockResolvedValue(status);
  listActivity.mockResolvedValue(activityPage(items));
}

describe('useOutboundActivityQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    mockSettledPair();
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

  it('pins the exact load key, schedule, and atomic pair with no signal', async () => {
    expect([...OUTBOUND_ACTIVITY_QUERY_KEY]).toEqual(['outbound-activity', 'load']);
    expect(OUTBOUND_ACTIVITY_QUERY_KEY).toHaveLength(2);
    expect(OUTBOUND_ACTIVITY_LIMIT).toBe(50);
    expect(OUTBOUND_ACTIVITY_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(OUTBOUND_ACTIVITY_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchOutboundActivity({ signal: controller.signal });
    expect(getLocalOnlyStatus).toHaveBeenCalledTimes(1);
    expect(listActivity).toHaveBeenCalledTimes(1);
    expect(getLocalOnlyStatus.mock.calls[0]).toEqual([]);
    expect(listActivity.mock.calls[0]).toEqual([{ limit: 50 }]);
  });

  it('is not barrel-exported and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useOutboundActivityQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useOutboundActivityQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['outbound-activity', 'load']);
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
    }
    expect(
      client.getQueryCache().find({
        queryKey: OUTBOUND_ACTIVITY_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(getLocalOnlyStatus.mock.calls[0]).toEqual([]);
    expect(listActivity.mock.calls[0]).toEqual([{ limit: 50 }]);
  });

  it('starts both GETs atomically and does not apply a one-sided page', async () => {
    const pendingStatus = createDeferred<LocalOnlyModeStatus>();
    const pendingPage = createDeferred<OutboundActivityPage>();
    getLocalOnlyStatus.mockReturnValueOnce(pendingStatus.promise);
    listActivity.mockReturnValueOnce(pendingPage.promise);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useOutboundActivityQuery(), { wrapper });

    await waitFor(() => expect(getLocalOnlyStatus).toHaveBeenCalledTimes(1));
    expect(listActivity).toHaveBeenCalledTimes(1);
    expect(result.current.isLoading).toBe(true);
    expect(result.current.status).toBeNull();
    expect(result.current.items).toEqual([]);

    await act(async () => {
      pendingPage.resolve(activityPage([activityItem('only-items')]));
      await pendingPage.promise;
    });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.status).toBeNull();
    expect(result.current.items).toEqual([]);

    await act(async () => {
      pendingStatus.resolve(localOnlyStatus(true));
      await pendingStatus.promise;
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.status?.enabled).toBe(true);
    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0]?.correlationId).toBe('only-items');
    expect(result.current.loadError).toBeNull();
  });

  it('treats empty 200 items as success and does not set loadError', async () => {
    mockSettledPair(localOnlyStatus(false), []);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useOutboundActivityQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.status?.enabled).toBe(false);
    expect(result.current.items).toEqual([]);
    expect(result.current.loadError).toBeNull();
    expect(result.current.isRefreshing).toBe(false);
  });

  it('atomically clears status and items when one side of the pair fails', async () => {
    getLocalOnlyStatus.mockRejectedValueOnce(serverError());
    listActivity.mockResolvedValueOnce(activityPage([activityItem('should-not-stick')]));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useOutboundActivityQuery(), { wrapper });

    await waitFor(() => expect(result.current.loadError).not.toBeNull());
    expect(result.current.status).toBeNull();
    expect(result.current.items).toEqual([]);
    expect(result.current.loadError?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
  });

  it('preserves prior rows during refresh and only swaps after the new pair settles', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useOutboundActivityQuery(), { wrapper });
    await waitFor(() => expect(result.current.items[0]?.correlationId).toBe('abcdef0123456789'));

    const pendingStatus = createDeferred<LocalOnlyModeStatus>();
    const pendingPage = createDeferred<OutboundActivityPage>();
    getLocalOnlyStatus.mockReturnValueOnce(pendingStatus.promise);
    listActivity.mockReturnValueOnce(pendingPage.promise);

    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    expect(result.current.isLoading).toBe(false);
    expect(result.current.items[0]?.correlationId).toBe('abcdef0123456789');
    expect(result.current.status?.enabled).toBe(true);

    await act(async () => {
      pendingStatus.resolve(localOnlyStatus(false));
      pendingPage.resolve(activityPage([activityItem('refreshed')]));
      await Promise.all([pendingStatus.promise, pendingPage.promise]);
    });
    await waitFor(() => expect(result.current.isRefreshing).toBe(false));
    expect(result.current.status?.enabled).toBe(false);
    expect(result.current.items[0]?.correlationId).toBe('refreshed');
    expect(result.current.loadError).toBeNull();
  });

  it('removes the exact load key on unmount and ignores a late 500', async () => {
    const pendingStatus = createDeferred<LocalOnlyModeStatus>();
    const pendingPage = createDeferred<OutboundActivityPage>();
    getLocalOnlyStatus.mockReturnValueOnce(pendingStatus.promise);
    listActivity.mockReturnValueOnce(pendingPage.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useOutboundActivityQuery(), { wrapper });

    await waitFor(() => expect(getLocalOnlyStatus).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pendingStatus.reject(serverError());
      pendingPage.resolve(activityPage([activityItem('late')]));
      await pendingStatus.promise.catch(() => undefined);
      await pendingPage.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.loadError).toBeNull();
    expect(result.current.status).toBeNull();
    expect(result.current.items).toEqual([]);
    expect(client.getQueryState(OUTBOUND_ACTIVITY_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['outbound-activity'] })).toHaveLength(0);
    expect(queryFetchStatus(client, OUTBOUND_ACTIVITY_QUERY_KEY)).toBeUndefined();
  });

  it('lets a newer 500 win over a stale 200 so prior rows cannot resurrect', async () => {
    const firstStatus = createDeferred<LocalOnlyModeStatus>();
    const firstPage = createDeferred<OutboundActivityPage>();
    getLocalOnlyStatus
      .mockReturnValueOnce(firstStatus.promise)
      .mockRejectedValueOnce(serverError());
    listActivity
      .mockReturnValueOnce(firstPage.promise)
      .mockResolvedValueOnce(activityPage([activityItem('stale-items')]));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useOutboundActivityQuery(), { wrapper });

    await waitFor(() => expect(getLocalOnlyStatus).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(getLocalOnlyStatus).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.loadError?.status).toBe(500));

    expect(result.current.status).toBeNull();
    expect(result.current.items).toEqual([]);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);

    await act(async () => {
      firstStatus.resolve(localOnlyStatus(true));
      firstPage.resolve(activityPage([activityItem('stale')]));
      await firstStatus.promise.catch(() => undefined);
      await firstPage.promise.catch(() => undefined);
    });

    expect(result.current.status).toBeNull();
    expect(result.current.items).toEqual([]);
    expect(result.current.loadError?.status).toBe(500);
  });

  it('lets a newer empty 200 win over a stale 500 so ApiErrorAlert cannot replace it', async () => {
    const firstStatus = createDeferred<LocalOnlyModeStatus>();
    const firstPage = createDeferred<OutboundActivityPage>();
    getLocalOnlyStatus
      .mockReturnValueOnce(firstStatus.promise)
      .mockResolvedValueOnce(localOnlyStatus(false));
    listActivity
      .mockReturnValueOnce(firstPage.promise)
      .mockResolvedValueOnce(activityPage([]));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useOutboundActivityQuery(), { wrapper });

    await waitFor(() => expect(getLocalOnlyStatus).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(getLocalOnlyStatus).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.status?.enabled).toBe(false));

    expect(result.current.items).toEqual([]);
    expect(result.current.loadError).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);

    await act(async () => {
      firstStatus.reject(serverError());
      firstPage.resolve(activityPage([activityItem('stale-error-items')]));
      await firstStatus.promise.catch(() => undefined);
      await firstPage.promise.catch(() => undefined);
    });

    expect(result.current.status?.enabled).toBe(false);
    expect(result.current.items).toEqual([]);
    expect(result.current.loadError).toBeNull();
  });

  it('fails closed on a 500 even when the test client default would retry', async () => {
    getLocalOnlyStatus.mockRejectedValue(serverError());
    listActivity.mockResolvedValue(activityPage([activityItem('ignored')]));
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useOutboundActivityQuery(), { wrapper });

    await waitFor(() => expect(result.current.loadError).not.toBeNull());
    expect(getLocalOnlyStatus).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(result.current.status).toBeNull();
    expect(result.current.items).toEqual([]);
    expect(result.current.loadError?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);
  });

  it('does not set loadError when the pair settles as CancelledError', async () => {
    getLocalOnlyStatus.mockRejectedValue(new CancelledError(OUTBOUND_ACTIVITY_CANCEL));
    listActivity.mockResolvedValue(activityPage([activityItem('cancelled')]));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useOutboundActivityQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.loadError).toBeNull();
    expect(result.current.status).toBeNull();
    expect(result.current.items).toEqual([]);
  });

  it('same-key refresh cancel+remove then fetchQuery and clears both on failure', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useOutboundActivityQuery(), { wrapper });

    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(getLocalOnlyStatus).toHaveBeenCalledTimes(1);
    expect(listActivity).toHaveBeenCalledTimes(1);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);

    const pendingStatus = createDeferred<LocalOnlyModeStatus>();
    const pendingPage = createDeferred<OutboundActivityPage>();
    getLocalOnlyStatus.mockReturnValueOnce(pendingStatus.promise);
    listActivity.mockReturnValueOnce(pendingPage.promise);
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    expect(result.current.isLoading).toBe(false);
    expect(result.current.items).toHaveLength(1);

    await act(async () => {
      pendingStatus.reject(serverError());
      pendingPage.resolve(activityPage([activityItem('fail-refresh')]));
      await pendingStatus.promise.catch(() => undefined);
      await pendingPage.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.loadError).not.toBeNull());

    expect(result.current.status).toBeNull();
    expect(result.current.items).toEqual([]);
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
    assertExactOutboundOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactOutboundOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('never prefix-cancels or prefix-removes ["outbound-activity"] or ["settings"]', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useOutboundActivityQuery(), { wrapper });
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
      && filters.queryKey[0] === 'outbound-activity'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'settings'
    ))).toBe(false);
    assertExactOutboundOps(allOps);
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useOutboundActivityQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(queryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(queryOptions(client)?.staleTime).toBe(0);
    expect(getLocalOnlyStatus).toHaveBeenCalledTimes(1);
    expect(listActivity).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(getLocalOnlyStatus).toHaveBeenCalledTimes(1);
    expect(listActivity).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call the pair again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useOutboundActivityQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getLocalOnlyStatus).toHaveBeenCalledTimes(1);
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

    expect(getLocalOnlyStatus).toHaveBeenCalledTimes(1);
    expect(listActivity).toHaveBeenCalledTimes(1);
  });

  it('issues the pair while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useOutboundActivityQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getLocalOnlyStatus).toHaveBeenCalledTimes(1);
    expect(listActivity).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.networkMode).toBe('always');
    expect(result.current.items).toHaveLength(1);
  });
});
