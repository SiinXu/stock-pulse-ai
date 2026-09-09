// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApiError, createParsedApiError } from '../../api/error';
import { investmentFrameworkApi } from '../../api/investmentFramework';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { InvestmentFrameworkResponse } from '../../types/investmentFramework';
import {
  INVESTMENT_FRAMEWORK_CURRENT_CANCEL,
  INVESTMENT_FRAMEWORK_CURRENT_QUERY_KEY,
  INVESTMENT_FRAMEWORK_CURRENT_QUERY_SCHEDULE,
  fetchInvestmentFrameworkCurrent,
  useInvestmentFrameworkQuery,
} from '../useInvestmentFrameworkQuery';

vi.mock('../../api/investmentFramework', () => ({
  investmentFrameworkApi: {
    get: vi.fn(),
  },
}));

const getFramework = vi.mocked(investmentFrameworkApi.get);

function framework(overrides: Partial<InvestmentFrameworkResponse> = {}): InvestmentFrameworkResponse {
  return {
    frameworkId: 1,
    scope: 'local',
    version: 1,
    activeVersion: 1,
    revision: 7,
    isActive: true,
    content: {
      title: 'Structured',
      freeFormRules: 'Hold cash when uncertain',
      riskRules: [],
      trackingCriteria: [],
    },
    createdAt: '2026-07-26T00:00:00Z',
    updatedAt: '2026-07-26T00:00:00Z',
    versionCreatedAt: '2026-07-26T00:00:00Z',
    ...overrides,
  };
}

function missingError(overrides: { status?: number; code?: string } = {}) {
  return createApiError(
    createParsedApiError({
      title: 'Not found',
      message: 'missing',
      rawMessage: 'missing',
      status: overrides.status ?? 404,
      category: 'http_error',
      code: overrides.code ?? 'investment_framework_not_found',
    }),
  );
}

function serverError() {
  return createApiError(
    createParsedApiError({
      title: '框架加载失败',
      message: '暂时无法读取个人投资框架。',
      rawMessage: 'framework unavailable',
      status: 500,
      category: 'http_error',
      code: 'framework_load_failed',
    }),
  );
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
  queryKey: readonly unknown[] = INVESTMENT_FRAMEWORK_CURRENT_QUERY_KEY,
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertExactInvestmentFrameworkCurrentOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'investment-framework' && key.length === 1).toBe(false);
    expect(key[0] === 'settings').toBe(false);
    expect(key[0] === 'config-presets').toBe(false);
    expect(key[0] === 'scheduled-tasks').toBe(false);
    expect(key[0] === 'scheduler').toBe(false);
    expect(key[0] === 'plugins').toBe(false);
    expect(key[0] === 'watchlist').toBe(false);
    expect(key[0] === 'home').toBe(false);
    if (key[0] === 'investment-framework') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['investment-framework', 'current']);
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

