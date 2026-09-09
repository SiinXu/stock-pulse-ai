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
  SCHEDULED_TASKS_LIST_CANCEL,
  SCHEDULED_TASKS_LIST_QUERY_KEY,
  SCHEDULED_TASKS_LIST_QUERY_SCHEDULE,
  fetchScheduledTasksList,
  useScheduledTasksListQuery,
} from '../useScheduledTasksListQuery';

vi.mock('../../api/scheduledTasks', () => ({
  scheduledTasksApi: {
    list: vi.fn(),
  },
}));

const listTasks = vi.mocked(scheduledTasksApi.list);

function task(overrides: Partial<ScheduledTaskDefinitionSummary> = {}): ScheduledTaskDefinitionSummary {
  return {
    compatibility: 'supported',
    id: 'task-1',
    schemaVersion: 2,
    name: 'AAPL risk check',
    taskType: 'risk_check',
    enabled: true,
    nextRunAt: '2026-07-26T15:00:00Z',
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
  queryKey: readonly unknown[] = SCHEDULED_TASKS_LIST_QUERY_KEY,
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertExactScheduledTasksListOps(
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
    if (key[0] === 'scheduled-tasks') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['scheduled-tasks', 'list']);
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

async function flushQueryMicrotasks(rounds = 2) {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
  }
}

describe('useScheduledTasksListQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    listTasks.mockResolvedValue(listResponse([task()]));
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

  it('pins the exact scheduled-tasks list key, schedule, and list({ limit: 200 }) with no signal or language', async () => {
    expect([...SCHEDULED_TASKS_LIST_QUERY_KEY]).toEqual(['scheduled-tasks', 'list']);
    expect(SCHEDULED_TASKS_LIST_QUERY_KEY).toHaveLength(2);
    expect(SCHEDULED_TASKS_LIST_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(SCHEDULED_TASKS_LIST_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchScheduledTasksList({ signal: controller.signal });
    expect(listTasks).toHaveBeenCalledTimes(1);
    expect(listTasks.mock.calls[0]).toEqual([{ limit: 200 }]);
  });

  it('is not barrel-exported and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useScheduledTasksListQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useScheduledTasksListQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['scheduled-tasks', 'list']);
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
      expect(scheduled.refetchInterval).toBeUndefined();
    }
    expect(
      client.getQueryCache().find({
        queryKey: SCHEDULED_TASKS_LIST_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(listTasks.mock.calls[0]).toEqual([{ limit: 200 }]);
  });

  it('fetches once on mount, sets items without total, and leaves zero live observers', async () => {
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTasksListQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listTasks).toHaveBeenCalledTimes(1);
    expect(result.current.items).toEqual([task()]);
    expect(result.current).not.toHaveProperty('total');
    expect(result.current.loadError).toBeNull();
    expect(result.current.isRefreshing).toBe(false);
    expect(typeof result.current.setItems).toBe('function');
    expect(
      client.getQueryCache().find({
        queryKey: SCHEDULED_TASKS_LIST_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
  });

  it('treats empty 200 as a success roster rather than an error', async () => {
    listTasks.mockResolvedValueOnce(listResponse([], 0));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTasksListQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.items).toEqual([]);
    expect(result.current.loadError).toBeNull();
  });

  it('clears rows on an initial 500 even when the test client default would retry', async () => {
    listTasks.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useScheduledTasksListQuery(), { wrapper });

    await waitFor(() => expect(result.current.loadError).not.toBeNull());
    expect(listTasks).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(result.current.items).toEqual([]);
    expect(result.current.loadError?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);
  });

  it('keeps last-good roster when a later refresh fails', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTasksListQuery(), { wrapper });
    await waitFor(() => expect(result.current.items[0]?.id).toBe('task-1'));

    listTasks.mockRejectedValueOnce(serverError());
    await act(async () => {
      await result.current.load('refresh');
    });

    expect(result.current.items[0]?.id).toBe('task-1');
    expect(result.current.loadError?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);
  });

  it('preserves prior rows while a refresh is in flight', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTasksListQuery(), { wrapper });
    await waitFor(() => expect(result.current.items[0]?.id).toBe('task-1'));

    const pending = createDeferred<ScheduledTaskListResponse>();
    listTasks.mockReturnValueOnce(pending.promise);
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    expect(result.current.isLoading).toBe(false);
    expect(result.current.items[0]?.id).toBe('task-1');

    await act(async () => {
      pending.resolve(listResponse([task({ id: 'task-refreshed', name: 'Refreshed' })]));
      await pending.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.isRefreshing).toBe(false));
    expect(result.current.items[0]?.id).toBe('task-refreshed');
    expect(result.current.loadError).toBeNull();
  });

  it('does not set loadError when list() settles as CancelledError', async () => {
    listTasks.mockRejectedValue(new CancelledError(SCHEDULED_TASKS_LIST_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTasksListQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.loadError).toBeNull();
    expect(result.current.items).toEqual([]);
  });

  it('removes the exact scheduled-tasks list key on unmount and ignores a late 500', async () => {
    const pending = createDeferred<ScheduledTaskListResponse>();
    listTasks.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useScheduledTasksListQuery(), { wrapper });

    await waitFor(() => expect(listTasks).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.loadError).toBeNull();
    expect(result.current.items).toEqual([]);
    expect(client.getQueryState(SCHEDULED_TASKS_LIST_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['scheduled-tasks'] })).toHaveLength(0);
    expect(queryFetchStatus(client, SCHEDULED_TASKS_LIST_QUERY_KEY)).toBeUndefined();
  });

  it('lets a newer 500 win over a stale 200 so a later success cannot resurrect', async () => {
    const first = createDeferred<ScheduledTaskListResponse>();
    listTasks
      .mockReturnValueOnce(first.promise)
      .mockRejectedValueOnce(serverError());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTasksListQuery(), { wrapper });

    await waitFor(() => expect(listTasks).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(listTasks).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.loadError?.status).toBe(500));

    expect(result.current.items).toEqual([]);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);

    await act(async () => {
      first.resolve(listResponse([task({ id: 'stale', name: 'Stale' })]));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.items).toEqual([]);
    expect(result.current.loadError?.status).toBe(500);
  });

  it('lets a newer 200 roster win over a stale 500', async () => {
    const first = createDeferred<ScheduledTaskListResponse>();
    listTasks
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(listResponse([task({ id: 'live', name: 'Live' })]));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTasksListQuery(), { wrapper });

    await waitFor(() => expect(listTasks).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(listTasks).toHaveBeenCalledTimes(2));
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
    const { result } = renderHook(() => useScheduledTasksListQuery(), { wrapper });

    await waitFor(() => expect(result.current.items[0]?.id).toBe('task-1'));
    expect(listTasks).toHaveBeenCalledTimes(1);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);

    const pending = createDeferred<ScheduledTaskListResponse>();
    listTasks.mockReturnValueOnce(pending.promise);
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

    expect(result.current.items[0]?.id).toBe('task-1');
    expect(result.current.loadError?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);
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
    assertExactScheduledTasksListOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactScheduledTasksListOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('never prefix-cancels or prefix-removes scheduled-tasks, scheduler, plugins, settings, watchlist, or home keys', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useScheduledTasksListQuery(), { wrapper });
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
      && filters.queryKey[0] === 'settings'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'watchlist'
    ))).toBe(false);
    expect(allOps.some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey[0] === 'home'
    ))).toBe(false);
    assertExactScheduledTasksListOps(allOps);
  });

  it('does not refetch when the window regains focus or reconnects', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useScheduledTasksListQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(queryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(queryOptions(client)?.staleTime).toBe(0);
    expect(listTasks).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
      onlineManager.setOnline(false);
      onlineManager.setOnline(true);
    });

    expect(listTasks).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call list() again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useScheduledTasksListQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
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
    const { result } = renderHook(() => useScheduledTasksListQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listTasks).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.networkMode).toBe('always');
    expect(result.current.items[0]?.id).toBe('task-1');
  });

  it('keeps setItems patches until the next successful GET', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTasksListQuery(), { wrapper });
    await waitFor(() => expect(result.current.items[0]?.enabled).toBe(true));

    await act(async () => {
      result.current.setItems((current) => current.map((item) => (
        item.id === 'task-1' ? { ...item, enabled: false } : item
      )));
    });
    expect(result.current.items[0]?.enabled).toBe(false);

    listTasks.mockResolvedValueOnce(listResponse([task({ enabled: true, name: 'From GET' })]));
    let returned: ScheduledTaskDefinitionSummary[] | undefined;
    await act(async () => {
      returned = await result.current.load('refresh');
    });
    expect(returned).toEqual([task({ enabled: true, name: 'From GET' })]);
    expect(result.current.items[0]?.name).toBe('From GET');
    expect(result.current.items[0]?.enabled).toBe(true);
  });

  it('returns the successful items array from load() and undefined on error or cancel', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTasksListQuery(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    listTasks.mockResolvedValueOnce(listResponse([task({ id: 'task-2', name: 'Second' })], 1));
    let success: ScheduledTaskDefinitionSummary[] | undefined;
    await act(async () => {
      success = await result.current.load('refresh');
    });
    expect(success).toEqual([task({ id: 'task-2', name: 'Second' })]);

    listTasks.mockResolvedValueOnce(listResponse([], 0));
    let empty: ScheduledTaskDefinitionSummary[] | undefined;
    await act(async () => {
      empty = await result.current.load('refresh');
    });
    expect(empty).toEqual([]);

    listTasks.mockRejectedValueOnce(serverError());
    let failed: ScheduledTaskDefinitionSummary[] | undefined;
    await act(async () => {
      failed = await result.current.load('refresh');
    });
    expect(failed).toBeUndefined();
    expect(result.current.items).toEqual([]);

    const pending = createDeferred<ScheduledTaskListResponse>();
    listTasks.mockReturnValueOnce(pending.promise);
    let cancelled: ScheduledTaskDefinitionSummary[] | undefined;
    await act(async () => {
      const pendingLoad = result.current.load('refresh');
      await result.current.load('refresh');
      pending.reject(new CancelledError(SCHEDULED_TASKS_LIST_CANCEL));
      cancelled = await pendingLoad;
    });
    expect(cancelled).toBeUndefined();
  });
});
