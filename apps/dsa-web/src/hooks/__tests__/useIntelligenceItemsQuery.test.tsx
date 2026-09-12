// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { intelligenceApi } from '../../api/intelligence';
import type { IntelligenceItemListResponse } from '../../api/intelligence';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import {
  INTELLIGENCE_ITEMS_CANCEL,
  INTELLIGENCE_ITEMS_LIST_QUERY_KEY,
  INTELLIGENCE_ITEMS_QUERY_SCHEDULE,
  fetchIntelligenceItemsList,
  isIntelligenceItemsCancelledError,
  useIntelligenceItemsQuery,
} from '../useIntelligenceItemsQuery';

vi.mock('../../api/intelligence', () => ({
  intelligenceApi: {
    listSources: vi.fn(),
    listTemplates: vi.fn(),
    listItems: vi.fn(),
    createSource: vi.fn(),
    createSourceFromTemplate: vi.fn(),
    createDefaultSources: vi.fn(),
    testSource: vi.fn(),
    fetchSource: vi.fn(),
    fetchEnabledSources: vi.fn(),
  },
}));

const listItems = vi.mocked(intelligenceApi.listItems);
const listSources = vi.mocked(intelligenceApi.listSources);
const listTemplates = vi.mocked(intelligenceApi.listTemplates);
const createSource = vi.mocked(intelligenceApi.createSource);
const testSource = vi.mocked(intelligenceApi.testSource);
const fetchSource = vi.mocked(intelligenceApi.fetchSource);
const fetchEnabledSources = vi.mocked(intelligenceApi.fetchEnabledSources);
const createDefaultSources = vi.mocked(intelligenceApi.createDefaultSources);

function itemList(
  overrides: Partial<IntelligenceItemListResponse> = {},
): IntelligenceItemListResponse {
  return {
    items: [],
    total: 0,
    page: 1,
    pageSize: 20,
    ...overrides,
  };
}

