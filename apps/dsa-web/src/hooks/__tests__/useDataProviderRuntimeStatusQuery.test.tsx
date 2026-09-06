// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { systemConfigApi } from '../../api/systemConfig';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { DataProviderRuntimeStatusResponse } from '../../types/systemConfig';
import {
  DATA_PROVIDER_RUNTIME_CANCEL,
  DATA_PROVIDER_RUNTIME_QUERY_SCHEDULE,
  DATA_PROVIDER_RUNTIME_STATUS_QUERY_KEY,
  fetchDataProviderRuntimeStatus,
  useDataProviderRuntimeStatusQuery,
} from '../useDataProviderRuntimeStatusQuery';

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getDataProviderRuntimeStatus: vi.fn(),
  },
}));

const getDataProviderRuntimeStatus = vi.mocked(systemConfigApi.getDataProviderRuntimeStatus);

function okStatus(): DataProviderRuntimeStatusResponse {
  return {
    schemaVersion: 'data_provider_runtime_status_v1',
    asOf: '2026-08-12T00:00:00+00:00',
    partial: false,
    sourceState: 'ok',
    errorCode: null,
    errorMessage: null,
    markets: [
      {
        market: 'cn',
        dataType: 'daily_data',
        orderedProviderIds: ['akshare', 'tushare'],
        primaryProviderId: 'akshare',
        fallbackProviderIds: ['tushare'],
        primarySelection: 'first_eligible_with_health',
        quality: 'ok',
        asOf: null,
      },
    ],
    providers: [
      {
        providerId: 'akshare',
        displayName: 'AkshareFetcher',
        role: 'baseline',
        markets: ['cn'],
        capabilities: ['daily_data'],
        configured: null,
        available: true,
        healthStatus: 'healthy',
        healthScore: 95,
        circuitState: 'closed',
        sampleCount: 3,
        staticPriority: 5,
        lastSuccessAt: '2026-08-12T00:00:00+00:00',
        lastFailureAt: null,
        failureReason: null,
        isPrimaryFor: ['daily_data:cn'],
        isFallbackFor: [],
        configDirectory: false,
      },
    ],
    cache: {
      enabled: true,
      fetchMode: 'remote_first',
      hits: 2,
      misses: 1,
      staleHits: 0,
      writes: 1,
      quality: 'active',
      note: null,
    },
  };
}

function partialStatus(): DataProviderRuntimeStatusResponse {
  return {
    schemaVersion: 'data_provider_runtime_status_v1',
    asOf: '2026-08-12T00:00:00+00:00',
    partial: true,
    sourceState: 'not_initialized',
    errorCode: 'data_runtime_not_initialized',
    errorMessage: 'Data provider runtime is not initialized in this process.',
    markets: [],
    providers: [],
    cache: null,
  };
}

