// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClientProvider, focusManager, onlineManager, type QueryClient } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { scheduledTasksApi } from '../../api/scheduledTasks';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type {
  ScheduledTaskDefinitionSummary,
  ScheduledTaskRunItem,
  ScheduledTaskStatusResponse,
} from '../../types/scheduledTasks';
import {
  SCHEDULED_TASK_LATEST_RUNS_CANCEL,
  SCHEDULED_TASK_LATEST_RUNS_QUERY_KEY,
  SCHEDULED_TASK_LATEST_RUNS_QUERY_SCHEDULE,
  fetchScheduledTaskLatestRuns,
  useScheduledTaskLatestRunsQuery,
} from '../useScheduledTaskLatestRunsQuery';

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

const getStatus = vi.mocked(scheduledTasksApi.getStatus);
const listTasks = vi.mocked(scheduledTasksApi.list);
const listRuns = vi.mocked(scheduledTasksApi.listRuns);
const createTask = vi.mocked(scheduledTasksApi.create);
const enableTask = vi.mocked(scheduledTasksApi.enable);
const disableTask = vi.mocked(scheduledTasksApi.disable);

const LIST_QUERY_KEY = ['scheduled-tasks', 'list'] as const;
const OVERLAP_QUERY_KEY = ['scheduled-tasks', 'overlap'] as const;
const RUNS_QUERY_KEY = ['scheduled-tasks', 'runs', 'task-1', 10] as const;
const SCHEDULER_STATUS_QUERY_KEY = ['scheduler', 'status'] as const;

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

function statusResponse(
  taskId: string,
  latestRun: ScheduledTaskRunItem | null,
): ScheduledTaskStatusResponse {
  return {
    task: task({ id: taskId }),
    latestRun,
  };
}

