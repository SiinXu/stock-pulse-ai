// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { scheduledTasksApi } from '../../api/scheduledTasks';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type {
  ScheduledTaskDefinitionSummary,
  ScheduledTaskListResponse,
} from '../../types/scheduledTasks';
import {
  SCHEDULED_TASKS_OVERLAP_CANCEL,
  SCHEDULED_TASKS_OVERLAP_QUERY_KEY,
  SCHEDULED_TASKS_OVERLAP_QUERY_SCHEDULE,
  fetchScheduledTasksOverlap,
  useScheduledTasksOverlapQuery,
} from '../useScheduledTasksOverlapQuery';

vi.mock('../../api/scheduledTasks', () => ({
  scheduledTasksApi: {
    list: vi.fn(),
    listRuns: vi.fn(),
    getStatus: vi.fn(),
    create: vi.fn(),
    enable: vi.fn(),
    disable: vi.fn(),
  },
}));

const listTasks = vi.mocked(scheduledTasksApi.list);

const LIST_QUERY_KEY = ['scheduled-tasks', 'list'] as const;
const RUNS_QUERY_KEY = ['scheduled-tasks', 'runs', 'task-1', 10] as const;
const SCHEDULER_STATUS_QUERY_KEY = ['scheduler', 'status'] as const;

function task(overrides: Partial<ScheduledTaskDefinitionSummary> = {}): ScheduledTaskDefinitionSummary {
  return {
    compatibility: 'supported',
    id: 'task-1',
    schemaVersion: 2,
    name: 'US close',
    taskType: 'stock_analysis',
    enabled: true,
    nextRunAt: '2026-07-26T20:30:00Z',
    createdAt: '2026-07-25T10:00:00Z',
    updatedAt: '2026-07-25T10:00:00Z',
    ...overrides,
  };
}

function listResponse(
  items: ScheduledTaskDefinitionSummary[],
  total = items.length,
): ScheduledTaskListResponse {
  return { items, total };
}

