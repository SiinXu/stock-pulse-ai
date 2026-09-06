// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { systemConfigApi } from '../../api/systemConfig';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { KronosStatusResponse } from '../../types/systemConfig';
import {
  KRONOS_STATUS_CANCEL,
  KRONOS_STATUS_QUERY_KEY,
  KRONOS_STATUS_QUERY_SCHEDULE,
  fetchKronosStatus,
  useKronosStatusQuery,
} from '../useKronosStatusQuery';

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getKronosStatus: vi.fn(),
  },
}));

const getKronosStatus = vi.mocked(systemConfigApi.getKronosStatus);

function readyStatus(): KronosStatusResponse {
  return {
    enabled: true,
    modelSize: 'mini',
    ready: true,
    reason: 'ready',
    message: 'Kronos is ready.',
    nextStep: 'Use the Kronos agent tool.',
    dependenciesInstalled: true,
    dependencies: [{ name: 'torch', available: true }],
    weightsPresent: true,
    weightsTotalBytes: 1024,
    weightsModifiedAt: '2026-08-05T00:00:00+00:00',
    packagedDesktop: false,
    installSupported: true,
    downloadSizeHint: null,
  };
}

function needsActionStatus(): KronosStatusResponse {
  return {
    enabled: false,
    modelSize: 'mini',
    ready: false,
    reason: 'disabled',
    message: 'Kronos agent tool is disabled.',
    nextStep: 'Install optional deps then enable.',
    dependenciesInstalled: false,
    dependencies: [
      { name: 'torch', available: false },
      { name: 'huggingface_hub', available: false },
    ],
    weightsPresent: false,
    weightsTotalBytes: null,
    weightsModifiedAt: null,
    packagedDesktop: false,
    installSupported: true,
    downloadSizeHint: '~40 MB (Kronos-mini + Kronos-Tokenizer-2k)',
  };
}

function packagedDesktopStatus(): KronosStatusResponse {
  return {
    enabled: true,
    modelSize: 'mini',
    ready: false,
    reason: 'packaged_desktop_unsupported',
    message: 'Ready but desktop blocked.',
    nextStep: 'Use a source install.',
    dependenciesInstalled: true,
    dependencies: [{ name: 'torch', available: true }],
    weightsPresent: true,
    weightsTotalBytes: 1024,
    weightsModifiedAt: '2026-08-05T00:00:00+00:00',
    packagedDesktop: true,
    installSupported: false,
    downloadSizeHint: null,
  };
}