describe('useInvestmentFrameworkQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    getFramework.mockResolvedValue(framework());
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

  it('pins the exact current key, schedule, and get() with no signal or language', async () => {
    expect([...INVESTMENT_FRAMEWORK_CURRENT_QUERY_KEY]).toEqual(['investment-framework', 'current']);
    expect(INVESTMENT_FRAMEWORK_CURRENT_QUERY_KEY).toHaveLength(2);
    expect(INVESTMENT_FRAMEWORK_CURRENT_QUERY_KEY).not.toContain('language');
    expect(INVESTMENT_FRAMEWORK_CURRENT_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(INVESTMENT_FRAMEWORK_CURRENT_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchInvestmentFrameworkCurrent({ signal: controller.signal });
    expect(getFramework).toHaveBeenCalledTimes(1);
    expect(getFramework.mock.calls[0]).toEqual([]);
  });

  it('is not barrel-exported and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useInvestmentFrameworkQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['investment-framework', 'current']);
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
        queryKey: INVESTMENT_FRAMEWORK_CURRENT_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(getFramework.mock.calls[0]).toEqual([]);
  });

  it('fetches once on mount, sets framework/exists, and leaves zero live observers', async () => {
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getFramework).toHaveBeenCalledTimes(1);
    expect(result.current.framework?.frameworkId).toBe(1);
    expect(result.current.exists).toBe(true);
    expect(result.current).not.toHaveProperty('isRefreshing');
    expect(result.current.loadError).toBeNull();
    expect(
      client.getQueryCache().find({
        queryKey: INVESTMENT_FRAMEWORK_CURRENT_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
  });

  it('treats HTTP 404 as a successful missing sentinel rather than a load error', async () => {
    getFramework.mockRejectedValueOnce(missingError({ status: 404, code: 'other' }));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.framework).toBeNull();
    expect(result.current.exists).toBe(false);
    expect(result.current.loadError).toBeNull();
  });

  it('treats investment_framework_not_found as a successful missing sentinel', async () => {
    getFramework.mockRejectedValueOnce(missingError({ status: 409, code: 'investment_framework_not_found' }));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.framework).toBeNull();
    expect(result.current.exists).toBe(false);
    expect(result.current.loadError).toBeNull();
  });

  it('keeps an initial 500 as a failed read, not missing, even when the test client default would retry', async () => {
    getFramework.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });

    await waitFor(() => expect(result.current.loadError).not.toBeNull());
    expect(getFramework).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(result.current.framework).toBeNull();
    expect(result.current.exists).toBe(false);
    expect(result.current.loadError?.status).toBe(500);
    expect(result.current.loadError?.code).toBe('framework_load_failed');
    expect(result.current.isLoading).toBe(false);
  });

  it('retries after 500 with another GET and can recover to an existing framework', async () => {
    getFramework
      .mockRejectedValueOnce(serverError())
      .mockResolvedValueOnce(framework({ revision: 8 }));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });
    await waitFor(() => expect(result.current.loadError?.status).toBe(500));
    expect(getFramework).toHaveBeenCalledTimes(1);

    let recovered: { framework: InvestmentFrameworkResponse | null; exists: boolean } | undefined;
    await act(async () => {
      recovered = await result.current.load();
    });

    expect(getFramework).toHaveBeenCalledTimes(2);
    expect(recovered).toEqual({ framework: framework({ revision: 8 }), exists: true });
    expect(result.current.framework?.revision).toBe(8);
    expect(result.current.exists).toBe(true);
    expect(result.current.loadError).toBeNull();
  });

  it('preserves last-good framework/exists when a later refresh fails', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });
    await waitFor(() => expect(result.current.framework?.revision).toBe(7));

    getFramework.mockRejectedValueOnce(serverError());
    let failed: { framework: InvestmentFrameworkResponse | null; exists: boolean } | undefined;
    await act(async () => {
      failed = await result.current.load();
    });

    expect(failed).toBeUndefined();
    expect(result.current.framework?.revision).toBe(7);
    expect(result.current.exists).toBe(true);
    expect(result.current.loadError?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
  });

  it('preserves prior framework while a refresh is in flight and sets isLoading', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });
    await waitFor(() => expect(result.current.framework?.revision).toBe(7));

    const pending = createDeferred<InvestmentFrameworkResponse>();
    getFramework.mockReturnValueOnce(pending.promise);
    await act(async () => {
      void result.current.load();
    });
    await waitFor(() => expect(result.current.isLoading).toBe(true));
    expect(result.current.framework?.revision).toBe(7);
    expect(result.current.exists).toBe(true);

    await act(async () => {
      pending.resolve(framework({ revision: 9, version: 2 }));
      await pending.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.framework?.revision).toBe(9);
    expect(result.current.exists).toBe(true);
    expect(result.current.loadError).toBeNull();
  });

  it('does not set loadError when get() settles as CancelledError', async () => {
    getFramework.mockRejectedValue(new CancelledError(INVESTMENT_FRAMEWORK_CURRENT_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.loadError).toBeNull();
    expect(result.current.framework).toBeNull();
    expect(result.current.exists).toBe(false);
  });

  it('removes the exact current key on unmount and ignores a late 500', async () => {
    const pending = createDeferred<InvestmentFrameworkResponse>();
    getFramework.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });

    await waitFor(() => expect(getFramework).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.loadError).toBeNull();
    expect(result.current.framework).toBeNull();
    expect(client.getQueryState(INVESTMENT_FRAMEWORK_CURRENT_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['investment-framework'] })).toHaveLength(0);
    expect(queryFetchStatus(client, INVESTMENT_FRAMEWORK_CURRENT_QUERY_KEY)).toBeUndefined();
  });

  it('lets a newer 500 win over a stale 200 so a later success cannot resurrect', async () => {
    const first = createDeferred<InvestmentFrameworkResponse>();
    getFramework
      .mockReturnValueOnce(first.promise)
      .mockRejectedValueOnce(serverError());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });

    await waitFor(() => expect(getFramework).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load();
    });
    await waitFor(() => expect(getFramework).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.loadError?.status).toBe(500));

    expect(result.current.framework).toBeNull();
    expect(result.current.exists).toBe(false);
    expect(result.current.isLoading).toBe(false);

    await act(async () => {
      first.resolve(framework({
        revision: 3,
        content: { title: 'Stale', riskRules: [], trackingCriteria: [] },
      }));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.framework).toBeNull();
    expect(result.current.exists).toBe(false);
    expect(result.current.loadError?.status).toBe(500);
  });

  it('lets a newer 200 win over a stale 500', async () => {
    const first = createDeferred<InvestmentFrameworkResponse>();
    getFramework
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(framework({ revision: 11, content: { title: 'Live', riskRules: [], trackingCriteria: [] } }));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });

    await waitFor(() => expect(getFramework).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load();
    });
    await waitFor(() => expect(getFramework).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.framework?.revision).toBe(11));

    expect(result.current.loadError).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.exists).toBe(true);

    await act(async () => {
      first.reject(serverError());
      await first.promise.catch(() => undefined);
    });

    expect(result.current.framework?.revision).toBe(11);
    expect(result.current.exists).toBe(true);
    expect(result.current.loadError).toBeNull();
  });

  it('lets a newer missing sentinel win over a stale 200', async () => {
    const first = createDeferred<InvestmentFrameworkResponse>();
    getFramework
      .mockReturnValueOnce(first.promise)
      .mockRejectedValueOnce(missingError());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });

    await waitFor(() => expect(getFramework).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load();
    });
    await waitFor(() => expect(getFramework).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.exists).toBe(false));
    expect(result.current.framework).toBeNull();
    expect(result.current.loadError).toBeNull();

    await act(async () => {
      first.resolve(framework({ revision: 99 }));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.framework).toBeNull();
    expect(result.current.exists).toBe(false);
    expect(result.current.loadError).toBeNull();
  });

  it('same-key refresh cancel+remove then fetchQuery and keeps last-good on refresh 500', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });

    await waitFor(() => expect(result.current.framework?.revision).toBe(7));
    expect(getFramework).toHaveBeenCalledTimes(1);
    expect(result.current.isLoading).toBe(false);

    const pending = createDeferred<InvestmentFrameworkResponse>();
    getFramework.mockReturnValueOnce(pending.promise);
    await act(async () => {
      void result.current.load();
    });
    await waitFor(() => expect(result.current.isLoading).toBe(true));

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.loadError).not.toBeNull());

    expect(result.current.framework?.revision).toBe(7);
    expect(result.current.exists).toBe(true);
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
    assertExactInvestmentFrameworkCurrentOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactInvestmentFrameworkCurrentOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('never prefix-cancels or prefix-removes investment-framework, settings, config-presets, scheduled-tasks, scheduler, plugins, watchlist, or home keys', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.load();
    });

    const allOps = [
      ...cancelSpy.mock.calls,
      ...removeSpy.mock.calls,
    ] as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>;
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey.length === 1
      && filters.queryKey[0] === 'investment-framework'
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
    assertExactInvestmentFrameworkCurrentOps(allOps);
  });

  it('does not refetch when the window regains focus or reconnects', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(queryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(queryOptions(client)?.staleTime).toBe(0);
    expect(getFramework).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
      onlineManager.setOnline(false);
      onlineManager.setOnline(true);
    });

    expect(getFramework).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call get() again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getFramework).toHaveBeenCalledTimes(1);
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

    expect(getFramework).toHaveBeenCalledTimes(1);
  });

  it('issues get() while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getFramework).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.networkMode).toBe('always');
    expect(result.current.framework?.revision).toBe(7);
  });

  it('returns successful { framework, exists } from load(), including missing, and undefined on error or cancel', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    getFramework.mockResolvedValueOnce(framework({ revision: 12 }));
    let success: { framework: InvestmentFrameworkResponse | null; exists: boolean } | undefined;
    await act(async () => {
      success = await result.current.load();
    });
    expect(success).toEqual({
      framework: framework({ revision: 12 }),
      exists: true,
    });

    getFramework.mockRejectedValueOnce(missingError());
    let missing: { framework: InvestmentFrameworkResponse | null; exists: boolean } | undefined;
    await act(async () => {
      missing = await result.current.load();
    });
    expect(missing).toEqual({ framework: null, exists: false });
    expect(result.current.framework).toBeNull();
    expect(result.current.exists).toBe(false);
    expect(result.current.loadError).toBeNull();

    getFramework.mockRejectedValueOnce(serverError());
    let failed: { framework: InvestmentFrameworkResponse | null; exists: boolean } | undefined;
    await act(async () => {
      failed = await result.current.load();
    });
    expect(failed).toBeUndefined();
    expect(result.current.framework).toBeNull();
    expect(result.current.exists).toBe(false);
    expect(result.current.loadError?.status).toBe(500);

    const pending = createDeferred<InvestmentFrameworkResponse>();
    getFramework.mockReturnValueOnce(pending.promise);
    let cancelled: { framework: InvestmentFrameworkResponse | null; exists: boolean } | undefined;
    await act(async () => {
      const pendingLoad = result.current.load();
      await result.current.load();
      pending.reject(new CancelledError(INVESTMENT_FRAMEWORK_CURRENT_CANCEL));
      cancelled = await pendingLoad;
    });
    expect(cancelled).toBeUndefined();
  });

  it('exposes setters so mutations can patch framework/exists without a re-GET', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useInvestmentFrameworkQuery(), { wrapper });
    await waitFor(() => expect(result.current.exists).toBe(true));
    expect(getFramework).toHaveBeenCalledTimes(1);

    const created = framework({ revision: 20, version: 2 });
    act(() => {
      result.current.setFramework(created);
      result.current.setExists(true);
    });
    expect(result.current.framework).toEqual(created);
    expect(result.current.exists).toBe(true);

    act(() => {
      result.current.setFramework(null);
      result.current.setExists(false);
    });
    expect(result.current.framework).toBeNull();
    expect(result.current.exists).toBe(false);
    expect(getFramework).toHaveBeenCalledTimes(1);
  });
});
