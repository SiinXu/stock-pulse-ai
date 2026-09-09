// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { localModelsApi } from '../../api/localModels';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { LocalModelCatalogResponse } from '../../types/localModels';
import {
  LOCAL_MODELS_CATALOG_CANCEL,
  LOCAL_MODELS_CATALOG_QUERY_KEY,
  LOCAL_MODELS_CATALOG_QUERY_SCHEDULE,
  fetchLocalModelsCatalog,
  isLocalModelsCatalogCancelledError,
  useLocalModelsCatalogQuery,
} from '../useLocalModelsCatalogQuery';

vi.mock('../../api/localModels', () => ({
  localModelsApi: {
    getCatalog: vi.fn(),
  },
}));

const getCatalog = vi.mocked(localModelsApi.getCatalog);

function catalog(overrides: Partial<LocalModelCatalogResponse> = {}): LocalModelCatalogResponse {
  return {
    schemaVersion: 1,
    verifiedAt: '2026-07-23',
    models: [],
    ...overrides,
  };
}

function serverError(): Error {
  return Object.assign(new Error('catalog unavailable'), {
    response: {
      status: 500,
      data: { error: 'internal', message: 'catalog unavailable' },
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
  queryKey: readonly unknown[] = LOCAL_MODELS_CATALOG_QUERY_KEY,
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertExactLocalModelsCatalogOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'local-models' && key.length === 1).toBe(false);
    expect(key[0] === 'settings').toBe(false);
    expect(key[0] === 'config-presets').toBe(false);
    expect(key[0] === 'investment-framework').toBe(false);
    expect(key[0] === 'scheduled-tasks').toBe(false);
    expect(key[0] === 'scheduler').toBe(false);
    expect(key[0] === 'plugins').toBe(false);
    expect(key[0] === 'watchlist').toBe(false);
    expect(key[0] === 'home').toBe(false);
    expect(key[0] === 'kronos').toBe(false);
    if (key[0] === 'local-models') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['local-models', 'catalog']);
      expect(key).toHaveLength(2);
      expect(key).not.toContain('language');
      expect(key).not.toContain('zh');
      expect(key).not.toContain('en');
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

describe('useLocalModelsCatalogQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    getCatalog.mockResolvedValue(catalog());
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

  it('pins the exact catalog key, schedule, and getCatalog() with no signal or language', async () => {
    expect([...LOCAL_MODELS_CATALOG_QUERY_KEY]).toEqual(['local-models', 'catalog']);
    expect(LOCAL_MODELS_CATALOG_QUERY_KEY).toHaveLength(2);
    expect(LOCAL_MODELS_CATALOG_QUERY_KEY).not.toContain('language');
    expect(LOCAL_MODELS_CATALOG_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(LOCAL_MODELS_CATALOG_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchLocalModelsCatalog({ signal: controller.signal });
    expect(getCatalog).toHaveBeenCalledTimes(1);
    expect(getCatalog.mock.calls[0]).toEqual([]);
  });

  it('is not barrel-exported, does not auto-GET on mount, and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useLocalModelsCatalogQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useLocalModelsCatalogQuery(), { wrapper });

    await flushQueryMicrotasks();
    expect(getCatalog).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.loadCatalog();
    });

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['local-models', 'catalog']);
      expect(options.queryKey).not.toContain('language');
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
      expect(scheduled.refetchInterval).toBeUndefined();
    }
    expect(
      client.getQueryCache().find({
        queryKey: LOCAL_MODELS_CATALOG_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(getCatalog.mock.calls[0]).toEqual([]);
  });

  it('returns a successful catalog including an empty 200 roster', async () => {
    const empty = catalog({ models: [] });
    getCatalog.mockResolvedValueOnce(empty);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useLocalModelsCatalogQuery(), { wrapper });

    let next: LocalModelCatalogResponse | undefined;
    await act(async () => {
      next = await result.current.loadCatalog();
    });

    expect(getCatalog).toHaveBeenCalledTimes(1);
    expect(next).toEqual(empty);
  });

  it('rethrows a 500 without retrying even when the test client default would retry', async () => {
    getCatalog.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useLocalModelsCatalogQuery(), { wrapper });

    await act(async () => {
      await expect(result.current.loadCatalog()).rejects.toBeDefined();
    });
    expect(getCatalog).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.retry).toBe(false);
  });

  it('retries after 500 with another GET and can recover', async () => {
    const recovered = catalog({ verifiedAt: '2026-08-01' });
    getCatalog
      .mockRejectedValueOnce(serverError())
      .mockResolvedValueOnce(recovered);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useLocalModelsCatalogQuery(), { wrapper });

    await act(async () => {
      await expect(result.current.loadCatalog()).rejects.toBeDefined();
    });
    expect(getCatalog).toHaveBeenCalledTimes(1);

    let next: LocalModelCatalogResponse | undefined;
    await act(async () => {
      next = await result.current.loadCatalog();
    });

    expect(getCatalog).toHaveBeenCalledTimes(2);
    expect(next).toEqual(recovered);
  });

  it('same-key refresh cancel+remove then fetchQuery', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useLocalModelsCatalogQuery(), { wrapper });

    await act(async () => {
      await result.current.loadCatalog();
    });
    expect(getCatalog).toHaveBeenCalledTimes(1);

    const pending = createDeferred<LocalModelCatalogResponse>();
    getCatalog.mockReturnValueOnce(pending.promise);
    let second: Promise<LocalModelCatalogResponse> | undefined;
    await act(async () => {
      second = result.current.loadCatalog();
    });

    await act(async () => {
      pending.resolve(catalog({ verifiedAt: '2026-08-02' }));
      await second;
    });

    expect(getCatalog).toHaveBeenCalledTimes(2);
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
    assertExactLocalModelsCatalogOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactLocalModelsCatalogOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('never prefix-cancels or prefix-removes local-models, settings, config-presets, investment-framework, scheduled-tasks, scheduler, plugins, watchlist, kronos, or home keys', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useLocalModelsCatalogQuery(), { wrapper });
    await act(async () => {
      await result.current.loadCatalog();
    });
    await act(async () => {
      await result.current.loadCatalog();
    });

    const allOps = [
      ...cancelSpy.mock.calls,
      ...removeSpy.mock.calls,
    ] as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>;
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey.length === 1
      && filters.queryKey[0] === 'local-models'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'settings'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'config-presets'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'investment-framework'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'scheduled-tasks'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'scheduler'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'plugins'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'watchlist'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'home'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'kronos'
    ))).toBe(false);
    assertExactLocalModelsCatalogOps(allOps);
  });

  it('does not refetch when the window regains focus or reconnects', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useLocalModelsCatalogQuery(), { wrapper });

    await act(async () => {
      await result.current.loadCatalog();
    });
    expect(queryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(queryOptions(client)?.staleTime).toBe(0);
    expect(getCatalog).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
      onlineManager.setOnline(false);
      onlineManager.setOnline(true);
    });

    expect(getCatalog).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call getCatalog() again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useLocalModelsCatalogQuery(), { wrapper });
    await act(async () => {
      await result.current.loadCatalog();
    });
    expect(getCatalog).toHaveBeenCalledTimes(1);
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

    expect(getCatalog).toHaveBeenCalledTimes(1);
  });

  it('issues getCatalog() while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useLocalModelsCatalogQuery(), { wrapper });

    await act(async () => {
      await result.current.loadCatalog();
    });
    expect(getCatalog).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.networkMode).toBe('always');
  });

  it('removes the exact catalog key on unmount and ignores a late 500', async () => {
    const pending = createDeferred<LocalModelCatalogResponse>();
    getCatalog.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useLocalModelsCatalogQuery(), { wrapper });

    let inFlight: Promise<LocalModelCatalogResponse> | undefined;
    await act(async () => {
      inFlight = result.current.loadCatalog();
    });
    await waitFor(() => expect(getCatalog).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
      await inFlight?.catch(() => undefined);
      await Promise.resolve();
    });

    expect(client.getQueryState(LOCAL_MODELS_CATALOG_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['local-models'] })).toHaveLength(0);
    expect(queryFetchStatus(client, LOCAL_MODELS_CATALOG_QUERY_KEY)).toBeUndefined();
  });

  it('lets a newer GET win over a stale catalog so a cancelled first load cannot resurrect', async () => {
    const first = createDeferred<LocalModelCatalogResponse>();
    const live = catalog({ verifiedAt: '2026-09-01' });
    getCatalog
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(live);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useLocalModelsCatalogQuery(), { wrapper });

    let staleError: unknown;
    let newer: LocalModelCatalogResponse | undefined;
    await act(async () => {
      const stale = result.current.loadCatalog();
      void stale.catch((error: unknown) => {
        staleError = error;
      });
    });
    await waitFor(() => expect(getCatalog).toHaveBeenCalledTimes(1));
    await act(async () => {
      newer = await result.current.loadCatalog();
    });
    expect(newer).toEqual(live);
    expect(getCatalog).toHaveBeenCalledTimes(2);

    await act(async () => {
      first.resolve(catalog({ verifiedAt: 'stale' }));
      await first.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(newer?.verifiedAt).toBe('2026-09-01');
    expect(
      staleError === undefined || isLocalModelsCatalogCancelledError(staleError),
    ).toBe(true);
  });

  it('classifies CancelledError without treating it as a catalog transport failure', async () => {
    expect(isLocalModelsCatalogCancelledError(
      new CancelledError(LOCAL_MODELS_CATALOG_CANCEL),
    )).toBe(true);
    expect(isLocalModelsCatalogCancelledError(serverError())).toBe(false);
  });

  it('overlapping loadCatalog from a second living consumer joins instead of cancelling', async () => {
    const pending = createDeferred<LocalModelCatalogResponse>();
    const live = catalog({ verifiedAt: '2026-09-09' });
    getCatalog.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const a = renderHook(() => useLocalModelsCatalogQuery(), { wrapper });

    let aResult: LocalModelCatalogResponse | undefined;
    let aError: unknown;
    let bResult: LocalModelCatalogResponse | undefined;
    let bError: unknown;
    await act(async () => {
      void a.result.current.loadCatalog().then(
        (value) => { aResult = value; },
        (error: unknown) => { aError = error; },
      );
    });
    await waitFor(() => expect(getCatalog).toHaveBeenCalledTimes(1));
    const cancelsAfterFirst = cancelSpy.mock.calls.length;
    const removesAfterFirst = removeSpy.mock.calls.length;

    const b = renderHook(() => useLocalModelsCatalogQuery(), { wrapper });
    await act(async () => {
      void b.result.current.loadCatalog().then(
        (value) => { bResult = value; },
        (error: unknown) => { bError = error; },
      );
    });
    await flushQueryMicrotasks();

    expect(getCatalog).toHaveBeenCalledTimes(1);
    expect(cancelSpy.mock.calls.length).toBe(cancelsAfterFirst);
    expect(removeSpy.mock.calls.length).toBe(removesAfterFirst);

    await act(async () => {
      pending.resolve(live);
      await pending.promise;
      await Promise.resolve();
    });

    expect(aError).toBeUndefined();
    expect(bError).toBeUndefined();
    expect(isLocalModelsCatalogCancelledError(aError)).toBe(false);
    expect(aResult).toEqual(live);
    expect(bResult).toEqual(live);
    expect(client.getQueryState(LOCAL_MODELS_CATALOG_QUERY_KEY)?.status).toBe('success');
    a.unmount();
    b.unmount();
  });

  it('unmount of a non-last consumer leaves the remaining in-flight catalog fetch intact', async () => {
    const pending = createDeferred<LocalModelCatalogResponse>();
    const live = catalog({ verifiedAt: '2026-09-09' });
    getCatalog.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const a = renderHook(() => useLocalModelsCatalogQuery(), { wrapper });

    let aError: unknown;
    let bResult: LocalModelCatalogResponse | undefined;
    let bError: unknown;
    await act(async () => {
      void a.result.current.loadCatalog().catch((error: unknown) => {
        aError = error;
      });
    });
    await waitFor(() => expect(getCatalog).toHaveBeenCalledTimes(1));

    const b = renderHook(() => useLocalModelsCatalogQuery(), { wrapper });
    await act(async () => {
      void b.result.current.loadCatalog().then(
        (value) => { bResult = value; },
        (error: unknown) => { bError = error; },
      );
    });
    await flushQueryMicrotasks();
    const cancelsBeforeUnmount = cancelSpy.mock.calls.length;
    const removesBeforeUnmount = removeSpy.mock.calls.length;

    a.unmount();
    await flushQueryMicrotasks();
    expect(cancelSpy.mock.calls.length).toBe(cancelsBeforeUnmount);
    expect(removeSpy.mock.calls.length).toBe(removesBeforeUnmount);
    expect(client.getQueryState(LOCAL_MODELS_CATALOG_QUERY_KEY)).toBeDefined();

    await act(async () => {
      pending.resolve(live);
      await pending.promise;
      await Promise.resolve();
    });

    expect(bError).toBeUndefined();
    expect(isLocalModelsCatalogCancelledError(aError)).toBe(false);
    expect(bResult).toEqual(live);
    expect(client.getQueryState(LOCAL_MODELS_CATALOG_QUERY_KEY)?.status).toBe('success');

    b.unmount();
    expect(client.getQueryState(LOCAL_MODELS_CATALOG_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['local-models'] })).toHaveLength(0);
  });
});
