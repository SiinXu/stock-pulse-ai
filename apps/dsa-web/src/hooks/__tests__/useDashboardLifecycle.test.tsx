import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { TaskInfo } from '../../types/analysis';
import { useDashboardLifecycle } from '../useDashboardLifecycle';
import { useTaskStream } from '../useTaskStream';

vi.mock('../useTaskStream', () => ({
  useTaskStream: vi.fn(),
}));

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

/** Flush microtasks so TanStack Query's initial queryFn can settle under fake timers. */
async function flushQueryMicrotasks() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

const createTask = () => ({
  taskId: 'task-1',
  stockCode: '600519',
  stockName: '贵州茅台',
  status: 'completed' as const,
  progress: 100,
  reportType: 'detailed',
  createdAt: '2026-03-18T08:00:00Z',
});

const defaultMocks = {
  loadStockBar: vi.fn().mockResolvedValue(undefined),
  refreshStockBar: vi.fn().mockResolvedValue(undefined),
};

describe('useDashboardLifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    vi.mocked(useTaskStream).mockReturnValue({
      isConnected: true,
      reconnect: vi.fn(),
      disconnect: vi.fn(),
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('loads history, refreshes on interval, and reacts to visibility changes', async () => {
    const loadInitialHistory = vi.fn().mockResolvedValue(undefined);
    const refreshHistory = vi.fn().mockResolvedValue(undefined);
    const refreshActiveTasks = vi.fn().mockResolvedValue(undefined);
    const onDashboardDataRefresh = vi.fn();

    renderHook(() =>
      useDashboardLifecycle({
        loadInitialHistory,
        refreshHistory,
        refreshActiveTasks,
        syncTaskCreated: vi.fn(),
        syncTaskUpdated: vi.fn(),
        syncTaskFailed: vi.fn(),
        removeTask: vi.fn(),
        onDashboardDataRefresh,
        ...defaultMocks,
      }),
      { wrapper: createWrapper() },
    );

    await flushQueryMicrotasks();
    expect(loadInitialHistory).toHaveBeenCalledTimes(1);
    expect(refreshActiveTasks).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    await flushQueryMicrotasks();
    expect(refreshHistory).toHaveBeenCalledWith(true);
    expect(refreshActiveTasks).toHaveBeenCalledTimes(2);
    expect(onDashboardDataRefresh).toHaveBeenCalledTimes(1);

    await act(async () => {
      Object.defineProperty(document, 'visibilityState', {
        configurable: true,
        value: 'visible',
      });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await flushQueryMicrotasks();

    expect(refreshHistory).toHaveBeenCalledTimes(2);
    expect(refreshActiveTasks).toHaveBeenCalledTimes(3);
    expect(onDashboardDataRefresh).toHaveBeenCalledTimes(2);
  });

  it('cleans pending task removal timers on unmount', () => {
    const removeTask = vi.fn();

    const { unmount } = renderHook(() =>
      useDashboardLifecycle({
        loadInitialHistory: vi.fn().mockResolvedValue(undefined),
        refreshHistory: vi.fn().mockResolvedValue(undefined),
        refreshActiveTasks: vi.fn().mockResolvedValue(undefined),
        syncTaskCreated: vi.fn(),
        syncTaskUpdated: vi.fn(),
        syncTaskFailed: vi.fn(),
        removeTask,
        ...defaultMocks,
      }),
      { wrapper: createWrapper() },
    );

    const taskStreamOptions = vi.mocked(useTaskStream).mock.calls[0]?.[0];
    expect(taskStreamOptions).toBeDefined();

    act(() => {
      taskStreamOptions?.onTaskCompleted?.(createTask());
    });

    unmount();

    act(() => {
      vi.advanceTimersByTime(2_000);
    });

    expect(removeTask).not.toHaveBeenCalled();
  });

  it('refreshes completed task history and removes completed tasks after the grace window', async () => {
    const refreshHistory = vi.fn().mockResolvedValue(undefined);
    const refreshHistoryForCompletedTask = vi.fn().mockResolvedValue(undefined);
    const syncTaskUpdated = vi.fn();
    const removeTask = vi.fn();
    const onCompletedTaskDataRefreshed = vi.fn();

    renderHook(() =>
      useDashboardLifecycle({
        loadInitialHistory: vi.fn().mockResolvedValue(undefined),
        refreshHistory,
        refreshHistoryForCompletedTask,
        refreshActiveTasks: vi.fn().mockResolvedValue(undefined),
        syncTaskCreated: vi.fn(),
        syncTaskUpdated,
        syncTaskFailed: vi.fn(),
        removeTask,
        onCompletedTaskDataRefreshed,
        terminalRetentionMs: 6_000,
        ...defaultMocks,
      }),
      { wrapper: createWrapper() },
    );

    const taskStreamOptions = vi.mocked(useTaskStream).mock.calls[0]?.[0];
    const completedTask = createTask();

    await act(async () => {
      taskStreamOptions?.onTaskCompleted?.(completedTask);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(syncTaskUpdated).toHaveBeenCalledWith(completedTask);
    expect(refreshHistoryForCompletedTask).toHaveBeenCalledWith(completedTask);
    expect(refreshHistory).not.toHaveBeenCalledWith(true);

    expect(onCompletedTaskDataRefreshed).toHaveBeenCalledWith(completedTask);

    act(() => {
      vi.advanceTimersByTime(6_000);
    });
    expect(removeTask).toHaveBeenCalledWith(completedTask.taskId);
  });

  it('forwards task progress updates to the task sync handler', () => {
    const syncTaskUpdated = vi.fn();

    renderHook(() =>
      useDashboardLifecycle({
        loadInitialHistory: vi.fn().mockResolvedValue(undefined),
        refreshHistory: vi.fn().mockResolvedValue(undefined),
        refreshActiveTasks: vi.fn().mockResolvedValue(undefined),
        syncTaskCreated: vi.fn(),
        syncTaskUpdated,
        syncTaskFailed: vi.fn(),
        removeTask: vi.fn(),
        ...defaultMocks,
      }),
      { wrapper: createWrapper() },
    );

    const taskStreamOptions = vi.mocked(useTaskStream).mock.calls[0]?.[0];
    const progressTask = {
      ...createTask(),
      status: 'processing' as const,
      progress: 72,
      message: 'LLM 正在生成分析结果',
    };

    act(() => {
      taskStreamOptions?.onTaskProgress?.(progressTask);
    });

    expect(syncTaskUpdated).toHaveBeenCalledWith(progressTask);
  });

  it('reports failed tasks and removes them after the failure grace window', () => {
    const syncTaskFailed = vi.fn();
    const removeTask = vi.fn();

    renderHook(() =>
      useDashboardLifecycle({
        loadInitialHistory: vi.fn().mockResolvedValue(undefined),
        refreshHistory: vi.fn().mockResolvedValue(undefined),
        refreshActiveTasks: vi.fn().mockResolvedValue(undefined),
        syncTaskCreated: vi.fn(),
        syncTaskUpdated: vi.fn(),
        syncTaskFailed,
        removeTask,
        terminalRetentionMs: 8_000,
        ...defaultMocks,
      }),
      { wrapper: createWrapper() },
    );

    const taskStreamOptions = vi.mocked(useTaskStream).mock.calls[0]?.[0];
    const failedTask = {
      ...createTask(),
      status: 'failed' as const,
      error: '分析失败',
    };

    act(() => {
      taskStreamOptions?.onTaskFailed?.(failedTask);
    });

    expect(syncTaskFailed).toHaveBeenCalledWith(failedTask);

    act(() => {
      vi.advanceTimersByTime(8_000);
    });

    expect(removeTask).toHaveBeenCalledWith(failedTask.taskId);
  });

  it('reconciles active tasks when the SSE stream connects', async () => {
    const refreshActiveTasks = vi.fn().mockResolvedValue(undefined);

    renderHook(() =>
      useDashboardLifecycle({
        loadInitialHistory: vi.fn().mockResolvedValue(undefined),
        refreshHistory: vi.fn().mockResolvedValue(undefined),
        refreshActiveTasks,
        syncTaskCreated: vi.fn(),
        syncTaskUpdated: vi.fn(),
        syncTaskFailed: vi.fn(),
        removeTask: vi.fn(),
        ...defaultMocks,
      }),
      { wrapper: createWrapper() },
    );

    await flushQueryMicrotasks();

    const taskStreamOptions = vi.mocked(useTaskStream).mock.calls[0]?.[0];

    act(() => {
      taskStreamOptions?.onConnected?.();
    });

    expect(refreshActiveTasks).toHaveBeenCalledTimes(2);
  });

  it('polls known task ids while SSE is disconnected', () => {
    const pollKnownTasks = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useTaskStream).mockReturnValue({
      isConnected: false,
      reconnect: vi.fn(),
      disconnect: vi.fn(),
    });

    renderHook(() =>
      useDashboardLifecycle({
        loadInitialHistory: vi.fn().mockResolvedValue(undefined),
        refreshHistory: vi.fn().mockResolvedValue(undefined),
        refreshActiveTasks: vi.fn().mockResolvedValue(undefined),
        pollKnownTasks,
        syncTaskCreated: vi.fn(),
        syncTaskUpdated: vi.fn(),
        syncTaskFailed: vi.fn(),
        removeTask: vi.fn(),
        taskPollIntervalMs: 2_000,
        ...defaultMocks,
      }),
      { wrapper: createWrapper() },
    );

    expect(pollKnownTasks).toHaveBeenCalledTimes(1);
    act(() => {
      vi.advanceTimersByTime(4_000);
    });
    expect(pollKnownTasks).toHaveBeenCalledTimes(3);

    const taskStreamOptions = vi.mocked(useTaskStream).mock.calls[0]?.[0];
    act(() => taskStreamOptions?.onError?.(new Event('error')));
    expect(pollKnownTasks).toHaveBeenCalledTimes(4);
  });

  it('runs the completion workflow when disconnected polling updates a known task', async () => {
    vi.mocked(useTaskStream).mockReturnValue({
      isConnected: false,
      reconnect: vi.fn(),
      disconnect: vi.fn(),
    });
    const processingTask: TaskInfo = {
      ...createTask(),
      status: 'processing' as const,
      progress: 70,
    };
    const completedTask = createTask();
    const refreshHistoryForCompletedTask = vi.fn().mockResolvedValue(undefined);
    const refreshStockBar = vi.fn().mockResolvedValue(undefined);
    const onCompletedTaskDataRefreshed = vi.fn();
    const removeTask = vi.fn();

    const { rerender } = renderHook(
      ({ activeTasks }) => useDashboardLifecycle({
        loadInitialHistory: vi.fn().mockResolvedValue(undefined),
        refreshHistory: vi.fn().mockResolvedValue(undefined),
        refreshHistoryForCompletedTask,
        refreshActiveTasks: vi.fn().mockResolvedValue(undefined),
        pollKnownTasks: vi.fn().mockResolvedValue(undefined),
        activeTasks,
        loadStockBar: vi.fn().mockResolvedValue(undefined),
        refreshStockBar,
        syncTaskCreated: vi.fn(),
        syncTaskUpdated: vi.fn(),
        syncTaskFailed: vi.fn(),
        removeTask,
        onCompletedTaskDataRefreshed,
        terminalRetentionMs: 6_000,
      }),
      { wrapper: createWrapper(), initialProps: { activeTasks: [processingTask] } },
    );

    await act(async () => {
      rerender({ activeTasks: [completedTask] });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(refreshHistoryForCompletedTask).toHaveBeenCalledWith(completedTask);
    expect(refreshStockBar).toHaveBeenCalledTimes(1);
    expect(onCompletedTaskDataRefreshed).toHaveBeenCalledWith(completedTask);

    act(() => vi.advanceTimersByTime(6_000));
    expect(removeTask).toHaveBeenCalledWith(completedTask.taskId);
  });
});
