// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { pluginsApi, type PluginInfo, type PluginListResponse } from '../../api/plugins';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import {
  LOADED_EXTENSIONS_CANCEL,
  LOADED_EXTENSIONS_QUERY_KEY,
  LOADED_EXTENSIONS_QUERY_SCHEDULE,
  fetchLoadedExtensionsList,
  useLoadedExtensionsQuery,
} from '../useLoadedExtensionsQuery';

vi.mock('../../api/plugins', () => ({
  pluginsApi: {
    list: vi.fn(),
  },
}));

const listPlugins = vi.mocked(pluginsApi.list);

function plugin(overrides: Partial<PluginInfo> = {}): PluginInfo {
  return {
    id: 'demo',
    name: 'Demo',
    version: '1.0.0',
    source: 'builtin',
    state: 'enabled',
    desiredEnabled: true,
    reloadable: false,
    packageRoot: null,
    extensionPoints: [],
    notificationChannels: [],
    description: '',
    author: '',
    settingsCount: 0,
    ...overrides,
  };
}

function listResponse(items: PluginInfo[], total = items.length): PluginListResponse {
  return { items, total };
}

function serverError(): Error {
  return Object.assign(new Error('server'), {
    response: {
      status: 500,
      data: { error: 'internal', message: 'plugins unavailable' },
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
  queryKey: readonly unknown[] = LOADED_EXTENSIONS_QUERY_KEY,
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertExactPluginsListOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'plugins' && key.length === 1).toBe(false);
    expect(key[0] === 'settings').toBe(false);
    expect(key[0] === 'scheduler').toBe(false);
    expect(key[0] === 'scorecard').toBe(false);
    if (key[0] === 'plugins') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['plugins', 'list']);
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

describe('useLoadedExtensionsQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    listPlugins.mockResolvedValue(listResponse([plugin()]));
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

  it('pins the exact plugins list key, schedule, and list() with no signal or language', async () => {
    expect([...LOADED_EXTENSIONS_QUERY_KEY]).toEqual(['plugins', 'list']);
    expect(LOADED_EXTENSIONS_QUERY_KEY).toHaveLength(2);
    expect(LOADED_EXTENSIONS_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(LOADED_EXTENSIONS_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchLoadedExtensionsList({ signal: controller.signal });
    expect(listPlugins).toHaveBeenCalledTimes(1);
    expect(listPlugins.mock.calls[0]).toEqual([]);
  });

  it('is not barrel-exported and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useLoadedExtensionsQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useLoadedExtensionsQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['plugins', 'list']);
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
      expect(scheduled.refetchInterval).toBeUndefined();
    }
    expect(
      client.getQueryCache().find({
        queryKey: LOADED_EXTENSIONS_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(listPlugins.mock.calls[0]).toEqual([]);
  });

  it('fetches once on mount, sets items/total, and leaves zero live observers', async () => {
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useLoadedExtensionsQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listPlugins).toHaveBeenCalledTimes(1);
    expect(result.current.items).toEqual([plugin()]);
    expect(result.current.total).toBe(1);
    expect(result.current.loadError).toBeNull();
    expect(result.current.isRefreshing).toBe(false);
    expect(typeof result.current.setItems).toBe('function');
    expect(
      client.getQueryCache().find({
        queryKey: LOADED_EXTENSIONS_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
  });

  it('treats empty 200 as a success roster rather than an error', async () => {
    listPlugins.mockResolvedValueOnce(listResponse([], 0));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useLoadedExtensionsQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.loadError).toBeNull();
  });

  it('clears rows on an initial 500 even when the test client default would retry', async () => {
    listPlugins.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useLoadedExtensionsQuery(), { wrapper });

    await waitFor(() => expect(result.current.loadError).not.toBeNull());
    expect(listPlugins).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.loadError?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);
  });

  it('keeps last-good roster when a later refresh fails', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useLoadedExtensionsQuery(), { wrapper });
    await waitFor(() => expect(result.current.items[0]?.id).toBe('demo'));

    listPlugins.mockRejectedValueOnce(serverError());
    await act(async () => {
      await result.current.load('refresh');
    });

    expect(result.current.items[0]?.id).toBe('demo');
    expect(result.current.total).toBe(1);
    expect(result.current.loadError?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);
  });

  it('preserves prior rows while a refresh is in flight', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useLoadedExtensionsQuery(), { wrapper });
    await waitFor(() => expect(result.current.items[0]?.id).toBe('demo'));

    const pending = createDeferred<PluginListResponse>();
    listPlugins.mockReturnValueOnce(pending.promise);
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    expect(result.current.isLoading).toBe(false);
    expect(result.current.items[0]?.id).toBe('demo');

    await act(async () => {
      pending.resolve(listResponse([plugin({ id: 'refreshed', name: 'Refreshed' })]));
      await pending.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.isRefreshing).toBe(false));
    expect(result.current.items[0]?.id).toBe('refreshed');
    expect(result.current.loadError).toBeNull();
  });

  it('does not set loadError when list() settles as CancelledError', async () => {
    listPlugins.mockRejectedValue(new CancelledError(LOADED_EXTENSIONS_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useLoadedExtensionsQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.loadError).toBeNull();
    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);
  });

  it('removes the exact plugins list key on unmount and ignores a late 500', async () => {
    const pending = createDeferred<PluginListResponse>();
    listPlugins.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useLoadedExtensionsQuery(), { wrapper });

    await waitFor(() => expect(listPlugins).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.loadError).toBeNull();
    expect(result.current.items).toEqual([]);
    expect(client.getQueryState(LOADED_EXTENSIONS_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['plugins'] })).toHaveLength(0);
    expect(queryFetchStatus(client, LOADED_EXTENSIONS_QUERY_KEY)).toBeUndefined();
  });

  it('lets a newer 500 win over a stale 200 so a later success cannot resurrect', async () => {
    const first = createDeferred<PluginListResponse>();
    listPlugins
      .mockReturnValueOnce(first.promise)
      .mockRejectedValueOnce(serverError());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useLoadedExtensionsQuery(), { wrapper });

    await waitFor(() => expect(listPlugins).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(listPlugins).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.loadError?.status).toBe(500));

    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);

    await act(async () => {
      first.resolve(listResponse([plugin({ id: 'stale', name: 'Stale' })]));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.items).toEqual([]);
    expect(result.current.loadError?.status).toBe(500);
  });

  it('lets a newer 200 roster win over a stale 500', async () => {
    const first = createDeferred<PluginListResponse>();
    listPlugins
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(listResponse([plugin({ id: 'live', name: 'Live' })]));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useLoadedExtensionsQuery(), { wrapper });

    await waitFor(() => expect(listPlugins).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(listPlugins).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.items[0]?.id).toBe('live'));

    expect(result.current.loadError).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);

    await act(async () => {
      first.reject(serverError());
      await first.promise.catch(() => undefined);
    });

    expect(result.current.items[0]?.id).toBe('live');
    expect(result.current.loadError).toBeNull();
  });

  it('same-key refresh cancel+remove then fetchQuery and keeps last-good on failure', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useLoadedExtensionsQuery(), { wrapper });

    await waitFor(() => expect(result.current.items[0]?.id).toBe('demo'));
    expect(listPlugins).toHaveBeenCalledTimes(1);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);

    const pending = createDeferred<PluginListResponse>();
    listPlugins.mockReturnValueOnce(pending.promise);
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

    expect(result.current.items[0]?.id).toBe('demo');
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
    assertExactPluginsListOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactPluginsListOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('never prefix-cancels or prefix-removes ["plugins"] or ["settings"]', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useLoadedExtensionsQuery(), { wrapper });
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
      && filters.queryKey[0] === 'plugins'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'settings'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'scheduler'
    ))).toBe(false);
    assertExactPluginsListOps(allOps);
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useLoadedExtensionsQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(queryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(queryOptions(client)?.staleTime).toBe(0);
    expect(listPlugins).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(listPlugins).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call list() again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useLoadedExtensionsQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listPlugins).toHaveBeenCalledTimes(1);
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

    expect(listPlugins).toHaveBeenCalledTimes(1);
  });

  it('issues list() while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useLoadedExtensionsQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listPlugins).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.networkMode).toBe('always');
    expect(result.current.items[0]?.id).toBe('demo');
  });
});
