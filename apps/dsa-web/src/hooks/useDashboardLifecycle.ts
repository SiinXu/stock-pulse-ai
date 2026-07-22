import { useEffect, useRef } from 'react';
import type { TaskInfo } from '../types/analysis';
import { useTaskStream } from './useTaskStream';

type UseDashboardLifecycleOptions = {
  loadInitialHistory: () => Promise<void>;
  refreshHistory: (silent?: boolean) => Promise<unknown>;
  refreshHistoryForCompletedTask?: (task: TaskInfo) => Promise<unknown>;
  refreshActiveTasks: () => Promise<void>;
  pollKnownTasks?: () => Promise<void>;
  loadStockBar: () => Promise<void>;
  refreshStockBar: () => Promise<void>;
  syncTaskCreated: (task: TaskInfo) => void;
  syncTaskUpdated: (task: TaskInfo) => void;
  syncTaskFailed: (task: TaskInfo) => void;
  removeTask: (taskId: string) => void;
  onDashboardDataRefresh?: () => void;
  onCompletedTaskDataRefreshed?: (task: TaskInfo) => void;
  enabled?: boolean;
  taskPollIntervalMs?: number;
  terminalRetentionMs?: number;
};

const noopAsync = async (): Promise<void> => undefined;

export function useDashboardLifecycle({
  loadInitialHistory,
  refreshHistory,
  refreshHistoryForCompletedTask,
  refreshActiveTasks,
  pollKnownTasks = noopAsync,
  loadStockBar,
  refreshStockBar,
  syncTaskCreated,
  syncTaskUpdated,
  syncTaskFailed,
  removeTask,
  onDashboardDataRefresh,
  onCompletedTaskDataRefreshed,
  enabled = true,
  taskPollIntervalMs = 2_000,
  terminalRetentionMs = 2 * 60 * 1000,
}: UseDashboardLifecycleOptions): void {
  const removalTimeoutsRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    if (!enabled) {
      return;
    }

    void loadInitialHistory();
    void loadStockBar();
    void refreshActiveTasks();
  }, [enabled, loadInitialHistory, loadStockBar, refreshActiveTasks]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refreshHistory(true);
      void refreshStockBar();
      void refreshActiveTasks();
      onDashboardDataRefresh?.();
    }, 30_000);

    return () => window.clearInterval(intervalId);
  }, [enabled, onDashboardDataRefresh, refreshHistory, refreshStockBar, refreshActiveTasks]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void refreshHistory(true);
        void refreshStockBar();
        void refreshActiveTasks();
        onDashboardDataRefresh?.();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [enabled, onDashboardDataRefresh, refreshHistory, refreshStockBar, refreshActiveTasks]);

  useEffect(() => {
    const removalTimeouts = removalTimeoutsRef.current;
    return () => {
      removalTimeouts.forEach((timeoutId) => window.clearTimeout(timeoutId));
      removalTimeouts.clear();
    };
  }, []);

  const scheduleTaskRemoval = (taskId: string, delayMs: number) => {
    const existingTimeout = removalTimeoutsRef.current.get(taskId);
    if (existingTimeout !== undefined) {
      window.clearTimeout(existingTimeout);
    }
    const timeoutId = window.setTimeout(() => {
      removeTask(taskId);
      removalTimeoutsRef.current.delete(taskId);
    }, delayMs);

    removalTimeoutsRef.current.set(taskId, timeoutId);
  };

  const taskStream = useTaskStream({
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
      // Keep the terminal task visible long enough for the user to see the
      // completion and dismiss it; the panel now renders terminal tasks.
      scheduleTaskRemoval(task.taskId, terminalRetentionMs);
    },
    onTaskFailed: (task) => {
      syncTaskFailed(task);
      scheduleTaskRemoval(task.taskId, terminalRetentionMs);
    },
    onError: () => {
      console.warn('SSE connection disconnected, reconnecting...');
      void pollKnownTasks();
    },
    enabled,
  });
  const isConnected = taskStream?.isConnected ?? false;

  useEffect(() => {
    if (!enabled || isConnected) {
      return;
    }

    void pollKnownTasks();
    const intervalId = window.setInterval(() => {
      void pollKnownTasks();
    }, taskPollIntervalMs);
    return () => window.clearInterval(intervalId);
  }, [enabled, isConnected, pollKnownTasks, taskPollIntervalMs]);
}

export default useDashboardLifecycle;
