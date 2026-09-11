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
  ScheduledTaskRunItem,
  ScheduledTaskRunListResponse,
} from '../../types/scheduledTasks';
import {
  SCHEDULED_TASK_RUN_HISTORY_CANCEL,
  SCHEDULED_TASK_RUN_HISTORY_QUERY_SCHEDULE,
  buildScheduledTaskRunHistoryQueryKey,
  fetchScheduledTaskRunHistory,
  useScheduledTaskRunHistoryQuery,
} from '../useScheduledTaskRunHistoryQuery';

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

const listRuns = vi.mocked(scheduledTasksApi.listRuns);
const listTasks = vi.mocked(scheduledTasksApi.list);
const getStatus = vi.mocked(scheduledTasksApi.getStatus);
const createTask = vi.mocked(scheduledTasksApi.create);
const enableTask = vi.mocked(scheduledTasksApi.enable);
const disableTask = vi.mocked(scheduledTasksApi.disable);

const LIST_QUERY_KEY = ['scheduled-tasks', 'list'] as const;

function runItem(overrides: Partial<ScheduledTaskRunItem> = {}): ScheduledTaskRunItem {
  return {
    id: 'run-1',
    taskId: 'task-1',
    scheduledFor: '2026-07-26T20:30:00Z',
    status: 'succeeded',
    attemptCount: 1,
    dispatchFailureCount: 0,
    executionTaskIds: ['execution-run-1'],
    resultRefs: ['result-run-1'],
    notificationStatus: 'succeeded',
    notificationChannels: ['email'],
    notificationFailedChannels: [],
    errorCode: null,
    nextAttemptAt: null,
    startedAt: '2026-07-26T20:30:01Z',
    finishedAt: '2026-07-26T20:31:00Z',
    createdAt: '2026-07-26T20:30:00Z',
    updatedAt: '2026-07-26T20:31:00Z',
    ...overrides,
  };
}

function runsResponse(
  items: ScheduledTaskRunItem[],
  total = items.length,
): ScheduledTaskRunListResponse {
  return { items, total };
}

