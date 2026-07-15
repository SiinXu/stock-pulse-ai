import { useEffect, useRef } from 'react';
import type { TaskInfo } from '../types/analysis';
import { useTaskStream } from './useTaskStream';
import { TASK_TERMINAL_RETENTION_MS } from '../utils/taskLifecycle';

type UseDashboardLifecycleOptions = {
  loadInitialHistory: () => Promise<void>;
  refreshHistory: (silent?: boolean) => Promise<void>;
  refreshHistoryForCompletedTask?: (task: TaskInfo) => Promise<void>;
  refreshActiveTasks: () => Promise<void>;
  loadStockBar: () => Promise<void>;
  refreshStockBar: () => Promise<void>;
  loadMarketReviewHistory?: () => Promise<void>;
  refreshMarketReviewHistory?: (silent?: boolean) => Promise<void>;
  syncTaskCreated: (task: TaskInfo) => void;
  syncTaskUpdated: (task: TaskInfo) => void;
  syncTaskFailed: (task: TaskInfo) => void;
  removeTask: (taskId: string, revision?: number) => void;
  onDashboardDataRefresh?: () => void;
  onCompletedTaskDataRefreshed?: (task: TaskInfo) => void;
  activeTasks?: readonly TaskInfo[];
  enabled?: boolean;
};

export function useDashboardLifecycle({
  loadInitialHistory,
  refreshHistory,
  refreshHistoryForCompletedTask,
  refreshActiveTasks,
  loadStockBar,
  refreshStockBar,
  loadMarketReviewHistory,
  refreshMarketReviewHistory,
  syncTaskCreated,
  syncTaskUpdated,
  syncTaskFailed,
  removeTask,
  onDashboardDataRefresh,
  onCompletedTaskDataRefreshed,
  activeTasks = [],
  enabled = true,
}: UseDashboardLifecycleOptions): void {
  const removalTimeoutsRef = useRef<number[]>([]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    void loadInitialHistory();
    void loadStockBar();
    void loadMarketReviewHistory?.();
    void refreshActiveTasks();
  }, [enabled, loadInitialHistory, loadMarketReviewHistory, loadStockBar, refreshActiveTasks]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refreshHistory(true);
      void refreshStockBar();
      void refreshMarketReviewHistory?.(true);
      void refreshActiveTasks();
      onDashboardDataRefresh?.();
    }, 30_000);

    return () => window.clearInterval(intervalId);
  }, [enabled, onDashboardDataRefresh, refreshHistory, refreshMarketReviewHistory, refreshStockBar, refreshActiveTasks]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void refreshHistory(true);
        void refreshStockBar();
        void refreshMarketReviewHistory?.(true);
        void refreshActiveTasks();
        onDashboardDataRefresh?.();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [enabled, onDashboardDataRefresh, refreshHistory, refreshMarketReviewHistory, refreshStockBar, refreshActiveTasks]);

  useEffect(() => {
    return () => {
      removalTimeoutsRef.current.forEach((timeoutId) => window.clearTimeout(timeoutId));
      removalTimeoutsRef.current = [];
    };
  }, []);

  const scheduleTaskRemoval = (taskId: string, revision: number | undefined, delayMs: number) => {
    const timeoutId = window.setTimeout(() => {
      removeTask(taskId, revision);
      removalTimeoutsRef.current = removalTimeoutsRef.current.filter((item) => item !== timeoutId);
    }, delayMs);

    removalTimeoutsRef.current.push(timeoutId);
  };

  useTaskStream({
    onTaskCreated: syncTaskCreated,
    onTaskStarted: syncTaskUpdated,
    onTaskProgress: syncTaskUpdated,
    onConnected: () => {
      void refreshActiveTasks();
    },
    onTaskCompleted: (task) => {
      syncTaskUpdated(task);
      const historyRefresh = refreshHistoryForCompletedTask
        ? refreshHistoryForCompletedTask(task)
        : refreshHistory(true);
      const stockBarRefresh = refreshStockBar();
      void Promise.allSettled([historyRefresh, stockBarRefresh]).then(() => {
        onCompletedTaskDataRefreshed?.(task);
      });
      void refreshMarketReviewHistory?.(true);
      // Keep the terminal task visible long enough for the user to see the
      // completion and dismiss it; the panel now renders terminal tasks.
      scheduleTaskRemoval(task.taskId, task.revision, TASK_TERMINAL_RETENTION_MS);
    },
    onTaskFailed: (task) => {
      syncTaskFailed(task);
      scheduleTaskRemoval(task.taskId, task.revision, TASK_TERMINAL_RETENTION_MS);
    },
    onError: () => {
      console.warn('SSE connection disconnected, reconnecting...');
    },
    enabled,
    trackedTasks: activeTasks,
  });
}

export default useDashboardLifecycle;
