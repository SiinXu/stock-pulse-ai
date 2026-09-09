// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { configProfilesApi } from '../../api/configProfiles';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { ConfigPresetItem, ConfigPresetListResponse } from '../../types/configProfiles';
import {
  CONFIG_PRESETS_LIST_CANCEL,
  CONFIG_PRESETS_LIST_QUERY_KEY,
  CONFIG_PRESETS_LIST_QUERY_SCHEDULE,
  fetchConfigPresetsList,
  useConfigPresetsListQuery,
} from '../useConfigPresetsListQuery';

vi.mock('../../api/configProfiles', () => ({
  configProfilesApi: {
    listPresets: vi.fn(),
  },
}));

const listPresets = vi.mocked(configProfilesApi.listPresets);

function preset(overrides: Partial<ConfigPresetItem> = {}): ConfigPresetItem {
  return {
    id: 'local-first',
    displayName: 'Local-first (Ollama / Model Pack)',
    description: 'Prefer local models',
    tags: ['local'],
    preferenceOrder: ['ollama'],
    configValues: {},
    strategies: {},
    features: { beginner_mode: true },
    requirements: {},
    recommended: true,
    score: 110,
    meetsRequirements: true,
    ...overrides,
  };
}

function listResponse(
  presets: ConfigPresetItem[],
  recommendedPresetId: string | null = presets[0]?.id ?? null,
): ConfigPresetListResponse {
  return {
    recommendedPresetId,
    detection: {
      ollamaHealthy: true,
      modelPackPresent: false,
      cliDetected: [],
      cloudReady: false,
    },
    presets,
  };
}

function serverError(): Error {
  return Object.assign(new Error('server'), {
    response: {
      status: 500,
      data: { error: 'internal', message: 'config presets unavailable' },
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
  queryKey: readonly unknown[] = CONFIG_PRESETS_LIST_QUERY_KEY,
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertExactConfigPresetsListOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'config-presets' && key.length === 1).toBe(false);
    expect(key[0] === 'settings').toBe(false);
    expect(key[0] === 'plugins').toBe(false);
    expect(key[0] === 'scheduler').toBe(false);
    expect(key[0] === 'scheduled-tasks').toBe(false);
    expect(key[0] === 'watchlist').toBe(false);
    expect(key[0] === 'home').toBe(false);
    if (key[0] === 'config-presets') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['config-presets', 'list']);
      expect(key).toHaveLength(2);
      expect(key).not.toContain('configVersion');
    }
  }
}