function serverError(message = 'intelligence items unavailable'): Error {
  return Object.assign(new Error(message), {
    response: {
      status: 500,
      data: { error: 'internal', message },
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
  queryKey: readonly unknown[],
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function isExactKey(
  filters: { queryKey?: readonly unknown[]; exact?: boolean } | undefined,
  expected: readonly unknown[],
): boolean {
  const key = filters?.queryKey ?? [];
  return filters?.exact === true
    && key.length === expected.length
    && expected.every((item, index) => key[index] === item);
}

function assertExactIntelligenceItemsOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'intelligence' && key.length === 1).toBe(false);
    expect(key[0] === 'generation-backend').toBe(false);
    expect(key[0] === 'local-models').toBe(false);
    expect(key[0] === 'settings').toBe(false);
    expect(key[0] === 'plugins').toBe(false);
    expect(key[0] === 'config-presets').toBe(false);
    expect(key[0] === 'investment-framework').toBe(false);
    expect(key[0] === 'scheduled-tasks').toBe(false);
    expect(key[0] === 'scheduler').toBe(false);
    expect(key[0] === 'watchlist').toBe(false);
    expect(key[0] === 'scorecard').toBe(false);
    expect(key[0] === 'kronos').toBe(false);
    expect(key[0] === 'data-providers').toBe(false);
    expect(key[0] === 'outbound-activity').toBe(false);
    expect(key[0] === 'security-audit').toBe(false);
    expect(key[0] === 'capabilities').toBe(false);
    expect(key[0] === 'agent-models').toBe(false);
    expect(key[0] === 'notifications').toBe(false);
    expect(key[0] === 'home').toBe(false);
    if (key[0] === 'intelligence') {
      expect(filters?.exact).toBe(true);
      expect(key).toEqual(['intelligence', 'items', 'list']);
      expect(key).not.toContain('language');
      expect(key).not.toContain('zh');
      expect(key).not.toContain('en');
      expect(key).not.toContain(20);
      expect(key).not.toContain('20');
      expect(key[1]).not.toBe('sources');
      expect(key[1]).not.toBe('templates');
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

function assertSiblingGetsUntouched() {
  expect(listSources).not.toHaveBeenCalled();
  expect(listTemplates).not.toHaveBeenCalled();
  expect(createSource).not.toHaveBeenCalled();
  expect(testSource).not.toHaveBeenCalled();
  expect(fetchSource).not.toHaveBeenCalled();
  expect(fetchEnabledSources).not.toHaveBeenCalled();
  expect(createDefaultSources).not.toHaveBeenCalled();
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

describe('useIntelligenceItemsQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    listItems.mockResolvedValue(itemList());
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

  it('pins the exact key, schedule, and transport with pageSize baked in and no AbortSignal', async () => {
    expect([...INTELLIGENCE_ITEMS_LIST_QUERY_KEY]).toEqual(['intelligence', 'items', 'list']);
    expect(INTELLIGENCE_ITEMS_LIST_QUERY_KEY).toHaveLength(3);
    expect(INTELLIGENCE_ITEMS_LIST_QUERY_KEY).not.toContain('language');
    expect(INTELLIGENCE_ITEMS_LIST_QUERY_KEY).not.toContain(20);
    expect(INTELLIGENCE_ITEMS_LIST_QUERY_KEY).not.toContain('20');
    expect(INTELLIGENCE_ITEMS_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(INTELLIGENCE_ITEMS_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchIntelligenceItemsList({ signal: controller.signal });
    expect(listItems).toHaveBeenCalledTimes(1);
    expect(listItems).toHaveBeenCalledWith({ pageSize: 20 });
    expect(listItems.mock.calls[0]).toHaveLength(1);
    assertSiblingGetsUntouched();
  });

  it('is not barrel-exported, does not auto-GET on mount, and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useIntelligenceItemsQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useIntelligenceItemsQuery(), { wrapper });

    await flushQueryMicrotasks();
    expect(listItems).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.loadItems();
    });

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['intelligence', 'items', 'list']);
      expect(options.queryKey).not.toContain('language');
      expect(options.queryKey).not.toContain(20);
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
      expect(scheduled.refetchInterval).toBeUndefined();
    }
    expect(
      client.getQueryCache().find({
        queryKey: INTELLIGENCE_ITEMS_LIST_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(listItems).toHaveBeenCalledTimes(1);
    expect(listItems).toHaveBeenCalledWith({ pageSize: 20 });
    assertSiblingGetsUntouched();
  });

  it('loadItems returns the payload including an empty 200', async () => {
    const empty = itemList({ items: [], total: 0 });
    listItems.mockResolvedValueOnce(empty);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useIntelligenceItemsQuery(), { wrapper });

    let next: IntelligenceItemListResponse | undefined;
    await act(async () => {
      next = await result.current.loadItems();
    });

    expect(listItems).toHaveBeenCalledTimes(1);
    expect(listItems).toHaveBeenCalledWith({ pageSize: 20 });
    expect(next).toEqual(empty);
    assertSiblingGetsUntouched();
  });

  it('same-key refresh cancel+remove then fetchQuery without touching sources or templates', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useIntelligenceItemsQuery(), { wrapper });

    await act(async () => {
      await result.current.loadItems();
    });
    expect(listItems).toHaveBeenCalledTimes(1);

    cancelSpy.mockClear();
    removeSpy.mockClear();
    fetchSpy.mockClear();

    const pending = createDeferred<IntelligenceItemListResponse>();
    listItems.mockReturnValueOnce(pending.promise);
    let second: Promise<IntelligenceItemListResponse> | undefined;
    await act(async () => {
      second = result.current.loadItems();
    });

    await act(async () => {
      pending.resolve(itemList({ total: 1 }));
      await second;
    });

    expect(listItems).toHaveBeenCalledTimes(2);
    expect(fetchSpy).toHaveBeenCalled();
    expect(cancelSpy).toHaveBeenCalled();
    expect(removeSpy).toHaveBeenCalled();
    assertSilentCancelOptions(
      cancelSpy.mock.calls as Array<[filters?: unknown, options?: { silent?: boolean; revert?: boolean }]>,
    );
    expect(Math.min(...cancelSpy.mock.invocationCallOrder))
      .toBeLessThan(Math.min(...fetchSpy.mock.invocationCallOrder));
    expect(Math.min(...removeSpy.mock.invocationCallOrder))
      .toBeLessThan(Math.min(...fetchSpy.mock.invocationCallOrder));
    expect(cancelSpy.mock.calls.every(([filters]) => (
      isExactKey(filters, INTELLIGENCE_ITEMS_LIST_QUERY_KEY)
    ))).toBe(true);
    expect(removeSpy.mock.calls.every(([filters]) => (
      isExactKey(filters, INTELLIGENCE_ITEMS_LIST_QUERY_KEY)
    ))).toBe(true);
    expect(cancelSpy.mock.calls.some(([filters]) => (
      isExactKey(filters, ['intelligence', 'sources', 'list'])
    ))).toBe(false);
    expect(removeSpy.mock.calls.some(([filters]) => (
      isExactKey(filters, ['intelligence', 'sources', 'list'])
    ))).toBe(false);
    expect(cancelSpy.mock.calls.some(([filters]) => (
      isExactKey(filters, ['intelligence', 'templates', 'list'])
    ))).toBe(false);
    expect(removeSpy.mock.calls.some(([filters]) => (
      isExactKey(filters, ['intelligence', 'templates', 'list'])
    ))).toBe(false);
    assertExactIntelligenceItemsOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactIntelligenceItemsOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertSiblingGetsUntouched();
  });

  it('never prefix-cancels intelligence, sources, templates, settings, or sibling keys', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useIntelligenceItemsQuery(), { wrapper });
    await act(async () => {
      await result.current.loadItems();
      await result.current.loadItems();
    });

    const allOps = [
      ...cancelSpy.mock.calls,
      ...removeSpy.mock.calls,
    ] as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>;
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey.length === 1
      && filters.queryKey[0] === 'intelligence'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      isExactKey(filters, ['intelligence', 'sources', 'list'])
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      isExactKey(filters, ['intelligence', 'templates', 'list'])
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'generation-backend'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'local-models'
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
      && filters.queryKey[0] === 'scheduled-tasks'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'home'
    ))).toBe(false);
    assertExactIntelligenceItemsOps(allOps);
  });

  it('rethrows a 500 without retrying even when the test client default would retry', async () => {
    listItems.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useIntelligenceItemsQuery(), { wrapper });

    await act(async () => {
      await expect(result.current.loadItems()).rejects.toBeDefined();
    });
    expect(listItems).toHaveBeenCalledTimes(1);
    expect(queryOptions(client, INTELLIGENCE_ITEMS_LIST_QUERY_KEY)?.retry).toBe(false);
    assertSiblingGetsUntouched();
  });

  it('classifies CancelledError without treating it as a transport failure', async () => {
    expect(isIntelligenceItemsCancelledError(
      new CancelledError(INTELLIGENCE_ITEMS_CANCEL),
    )).toBe(true);
    expect(isIntelligenceItemsCancelledError(serverError())).toBe(false);

    listItems.mockRejectedValue(new CancelledError(INTELLIGENCE_ITEMS_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useIntelligenceItemsQuery(), { wrapper });

    let thrown: unknown;
    await act(async () => {
      await result.current.loadItems().catch((error: unknown) => {
        thrown = error;
      });
    });
    expect(isIntelligenceItemsCancelledError(thrown)).toBe(true);
    expect(listItems).toHaveBeenCalledTimes(1);
  });

  it('lets a newer items 500 win over a stale 200', async () => {
    const first = createDeferred<IntelligenceItemListResponse>();
    listItems
      .mockReturnValueOnce(first.promise)
      .mockRejectedValueOnce(serverError('newer items'));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useIntelligenceItemsQuery(), { wrapper });

    let staleError: unknown;
    let newerError: unknown;
    await act(async () => {
      void result.current.loadItems().catch((error: unknown) => {
        staleError = error;
      });
    });
    await waitFor(() => expect(listItems).toHaveBeenCalledTimes(1));
    await act(async () => {
      await result.current.loadItems().catch((error: unknown) => {
        newerError = error;
      });
    });
    expect(listItems).toHaveBeenCalledTimes(2);
    expect(newerError).toBeDefined();
    expect(isIntelligenceItemsCancelledError(newerError)).toBe(false);

    await act(async () => {
      first.resolve(itemList({ total: 9 }));
      await first.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(
      staleError === undefined || isIntelligenceItemsCancelledError(staleError),
    ).toBe(true);
  });

  it('lets a newer empty items list win over a stale 500', async () => {
    const first = createDeferred<IntelligenceItemListResponse>();
    const empty = itemList({ items: [], total: 0 });
    listItems
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(empty);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useIntelligenceItemsQuery(), { wrapper });

    let staleError: unknown;
    let newer: IntelligenceItemListResponse | undefined;
    await act(async () => {
      void result.current.loadItems().catch((error: unknown) => {
        staleError = error;
      });
    });
    await waitFor(() => expect(listItems).toHaveBeenCalledTimes(1));
    await act(async () => {
      newer = await result.current.loadItems();
    });
    expect(newer).toEqual(empty);

    await act(async () => {
      first.reject(serverError('stale items'));
      await first.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(newer).toEqual(empty);
    expect(
      staleError === undefined || isIntelligenceItemsCancelledError(staleError),
    ).toBe(true);
  });

  it('removes the exact live key on unmount and ignores a late fulfillment or 500', async () => {
    const pendingItems = createDeferred<IntelligenceItemListResponse>();
    listItems.mockReturnValueOnce(pendingItems.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useIntelligenceItemsQuery(), { wrapper });

    let inFlight: Promise<IntelligenceItemListResponse> | undefined;
    await act(async () => {
      inFlight = result.current.loadItems();
    });
    await waitFor(() => expect(listItems).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pendingItems.resolve(itemList({ total: 3 }));
      await pendingItems.promise.catch(() => undefined);
      await inFlight?.catch(() => undefined);
      await Promise.resolve();
    });

    expect(client.getQueryState(INTELLIGENCE_ITEMS_LIST_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['intelligence'] })).toHaveLength(0);
    expect(queryFetchStatus(client, INTELLIGENCE_ITEMS_LIST_QUERY_KEY)).toBeUndefined();
  });

  it('does not refetch when the window regains focus or reconnects', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useIntelligenceItemsQuery(), { wrapper });

    await act(async () => {
      await result.current.loadItems();
    });
    expect(queryOptions(client, INTELLIGENCE_ITEMS_LIST_QUERY_KEY)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client, INTELLIGENCE_ITEMS_LIST_QUERY_KEY)?.retry).toBe(false);
    expect(queryOptions(client, INTELLIGENCE_ITEMS_LIST_QUERY_KEY)?.staleTime).toBe(0);
    expect(listItems).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
      onlineManager.setOnline(false);
      onlineManager.setOnline(true);
    });

    expect(listItems).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call listItems again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useIntelligenceItemsQuery(), { wrapper });
    await act(async () => {
      await result.current.loadItems();
    });
    expect(listItems).toHaveBeenCalledTimes(1);
    expect(queryOptions(client, INTELLIGENCE_ITEMS_LIST_QUERY_KEY)?.refetchInterval).toBeUndefined();

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

    expect(listItems).toHaveBeenCalledTimes(1);
  });

  it('issues listItems while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useIntelligenceItemsQuery(), { wrapper });

    await act(async () => {
      await result.current.loadItems();
    });
    expect(listItems).toHaveBeenCalledTimes(1);
    expect(queryOptions(client, INTELLIGENCE_ITEMS_LIST_QUERY_KEY)?.networkMode).toBe('always');
  });
});
