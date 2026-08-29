// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { systemConfigApi } from '../../api/systemConfig';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { SystemConfigResponse } from '../../types/systemConfig';
import { useSystemConfig } from '../useSystemConfig';
import {
  SYSTEM_CONFIG_LOAD_CANCEL,
  SYSTEM_CONFIG_LOAD_QUERY_KEY,
  SYSTEM_CONFIG_LOAD_QUERY_SCHEDULE,
  fetchSystemConfigLoad,
} from '../useSystemConfigLoadQuery';

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getConfig: vi.fn(),
    validate: vi.fn(),
    update: vi.fn(),
  },
  SystemConfigConflictError: class extends Error {},
  SystemConfigValidationError: class extends Error {},
}));

const getConfig = vi.mocked(systemConfigApi.getConfig);

const sampleConfig = {
  configVersion: 'v1',
  maskToken: '******',
  items: [
    {
      key: 'STOCK_LIST',
      value: 'SH600000',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'STOCK_LIST',
        category: 'base',
        dataType: 'string',
        uiControl: 'textarea',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
      },
    },
  ],
} as SystemConfigResponse;

function createWrapper(client?: QueryClient) {
  const queryClient = client ?? createAppQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return { client: queryClient, wrapper: Wrapper };
}

function loadQueryOptions(client: QueryClient) {
  const query = client.getQueryCache().find({ queryKey: SYSTEM_CONFIG_LOAD_QUERY_KEY, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient) {
  return client.getQueryState(SYSTEM_CONFIG_LOAD_QUERY_KEY)?.fetchStatus;
}

function assertNoSettingsPrefixOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'settings' && key.length === 1).toBe(false);
    if (key[0] === 'settings') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['settings', 'system-config', 'load']);
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