function assertSilentCancelOptions(
  calls: Array<[filters?: unknown, options?: { silent?: boolean; revert?: boolean }]>,
) {
  expect(calls.some(([, options]) => (
    options?.silent === true && options?.revert === false
  ))).toBe(true);
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

describe('useConfigPresetsListQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    listPresets.mockResolvedValue(listResponse([preset()]));
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

  it('pins the exact config-presets list key, schedule, and listPresets() with no signal, language, or configVersion', async () => {
    expect([...CONFIG_PRESETS_LIST_QUERY_KEY]).toEqual(['config-presets', 'list']);
    expect(CONFIG_PRESETS_LIST_QUERY_KEY).toHaveLength(2);
    expect(CONFIG_PRESETS_LIST_QUERY_KEY).not.toContain('configVersion');
    expect(CONFIG_PRESETS_LIST_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(CONFIG_PRESETS_LIST_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchConfigPresetsList({ signal: controller.signal });
    expect(listPresets).toHaveBeenCalledTimes(1);
    expect(listPresets.mock.calls[0]).toEqual([]);
  });

  it('is not barrel-exported and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useConfigPresetsListQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useConfigPresetsListQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['config-presets', 'list']);
      expect(options.queryKey).not.toContain('configVersion');
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
      expect(scheduled.refetchInterval).toBeUndefined();
    }
    expect(
      client.getQueryCache().find({
        queryKey: CONFIG_PRESETS_LIST_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(listPresets.mock.calls[0]).toEqual([]);
  });

  it('fetches once on mount, sets presets without total/detection/isRefreshing, and leaves zero live observers', async () => {
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useConfigPresetsListQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listPresets).toHaveBeenCalledTimes(1);
    expect(result.current.presets).toEqual([preset()]);
    expect(result.current.recommendedId).toBe('local-first');
    expect(result.current).not.toHaveProperty('total');
    expect(result.current).not.toHaveProperty('detection');
    expect(result.current).not.toHaveProperty('isRefreshing');
    expect(result.current).not.toHaveProperty('setPresets');
    expect(result.current.loadError).toBeNull();
    expect(
      client.getQueryCache().find({
        queryKey: CONFIG_PRESETS_LIST_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
  });

  it('treats empty 200 as a success roster rather than an error', async () => {
    listPresets.mockResolvedValueOnce(listResponse([], null));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useConfigPresetsListQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.presets).toEqual([]);
    expect(result.current.recommendedId).toBeNull();
    expect(result.current.loadError).toBeNull();
  });

  it('clears presets on an initial 500 even when the test client default would retry', async () => {
    listPresets.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useConfigPresetsListQuery(), { wrapper });

    await waitFor(() => expect(result.current.loadError).not.toBeNull());
    expect(listPresets).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(result.current.presets).toEqual([]);
    expect(result.current.recommendedId).toBeNull();
    expect(result.current.loadError?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
  });

  it('clears last-good presets when a later refresh fails', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useConfigPresetsListQuery(), { wrapper });
    await waitFor(() => expect(result.current.presets[0]?.id).toBe('local-first'));

    listPresets.mockRejectedValueOnce(serverError());
    await act(async () => {
      await result.current.load('refresh');
    });

    expect(result.current.presets).toEqual([]);
    expect(result.current.recommendedId).toBeNull();
    expect(result.current.loadError?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
  });

  it('preserves prior presets while a refresh is in flight and sets isLoading', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useConfigPresetsListQuery(), { wrapper });
    await waitFor(() => expect(result.current.presets[0]?.id).toBe('local-first'));

    const pending = createDeferred<ConfigPresetListResponse>();
    listPresets.mockReturnValueOnce(pending.promise);
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(result.current.isLoading).toBe(true));
    expect(result.current.presets[0]?.id).toBe('local-first');
    expect(result.current.recommendedId).toBe('local-first');

    await act(async () => {
      pending.resolve(listResponse([preset({ id: 'cloud-first', displayName: 'Cloud-first', recommended: false })]));
      await pending.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.presets[0]?.id).toBe('cloud-first');
    expect(result.current.recommendedId).toBe('cloud-first');
    expect(result.current.loadError).toBeNull();
  });

  it('does not set loadError when listPresets() settles as CancelledError', async () => {
    listPresets.mockRejectedValue(new CancelledError(CONFIG_PRESETS_LIST_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useConfigPresetsListQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.loadError).toBeNull();
    expect(result.current.presets).toEqual([]);
    expect(result.current.recommendedId).toBeNull();
  });

  it('removes the exact config-presets list key on unmount and ignores a late 500', async () => {
    const pending = createDeferred<ConfigPresetListResponse>();
    listPresets.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useConfigPresetsListQuery(), { wrapper });

    await waitFor(() => expect(listPresets).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.loadError).toBeNull();
    expect(result.current.presets).toEqual([]);
    expect(client.getQueryState(CONFIG_PRESETS_LIST_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['config-presets'] })).toHaveLength(0);
    expect(queryFetchStatus(client, CONFIG_PRESETS_LIST_QUERY_KEY)).toBeUndefined();
  });

  it('lets a newer 500 win over a stale 200 so a later success cannot resurrect', async () => {
    const first = createDeferred<ConfigPresetListResponse>();
    listPresets
      .mockReturnValueOnce(first.promise)
      .mockRejectedValueOnce(serverError());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useConfigPresetsListQuery(), { wrapper });

    await waitFor(() => expect(listPresets).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(listPresets).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.loadError?.status).toBe(500));

    expect(result.current.presets).toEqual([]);
    expect(result.current.recommendedId).toBeNull();
    expect(result.current.isLoading).toBe(false);

    await act(async () => {
      first.resolve(listResponse([preset({ id: 'stale', displayName: 'Stale' })]));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.presets).toEqual([]);
    expect(result.current.recommendedId).toBeNull();
    expect(result.current.loadError?.status).toBe(500);
  });

  it('lets a newer 200 roster win over a stale 500', async () => {
    const first = createDeferred<ConfigPresetListResponse>();
    listPresets
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(listResponse([preset({ id: 'live', displayName: 'Live' })]));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useConfigPresetsListQuery(), { wrapper });

    await waitFor(() => expect(listPresets).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(listPresets).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.presets[0]?.id).toBe('live'));

    expect(result.current.loadError).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.recommendedId).toBe('live');

    await act(async () => {
      first.reject(serverError());
      await first.promise.catch(() => undefined);
    });

    expect(result.current.presets[0]?.id).toBe('live');
    expect(result.current.recommendedId).toBe('live');
    expect(result.current.loadError).toBeNull();
  });

  it('same-key refresh cancel+remove then fetchQuery and fail-closes on refresh 500', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useConfigPresetsListQuery(), { wrapper });

    await waitFor(() => expect(result.current.presets[0]?.id).toBe('local-first'));
    expect(listPresets).toHaveBeenCalledTimes(1);
    expect(result.current.isLoading).toBe(false);

    const pending = createDeferred<ConfigPresetListResponse>();
    listPresets.mockReturnValueOnce(pending.promise);
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(result.current.isLoading).toBe(true));

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.loadError).not.toBeNull());

    expect(result.current.presets).toEqual([]);
    expect(result.current.recommendedId).toBeNull();
    expect(result.current.loadError?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
    expect(fetchSpy).toHaveBeenCalled();
    expect(cancelSpy).toHaveBeenCalled();
    expect(removeSpy).toHaveBeenCalled();
    assertSilentCancelOptions(
      cancelSpy.mock.calls as Array<[filters?: unknown, options?: { silent?: boolean; revert?: boolean }]>,
    );

    const cancelOrders = cancelSpy.mock.invocationCallOrder;
    const removeOrders = removeSpy.mock.invocationCallOrder;
    const fetchOrders = fetchSpy.mock.invocationCallOrder;
    expect(Math.min(...cancelOrders)).toBeLessThan(Math.min(...fetchOrders));
    expect(Math.min(...removeOrders)).toBeLessThan(Math.min(...fetchOrders));
    assertExactConfigPresetsListOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactConfigPresetsListOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('never prefix-cancels or prefix-removes config-presets, settings, plugins, scheduler, scheduled-tasks, watchlist, or home keys', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useConfigPresetsListQuery(), { wrapper });
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
      && filters.queryKey[0] === 'config-presets'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'settings'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'plugins'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'scheduler'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'scheduled-tasks'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'watchlist'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'home'
    ))).toBe(false);
    assertExactConfigPresetsListOps(allOps);
  });

  it('does not refetch when the window regains focus or reconnects', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useConfigPresetsListQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(queryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(queryOptions(client)?.staleTime).toBe(0);
    expect(listPresets).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
      onlineManager.setOnline(false);
      onlineManager.setOnline(true);
    });

    expect(listPresets).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call listPresets() again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useConfigPresetsListQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listPresets).toHaveBeenCalledTimes(1);
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

    expect(listPresets).toHaveBeenCalledTimes(1);
  });

  it('issues listPresets() while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useConfigPresetsListQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listPresets).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.networkMode).toBe('always');
    expect(result.current.presets[0]?.id).toBe('local-first');
  });

  it('returns the successful { presets, recommendedPresetId } from load() and undefined on error or cancel', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useConfigPresetsListQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    listPresets.mockResolvedValueOnce(listResponse([preset({ id: 'cloud-first', displayName: 'Cloud' })], 'cloud-first'));
    let success: { presets: ConfigPresetItem[]; recommendedPresetId: string | null } | undefined;
    await act(async () => {
      success = await result.current.load('refresh');
    });
    expect(success).toEqual({
      presets: [preset({ id: 'cloud-first', displayName: 'Cloud' })],
      recommendedPresetId: 'cloud-first',
    });

    listPresets.mockResolvedValueOnce(listResponse([], null));
    let empty: { presets: ConfigPresetItem[]; recommendedPresetId: string | null } | undefined;
    await act(async () => {
      empty = await result.current.load('refresh');
    });
    expect(empty).toEqual({ presets: [], recommendedPresetId: null });
    expect(result.current.presets).toEqual([]);
    expect(result.current.recommendedId).toBeNull();

    listPresets.mockRejectedValueOnce(serverError());
    let failed: { presets: ConfigPresetItem[]; recommendedPresetId: string | null } | undefined;
    await act(async () => {
      failed = await result.current.load('refresh');
    });
    expect(failed).toBeUndefined();
    expect(result.current.presets).toEqual([]);
    expect(result.current.recommendedId).toBeNull();

    const pending = createDeferred<ConfigPresetListResponse>();
    listPresets.mockReturnValueOnce(pending.promise);
    let cancelled: { presets: ConfigPresetItem[]; recommendedPresetId: string | null } | undefined;
    await act(async () => {
      const pendingLoad = result.current.load('refresh');
      await result.current.load('refresh');
      pending.reject(new CancelledError(CONFIG_PRESETS_LIST_CANCEL));
      cancelled = await pendingLoad;
    });
    expect(cancelled).toBeUndefined();
  });
});
