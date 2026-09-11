// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useEffect, useState, type ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { pluginsApi, type PluginInfo, type PluginListResponse } from '../../api/plugins';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import {
  NOTIFICATION_CHANNEL_PLUGINS_CANCEL,
  NOTIFICATION_CHANNEL_PLUGINS_QUERY_KEY,
  NOTIFICATION_CHANNEL_PLUGINS_QUERY_SCHEDULE,
  fetchNotificationChannelPluginsList,
  useNotificationChannelPluginsQuery,
} from '../useNotificationChannelPluginsQuery';

vi.mock('../../api/plugins', () => ({
  pluginsApi: {
    list: vi.fn(),
    updateLifecycle: vi.fn(),
    getSettings: vi.fn(),
    updateSettings: vi.fn(),
  },
}));

const listPlugins = vi.mocked(pluginsApi.list);
const updateLifecycle = vi.mocked(pluginsApi.updateLifecycle);
const getSettings = vi.mocked(pluginsApi.getSettings);
const updateSettings = vi.mocked(pluginsApi.updateSettings);

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

function createSwappableWrapper() {
  const clients = [createAppQueryClient(), createAppQueryClient()] as const;
  const swapRef = { current: () => {} };
  function Wrapper({ children }: { children: ReactNode }) {
    const [client, setClient] = useState(clients[0]);
    useEffect(() => {
      swapRef.current = () => setClient(clients[1]);
    }, [setClient]);
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return {
    client: clients[0],
    swapClient: () => swapRef.current(),
    wrapper: Wrapper,
  };
}

function queryOptions(
  client: QueryClient,
  queryKey: readonly unknown[] = NOTIFICATION_CHANNEL_PLUGINS_QUERY_KEY,
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertExactNotificationChannelPluginsOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'plugins' && key.length === 1).toBe(false);
    expect(key[0] === 'settings').toBe(false);
    expect(key[0] === 'scheduler').toBe(false);
    expect(key[0] === 'scorecard').toBe(false);
    expect(key[0] === 'intelligence').toBe(false);
    expect(key[0] === 'generation-backend').toBe(false);
    expect(key[0] === 'local-models').toBe(false);
    if (key[0] === 'plugins') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['plugins', 'notification-channels']);
      expect(key).toHaveLength(2);
    }
  }
}