describe('useSystemConfigLoadQuery (counterexamples 18-26)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    getConfig.mockResolvedValue(sampleConfig);
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

  it('pins the exact load key, schedule, and getConfig(true) without an AbortSignal', async () => {
    expect(SYSTEM_CONFIG_LOAD_QUERY_KEY).toEqual(['settings', 'system-config', 'load']);
    expect(SYSTEM_CONFIG_LOAD_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    await fetchSystemConfigLoad();
    expect(getConfig).toHaveBeenCalledTimes(1);
    expect(getConfig).toHaveBeenCalledWith(true);
    expect(getConfig.mock.calls[0]).toHaveLength(1);
  });

  it('does not auto-retry a 5xx load when the QueryClient default would retry', async () => {
    getConfig.mockRejectedValue(Object.assign(new Error('server'), { response: { status: 500 } }));
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useSystemConfig(), { wrapper });

    await act(async () => {
      await result.current.load();
    });

    expect(getConfig).toHaveBeenCalledTimes(1);
    expect(getConfig).toHaveBeenCalledWith(true);
    expect(loadQueryOptions(client)?.retry).toBe(false);
    expect(result.current.loadError).not.toBeNull();
    expect(result.current.retryAction).toBe('load');

    await act(async () => {
      await result.current.retry();
    });
    expect(getConfig).toHaveBeenCalledTimes(2);
    expect(loadQueryOptions(client)?.retry).toBe(false);
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useSystemConfig(), { wrapper });

    await act(async () => {
      await result.current.load();
    });
    expect(loadQueryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(loadQueryOptions(client)?.retry).toBe(false);
    expect(loadQueryOptions(client)?.staleTime).toBe(0);
    expect(getConfig).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(getConfig).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call getConfig again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useSystemConfig(), { wrapper });
    await act(async () => {
      await result.current.load();
    });
    expect(getConfig).toHaveBeenCalledTimes(1);
    expect(loadQueryOptions(client)?.refetchInterval).toBeUndefined();

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

    expect(getConfig).toHaveBeenCalledTimes(1);
  });

  it('removes the exact load key on unmount and ignores a late getConfig failure', async () => {
    const pending = createDeferred<typeof sampleConfig>();
    getConfig.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useSystemConfig(), { wrapper });

    await act(async () => {
      void result.current.load();
    });
    await waitFor(() => expect(getConfig).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(Object.assign(new Error('server'), { response: { status: 500 } }));
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.loadError).toBeNull();
    expect(result.current.retryAction).toBeNull();
    expect(client.getQueryState(SYSTEM_CONFIG_LOAD_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['settings', 'system-config'] })).toHaveLength(0);
    expect(queryFetchStatus(client)).toBeUndefined();
  });

  it('silently cancels the predecessor same-key load then lets the successor snapshot win', async () => {
    const first = createDeferred<typeof sampleConfig>();
    const successor = createDeferred<typeof sampleConfig>();
    const latest = {
      ...sampleConfig,
      configVersion: 'v2',
      items: sampleConfig.items.map((item) => ({ ...item, value: 'SH600519' })),
    };
    getConfig
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(successor.promise);
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useSystemConfig(), { wrapper });

    let firstLoad!: Promise<boolean>;
    let secondLoad!: Promise<boolean>;
    act(() => {
      firstLoad = result.current.load();
      secondLoad = result.current.load();
    });
    await waitFor(() => expect(getConfig).toHaveBeenCalledTimes(2));
    assertNoSettingsPrefixOps(cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
    assertNoSettingsPrefixOps(removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);

    await act(async () => {
      successor.resolve(latest);
      await secondLoad;
    });
    await act(async () => {
      first.resolve(sampleConfig);
      await firstLoad;
    });

    expect(result.current.configVersion).toBe('v2');
    expect(result.current.serverItems[0]?.value).toBe('SH600519');
    expect(result.current.loadError).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(queryFetchStatus(client)).toBe('idle');
  });

  it('does not setLoadError when getConfig settles as CancelledError', async () => {
    getConfig.mockRejectedValue(new CancelledError(SYSTEM_CONFIG_LOAD_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useSystemConfig(), { wrapper });

    await act(async () => {
      await result.current.load();
    });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.loadError).toBeNull();
    expect(result.current.retryAction).toBeNull();
  });

  it('issues getConfig while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useSystemConfig(), { wrapper });

    await act(async () => {
      await result.current.load();
    });

    expect(getConfig).toHaveBeenCalledTimes(1);
    expect(loadQueryOptions(client)?.networkMode).toBe('always');
    expect(result.current.configVersion).toBe('v1');
  });

  it('never prefix-operates on [settings] when cancelling or removing the load key', async () => {
    const pending = createDeferred<typeof sampleConfig>();
    getConfig.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(sampleConfig);
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result, unmount } = renderHook(() => useSystemConfig(), { wrapper });

    await act(async () => {
      void result.current.load();
    });
    await waitFor(() => expect(getConfig).toHaveBeenCalledTimes(1));
    await act(async () => {
      await result.current.load();
    });
    unmount();
    await act(async () => {
      pending.resolve(sampleConfig);
      await pending.promise.catch(() => undefined);
    });

    assertNoSettingsPrefixOps(cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
    assertNoSettingsPrefixOps(removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
    expect(client.getQueryCache().findAll({ queryKey: ['settings'] }).length).toBe(
      client.getQueryCache().findAll({ queryKey: SYSTEM_CONFIG_LOAD_QUERY_KEY, exact: true }).length,
    );
  });

  it('keeps save-path getConfig off the load query key so cancel/remove cannot abort it', async () => {
    const loadPending = createDeferred<typeof sampleConfig>();
    const refreshPending = createDeferred<typeof sampleConfig>();
    const refreshed = {
      ...sampleConfig,
      configVersion: 'v-refresh',
    };
    getConfig
      .mockReturnValueOnce(loadPending.promise)
      .mockReturnValueOnce(refreshPending.promise)
      .mockResolvedValueOnce(sampleConfig);
    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const setDataSpy = vi.spyOn(client, 'setQueryData');
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useSystemConfig(), { wrapper });

    await act(async () => {
      void result.current.load();
    });
    await waitFor(() => expect(getConfig).toHaveBeenCalledTimes(1));
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    let refreshPromise!: Promise<void>;
    act(() => {
      refreshPromise = result.current.refreshAfterExternalSave([]);
    });
    await waitFor(() => expect(getConfig).toHaveBeenCalledTimes(2));
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(getConfig.mock.calls[1]).toEqual([true]);

    await act(async () => {
      await result.current.load();
    });
    await act(async () => {
      refreshPending.resolve(refreshed);
      await refreshPromise;
    });
    await act(async () => {
      loadPending.resolve(sampleConfig);
      await loadPending.promise.catch(() => undefined);
    });

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['settings', 'system-config', 'load']);
    }
    expect(setDataSpy).not.toHaveBeenCalled();
    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(result.current.loadError).toBeNull();
    expect(result.current.configVersion).toBe('v1');
  });
});