function serverError(): Error {
  return Object.assign(new Error('server'), {
    response: {
      status: 500,
      data: { error: 'internal', message: 'scheduled tasks unavailable' },
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
  queryKey: readonly unknown[] = SCHEDULED_TASKS_OVERLAP_QUERY_KEY,
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function seedSiblingKeys(client: QueryClient) {
  client.setQueryData(LIST_QUERY_KEY, { items: [], total: 0 });
  client.setQueryData(RUNS_QUERY_KEY, { items: [], total: 0, limit: 10 });
  client.setQueryData(SCHEDULER_STATUS_QUERY_KEY, { enabled: true });
}

function assertExactOverlapOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'scheduled-tasks' && key.length === 1).toBe(false);
    expect(key[0] === 'scheduler').toBe(false);
    expect(key[0] === 'plugins').toBe(false);
    expect(key[0] === 'settings').toBe(false);
    expect(key[0] === 'watchlist').toBe(false);
    expect(key[0] === 'home').toBe(false);
    expect(key[0] === 'generation-backend').toBe(false);
    expect(key[0] === 'local-models').toBe(false);
    expect(key[0] === 'intelligence').toBe(false);
    expect(key[0] === 'notifications').toBe(false);
    if (key[0] === 'scheduled-tasks') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['scheduled-tasks', 'overlap']);
      expect(key).toHaveLength(2);
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

function keyEquals(filters: { queryKey?: readonly unknown[] } | undefined, expected: readonly unknown[]) {
  return JSON.stringify([...(filters?.queryKey ?? [])]) === JSON.stringify([...expected]);
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

describe('useScheduledTasksOverlapQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    listTasks.mockResolvedValue(listResponse([], 0));
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

  it('pins the exact overlap key, schedule, and list({ enabled: true, limit: 1 }) with no signal or language', async () => {
    expect([...SCHEDULED_TASKS_OVERLAP_QUERY_KEY]).toEqual(['scheduled-tasks', 'overlap']);
    expect(SCHEDULED_TASKS_OVERLAP_QUERY_KEY).toHaveLength(2);
    expect(SCHEDULED_TASKS_OVERLAP_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(SCHEDULED_TASKS_OVERLAP_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchScheduledTasksOverlap({ signal: controller.signal });
    expect(listTasks).toHaveBeenCalledTimes(1);
    expect(listTasks.mock.calls[0]).toEqual([{ enabled: true, limit: 1 }]);
  });

  it('is not barrel-exported and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useScheduledTasksOverlapQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(
      () => useScheduledTasksOverlapQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBe(false));

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['scheduled-tasks', 'overlap']);
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
    }
    expect(
      client.getQueryCache().find({
        queryKey: SCHEDULED_TASKS_OVERLAP_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(listTasks.mock.calls[0]).toEqual([{ enabled: true, limit: 1 }]);
    expect(result.current).not.toHaveProperty('isLoading');
    expect(result.current).not.toHaveProperty('isRefreshing');
    expect(result.current).not.toHaveProperty('loadError');
    expect(result.current).not.toHaveProperty('refresh');
  });

  it('fetches once on mount, maps empty 200 to false, and leaves zero live observers', async () => {
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(
      () => useScheduledTasksOverlapQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBe(false));
    expect(listTasks).toHaveBeenCalledTimes(1);
    expect(
      client.getQueryCache().find({
        queryKey: SCHEDULED_TASKS_OVERLAP_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
  });

  it('maps { items: [task], total: 1 } and { items: [], total: 2 } to true', async () => {
    listTasks.mockResolvedValueOnce(listResponse([task()], 1));
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ refreshToken }) => useScheduledTasksOverlapQuery({ enabled: true, refreshToken }),
      { wrapper, initialProps: { refreshToken: 0 } },
    );

    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBe(true));

    listTasks.mockResolvedValueOnce(listResponse([], 2));
    rerender({ refreshToken: 1 });
    await waitFor(() => expect(listTasks).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBe(true));
  });

  it('skips GET when enabled is false, exact-removes the overlap key, and reports null', async () => {
    const { client, wrapper } = createWrapper();
    seedSiblingKeys(client);
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(
      () => useScheduledTasksOverlapQuery({ enabled: false, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBeNull());
    expect(listTasks).not.toHaveBeenCalled();
    expect(client.getQueryState(SCHEDULED_TASKS_OVERLAP_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: LIST_QUERY_KEY, exact: true })).toHaveLength(1);
    expect(client.getQueryCache().findAll({ queryKey: RUNS_QUERY_KEY, exact: true })).toHaveLength(1);
    expect(client.getQueryCache().findAll({ queryKey: SCHEDULER_STATUS_QUERY_KEY, exact: true })).toHaveLength(1);
    assertExactOverlapOps(
      [...cancelSpy.mock.calls, ...removeSpy.mock.calls] as Array<
        [filters?: { queryKey?: readonly unknown[]; exact?: boolean }]
      >,
    );
  });

  it('shares one load path across mount and refreshToken change', async () => {
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ refreshToken }) => useScheduledTasksOverlapQuery({ enabled: true, refreshToken }),
      { wrapper, initialProps: { refreshToken: 0 } },
    );

    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBe(false));
    expect(listTasks).toHaveBeenCalledTimes(1);

    rerender({ refreshToken: 1 });
    await waitFor(() => expect(listTasks).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBe(false));
    expect(result.current).not.toHaveProperty('refresh');
  });

  it('fails soft to null on an initial 500 even when the test client default would retry', async () => {
    listTasks.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(
      () => useScheduledTasksOverlapQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBeNull());
    expect(listTasks).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.retry).toBe(false);
  });

  it('drops a later 500 after a 200 to null (no last-good true)', async () => {
    listTasks.mockResolvedValueOnce(listResponse([task()], 1));
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ refreshToken }) => useScheduledTasksOverlapQuery({ enabled: true, refreshToken }),
      { wrapper, initialProps: { refreshToken: 0 } },
    );
    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBe(true));

    listTasks.mockRejectedValueOnce(serverError());
    rerender({ refreshToken: 1 });
    await waitFor(() => expect(listTasks).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBeNull());
  });

  it('lets a later 200 after a 500 map to the newest boolean', async () => {
    listTasks.mockRejectedValueOnce(serverError());
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ refreshToken }) => useScheduledTasksOverlapQuery({ enabled: true, refreshToken }),
      { wrapper, initialProps: { refreshToken: 0 } },
    );
    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBeNull());

    listTasks.mockResolvedValueOnce(listResponse([task()], 1));
    rerender({ refreshToken: 1 });
    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBe(true));
  });

  it('lets a newer 500 win over a stale 200 so last-good true cannot stick', async () => {
    const first = createDeferred<ScheduledTaskListResponse>();
    listTasks
      .mockReturnValueOnce(first.promise)
      .mockRejectedValueOnce(serverError());
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ refreshToken }) => useScheduledTasksOverlapQuery({ enabled: true, refreshToken }),
      { wrapper, initialProps: { refreshToken: 0 } },
    );

    await waitFor(() => expect(listTasks).toHaveBeenCalledTimes(1));
    rerender({ refreshToken: 1 });
    await waitFor(() => expect(listTasks).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBeNull());

    await act(async () => {
      first.resolve(listResponse([task()], 1));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.hasEnabledVersionedTasks).toBeNull();
  });

  it('lets a newer 200 win over a stale 500', async () => {
    const first = createDeferred<ScheduledTaskListResponse>();
    listTasks
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(listResponse([task()], 1));
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ refreshToken }) => useScheduledTasksOverlapQuery({ enabled: true, refreshToken }),
      { wrapper, initialProps: { refreshToken: 0 } },
    );

    await waitFor(() => expect(listTasks).toHaveBeenCalledTimes(1));
    rerender({ refreshToken: 1 });
    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBe(true));

    await act(async () => {
      first.reject(serverError());
      await first.promise.catch(() => undefined);
    });

    expect(result.current.hasEnabledVersionedTasks).toBe(true);
  });

  it('does not set null when list() settles as CancelledError', async () => {
    listTasks.mockResolvedValueOnce(listResponse([task()], 1));
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ refreshToken }) => useScheduledTasksOverlapQuery({ enabled: true, refreshToken }),
      { wrapper, initialProps: { refreshToken: 0 } },
    );
    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBe(true));

    listTasks.mockRejectedValueOnce(new CancelledError(SCHEDULED_TASKS_OVERLAP_CANCEL));
    rerender({ refreshToken: 1 });
    await waitFor(() => expect(listTasks).toHaveBeenCalledTimes(2));
    await flushQueryMicrotasks();
    expect(result.current.hasEnabledVersionedTasks).toBe(true);
  });

  it('removes the exact overlap key on unmount and ignores a late 500', async () => {
    const pending = createDeferred<ScheduledTaskListResponse>();
    listTasks.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    seedSiblingKeys(client);
    const { result, unmount } = renderHook(
      () => useScheduledTasksOverlapQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(listTasks).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.hasEnabledVersionedTasks).toBeNull();
    expect(client.getQueryState(SCHEDULED_TASKS_OVERLAP_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: LIST_QUERY_KEY, exact: true })).toHaveLength(1);
    expect(client.getQueryCache().findAll({ queryKey: RUNS_QUERY_KEY, exact: true })).toHaveLength(1);
    expect(queryFetchStatus(client, SCHEDULED_TASKS_OVERLAP_QUERY_KEY)).toBeUndefined();
  });

  it('same-key refresh cancel+remove then fetchQuery', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result, rerender } = renderHook(
      ({ refreshToken }) => useScheduledTasksOverlapQuery({ enabled: true, refreshToken }),
      { wrapper, initialProps: { refreshToken: 0 } },
    );

    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBe(false));
    expect(listTasks).toHaveBeenCalledTimes(1);

    listTasks.mockResolvedValueOnce(listResponse([task()], 1));
    rerender({ refreshToken: 1 });
    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBe(true));
    expect(listTasks).toHaveBeenCalledTimes(2);

    expect(fetchSpy).toHaveBeenCalled();
    expect(cancelSpy).toHaveBeenCalled();
    expect(removeSpy).toHaveBeenCalled();
    assertSilentCancelOptions(
      cancelSpy.mock.calls as Array<[filters?: unknown, options?: { silent?: boolean; revert?: boolean }]>,
    );

    const lastFetchOrder = Math.max(...fetchSpy.mock.invocationCallOrder);
    const cancelsBeforeLastFetch = cancelSpy.mock.invocationCallOrder.filter((order) => order < lastFetchOrder);
    const removesBeforeLastFetch = removeSpy.mock.invocationCallOrder.filter((order) => order < lastFetchOrder);
    expect(cancelsBeforeLastFetch.length).toBeGreaterThan(0);
    expect(removesBeforeLastFetch.length).toBeGreaterThan(0);
    expect(Math.max(...cancelsBeforeLastFetch)).toBeLessThan(lastFetchOrder);
    expect(Math.max(...removesBeforeLastFetch)).toBeLessThan(lastFetchOrder);
    assertExactOverlapOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactOverlapOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('never prefix-cancels scheduled-tasks or exact-cancels list, runs, scheduler, settings, plugins, or Home keys', async () => {
    const { client, wrapper } = createWrapper();
    seedSiblingKeys(client);
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result, rerender, unmount } = renderHook(
      ({ refreshToken }) => useScheduledTasksOverlapQuery({ enabled: true, refreshToken }),
      { wrapper, initialProps: { refreshToken: 0 } },
    );
    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBe(false));
    rerender({ refreshToken: 1 });
    await waitFor(() => expect(listTasks).toHaveBeenCalledTimes(2));
    unmount();

    const allOps = [
      ...cancelSpy.mock.calls,
      ...removeSpy.mock.calls,
    ] as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>;
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey.length === 1
      && filters.queryKey[0] === 'scheduled-tasks'
    ))).toBe(false);
    expect(allOps.some(([filters]) => keyEquals(filters, LIST_QUERY_KEY))).toBe(false);
    expect(allOps.some(([filters]) => keyEquals(filters, RUNS_QUERY_KEY))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey) && filters.queryKey[0] === 'scheduler'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey) && filters.queryKey[0] === 'settings'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey) && filters.queryKey[0] === 'plugins'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey) && filters.queryKey[0] === 'watchlist'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey) && filters.queryKey[0] === 'home'
    ))).toBe(false);
    expect(client.getQueryCache().findAll({ queryKey: LIST_QUERY_KEY, exact: true })).toHaveLength(1);
    expect(client.getQueryCache().findAll({ queryKey: RUNS_QUERY_KEY, exact: true })).toHaveLength(1);
    expect(client.getQueryCache().findAll({ queryKey: SCHEDULER_STATUS_QUERY_KEY, exact: true })).toHaveLength(1);
    assertExactOverlapOps(allOps);
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(
      () => useScheduledTasksOverlapQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBe(false));
    expect(queryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(queryOptions(client)?.staleTime).toBe(0);
    expect(listTasks).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(listTasks).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call list() again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(
      () => useScheduledTasksOverlapQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBe(false));
    expect(listTasks).toHaveBeenCalledTimes(1);
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

    expect(listTasks).toHaveBeenCalledTimes(1);
  });

  it('issues list() while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(
      () => useScheduledTasksOverlapQuery({ enabled: true, refreshToken: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.hasEnabledVersionedTasks).toBe(false));
    expect(listTasks).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.networkMode).toBe('always');
  });
});