function serverError(): Error {
  return Object.assign(new Error('server'), {
    response: {
      status: 500,
      data: { error: 'internal', message: 'scheduled task runs unavailable' },
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
  queryKey: readonly unknown[] = buildScheduledTaskRunHistoryQueryKey('task-1', 10),
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function assertExactHistoryOps(
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
      expect(key[1]).toBe('runs');
      expect(key).toHaveLength(4);
      expect([...key].slice(0, 2)).toEqual(['scheduled-tasks', 'runs']);
      expect([...key]).not.toEqual(['scheduled-tasks', 'list']);
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

function seedListCache(client: QueryClient) {
  client.setQueryData(LIST_QUERY_KEY, { items: [], total: 0 });
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

describe('useScheduledTaskRunHistoryQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    listRuns.mockResolvedValue(runsResponse([runItem()]));
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

  it('pins the exact four-element runs key, schedule, and cancel options', async () => {
    const key = buildScheduledTaskRunHistoryQueryKey('task-1', 10);
    expect([...key]).toEqual(['scheduled-tasks', 'runs', 'task-1', 10]);
    expect(key).toHaveLength(4);
    expect(typeof key[3]).toBe('number');
    expect(SCHEDULED_TASK_RUN_HISTORY_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(SCHEDULED_TASK_RUN_HISTORY_CANCEL).toEqual({ silent: true, revert: false });

    await fetchScheduledTaskRunHistory({ taskId: 'task-1', limit: 10 });
    expect(listRuns).toHaveBeenCalledTimes(1);
    expect(listRuns).toHaveBeenCalledWith('task-1', { limit: 10 });
    expect(listTasks).not.toHaveBeenCalled();
    expect(getStatus).not.toHaveBeenCalled();
    expect(createTask).not.toHaveBeenCalled();
    expect(enableTask).not.toHaveBeenCalled();
    expect(disableTask).not.toHaveBeenCalled();
  });

  it('is not barrel-exported, has no live observer, and does not fetch on mount', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useScheduledTaskRunHistoryQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useScheduledTaskRunHistoryQuery('task-1'), { wrapper });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.runs).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.limit).toBe(10);
    expect(result.current.error).toBeNull();
    expect(listRuns).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.load(10);
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(listRuns).toHaveBeenCalledTimes(1);
    expect(listRuns).toHaveBeenCalledWith('task-1', { limit: 10 });
    expect(listTasks).not.toHaveBeenCalled();
    expect(getStatus).not.toHaveBeenCalled();
    expect(createTask).not.toHaveBeenCalled();
    expect(enableTask).not.toHaveBeenCalled();
    expect(disableTask).not.toHaveBeenCalled();
    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['scheduled-tasks', 'runs', 'task-1', 10]);
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
      expect(scheduled.refetchInterval).toBeUndefined();
    }
    expect(
      client.getQueryCache().find({
        queryKey: buildScheduledTaskRunHistoryQueryKey('task-1', 10),
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
  });

  it('treats empty 200 as success and returns the response from load()', async () => {
    listRuns.mockResolvedValueOnce(runsResponse([], 0));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTaskRunHistoryQuery('task-1'), { wrapper });

    let returned: ScheduledTaskRunListResponse | undefined;
    await act(async () => {
      returned = await result.current.load(10);
    });

    expect(returned).toEqual(runsResponse([], 0));
    expect(result.current.runs).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.limit).toBe(10);
    expect(result.current.error).toBeNull();
    expect(result.current.isLoading).toBe(false);
  });

  it('keeps empty runs and parsed error on an initial 500 even when the test client would retry', async () => {
    listRuns.mockRejectedValue(serverError());
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useScheduledTaskRunHistoryQuery('task-1'), { wrapper });

    let returned: ScheduledTaskRunListResponse | undefined;
    await act(async () => {
      returned = await result.current.load(10);
    });

    expect(returned).toBeUndefined();
    expect(listRuns).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(result.current.runs).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.limit).toBe(10);
    expect(result.current.error?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
  });

  it('keeps last-good runs, total, and limit when a later refresh fails', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTaskRunHistoryQuery('task-1'), { wrapper });
    await act(async () => {
      await result.current.load(10);
    });
    expect(result.current.runs[0]?.id).toBe('run-1');
    expect(result.current.limit).toBe(10);

    listRuns.mockRejectedValueOnce(serverError());
    await act(async () => {
      await result.current.load(10);
    });

    expect(result.current.runs[0]?.id).toBe('run-1');
    expect(result.current.total).toBe(1);
    expect(result.current.limit).toBe(10);
    expect(result.current.error?.status).toBe(500);
    expect(result.current.isLoading).toBe(false);
  });

  it('does not set error when listRuns settles as CancelledError', async () => {
    listRuns.mockRejectedValue(new CancelledError(SCHEDULED_TASK_RUN_HISTORY_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTaskRunHistoryQuery('task-1'), { wrapper });

    let returned: ScheduledTaskRunListResponse | undefined;
    await act(async () => {
      returned = await result.current.load(10);
    });

    expect(returned).toBeUndefined();
    expect(result.current.error).toBeNull();
    expect(result.current.runs).toEqual([]);
    expect(result.current.isLoading).toBe(false);
  });

  it('lets a newer 500 win over a stale 200 and keeps last-good runs', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTaskRunHistoryQuery('task-1'), { wrapper });
    await act(async () => {
      await result.current.load(10);
    });
    expect(result.current.runs[0]?.id).toBe('run-1');

    const stale = createDeferred<ScheduledTaskRunListResponse>();
    listRuns
      .mockReturnValueOnce(stale.promise)
      .mockRejectedValueOnce(serverError());
    await act(async () => {
      void result.current.load(10);
    });
    await waitFor(() => expect(listRuns).toHaveBeenCalledTimes(2));
    await act(async () => {
      void result.current.load(10);
    });
    await waitFor(() => expect(result.current.error?.status).toBe(500));

    expect(result.current.runs[0]?.id).toBe('run-1');
    expect(result.current.limit).toBe(10);
    expect(result.current.isLoading).toBe(false);

    await act(async () => {
      stale.resolve(runsResponse([runItem({ id: 'stale' })]));
      await stale.promise.catch(() => undefined);
    });

    expect(result.current.runs[0]?.id).toBe('run-1');
    expect(result.current.error?.status).toBe(500);
  });

  it('lets a newer 200 win over a stale 500', async () => {
    const first = createDeferred<ScheduledTaskRunListResponse>();
    listRuns
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(runsResponse([runItem({ id: 'live' })]));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTaskRunHistoryQuery('task-1'), { wrapper });

    await act(async () => {
      void result.current.load(10);
    });
    await waitFor(() => expect(listRuns).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load(10);
    });
    await waitFor(() => expect(result.current.runs[0]?.id).toBe('live'));

    expect(result.current.error).toBeNull();
    expect(result.current.isLoading).toBe(false);

    await act(async () => {
      first.reject(serverError());
      await first.promise.catch(() => undefined);
    });

    expect(result.current.runs[0]?.id).toBe('live');
    expect(result.current.error).toBeNull();
  });

  it('does not let a silent CancelledError clear a newer generation', async () => {
    const first = createDeferred<ScheduledTaskRunListResponse>();
    listRuns
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(runsResponse([runItem({ id: 'live' })]));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTaskRunHistoryQuery('task-1'), { wrapper });

    await act(async () => {
      void result.current.load(10);
    });
    await waitFor(() => expect(listRuns).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load(10);
    });
    await waitFor(() => expect(result.current.runs[0]?.id).toBe('live'));

    await act(async () => {
      first.reject(new CancelledError(SCHEDULED_TASK_RUN_HISTORY_CANCEL));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.runs[0]?.id).toBe('live');
    expect(result.current.error).toBeNull();
  });

  it('load more cancel+removes the previous and successor keys then replaces rows', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useScheduledTaskRunHistoryQuery('task-1'), { wrapper });

    await act(async () => {
      await result.current.load(10);
    });
    expect(result.current.runs).toEqual([runItem()]);

    listRuns.mockResolvedValueOnce(runsResponse([
      runItem({ id: 'run-1' }),
      runItem({ id: 'run-2' }),
    ], 2));
    cancelSpy.mockClear();
    removeSpy.mockClear();
    fetchSpy.mockClear();

    await act(async () => {
      await result.current.load(20);
    });

    expect(listRuns).toHaveBeenLastCalledWith('task-1', { limit: 20 });
    expect(result.current.runs.map((item) => item.id)).toEqual(['run-1', 'run-2']);
    expect(result.current.limit).toBe(20);
    expect(result.current.total).toBe(2);

    const key10 = buildScheduledTaskRunHistoryQueryKey('task-1', 10);
    const key20 = buildScheduledTaskRunHistoryQueryKey('task-1', 20);
    expect(cancelSpy.mock.calls.some(([filters]) => (
      filters?.exact === true
      && JSON.stringify([...(filters.queryKey ?? [])]) === JSON.stringify([...key10])
    ))).toBe(true);
    expect(cancelSpy.mock.calls.some(([filters]) => (
      filters?.exact === true
      && JSON.stringify([...(filters.queryKey ?? [])]) === JSON.stringify([...key20])
    ))).toBe(true);
    expect(removeSpy.mock.calls.some(([filters]) => (
      filters?.exact === true
      && JSON.stringify([...(filters.queryKey ?? [])]) === JSON.stringify([...key10])
    ))).toBe(true);
    expect(removeSpy.mock.calls.some(([filters]) => (
      filters?.exact === true
      && JSON.stringify([...(filters.queryKey ?? [])]) === JSON.stringify([...key20])
    ))).toBe(true);
    expect(fetchSpy.mock.calls.some(([options]) => (
      JSON.stringify([...(options.queryKey as readonly unknown[])]) === JSON.stringify([...key20])
    ))).toBe(true);

    const cancelOrders = cancelSpy.mock.invocationCallOrder;
    const removeOrders = removeSpy.mock.invocationCallOrder;
    const fetchOrders = fetchSpy.mock.invocationCallOrder;
    expect(Math.min(...cancelOrders)).toBeLessThan(Math.min(...fetchOrders));
    expect(Math.min(...removeOrders)).toBeLessThan(Math.min(...fetchOrders));
    assertExactHistoryOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactHistoryOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('same-key refresh cancel+remove then fetchQuery', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useScheduledTaskRunHistoryQuery('task-1'), { wrapper });

    await act(async () => {
      await result.current.load(10);
    });

    cancelSpy.mockClear();
    removeSpy.mockClear();
    fetchSpy.mockClear();
    const pending = createDeferred<ScheduledTaskRunListResponse>();
    listRuns.mockReturnValueOnce(pending.promise);
    await act(async () => {
      void result.current.load(10);
    });
    await waitFor(() => expect(result.current.isLoading).toBe(true));
    expect(result.current.runs[0]?.id).toBe('run-1');

    await act(async () => {
      pending.resolve(runsResponse([runItem({ id: 'run-refreshed' })]));
      await pending.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const key = buildScheduledTaskRunHistoryQueryKey('task-1', 10);
    expect(cancelSpy.mock.calls.some(([filters]) => (
      filters?.exact === true
      && JSON.stringify([...(filters.queryKey ?? [])]) === JSON.stringify([...key])
    ))).toBe(true);
    expect(removeSpy.mock.calls.some(([filters]) => (
      filters?.exact === true
      && JSON.stringify([...(filters.queryKey ?? [])]) === JSON.stringify([...key])
    ))).toBe(true);
    expect(Math.min(...cancelSpy.mock.invocationCallOrder))
      .toBeLessThan(Math.min(...fetchSpy.mock.invocationCallOrder));
    expect(Math.min(...removeSpy.mock.invocationCallOrder))
      .toBeLessThan(Math.min(...fetchSpy.mock.invocationCallOrder));
    assertSilentCancelOptions(
      cancelSpy.mock.calls as Array<[filters?: unknown, options?: { silent?: boolean; revert?: boolean }]>,
    );
    assertExactHistoryOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('taskId change discards only the previous live key, resets display, and does not fetch', async () => {
    const { client, wrapper } = createWrapper();
    seedListCache(client);
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result, rerender } = renderHook(
      ({ taskId }: { taskId: string }) => useScheduledTaskRunHistoryQuery(taskId),
      { wrapper, initialProps: { taskId: 'task-1' } },
    );

    await act(async () => {
      await result.current.load(10);
    });
    expect(result.current.runs[0]?.id).toBe('run-1');
    expect(listRuns).toHaveBeenCalledTimes(1);

    cancelSpy.mockClear();
    removeSpy.mockClear();
    rerender({ taskId: 'task-2' });

    expect(result.current.runs).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.limit).toBe(10);
    expect(result.current.error).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(listRuns).toHaveBeenCalledTimes(1);
    expect(client.getQueryState(buildScheduledTaskRunHistoryQueryKey('task-1', 10))).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: LIST_QUERY_KEY, exact: true })).toHaveLength(1);
    expect(cancelSpy.mock.calls.some(([filters]) => (
      JSON.stringify([...(filters?.queryKey ?? [])]) === JSON.stringify([...LIST_QUERY_KEY])
    ))).toBe(false);
    expect(removeSpy.mock.calls.some(([filters]) => (
      JSON.stringify([...(filters?.queryKey ?? [])]) === JSON.stringify([...LIST_QUERY_KEY])
    ))).toBe(false);
    assertExactHistoryOps([
      ...cancelSpy.mock.calls,
      ...removeSpy.mock.calls,
    ] as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
  });

  it('unmount exact-removes only the live four-element key and ignores a late 500', async () => {
    const pending = createDeferred<ScheduledTaskRunListResponse>();
    listRuns.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    seedListCache(client);
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const first = renderHook(() => useScheduledTaskRunHistoryQuery('task-1'), { wrapper });
    const second = renderHook(() => useScheduledTaskRunHistoryQuery('task-2'), { wrapper });

    await act(async () => {
      void first.result.current.load(10);
      void second.result.current.load(10);
    });
    await waitFor(() => expect(listRuns).toHaveBeenCalledTimes(2));
    cancelSpy.mockClear();
    removeSpy.mockClear();

    first.unmount();
    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(first.result.current.error).toBeNull();
    expect(client.getQueryState(buildScheduledTaskRunHistoryQueryKey('task-1', 10))).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: LIST_QUERY_KEY, exact: true })).toHaveLength(1);
    expect(
      cancelSpy.mock.calls.some(([filters]) => (
        JSON.stringify([...(filters?.queryKey ?? [])])
        === JSON.stringify([...buildScheduledTaskRunHistoryQueryKey('task-2', 10)])
      )),
    ).toBe(false);
    expect(
      removeSpy.mock.calls.some(([filters]) => (
        JSON.stringify([...(filters?.queryKey ?? [])])
        === JSON.stringify([...buildScheduledTaskRunHistoryQueryKey('task-2', 10)])
      )),
    ).toBe(false);
    expect([
      ...cancelSpy.mock.calls,
      ...removeSpy.mock.calls,
    ].some(([filters]) => (
      Array.isArray(filters?.queryKey)
      && filters.queryKey.length === 1
      && filters.queryKey[0] === 'scheduled-tasks'
    ))).toBe(false);
    assertExactHistoryOps([
      ...cancelSpy.mock.calls,
      ...removeSpy.mock.calls,
    ] as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);

    await waitFor(() => expect(second.result.current.runs[0]?.id).toBe('run-1'));
    expect(second.result.current.error).toBeNull();
    second.unmount();
  });

  it('does not refetch when the window regains focus or reconnects', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useScheduledTaskRunHistoryQuery('task-1'), { wrapper });

    await act(async () => {
      await result.current.load(10);
    });
    expect(queryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(queryOptions(client)?.staleTime).toBe(0);
    expect(listRuns).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
      onlineManager.setOnline(false);
      onlineManager.setOnline(true);
    });

    expect(listRuns).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call listRuns again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useScheduledTaskRunHistoryQuery('task-1'), { wrapper });
    await act(async () => {
      await result.current.load(10);
    });
    expect(listRuns).toHaveBeenCalledTimes(1);
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

    expect(listRuns).toHaveBeenCalledTimes(1);
  });

  it('issues listRuns while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTaskRunHistoryQuery('task-1'), { wrapper });

    await act(async () => {
      await result.current.load(10);
    });

    expect(listRuns).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.networkMode).toBe('always');
    expect(result.current.runs[0]?.id).toBe('run-1');
  });
});