function serverError(): Error {
  return Object.assign(new Error('server'), {
    response: {
      status: 500,
      data: { error: 'internal', message: 'runtime status unavailable' },
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
  queryKey: readonly unknown[] = DATA_PROVIDER_RUNTIME_STATUS_QUERY_KEY,
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertExactRuntimeOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'data-providers' && key.length === 1).toBe(false);
    expect(key[0] === 'settings').toBe(false);
    if (key[0] === 'data-providers') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['data-providers', 'runtime-status']);
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

describe('useDataProviderRuntimeStatusQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    getDataProviderRuntimeStatus.mockResolvedValue(okStatus());
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

  it('pins the exact runtime key, schedule, and getDataProviderRuntimeStatus() with no signal', async () => {
    expect([...DATA_PROVIDER_RUNTIME_STATUS_QUERY_KEY]).toEqual(['data-providers', 'runtime-status']);
    expect(DATA_PROVIDER_RUNTIME_STATUS_QUERY_KEY).toHaveLength(2);
    expect(DATA_PROVIDER_RUNTIME_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(DATA_PROVIDER_RUNTIME_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchDataProviderRuntimeStatus({ signal: controller.signal });
    expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(1);
    expect(getDataProviderRuntimeStatus.mock.calls[0]).toEqual([]);
  });

  it('is not barrel-exported and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useDataProviderRuntimeStatusQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useDataProviderRuntimeStatusQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['data-providers', 'runtime-status']);
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
    }
    expect(
      client.getQueryCache().find({
        queryKey: DATA_PROVIDER_RUNTIME_STATUS_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(getDataProviderRuntimeStatus.mock.calls[0]).toEqual([]);
    expect(result.current).not.toHaveProperty('isRefreshing');
  });

  it('fetches once on mount, sets status, and leaves zero live observers', async () => {
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useDataProviderRuntimeStatusQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(1);
    expect(result.current.status?.sourceState).toBe('ok');
    expect(result.current.status?.providers[0]?.providerId).toBe('akshare');
    expect(result.current.error).toBeNull();
    expect(
      client.getQueryCache().find({
        queryKey: DATA_PROVIDER_RUNTIME_STATUS_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
  });

  it('treats 200 partial / not_initialized as success payload', async () => {
    getDataProviderRuntimeStatus.mockResolvedValue(partialStatus());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useDataProviderRuntimeStatusQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.status?.partial).toBe(true);
    expect(result.current.status?.sourceState).toBe('not_initialized');
    expect(result.current.status?.markets).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it('removes the exact runtime key on unmount and ignores a late 500', async () => {
    const pending = createDeferred<DataProviderRuntimeStatusResponse>();
    getDataProviderRuntimeStatus.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useDataProviderRuntimeStatusQuery(), { wrapper });

    await waitFor(() => expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.error).toBeNull();
    expect(result.current.status).toBeNull();
    expect(client.getQueryState(DATA_PROVIDER_RUNTIME_STATUS_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['data-providers'] })).toHaveLength(0);
    expect(queryFetchStatus(client, DATA_PROVIDER_RUNTIME_STATUS_QUERY_KEY)).toBeUndefined();
  });

  it('lets a newer 500 win over a stale 200 so healthy rows cannot resurrect', async () => {
    const first = createDeferred<DataProviderRuntimeStatusResponse>();
    getDataProviderRuntimeStatus
      .mockReturnValueOnce(first.promise)
      .mockRejectedValueOnce(serverError());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useDataProviderRuntimeStatusQuery(), { wrapper });

    await waitFor(() => expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.refresh();
    });
    await waitFor(() => expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.error?.status).toBe(500));

    expect(result.current.status).toBeNull();
    expect(result.current.isLoading).toBe(false);

    await act(async () => {
      first.resolve(okStatus());
      await first.promise.catch(() => undefined);
    });

    expect(result.current.status).toBeNull();
    expect(result.current.error?.status).toBe(500);
  });

  it('lets a newer 200-partial win over a stale 500 so ApiErrorAlert cannot replace it', async () => {
    const first = createDeferred<DataProviderRuntimeStatusResponse>();
    getDataProviderRuntimeStatus
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(partialStatus());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useDataProviderRuntimeStatusQuery(), { wrapper });

    await waitFor(() => expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.refresh();
    });
    await waitFor(() => expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.status?.sourceState).toBe('not_initialized'));

    expect(result.current.status?.markets).toEqual([]);
    expect(result.current.error).toBeNull();
    expect(result.current.isLoading).toBe(false);

    await act(async () => {
      first.reject(serverError());
      await first.promise.catch(() => undefined);
    });

    expect(result.current.status?.sourceState).toBe('not_initialized');
    expect(result.current.status?.markets).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it('fails closed on a 500 even when the test client default would retry', async () => {
    getDataProviderRuntimeStatus.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useDataProviderRuntimeStatusQuery(), { wrapper });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(result.current.status).toBeNull();
    expect(result.current.error?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
  });

  it('does not set error when getDataProviderRuntimeStatus settles as CancelledError', async () => {
    getDataProviderRuntimeStatus.mockRejectedValue(new CancelledError(DATA_PROVIDER_RUNTIME_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useDataProviderRuntimeStatusQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.status).toBeNull();
  });

  it('keeps empty classification false while a cancelled generation is still in flight', async () => {
    const pending = createDeferred<DataProviderRuntimeStatusResponse>();
    getDataProviderRuntimeStatus.mockReturnValueOnce(pending.promise);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useDataProviderRuntimeStatusQuery(), { wrapper });

    await waitFor(() => expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(1));
    expect(result.current.isLoading).toBe(true);
    expect(result.current.error).toBeNull();
    expect(result.current.status).toBeNull();
    const looksEmpty = !result.current.isLoading && !result.current.error && !result.current.status;
    expect(looksEmpty).toBe(false);

    await act(async () => {
      pending.reject(new CancelledError(DATA_PROVIDER_RUNTIME_CANCEL));
      await pending.promise.catch(() => undefined);
    });

    expect(result.current.error).toBeNull();
  });

  it('same-key refresh cancel+remove then fetchQuery and clears status on failure', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useDataProviderRuntimeStatusQuery(), { wrapper });

    await waitFor(() => expect(result.current.status?.sourceState).toBe('ok'));
    expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(1);
    expect(result.current.isLoading).toBe(false);

    const pending = createDeferred<DataProviderRuntimeStatusResponse>();
    getDataProviderRuntimeStatus.mockReturnValueOnce(pending.promise);
    await act(async () => {
      void result.current.refresh();
    });
    await waitFor(() => expect(result.current.isLoading).toBe(true));
    expect(result.current).not.toHaveProperty('isRefreshing');

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.error).not.toBeNull());

    expect(result.current.status).toBeNull();
    expect(result.current.error?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
    expect(fetchSpy).toHaveBeenCalled();
    expect(cancelSpy).toHaveBeenCalled();
    expect(removeSpy).toHaveBeenCalled();

    const cancelOrders = cancelSpy.mock.invocationCallOrder;
    const removeOrders = removeSpy.mock.invocationCallOrder;
    const fetchOrders = fetchSpy.mock.invocationCallOrder;
    expect(Math.min(...cancelOrders)).toBeLessThan(Math.min(...fetchOrders));
    expect(Math.min(...removeOrders)).toBeLessThan(Math.min(...fetchOrders));
    assertExactRuntimeOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactRuntimeOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('never prefix-cancels or prefix-removes ["data-providers"] or ["settings"]', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useDataProviderRuntimeStatusQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
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
      && filters.queryKey[0] === 'data-providers'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'settings'
    ))).toBe(false);
    assertExactRuntimeOps(allOps);
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useDataProviderRuntimeStatusQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(queryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(queryOptions(client)?.staleTime).toBe(0);
    expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call getDataProviderRuntimeStatus again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useDataProviderRuntimeStatusQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(1);
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

    expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(1);
  });

  it('issues getDataProviderRuntimeStatus while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useDataProviderRuntimeStatusQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.networkMode).toBe('always');
    expect(result.current.status?.sourceState).toBe('ok');
  });
});