function serverError(): Error {
  return Object.assign(new Error('server'), {
    response: {
      status: 500,
      data: { error: 'internal', message: 'scheduled task status unavailable' },
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
  queryKey: readonly unknown[] = SCHEDULED_TASK_LATEST_RUNS_QUERY_KEY,
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function seedSiblingKeys(client: QueryClient) {
  client.setQueryData(LIST_QUERY_KEY, { items: [], total: 0 });
  client.setQueryData(OVERLAP_QUERY_KEY, { items: [], total: 0 });
  client.setQueryData(RUNS_QUERY_KEY, { items: [], total: 0, limit: 10 });
  client.setQueryData(SCHEDULER_STATUS_QUERY_KEY, { enabled: true });
}

function assertExactLatestRunsOps(
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
      expect([...key]).toEqual(['scheduled-tasks', 'latest-runs']);
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

describe('useScheduledTaskLatestRunsQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    getStatus.mockResolvedValue(statusResponse('task-1', runItem()));
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

  it('pins the exact latest-runs key, schedule, and getStatus(taskId) with no signal or language', async () => {
    expect([...SCHEDULED_TASK_LATEST_RUNS_QUERY_KEY]).toEqual(['scheduled-tasks', 'latest-runs']);
    expect(SCHEDULED_TASK_LATEST_RUNS_QUERY_KEY).toHaveLength(2);
    expect(SCHEDULED_TASK_LATEST_RUNS_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(SCHEDULED_TASK_LATEST_RUNS_CANCEL).toEqual({ silent: true, revert: false });

    const controller = new AbortController();
    await fetchScheduledTaskLatestRuns({ taskIds: ['task-1'], signal: controller.signal });
    expect(getStatus).toHaveBeenCalledTimes(1);
    expect(getStatus).toHaveBeenCalledWith('task-1');
    expect(listTasks).not.toHaveBeenCalled();
    expect(listRuns).not.toHaveBeenCalled();
    expect(createTask).not.toHaveBeenCalled();
    expect(enableTask).not.toHaveBeenCalled();
    expect(disableTask).not.toHaveBeenCalled();
  });

  it('is not barrel-exported and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('useScheduledTaskLatestRunsQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useScheduledTaskLatestRunsQuery(), { wrapper });

    expect(result.current.latestRuns).toEqual({});
    expect(getStatus).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.current).not.toHaveProperty('isLoading');
    expect(result.current).not.toHaveProperty('isRefreshing');
    expect(result.current).not.toHaveProperty('loadError');

    await act(async () => {
      await result.current.loadLatestRuns([task()]);
    });

    expect(getStatus).toHaveBeenCalledTimes(1);
    expect(getStatus).toHaveBeenCalledWith('task-1');
    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['scheduled-tasks', 'latest-runs']);
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
      expect(scheduled.refetchInterval).toBeUndefined();
    }
    expect(
      client.getQueryCache().find({
        queryKey: SCHEDULED_TASK_LATEST_RUNS_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
  });

  it('does not fetch on mount until loadLatestRuns', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTaskLatestRunsQuery(), { wrapper });

    expect(result.current.latestRuns).toEqual({});
    expect(getStatus).not.toHaveBeenCalled();
    await flushQueryMicrotasks();
    expect(getStatus).not.toHaveBeenCalled();
  });

  it('loadLatestRuns([]) sets {} and does not call getStatus', async () => {
    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useScheduledTaskLatestRunsQuery(), { wrapper });

    await act(async () => {
      await result.current.loadLatestRuns([]);
    });

    expect(result.current.latestRuns).toEqual({});
    expect(getStatus).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('loadLatestRuns calls getStatus once per id, maps fulfilled latestRun, and leaves zero observers', async () => {
    getStatus.mockImplementation(async (taskId: string) => (
      statusResponse(taskId, runItem({ id: `run-${taskId}`, taskId }))
    ));
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTaskLatestRunsQuery(), { wrapper });

    await act(async () => {
      await result.current.loadLatestRuns([
        task({ id: 'task-1' }),
        task({ id: 'task-2', name: 'Second' }),
      ]);
    });

    expect(getStatus).toHaveBeenCalledTimes(2);
    expect(getStatus).toHaveBeenCalledWith('task-1');
    expect(getStatus).toHaveBeenCalledWith('task-2');
    expect(result.current.latestRuns['task-1']?.id).toBe('run-task-1');
    expect(result.current.latestRuns['task-2']?.id).toBe('run-task-2');
    expect(
      client.getQueryCache().find({
        queryKey: SCHEDULED_TASK_LATEST_RUNS_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
  });

  it('mixed allSettled keeps only fulfilled ids and does not fail the batch', async () => {
    getStatus.mockImplementation(async (taskId: string) => {
      if (taskId === 'task-2') throw serverError();
      return statusResponse('task-1', runItem());
    });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTaskLatestRunsQuery(), { wrapper });

    await act(async () => {
      await result.current.loadLatestRuns([
        task({ id: 'task-1' }),
        task({ id: 'task-2', name: 'Second' }),
      ]);
    });

    expect(getStatus).toHaveBeenCalledTimes(2);
    expect(result.current.latestRuns).toEqual({ 'task-1': runItem() });
    expect(result.current.latestRuns).not.toHaveProperty('task-2');
    expect(result.current).not.toHaveProperty('loadError');
  });

  it('stores fulfilled null latestRun instead of omitting the id', async () => {
    getStatus.mockResolvedValueOnce(statusResponse('task-1', null));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTaskLatestRunsQuery(), { wrapper });

    await act(async () => {
      await result.current.loadLatestRuns([task()]);
    });

    expect(result.current.latestRuns).toEqual({ 'task-1': null });
    expect(Object.prototype.hasOwnProperty.call(result.current.latestRuns, 'task-1')).toBe(true);
  });

  it('lets the newest loadLatestRuns generation win over a stale map', async () => {
    const stale = createDeferred<ScheduledTaskStatusResponse>();
    getStatus
      .mockReturnValueOnce(stale.promise)
      .mockResolvedValueOnce(statusResponse('task-1', runItem({ id: 'live' })));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTaskLatestRunsQuery(), { wrapper });

    await act(async () => {
      void result.current.loadLatestRuns([task()]);
    });
    await waitFor(() => expect(getStatus).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.loadLatestRuns([task()]);
    });
    await waitFor(() => expect(result.current.latestRuns['task-1']?.id).toBe('live'));

    await act(async () => {
      stale.resolve(statusResponse('task-1', runItem({ id: 'stale' })));
      await stale.promise.catch(() => undefined);
    });

    expect(result.current.latestRuns['task-1']?.id).toBe('live');
  });

  it('CancelledError / unmount exact-removes the fan-out key and ignores a late 500', async () => {
    const pending = createDeferred<ScheduledTaskStatusResponse>();
    getStatus.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    seedSiblingKeys(client);
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result, unmount } = renderHook(() => useScheduledTaskLatestRunsQuery(), { wrapper });

    await act(async () => {
      void result.current.loadLatestRuns([task()]);
    });
    await waitFor(() => expect(getStatus).toHaveBeenCalledTimes(1));
    cancelSpy.mockClear();
    removeSpy.mockClear();
    unmount();

    await act(async () => {
      pending.reject(serverError());
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.latestRuns).toEqual({});
    expect(client.getQueryState(SCHEDULED_TASK_LATEST_RUNS_QUERY_KEY)).toBeUndefined();
    expect(queryFetchStatus(client, SCHEDULED_TASK_LATEST_RUNS_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: LIST_QUERY_KEY, exact: true })).toHaveLength(1);
    expect(client.getQueryCache().findAll({ queryKey: OVERLAP_QUERY_KEY, exact: true })).toHaveLength(1);
    expect(client.getQueryCache().findAll({ queryKey: RUNS_QUERY_KEY, exact: true })).toHaveLength(1);
    assertExactLatestRunsOps([
      ...cancelSpy.mock.calls,
      ...removeSpy.mock.calls,
    ] as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
  });

  it('same-key refresh cancel+remove then fetchQuery', async () => {
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useScheduledTaskLatestRunsQuery(), { wrapper });

    await act(async () => {
      await result.current.loadLatestRuns([task()]);
    });
    expect(result.current.latestRuns['task-1']?.id).toBe('run-1');

    cancelSpy.mockClear();
    removeSpy.mockClear();
    fetchSpy.mockClear();
    const pending = createDeferred<ScheduledTaskStatusResponse>();
    getStatus.mockReturnValueOnce(pending.promise);
    await act(async () => {
      void result.current.loadLatestRuns([task()]);
    });
    await waitFor(() => expect(getStatus).toHaveBeenCalledTimes(2));

    await act(async () => {
      pending.resolve(statusResponse('task-1', runItem({ id: 'run-refreshed' })));
      await pending.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.latestRuns['task-1']?.id).toBe('run-refreshed'));

    expect(cancelSpy.mock.calls.some(([filters]) => (
      filters?.exact === true
      && JSON.stringify([...(filters.queryKey ?? [])])
        === JSON.stringify([...SCHEDULED_TASK_LATEST_RUNS_QUERY_KEY])
    ))).toBe(true);
    expect(removeSpy.mock.calls.some(([filters]) => (
      filters?.exact === true
      && JSON.stringify([...(filters.queryKey ?? [])])
        === JSON.stringify([...SCHEDULED_TASK_LATEST_RUNS_QUERY_KEY])
    ))).toBe(true);
    expect(Math.min(...cancelSpy.mock.invocationCallOrder))
      .toBeLessThan(Math.min(...fetchSpy.mock.invocationCallOrder));
    expect(Math.min(...removeSpy.mock.invocationCallOrder))
      .toBeLessThan(Math.min(...fetchSpy.mock.invocationCallOrder));
    assertSilentCancelOptions(
      cancelSpy.mock.calls as Array<[filters?: unknown, options?: { silent?: boolean; revert?: boolean }]>,
    );
    assertExactLatestRunsOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('never prefix-cancels scheduled-tasks or exact-cancels list, overlap, runs, scheduler, settings, plugins, or Home keys', async () => {
    const { client, wrapper } = createWrapper();
    seedSiblingKeys(client);
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result, unmount } = renderHook(() => useScheduledTaskLatestRunsQuery(), { wrapper });

    await act(async () => {
      await result.current.loadLatestRuns([task()]);
    });
    await act(async () => {
      await result.current.loadLatestRuns([task()]);
    });
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
    expect(allOps.some(([filters]) => keyEquals(filters, OVERLAP_QUERY_KEY))).toBe(false);
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
    expect(client.getQueryCache().findAll({ queryKey: OVERLAP_QUERY_KEY, exact: true })).toHaveLength(1);
    expect(client.getQueryCache().findAll({ queryKey: RUNS_QUERY_KEY, exact: true })).toHaveLength(1);
    expect(client.getQueryCache().findAll({ queryKey: SCHEDULER_STATUS_QUERY_KEY, exact: true })).toHaveLength(1);
    assertExactLatestRunsOps(allOps);
  });

  it('does not refetch when the window regains focus or reconnects', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useScheduledTaskLatestRunsQuery(), { wrapper });

    await act(async () => {
      await result.current.loadLatestRuns([task()]);
    });
    expect(queryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client)?.retry).toBe(false);
    expect(queryOptions(client)?.staleTime).toBe(0);
    expect(getStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
      onlineManager.setOnline(false);
      onlineManager.setOnline(true);
    });

    expect(getStatus).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call getStatus again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useScheduledTaskLatestRunsQuery(), { wrapper });
    await act(async () => {
      await result.current.loadLatestRuns([task()]);
    });
    expect(getStatus).toHaveBeenCalledTimes(1);
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

    expect(getStatus).toHaveBeenCalledTimes(1);
  });

  it('issues getStatus while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useScheduledTaskLatestRunsQuery(), { wrapper });

    await act(async () => {
      await result.current.loadLatestRuns([task()]);
    });

    expect(getStatus).toHaveBeenCalledTimes(1);
    expect(queryOptions(client)?.networkMode).toBe('always');
    expect(result.current.latestRuns['task-1']?.id).toBe('run-1');
  });

  it('refreshLatestRun patches one key on 200, keeps it on 500, and does not cancel the fan-out key', async () => {
    getStatus.mockImplementation(async (taskId: string) => (
      statusResponse(taskId, runItem({ id: `run-${taskId}`, taskId }))
    ));
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useScheduledTaskLatestRunsQuery(), { wrapper });

    await act(async () => {
      await result.current.loadLatestRuns([
        task({ id: 'task-1' }),
        task({ id: 'task-2', name: 'Second' }),
      ]);
    });
    expect(result.current.latestRuns['task-1']?.id).toBe('run-task-1');
    expect(result.current.latestRuns['task-2']?.id).toBe('run-task-2');

    cancelSpy.mockClear();
    removeSpy.mockClear();
    fetchSpy.mockClear();
    getStatus.mockReset();
    getStatus.mockResolvedValueOnce(statusResponse('task-1', runItem({ id: 'from-toggle' })));
    await act(async () => {
      await result.current.refreshLatestRun('task-1');
    });

    expect(result.current.latestRuns['task-1']?.id).toBe('from-toggle');
    expect(result.current.latestRuns['task-2']?.id).toBe('run-task-2');
    expect(getStatus).toHaveBeenCalledTimes(1);
    expect(getStatus).toHaveBeenCalledWith('task-1');
    expect(listTasks).not.toHaveBeenCalled();
    expect(listRuns).not.toHaveBeenCalled();
    expect(cancelSpy).not.toHaveBeenCalled();
    expect(removeSpy).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();

    getStatus.mockRejectedValueOnce(serverError());
    await act(async () => {
      await result.current.refreshLatestRun('task-1');
    });

    expect(result.current.latestRuns['task-1']?.id).toBe('from-toggle');
    expect(result.current.latestRuns['task-2']?.id).toBe('run-task-2');
    expect(cancelSpy).not.toHaveBeenCalled();
    expect(removeSpy).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(listTasks).not.toHaveBeenCalled();
    expect(listRuns).not.toHaveBeenCalled();
  });

  it('refreshLatestRun during an in-flight fan-out does not cancel the batch', async () => {
    const stale = createDeferred<ScheduledTaskStatusResponse>();
    getStatus
      .mockReturnValueOnce(stale.promise)
      .mockResolvedValueOnce(statusResponse('task-1', runItem({ id: 'from-toggle' })));
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useScheduledTaskLatestRunsQuery(), { wrapper });

    await act(async () => {
      void result.current.loadLatestRuns([task()]);
    });
    await waitFor(() => expect(getStatus).toHaveBeenCalledTimes(1));
    cancelSpy.mockClear();
    removeSpy.mockClear();

    await act(async () => {
      await result.current.refreshLatestRun('task-1');
    });

    expect(result.current.latestRuns['task-1']?.id).toBe('from-toggle');
    expect(cancelSpy).not.toHaveBeenCalled();
    expect(removeSpy).not.toHaveBeenCalled();

    await act(async () => {
      stale.resolve(statusResponse('task-1', runItem({ id: 'from-fanout' })));
      await stale.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.latestRuns['task-1']?.id).toBe('from-fanout'));
  });
});
