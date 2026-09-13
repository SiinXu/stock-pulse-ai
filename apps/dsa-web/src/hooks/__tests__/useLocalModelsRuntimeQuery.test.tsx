// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { LocalModelRuntimeState } from '../../types/localModels';
import {
  LOCAL_MODELS_RUNTIME_CANCEL,
  LOCAL_MODELS_RUNTIME_QUERY_KEY,
  LOCAL_MODELS_RUNTIME_QUERY_SCHEDULE,
  fetchLocalModelsRuntime,
  isLocalModelsRuntimeCancelledError,
  useLocalModelsRuntimeQuery,
} from '../useLocalModelsRuntimeQuery';

const getRuntime = vi.fn<() => Promise<LocalModelRuntimeState>>();

function runtime(overrides: Partial<LocalModelRuntimeState> = {}): LocalModelRuntimeState {
  return {
    runtime: 'ollama',
    status: 'running',
    installedModels: ['qwen3:4b'],
    manualPullSupported: false,
    localInstallPlatform: 'macos',
    totalMemoryGb: 16,
    configuration: {
      configVersion: 'config-1',
      registeredModels: ['qwen3:4b'],
      primaryModel: 'ollama/qwen3:4b',
      agentModel: '',
    },
    ...overrides,
  };
}

function serverError(): Error {
  return Object.assign(new Error('runtime unavailable'), {
    response: {
      status: 500,
      data: { error: 'internal', message: 'runtime unavailable' },
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
  queryKey: readonly unknown[] = LOCAL_MODELS_RUNTIME_QUERY_KEY,
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertExactLocalModelsRuntimeOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'local-models' && key.length === 1).toBe(false);
    expect([...key]).not.toEqual(['local-models', 'catalog']);
    expect(key[0] === 'settings').toBe(false);
    expect(key[0] === 'generation-backend').toBe(false);
    expect(key[0] === 'intelligence').toBe(false);
    expect(key[0] === 'config-presets').toBe(false);
    expect(key[0] === 'investment-framework').toBe(false);
    expect(key[0] === 'scheduled-tasks').toBe(false);
    expect(key[0] === 'scheduler').toBe(false);
    expect(key[0] === 'plugins').toBe(false);
    expect(key[0] === 'watchlist').toBe(false);
    expect(key[0] === 'scorecard').toBe(false);
    expect(key[0] === 'home').toBe(false);
    expect(key[0] === 'kronos').toBe(false);
    expect(key[0] === 'data-providers').toBe(false);
    expect(key[0] === 'outbound-activity').toBe(false);
    expect(key[0] === 'security-audit').toBe(false);
    expect(key[0] === 'capabilities').toBe(false);
    expect(key[0] === 'agent-models').toBe(false);
    expect(key[0] === 'notifications').toBe(false);
    if (key[0] === 'local-models') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['local-models', 'runtime']);
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

describe('useLocalModelsRuntimeQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    getRuntime.mockResolvedValue(runtime());
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

  it('pins the exact runtime key, schedule, and getRuntime with no signal or language', async () => {
    expect([...LOCAL_MODELS_RUNTIME_QUERY_KEY]).toEqual(['local-models', 'runtime']);
    expect(LOCAL_MODELS_RUNTIME_QUERY_KEY).toHaveLength(2);
    expect(LOCAL_MODELS_RUNTIME_QUERY_KEY).not.toContain('language');
    expect(LOCAL_MODELS_RUNTIME_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(LOCAL_MODELS_RUNTIME_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchLocalModelsRuntime(getRuntime, { signal: controller.signal });
    expect(getRuntime).toHaveBeenCalledTimes(1);
    expect(getRuntime.mock.calls[0]).toEqual([]);
  });

  it('is not barrel-exported, does not auto-GET on mount, and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useLocalModelsRuntimeQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useLocalModelsRuntimeQuery(getRuntime), { wrapper });

    await flushQueryMicrotasks();
    expect(getRuntime).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.loadRuntime();
    });

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['local-models', 'runtime']);
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
        queryKey: LOCAL_MODELS_RUNTIME_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(getRuntime.mock.calls[0]).toEqual([]);
  });

  it('returns a successful running runtime snapshot', async () => {
    const live = runtime({
      status: 'running',
      installedModels: ['qwen3:4b', 'fin-r1:7b'],
    });
    getRuntime.mockResolvedValueOnce(live);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useLocalModelsRuntimeQuery(getRuntime), { wrapper });

    let next: LocalModelRuntimeState | undefined;
    await act(async () => {
      next = await result.current.loadRuntime();
    });

    expect(getRuntime).toHaveBeenCalledTimes(1);
    expect(getRuntime.mock.calls[0]).toEqual([]);
    expect(next).toEqual(live);
    expect(next?.status).toBe('running');
  });

  it('rethrows a 500 without retrying even when the test client default would retry', async () => {
    getRuntime.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useLocalModelsRuntimeQuery(getRuntime), { wrapper });

    await act(async () => {
      await expect(result.current.loadRuntime()).rejects.toBeDefined();
    });
    expect(getRuntime).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.retry).toBe(false);
  });

  it('retries after 500 with another GET and can recover', async () => {
    const recovered = runtime({ status: 'running', operation: 'idle' });
    getRuntime
      .mockRejectedValueOnce(serverError())
      .mockResolvedValueOnce(recovered);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useLocalModelsRuntimeQuery(getRuntime), { wrapper });

    await act(async () => {
      await expect(result.current.loadRuntime()).rejects.toBeDefined();
    });
    expect(getRuntime).toHaveBeenCalledTimes(1);

    let next: LocalModelRuntimeState | undefined;
    await act(async () => {
      next = await result.current.loadRuntime();
    });

    expect(getRuntime).toHaveBeenCalledTimes(2);
    expect(next).toEqual(recovered);
  });

  it('same-key refresh cancel+remove then fetchQuery', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useLocalModelsRuntimeQuery(getRuntime), { wrapper });

    await act(async () => {
      await result.current.loadRuntime();
    });
    expect(getRuntime).toHaveBeenCalledTimes(1);

    const pending = createDeferred<LocalModelRuntimeState>();
    getRuntime.mockReturnValueOnce(pending.promise);
    let second: Promise<LocalModelRuntimeState> | undefined;
    await act(async () => {
      second = result.current.loadRuntime();
    });

    await act(async () => {
      pending.resolve(runtime({ status: 'running', totalMemoryGb: 32 }));
      await second;
    });

    expect(getRuntime).toHaveBeenCalledTimes(2);
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
    assertExactLocalModelsRuntimeOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactLocalModelsRuntimeOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('never prefix-cancels or prefix-removes local-models, catalog, settings, generation-backend, intelligence, or sibling keys', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useLocalModelsRuntimeQuery(getRuntime), { wrapper });
    await act(async () => {
      await result.current.loadRuntime();
    });
    await act(async () => {
      await result.current.loadRuntime();
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
      && filters.queryKey[0] === 'local-models'
      && filters.queryKey[1] === 'catalog'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'settings'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'generation-backend'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'intelligence'
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
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'scorecard'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'data-providers'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'outbound-activity'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'security-audit'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'capabilities'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'agent-models'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'notifications'
    ))).toBe(false);
    assertExactLocalModelsRuntimeOps(allOps);
  });

  it('does not refetch when the window regains focus or reconnects', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useLocalModelsRuntimeQuery(getRuntime), { wrapper });

    await act(async () => {
      await result.current.loadRuntime();
    });
    expect(queryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(queryOptions(client)?.staleTime).toBe(0);
    expect(getRuntime).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
      onlineManager.setOnline(false);
      onlineManager.setOnline(true);
    });

    expect(getRuntime).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call getRuntime again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useLocalModelsRuntimeQuery(getRuntime), { wrapper });
    await act(async () => {
      await result.current.loadRuntime();
    });
    expect(getRuntime).toHaveBeenCalledTimes(1);
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

    expect(getRuntime).toHaveBeenCalledTimes(1);
  });

  it('issues getRuntime while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useLocalModelsRuntimeQuery(getRuntime), { wrapper });

    await act(async () => {
      await result.current.loadRuntime();
    });
    expect(getRuntime).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.networkMode).toBe('always');
  });

  it('removes the exact runtime key on unmount and ignores a late 500', async () => {
    const pending = createDeferred<LocalModelRuntimeState>();
    getRuntime.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useLocalModelsRuntimeQuery(getRuntime), { wrapper });

    let inFlight: Promise<LocalModelRuntimeState> | undefined;
    await act(async () => {
      inFlight = result.current.loadRuntime();
    });
    await waitFor(() => expect(getRuntime).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
      await inFlight?.catch(() => undefined);
      await Promise.resolve();
    });

    expect(client.getQueryState(LOCAL_MODELS_RUNTIME_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['local-models'] })).toHaveLength(0);
    expect(queryFetchStatus(client, LOCAL_MODELS_RUNTIME_QUERY_KEY)).toBeUndefined();
  });

  it('lets a newer GET win over a stale runtime so a cancelled first load cannot resurrect', async () => {
    const first = createDeferred<LocalModelRuntimeState>();
    const live = runtime({ status: 'running', totalMemoryGb: 64 });
    getRuntime
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(live);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useLocalModelsRuntimeQuery(getRuntime), { wrapper });

    let staleError: unknown;
    let newer: LocalModelRuntimeState | undefined;
    await act(async () => {
      const stale = result.current.loadRuntime();
      void stale.catch((error: unknown) => {
        staleError = error;
      });
    });
    await waitFor(() => expect(getRuntime).toHaveBeenCalledTimes(1));
    await act(async () => {
      newer = await result.current.loadRuntime();
    });
    expect(newer).toEqual(live);
    expect(getRuntime).toHaveBeenCalledTimes(2);

    await act(async () => {
      first.resolve(runtime({ status: 'unavailable', totalMemoryGb: 1 }));
      await first.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(newer?.status).toBe('running');
    expect(newer?.totalMemoryGb).toBe(64);
    expect(
      staleError === undefined || isLocalModelsRuntimeCancelledError(staleError),
    ).toBe(true);
  });

  it('classifies CancelledError without treating it as a runtime transport failure', async () => {
    expect(isLocalModelsRuntimeCancelledError(
      new CancelledError(LOCAL_MODELS_RUNTIME_CANCEL),
    )).toBe(true);
    expect(isLocalModelsRuntimeCancelledError(serverError())).toBe(false);
  });

  it('overlapping loadRuntime from a second living consumer joins instead of cancelling', async () => {
    const pending = createDeferred<LocalModelRuntimeState>();
    const live = runtime({ status: 'running', totalMemoryGb: 24 });
    getRuntime.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const a = renderHook(() => useLocalModelsRuntimeQuery(getRuntime), { wrapper });

    let aResult: LocalModelRuntimeState | undefined;
    let aError: unknown;
    let bResult: LocalModelRuntimeState | undefined;
    let bError: unknown;
    await act(async () => {
      void a.result.current.loadRuntime().then(
        (value) => { aResult = value; },
        (error: unknown) => { aError = error; },
      );
    });
    await waitFor(() => expect(getRuntime).toHaveBeenCalledTimes(1));
    const cancelsAfterFirst = cancelSpy.mock.calls.length;
    const removesAfterFirst = removeSpy.mock.calls.length;

    const b = renderHook(() => useLocalModelsRuntimeQuery(getRuntime), { wrapper });
    await act(async () => {
      void b.result.current.loadRuntime().then(
        (value) => { bResult = value; },
        (error: unknown) => { bError = error; },
      );
    });
    await flushQueryMicrotasks();

    expect(getRuntime).toHaveBeenCalledTimes(1);
    expect(cancelSpy.mock.calls.length).toBe(cancelsAfterFirst);
    expect(removeSpy.mock.calls.length).toBe(removesAfterFirst);

    await act(async () => {
      pending.resolve(live);
      await pending.promise;
      await Promise.resolve();
    });

    expect(aError).toBeUndefined();
    expect(bError).toBeUndefined();
    expect(isLocalModelsRuntimeCancelledError(aError)).toBe(false);
    expect(aResult).toEqual(live);
    expect(bResult).toEqual(live);
    expect(client.getQueryState(LOCAL_MODELS_RUNTIME_QUERY_KEY)?.status).toBe('success');
    a.unmount();
    b.unmount();
  });

  it('unmount of a non-last consumer leaves the remaining in-flight runtime fetch intact', async () => {
    const pending = createDeferred<LocalModelRuntimeState>();
    const live = runtime({ status: 'running', totalMemoryGb: 24 });
    getRuntime.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const a = renderHook(() => useLocalModelsRuntimeQuery(getRuntime), { wrapper });

    let aError: unknown;
    let bResult: LocalModelRuntimeState | undefined;
    let bError: unknown;
    await act(async () => {
      void a.result.current.loadRuntime().catch((error: unknown) => {
        aError = error;
      });
    });
    await waitFor(() => expect(getRuntime).toHaveBeenCalledTimes(1));

    const b = renderHook(() => useLocalModelsRuntimeQuery(getRuntime), { wrapper });
    await act(async () => {
      void b.result.current.loadRuntime().then(
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
    expect(client.getQueryState(LOCAL_MODELS_RUNTIME_QUERY_KEY)).toBeDefined();

    await act(async () => {
      pending.resolve(live);
      await pending.promise;
      await Promise.resolve();
    });

    expect(bError).toBeUndefined();
    expect(isLocalModelsRuntimeCancelledError(aError)).toBe(false);
    expect(bResult).toEqual(live);
    expect(client.getQueryState(LOCAL_MODELS_RUNTIME_QUERY_KEY)?.status).toBe('success');

    b.unmount();
    expect(client.getQueryState(LOCAL_MODELS_RUNTIME_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['local-models'] })).toHaveLength(0);
  });
});
