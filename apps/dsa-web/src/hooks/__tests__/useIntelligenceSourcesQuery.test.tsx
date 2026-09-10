// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { intelligenceApi } from '../../api/intelligence';
import type {
  IntelligenceSourceListResponse,
  IntelligenceSourceTemplateListResponse,
} from '../../api/intelligence';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import {
  INTELLIGENCE_SOURCES_CANCEL,
  INTELLIGENCE_SOURCES_LIST_QUERY_KEY,
  INTELLIGENCE_SOURCES_QUERY_SCHEDULE,
  INTELLIGENCE_TEMPLATES_LIST_QUERY_KEY,
  fetchIntelligenceSourcesList,
  fetchIntelligenceTemplatesList,
  isIntelligenceSourcesCancelledError,
  useIntelligenceSourcesQuery,
} from '../useIntelligenceSourcesQuery';

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

const listSources = vi.mocked(intelligenceApi.listSources);
const listTemplates = vi.mocked(intelligenceApi.listTemplates);
const listItems = vi.mocked(intelligenceApi.listItems);
const createSource = vi.mocked(intelligenceApi.createSource);
const testSource = vi.mocked(intelligenceApi.testSource);
const fetchSource = vi.mocked(intelligenceApi.fetchSource);

function sourceList(
  overrides: Partial<IntelligenceSourceListResponse> = {},
): IntelligenceSourceListResponse {
  return {
    items: [],
    total: 0,
    page: 1,
    pageSize: 100,
    ...overrides,
  };
}

function templateList(
  overrides: Partial<IntelligenceSourceTemplateListResponse> = {},
): IntelligenceSourceTemplateListResponse {
  return {
    items: [],
    total: 0,
    ...overrides,
  };
}