function assertMutationsUntouched() {
  expect(updateLifecycle).not.toHaveBeenCalled();
  expect(getSettings).not.toHaveBeenCalled();
  expect(updateSettings).not.toHaveBeenCalled();
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

describe('useNotificationChannelPluginsQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listPlugins.mockReset();
    updateLifecycle.mockReset();
    getSettings.mockReset();
    updateSettings.mockReset();
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

  it('pins the exact notification-channels key, schedule, and list() with no arguments', async () => {
    expect([...NOTIFICATION_CHANNEL_PLUGINS_QUERY_KEY]).toEqual(['plugins', 'notification-channels']);
    expect(NOTIFICATION_CHANNEL_PLUGINS_QUERY_KEY).toHaveLength(2);
    expect(NOTIFICATION_CHANNEL_PLUGINS_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(NOTIFICATION_CHANNEL_PLUGINS_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchNotificationChannelPluginsList({ signal: controller.signal });
    expect(listPlugins).toHaveBeenCalledTimes(1);
    expect(listPlugins.mock.calls[0]).toEqual([]);
    assertMutationsUntouched();
  });

  it('is not barrel-exported, does not mount a live useQuery observer, and omits mutation/query APIs from source', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useNotificationChannelPluginsQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useNotificationChannelPluginsQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['plugins', 'notification-channels']);
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
      expect(scheduled.refetchInterval).toBeUndefined();
    }
    expect(
      client.getQueryCache().find({
        queryKey: NOTIFICATION_CHANNEL_PLUGINS_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(listPlugins.mock.calls[0]).toEqual([]);
    expect(listPlugins).toHaveBeenCalledTimes(1);
    assertMutationsUntouched();
  });

  it('fetches once on mount, sets items, and leaves zero live observers', async () => {
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useNotificationChannelPluginsQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listPlugins).toHaveBeenCalledTimes(1);
    expect(listPlugins.mock.calls[0]).toEqual([]);
    expect(result.current.items).toEqual([plugin()]);
    expect(result.current.loadFailed).toBe(false);
    expect(
      client.getQueryCache().find({
        queryKey: NOTIFICATION_CHANNEL_PLUGINS_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    assertMutationsUntouched();
  });

  it('treats empty 200 as a success roster rather than a warning', async () => {
    listPlugins.mockResolvedValueOnce(listResponse([], 0));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useNotificationChannelPluginsQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.items).toEqual([]);
    expect(result.current.loadFailed).toBe(false);
  });

  it('fail-closes on an initial 500 even when the test client default would retry', async () => {
    listPlugins.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useNotificationChannelPluginsQuery(), { wrapper });

    await waitFor(() => expect(result.current.loadFailed).toBe(true));
    expect(listPlugins).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(result.current.items).toEqual([]);
    expect(result.current.isLoading).toBe(false);
  });

  it('does not set loadFailed when list() settles as CancelledError', async () => {
    listPlugins.mockRejectedValue(new CancelledError(NOTIFICATION_CHANNEL_PLUGINS_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useNotificationChannelPluginsQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.loadFailed).toBe(false);
    expect(result.current.items).toEqual([]);
  });

  it('lets a newer 500 win over a stale 200 so a later success cannot resurrect', async () => {
    const first = createDeferred<PluginListResponse>();
    const second = createDeferred<PluginListResponse>();
    listPlugins
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const { wrapper, swapClient } = createSwappableWrapper();
    const { result } = renderHook(() => useNotificationChannelPluginsQuery(), { wrapper });

    await waitFor(() => expect(listPlugins).toHaveBeenCalledTimes(1));
    await act(async () => {
      swapClient();
    });
    await waitFor(() => expect(listPlugins).toHaveBeenCalledTimes(2));
    await act(async () => {
      second.reject(serverError());
      await second.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.loadFailed).toBe(true));
    expect(result.current.items).toEqual([]);
    expect(result.current.isLoading).toBe(false);

    await act(async () => {
      first.resolve(listResponse([plugin({ id: 'stale', name: 'Stale' })]));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.items).toEqual([]);
    expect(result.current.loadFailed).toBe(true);
  });

  it('lets a newer empty list win over a stale 500', async () => {
    const first = createDeferred<PluginListResponse>();
    const second = createDeferred<PluginListResponse>();
    listPlugins
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const { wrapper, swapClient } = createSwappableWrapper();
    const { result } = renderHook(() => useNotificationChannelPluginsQuery(), { wrapper });

    await waitFor(() => expect(listPlugins).toHaveBeenCalledTimes(1));
    await act(async () => {
      swapClient();
    });
    await waitFor(() => expect(listPlugins).toHaveBeenCalledTimes(2));
    await act(async () => {
      second.resolve(listResponse([], 0));
      await second.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.items).toEqual([]);
    expect(result.current.loadFailed).toBe(false);

    await act(async () => {
      first.reject(serverError());
      await first.promise.catch(() => undefined);
    });

    expect(result.current.items).toEqual([]);
    expect(result.current.loadFailed).toBe(false);
  });

  it('removes only the notification-channels key on unmount and ignores a late 500', async () => {
    const pending = createDeferred<PluginListResponse>();
    listPlugins.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result, unmount } = renderHook(() => useNotificationChannelPluginsQuery(), { wrapper });

    await waitFor(() => expect(listPlugins).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.loadFailed).toBe(false);
    expect(result.current.items).toEqual([]);
    expect(client.getQueryState(NOTIFICATION_CHANNEL_PLUGINS_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({
      queryKey: ['plugins', 'list'],
      exact: true,
    })).toHaveLength(0);
    expect(queryFetchStatus(client, NOTIFICATION_CHANNEL_PLUGINS_QUERY_KEY)).toBeUndefined();
    assertExactNotificationChannelPluginsOps([
      ...cancelSpy.mock.calls,
      ...removeSpy.mock.calls,
    ] as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
  });

  it('same-key remount cancel+remove then fetchQuery', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const first = renderHook(() => useNotificationChannelPluginsQuery(), { wrapper });
    await waitFor(() => expect(first.result.current.isLoading).toBe(false));
    expect(listPlugins).toHaveBeenCalledTimes(1);

    first.unmount();
    const second = renderHook(() => useNotificationChannelPluginsQuery(), { wrapper });
    await waitFor(() => expect(second.result.current.isLoading).toBe(false));
    expect(listPlugins).toHaveBeenCalledTimes(2);

    const lastFetchOrder = Math.max(...fetchSpy.mock.invocationCallOrder);
    const cancelsBeforeLastFetch = cancelSpy.mock.invocationCallOrder.filter((order) => order < lastFetchOrder);
    const removesBeforeLastFetch = removeSpy.mock.invocationCallOrder.filter((order) => order < lastFetchOrder);
    expect(cancelsBeforeLastFetch.length).toBeGreaterThan(0);
    expect(removesBeforeLastFetch.length).toBeGreaterThan(0);
    expect(Math.max(...cancelsBeforeLastFetch)).toBeLessThan(lastFetchOrder);
    expect(Math.max(...removesBeforeLastFetch)).toBeLessThan(lastFetchOrder);
    assertExactNotificationChannelPluginsOps([
      ...cancelSpy.mock.calls,
      ...removeSpy.mock.calls,
    ] as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
  });

  it('never prefix-cancels or prefix-removes ["plugins"] or exact-cancels the loaded-extensions key', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result, unmount } = renderHook(() => useNotificationChannelPluginsQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    unmount();

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
      && filters.queryKey[0] === 'plugins'
      && filters.queryKey[1] === 'list'
    ))).toBe(false);
    assertExactNotificationChannelPluginsOps(allOps);
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useNotificationChannelPluginsQuery(), { wrapper });

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
    const { result } = renderHook(() => useNotificationChannelPluginsQuery(), { wrapper });
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
    const { result } = renderHook(() => useNotificationChannelPluginsQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listPlugins).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.networkMode).toBe('always');
    expect(result.current.items[0]?.id).toBe('demo');
  });
});