function serverError(): Error {
  return Object.assign(new Error('server'), {
    response: {
      status: 500,
      data: { error: 'internal', message: 'kronos status unavailable' },
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
  queryKey: readonly unknown[] = KRONOS_STATUS_QUERY_KEY,
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertExactKronosOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'kronos' && key.length === 1).toBe(false);
    expect(key[0] === 'settings').toBe(false);
    expect(key[0] === 'data-providers').toBe(false);
    expect(key[0] === 'scorecard').toBe(false);
    if (key[0] === 'kronos') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['kronos', 'status']);
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

describe('useKronosStatusQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    getKronosStatus.mockResolvedValue(readyStatus());
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

  it('pins the exact kronos key, schedule, and getKronosStatus() with no signal', async () => {
    expect([...KRONOS_STATUS_QUERY_KEY]).toEqual(['kronos', 'status']);
    expect(KRONOS_STATUS_QUERY_KEY).toHaveLength(2);
    expect(KRONOS_STATUS_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(KRONOS_STATUS_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchKronosStatus({ signal: controller.signal });
    expect(getKronosStatus).toHaveBeenCalledTimes(1);
    expect(getKronosStatus.mock.calls[0]).toEqual([]);
  });

  it('is not barrel-exported and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useKronosStatusQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useKronosStatusQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['kronos', 'status']);
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
    }
    expect(
      client.getQueryCache().find({
        queryKey: KRONOS_STATUS_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(getKronosStatus.mock.calls[0]).toEqual([]);
    expect(result.current).not.toHaveProperty('isRefreshing');
  });

  it('fetches once on mount, sets status, and leaves zero live observers', async () => {
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useKronosStatusQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getKronosStatus).toHaveBeenCalledTimes(1);
    expect(result.current.status?.ready).toBe(true);
    expect(result.current.status?.modelSize).toBe('mini');
    expect(result.current.error).toBeNull();
    expect(
      client.getQueryCache().find({
        queryKey: KRONOS_STATUS_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
  });

  it('treats 200 ready:false / missing deps / packagedDesktop as success payload', async () => {
    getKronosStatus.mockResolvedValueOnce(needsActionStatus());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useKronosStatusQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.status?.ready).toBe(false);
    expect(result.current.status?.enabled).toBe(false);
    expect(result.current.status?.dependenciesInstalled).toBe(false);
    expect(result.current.error).toBeNull();

    getKronosStatus.mockResolvedValueOnce(packagedDesktopStatus());
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.status?.packagedDesktop).toBe(true);
    expect(result.current.status?.installSupported).toBe(false);
    expect(result.current.status?.ready).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('removes the exact kronos key on unmount and ignores a late 500', async () => {
    const pending = createDeferred<KronosStatusResponse>();
    getKronosStatus.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useKronosStatusQuery(), { wrapper });

    await waitFor(() => expect(getKronosStatus).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.error).toBeNull();
    expect(result.current.status).toBeNull();
    expect(client.getQueryState(KRONOS_STATUS_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['kronos'] })).toHaveLength(0);
    expect(queryFetchStatus(client, KRONOS_STATUS_QUERY_KEY)).toBeUndefined();
  });

  it('lets a newer 500 win over a stale 200 so ready badges cannot resurrect', async () => {
    const first = createDeferred<KronosStatusResponse>();
    getKronosStatus
      .mockReturnValueOnce(first.promise)
      .mockRejectedValueOnce(serverError());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useKronosStatusQuery(), { wrapper });

    await waitFor(() => expect(getKronosStatus).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.refresh();
    });
    await waitFor(() => expect(getKronosStatus).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.error?.status).toBe(500));

    expect(result.current.status).toBeNull();
    expect(result.current.isLoading).toBe(false);

    await act(async () => {
      first.resolve(readyStatus());
      await first.promise.catch(() => undefined);
    });

    expect(result.current.status).toBeNull();
    expect(result.current.error?.status).toBe(500);
  });

  it('lets a newer 200 needs-action win over a stale 500 so ApiErrorAlert cannot replace it', async () => {
    const first = createDeferred<KronosStatusResponse>();
    getKronosStatus
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(needsActionStatus());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useKronosStatusQuery(), { wrapper });

    await waitFor(() => expect(getKronosStatus).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.refresh();
    });
    await waitFor(() => expect(getKronosStatus).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.status?.ready).toBe(false));

    expect(result.current.status?.enabled).toBe(false);
    expect(result.current.status?.reason).toBe('disabled');
    expect(result.current.error).toBeNull();
    expect(result.current.isLoading).toBe(false);

    await act(async () => {
      first.reject(serverError());
      await first.promise.catch(() => undefined);
    });

    expect(result.current.status?.ready).toBe(false);
    expect(result.current.status?.enabled).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('fails closed on a 500 even when the test client default would retry', async () => {
    getKronosStatus.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useKronosStatusQuery(), { wrapper });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(getKronosStatus).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(result.current.status).toBeNull();
    expect(result.current.error?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
  });

  it('does not set error when getKronosStatus settles as CancelledError', async () => {
    getKronosStatus.mockRejectedValue(new CancelledError(KRONOS_STATUS_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useKronosStatusQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.status).toBeNull();
  });

  it('keeps empty classification false while a cancelled generation is still in flight', async () => {
    const pending = createDeferred<KronosStatusResponse>();
    getKronosStatus.mockReturnValueOnce(pending.promise);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useKronosStatusQuery(), { wrapper });

    await waitFor(() => expect(getKronosStatus).toHaveBeenCalledTimes(1));
    expect(result.current.isLoading).toBe(true);
    expect(result.current.error).toBeNull();
    expect(result.current.status).toBeNull();
    const looksEmpty = !result.current.isLoading && !result.current.error && !result.current.status;
    expect(looksEmpty).toBe(false);

    await act(async () => {
      pending.reject(new CancelledError(KRONOS_STATUS_CANCEL));
      await pending.promise.catch(() => undefined);
    });

    expect(result.current.error).toBeNull();
  });

  it('same-key refresh cancel+remove then fetchQuery and clears status on failure', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useKronosStatusQuery(), { wrapper });

    await waitFor(() => expect(result.current.status?.ready).toBe(true));
    expect(getKronosStatus).toHaveBeenCalledTimes(1);
    expect(result.current.isLoading).toBe(false);

    const pending = createDeferred<KronosStatusResponse>();
    getKronosStatus.mockReturnValueOnce(pending.promise);
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
    assertExactKronosOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactKronosOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('never prefix-cancels or prefix-removes ["kronos"] or ["settings"]', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useKronosStatusQuery(), { wrapper });
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
      && filters.queryKey[0] === 'kronos'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'settings'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'data-providers'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'scorecard'
    ))).toBe(false);
    assertExactKronosOps(allOps);
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useKronosStatusQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(queryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(queryOptions(client)?.staleTime).toBe(0);
    expect(getKronosStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(getKronosStatus).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call getKronosStatus again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useKronosStatusQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getKronosStatus).toHaveBeenCalledTimes(1);
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

    expect(getKronosStatus).toHaveBeenCalledTimes(1);
  });

  it('issues getKronosStatus while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useKronosStatusQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getKronosStatus).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.networkMode).toBe('always');
    expect(result.current.status?.ready).toBe(true);
  });
});