function serverError(message = 'intelligence unavailable'): Error {
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

function assertExactIntelligenceOps(
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
    expect(key[0] === 'home').toBe(false);
    if (key[0] === 'intelligence') {
      expect(filters?.exact).toBe(true);
      expect(key).toHaveLength(3);
      expect(key[1] === 'sources' || key[1] === 'templates').toBe(true);
      expect(key[2]).toBe('list');
      expect(key).not.toContain('language');
      expect(key).not.toContain('zh');
      expect(key).not.toContain('en');
      expect(key).not.toContain(100);
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

function assertMutationsUntouched() {
  expect(listItems).not.toHaveBeenCalled();
  expect(createSource).not.toHaveBeenCalled();
  expect(testSource).not.toHaveBeenCalled();
  expect(fetchSource).not.toHaveBeenCalled();
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

describe('useIntelligenceSourcesQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    listSources.mockResolvedValue(sourceList());
    listTemplates.mockResolvedValue(templateList());
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

  it('pins the exact keys, schedule, and transport with pageSize baked in and no AbortSignal', async () => {
    expect([...INTELLIGENCE_SOURCES_LIST_QUERY_KEY]).toEqual(['intelligence', 'sources', 'list']);
    expect(INTELLIGENCE_SOURCES_LIST_QUERY_KEY).toHaveLength(3);
    expect([...INTELLIGENCE_TEMPLATES_LIST_QUERY_KEY]).toEqual(['intelligence', 'templates', 'list']);
    expect(INTELLIGENCE_TEMPLATES_LIST_QUERY_KEY).toHaveLength(3);
    expect(INTELLIGENCE_SOURCES_LIST_QUERY_KEY).not.toContain('language');
    expect(INTELLIGENCE_TEMPLATES_LIST_QUERY_KEY).not.toContain('language');
    expect(INTELLIGENCE_SOURCES_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(INTELLIGENCE_SOURCES_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchIntelligenceSourcesList({ signal: controller.signal });
    expect(listSources).toHaveBeenCalledTimes(1);
    expect(listSources).toHaveBeenCalledWith({ pageSize: 100 });
    expect(listTemplates).not.toHaveBeenCalled();

    await fetchIntelligenceTemplatesList({ signal: controller.signal });
    expect(listTemplates).toHaveBeenCalledTimes(1);
    expect(listTemplates.mock.calls[0]).toEqual([]);
    expect(listSources).toHaveBeenCalledTimes(1);
    assertMutationsUntouched();
  });

  it('is not barrel-exported, does not auto-GET on mount, and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useIntelligenceSourcesQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useIntelligenceSourcesQuery(), { wrapper });

    await flushQueryMicrotasks();
    expect(listSources).not.toHaveBeenCalled();
    expect(listTemplates).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.loadSources();
    });

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['intelligence', 'sources', 'list']);
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
        queryKey: INTELLIGENCE_SOURCES_LIST_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(listSources).toHaveBeenCalledTimes(1);
    expect(listSources).toHaveBeenCalledWith({ pageSize: 100 });
    expect(listTemplates).not.toHaveBeenCalled();
    assertMutationsUntouched();
  });

  it('loadSources returns the payload including an empty 200 and never calls listTemplates', async () => {
    const empty = sourceList({ items: [], total: 0 });
    listSources.mockResolvedValueOnce(empty);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useIntelligenceSourcesQuery(), { wrapper });

    let next: IntelligenceSourceListResponse | undefined;
    await act(async () => {
      next = await result.current.loadSources();
    });

    expect(listSources).toHaveBeenCalledTimes(1);
    expect(listSources).toHaveBeenCalledWith({ pageSize: 100 });
    expect(listTemplates).not.toHaveBeenCalled();
    expect(next).toEqual(empty);
    assertMutationsUntouched();
  });

  it('loadTemplates returns the payload once and never calls listSources', async () => {
    const empty = templateList({ items: [], total: 0 });
    listTemplates.mockResolvedValueOnce(empty);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useIntelligenceSourcesQuery(), { wrapper });

    let next: IntelligenceSourceTemplateListResponse | undefined;
    await act(async () => {
      next = await result.current.loadTemplates();
    });

    expect(listTemplates).toHaveBeenCalledTimes(1);
    expect(listSources).not.toHaveBeenCalled();
    expect(next).toEqual(empty);
    assertMutationsUntouched();
  });

  it('same-key sources refresh cancel+remove then fetchQuery without touching templates', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useIntelligenceSourcesQuery(), { wrapper });

    await act(async () => {
      await result.current.loadSources();
    });
    expect(listSources).toHaveBeenCalledTimes(1);

    cancelSpy.mockClear();
    removeSpy.mockClear();
    fetchSpy.mockClear();

    const pending = createDeferred<IntelligenceSourceListResponse>();
    listSources.mockReturnValueOnce(pending.promise);
    let second: Promise<IntelligenceSourceListResponse> | undefined;
    await act(async () => {
      second = result.current.loadSources();
    });

    await act(async () => {
      pending.resolve(sourceList({ total: 1 }));
      await second;
    });

    expect(listSources).toHaveBeenCalledTimes(2);
    expect(listTemplates).not.toHaveBeenCalled();
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
      isExactKey(filters, INTELLIGENCE_SOURCES_LIST_QUERY_KEY)
    ))).toBe(true);
    expect(removeSpy.mock.calls.every(([filters]) => (
      isExactKey(filters, INTELLIGENCE_SOURCES_LIST_QUERY_KEY)
    ))).toBe(true);
    expect(cancelSpy.mock.calls.some(([filters]) => (
      isExactKey(filters, INTELLIGENCE_TEMPLATES_LIST_QUERY_KEY)
    ))).toBe(false);
    expect(removeSpy.mock.calls.some(([filters]) => (
      isExactKey(filters, INTELLIGENCE_TEMPLATES_LIST_QUERY_KEY)
    ))).toBe(false);
    assertExactIntelligenceOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactIntelligenceOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('same-key templates refresh cancel+remove then fetchQuery without touching sources', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useIntelligenceSourcesQuery(), { wrapper });

    await act(async () => {
      await result.current.loadTemplates();
    });
    expect(listTemplates).toHaveBeenCalledTimes(1);

    cancelSpy.mockClear();
    removeSpy.mockClear();
    fetchSpy.mockClear();

    await act(async () => {
      await result.current.loadTemplates();
    });

    expect(listTemplates).toHaveBeenCalledTimes(2);
    expect(listSources).not.toHaveBeenCalled();
    expect(Math.min(...cancelSpy.mock.invocationCallOrder))
      .toBeLessThan(Math.min(...fetchSpy.mock.invocationCallOrder));
    expect(Math.min(...removeSpy.mock.invocationCallOrder))
      .toBeLessThan(Math.min(...fetchSpy.mock.invocationCallOrder));
    expect(cancelSpy.mock.calls.every(([filters]) => (
      isExactKey(filters, INTELLIGENCE_TEMPLATES_LIST_QUERY_KEY)
    ))).toBe(true);
    expect(removeSpy.mock.calls.every(([filters]) => (
      isExactKey(filters, INTELLIGENCE_TEMPLATES_LIST_QUERY_KEY)
    ))).toBe(true);
    expect(cancelSpy.mock.calls.some(([filters]) => (
      isExactKey(filters, INTELLIGENCE_SOURCES_LIST_QUERY_KEY)
    ))).toBe(false);
    expect(removeSpy.mock.calls.some(([filters]) => (
      isExactKey(filters, INTELLIGENCE_SOURCES_LIST_QUERY_KEY)
    ))).toBe(false);
    assertExactIntelligenceOps(
      [...cancelSpy.mock.calls, ...removeSpy.mock.calls] as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('never prefix-cancels intelligence, generation-backend, local-models, settings, or plugins', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useIntelligenceSourcesQuery(), { wrapper });
    await act(async () => {
      await result.current.loadSources();
      await result.current.loadTemplates();
      await result.current.loadSources();
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
    assertExactIntelligenceOps(allOps);
  });

  it('rethrows a 500 without retrying even when the test client default would retry', async () => {
    listSources.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useIntelligenceSourcesQuery(), { wrapper });

    await act(async () => {
      await expect(result.current.loadSources()).rejects.toBeDefined();
    });
    expect(listSources).toHaveBeenCalledTimes(1);
    expect(queryOptions(client, INTELLIGENCE_SOURCES_LIST_QUERY_KEY)?.retry).toBe(false);
    expect(listTemplates).not.toHaveBeenCalled();
    assertMutationsUntouched();
  });

  it('classifies CancelledError without treating it as a transport failure', async () => {
    expect(isIntelligenceSourcesCancelledError(
      new CancelledError(INTELLIGENCE_SOURCES_CANCEL),
    )).toBe(true);
    expect(isIntelligenceSourcesCancelledError(serverError())).toBe(false);

    listSources.mockRejectedValue(new CancelledError(INTELLIGENCE_SOURCES_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useIntelligenceSourcesQuery(), { wrapper });

    let thrown: unknown;
    await act(async () => {
      await result.current.loadSources().catch((error: unknown) => {
        thrown = error;
      });
    });
    expect(isIntelligenceSourcesCancelledError(thrown)).toBe(true);
    expect(listSources).toHaveBeenCalledTimes(1);
  });

  it('lets a newer sources 500 win over a stale 200', async () => {
    const first = createDeferred<IntelligenceSourceListResponse>();
    listSources
      .mockReturnValueOnce(first.promise)
      .mockRejectedValueOnce(serverError('newer sources'));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useIntelligenceSourcesQuery(), { wrapper });

    let staleError: unknown;
    let newerError: unknown;
    await act(async () => {
      void result.current.loadSources().catch((error: unknown) => {
        staleError = error;
      });
    });
    await waitFor(() => expect(listSources).toHaveBeenCalledTimes(1));
    await act(async () => {
      await result.current.loadSources().catch((error: unknown) => {
        newerError = error;
      });
    });
    expect(listSources).toHaveBeenCalledTimes(2);
    expect(newerError).toBeDefined();
    expect(isIntelligenceSourcesCancelledError(newerError)).toBe(false);

    await act(async () => {
      first.resolve(sourceList({ total: 9 }));
      await first.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(
      staleError === undefined || isIntelligenceSourcesCancelledError(staleError),
    ).toBe(true);
    expect(listTemplates).not.toHaveBeenCalled();
  });

  it('lets a newer empty sources list win over a stale 500', async () => {
    const first = createDeferred<IntelligenceSourceListResponse>();
    const empty = sourceList({ items: [], total: 0 });
    listSources
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(empty);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useIntelligenceSourcesQuery(), { wrapper });

    let staleError: unknown;
    let newer: IntelligenceSourceListResponse | undefined;
    await act(async () => {
      void result.current.loadSources().catch((error: unknown) => {
        staleError = error;
      });
    });
    await waitFor(() => expect(listSources).toHaveBeenCalledTimes(1));
    await act(async () => {
      newer = await result.current.loadSources();
    });
    expect(newer).toEqual(empty);

    await act(async () => {
      first.reject(serverError('stale sources'));
      await first.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(newer).toEqual(empty);
    expect(
      staleError === undefined || isIntelligenceSourcesCancelledError(staleError),
    ).toBe(true);
  });

  it('removes both exact live keys on unmount and ignores a late fulfillment or 500', async () => {
    const pendingSources = createDeferred<IntelligenceSourceListResponse>();
    const pendingTemplates = createDeferred<IntelligenceSourceTemplateListResponse>();
    listSources.mockReturnValueOnce(pendingSources.promise);
    listTemplates.mockReturnValueOnce(pendingTemplates.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useIntelligenceSourcesQuery(), { wrapper });

    let sourcesInFlight: Promise<IntelligenceSourceListResponse> | undefined;
    let templatesInFlight: Promise<IntelligenceSourceTemplateListResponse> | undefined;
    await act(async () => {
      sourcesInFlight = result.current.loadSources();
      templatesInFlight = result.current.loadTemplates();
    });
    await waitFor(() => expect(listSources).toHaveBeenCalledTimes(1));
    expect(listTemplates).toHaveBeenCalledTimes(1);
    unmount();

    await act(async () => {
      pendingSources.resolve(sourceList({ total: 3 }));
      pendingTemplates.reject(serverError('late templates'));
      await pendingSources.promise.catch(() => undefined);
      await pendingTemplates.promise.catch(() => undefined);
      await sourcesInFlight?.catch(() => undefined);
      await templatesInFlight?.catch(() => undefined);
      await Promise.resolve();
    });

    expect(client.getQueryState(INTELLIGENCE_SOURCES_LIST_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryState(INTELLIGENCE_TEMPLATES_LIST_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['intelligence'] })).toHaveLength(0);
    expect(queryFetchStatus(client, INTELLIGENCE_SOURCES_LIST_QUERY_KEY)).toBeUndefined();
    expect(queryFetchStatus(client, INTELLIGENCE_TEMPLATES_LIST_QUERY_KEY)).toBeUndefined();
  });

  it('does not refetch when the window regains focus or reconnects', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useIntelligenceSourcesQuery(), { wrapper });

    await act(async () => {
      await result.current.loadSources();
    });
    expect(queryOptions(client, INTELLIGENCE_SOURCES_LIST_QUERY_KEY)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client, INTELLIGENCE_SOURCES_LIST_QUERY_KEY)?.retry).toBe(false);
    expect(queryOptions(client, INTELLIGENCE_SOURCES_LIST_QUERY_KEY)?.staleTime).toBe(0);
    expect(listSources).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
      onlineManager.setOnline(false);
      onlineManager.setOnline(true);
    });

    expect(listSources).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call listSources again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useIntelligenceSourcesQuery(), { wrapper });
    await act(async () => {
      await result.current.loadSources();
    });
    expect(listSources).toHaveBeenCalledTimes(1);
    expect(queryOptions(client, INTELLIGENCE_SOURCES_LIST_QUERY_KEY)?.refetchInterval).toBeUndefined();

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

    expect(listSources).toHaveBeenCalledTimes(1);
  });

  it('issues listSources while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useIntelligenceSourcesQuery(), { wrapper });

    await act(async () => {
      await result.current.loadSources();
    });
    expect(listSources).toHaveBeenCalledTimes(1);
    expect(queryOptions(client, INTELLIGENCE_SOURCES_LIST_QUERY_KEY)?.networkMode).toBe('always');
  });

  it('loadSources and loadTemplates never call items GET or mutations', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useIntelligenceSourcesQuery(), { wrapper });
    await act(async () => {
      await result.current.loadSources();
      await result.current.loadTemplates();
    });
    expect(listSources).toHaveBeenCalledTimes(1);
    expect(listTemplates).toHaveBeenCalledTimes(1);
    assertMutationsUntouched();
  });
});
