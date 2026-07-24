import { useCallback, useEffect, useRef, useState } from 'react';
import type { TaskInfo } from '../types/analysis';
import { useTaskStream } from './useTaskStream';

type UseDashboardLifecycleOptions = {
  loadInitialHistory: () => Promise<void>;
  refreshHistory: (silent?: boolean) => Promise<unknown>;
  refreshHistoryForCompletedTask?: (task: TaskInfo) => Promise<unknown>;
  refreshActiveTasks: () => Promise<void>;
  pollKnownTasks?: () => Promise<void>;
  activeTasks?: readonly TaskInfo[];
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
const EMPTY_TASKS: readonly TaskInfo[] = [];

function isTerminalTaskStatus(status: TaskInfo['status']): boolean {
  return ['completed', 'failed', 'cancelled', 'interrupted'].includes(status);
}

export type DashboardLifecycleState = {
  isInitialStockBarLoadSettled: boolean;
};

export function useDashboardLifecycle({
  loadInitialHistory,
  refreshHistory,
  refreshHistoryForCompletedTask,
  refreshActiveTasks,
  pollKnownTasks = noopAsync,
  activeTasks = EMPTY_TASKS,
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
}: UseDashboardLifecycleOptions): DashboardLifecycleState {
  const removalTimeoutsRef = useRef<Map<string, number>>(new Map());
  const previousTaskStatusesRef = useRef<Map<string, TaskInfo['status']>>(new Map());
  const handledTerminalStatusesRef = useRef<Map<string, TaskInfo['status']>>(new Map());
  const [isInitialStockBarLoadSettled, setIsInitialStockBarLoadSettled] = useState(false);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    void loadInitialHistory();
    let active = true;
    void loadStockBar().finally(() => {
      if (active) setIsInitialStockBarLoadSettled(true);
    });
    void refreshActiveTasks();
    return () => {
      active = false;
    };
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

  const scheduleTaskRemoval = useCallback((taskId: string, delayMs: number) => {
    const existingTimeout = removalTimeoutsRef.current.get(taskId);
    if (existingTimeout !== undefined) {
      window.clearTimeout(existingTimeout);
    }
    const timeoutId = window.setTimeout(() => {
      removeTask(taskId);
      removalTimeoutsRef.current.delete(taskId);
    }, delayMs);

    removalTimeoutsRef.current.set(taskId, timeoutId);
  }, [removeTask]);

  const claimTerminalTask = useCallback((task: TaskInfo): boolean => {
    if (handledTerminalStatusesRef.current.get(task.taskId) === task.status) return false;
    handledTerminalStatusesRef.current.set(task.taskId, task.status);
    return true;
  }, []);

  const handleCompletedTask = useCallback((task: TaskInfo) => {
    if (!claimTerminalTask(task)) return;
    const historyRefresh = refreshHistoryForCompletedTask
      ? refreshHistoryForCompletedTask(task)
      : refreshHistory(true);
    const stockBarRefresh = refreshStockBar();
    void Promise.allSettled([historyRefresh, stockBarRefresh]).then(() => {
      onCompletedTaskDataRefreshed?.(task);
    });
    scheduleTaskRemoval(task.taskId, terminalRetentionMs);
  }, [
    claimTerminalTask,
    onCompletedTaskDataRefreshed,
    refreshHistory,
    refreshHistoryForCompletedTask,
    refreshStockBar,
    scheduleTaskRemoval,
    terminalRetentionMs,
  ]);

  const handleNonCompletedTerminalTask = useCallback((task: TaskInfo) => {
    if (!claimTerminalTask(task)) return;
    scheduleTaskRemoval(task.taskId, terminalRetentionMs);
  }, [claimTerminalTask, scheduleTaskRemoval, terminalRetentionMs]);

  useEffect(() => {
    const previousStatuses = previousTaskStatusesRef.current;
    const nextStatuses = new Map(activeTasks.map((task) => [task.taskId, task.status]));
    if (enabled) {
      for (const task of activeTasks) {
        const previousStatus = previousStatuses.get(task.taskId);
        if (!previousStatus || isTerminalTaskStatus(previousStatus) || !isTerminalTaskStatus(task.status)) {
          continue;
        }
        if (task.status === 'completed') handleCompletedTask(task);
        else handleNonCompletedTerminalTask(task);
      }
    }
    previousTaskStatusesRef.current = nextStatuses;
  }, [activeTasks, enabled, handleCompletedTask, handleNonCompletedTerminalTask]);

  const taskStream = useTaskStream({
    onTaskCreated: syncTaskCreated,
    onTaskStarted: syncTaskUpdated,
    onTaskProgress: syncTaskUpdated,
    onConnected: () => {
      void refreshActiveTasks();
    },
    onTaskCompleted: (task) => {
      syncTaskUpdated(task);
      handleCompletedTask(task);
    },
    onTaskFailed: (task) => {
      syncTaskFailed(task);
      handleNonCompletedTerminalTask(task);
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

  return { isInitialStockBarLoadSettled };
}

export default useDashboardLifecycle;
