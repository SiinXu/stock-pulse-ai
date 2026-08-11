// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Portfolio-owned analysis task panel state: accept, poll/SSE, session+URL restore.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { SetURLSearchParams } from 'react-router-dom';
import { analysisApi } from '../../api/analysis';
import {
  getParsedApiError,
  isPermanentlyUnavailableResourceError,
} from '../../api/error';
import { useTaskStream } from '../../hooks/useTaskStream';
import type {
  AnalysisPhase,
  TaskAccepted,
  TaskInfo,
  TaskLifecycleStatus,
  TaskStatus,
} from '../../types/analysis';
import type { RunFlowSnapshotSource } from '../../types/runFlow';
import {
  applyPortfolioAnalysisTaskToSearch,
  persistPortfolioAnalysisTasks,
  readPersistedPortfolioAnalysisTasks,
  readPortfolioAnalysisTaskIdFromSearch,
  removePersistedPortfolioAnalysisTask,
  upsertPersistedPortfolioAnalysisTask,
  type PersistedPortfolioAnalysisTask,
} from './portfolioAnalysisTaskState';

const POLL_INTERVAL_MS = 2_000;
const TERMINAL_STATUSES = new Set<TaskLifecycleStatus>([
  'completed',
  'failed',
  'cancelled',
  'interrupted',
]);

function isTerminalStatus(status: TaskLifecycleStatus | string | undefined | null): boolean {
  return typeof status === 'string' && TERMINAL_STATUSES.has(status as TaskLifecycleStatus);
}

function isRunningStatus(status: TaskLifecycleStatus | string | undefined | null): boolean {
  return status === 'pending' || status === 'processing' || status === 'cancel_requested';
}

function taskStatusToInfo(
  status: TaskStatus,
  fallback: { stockCode: string; analysisPhase?: AnalysisPhase; reportType?: string },
): TaskInfo {
  return {
    taskId: status.taskId,
    stockCode: fallback.stockCode,
    stockName: status.stockName,
    status: status.status,
    progress: Number(status.progress ?? 0),
    message: status.message,
    messageCode: status.messageCode,
    messageParams: status.messageParams,
    reportType: fallback.reportType ?? 'detailed',
    createdAt: new Date().toISOString(),
    error: status.error,
    originalQuery: status.originalQuery ?? fallback.stockCode,
    selectionSource: status.selectionSource ?? 'manual',
    analysisPhase: status.analysisPhase ?? fallback.analysisPhase,
    skills: status.skills,
    ...(status.traceId ? { traceId: status.traceId } : {}),
    ...(isTerminalStatus(status.status) ? { completedAt: new Date().toISOString() } : {}),
  };
}

function acceptedToInfo(
  accepted: TaskAccepted,
  stockCode: string,
  analysisPhase: AnalysisPhase,
): TaskInfo {
  return {
    taskId: accepted.taskId,
    stockCode,
    status: accepted.status,
    progress: 0,
    message: accepted.message,
    messageCode: accepted.messageCode,
    messageParams: accepted.messageParams,
    reportType: 'detailed',
    createdAt: new Date().toISOString(),
    originalQuery: stockCode,
    selectionSource: 'manual',
    analysisPhase: accepted.analysisPhase ?? analysisPhase,
    ...(accepted.traceId ? { traceId: accepted.traceId } : {}),
  };
}

function mergeTask(current: TaskInfo | undefined, incoming: TaskInfo): TaskInfo {
  if (!current) return incoming;
  return {
    ...current,
    ...incoming,
    stockCode: incoming.stockCode || current.stockCode,
    stockName: incoming.stockName ?? current.stockName,
    progress: incoming.progress ?? current.progress,
    message: incoming.message ?? current.message,
    messageCode: incoming.messageCode ?? current.messageCode,
    messageParams: incoming.messageParams ?? current.messageParams,
    reportType: incoming.reportType || current.reportType,
    createdAt: current.createdAt || incoming.createdAt,
    startedAt: incoming.startedAt ?? current.startedAt,
    completedAt: incoming.completedAt ?? current.completedAt,
    error: incoming.error ?? current.error,
    originalQuery: incoming.originalQuery ?? current.originalQuery,
    selectionSource: incoming.selectionSource ?? current.selectionSource,
    analysisPhase: incoming.analysisPhase ?? current.analysisPhase,
    skills: incoming.skills ?? current.skills,
    traceId: incoming.traceId ?? current.traceId,
  };
}

function toPersisted(task: TaskInfo): PersistedPortfolioAnalysisTask {
  return {
    taskId: task.taskId,
    stockCode: task.stockCode,
    ...(task.analysisPhase ? { analysisPhase: task.analysisPhase } : {}),
  };
}

export type PortfolioRunFlowDialogState =
  | { open: false }
  | { open: true; source: RunFlowSnapshotSource; title: string; stockCode: string };

type UsePortfolioAnalysisTasksOptions = {
  searchParams: URLSearchParams;
  setSearchParams: SetURLSearchParams;
  enabled?: boolean;
};

export function usePortfolioAnalysisTasks({
  searchParams,
  setSearchParams,
  enabled = true,
}: UsePortfolioAnalysisTasksOptions) {
  const [tasks, setTasks] = useState<TaskInfo[]>([]);
  const [runFlowTaskId, setRunFlowTaskId] = useState<string | null>(null);
  const [hasHydrated, setHasHydrated] = useState(!enabled);
  const trackedIdsRef = useRef<Set<string>>(new Set());
  const tasksRef = useRef<TaskInfo[]>([]);
  const searchParamsRef = useRef(searchParams);
  const setSearchParamsRef = useRef(setSearchParams);
  useEffect(() => {
    tasksRef.current = tasks;
  }, [tasks]);

  useEffect(() => {
    searchParamsRef.current = searchParams;
    setSearchParamsRef.current = setSearchParams;
  }, [searchParams, setSearchParams]);

  const syncPersistence = useCallback((nextTasks: TaskInfo[]) => {
    const running = nextTasks.filter((task) => isRunningStatus(task.status));
    const terminal = nextTasks.filter((task) => isTerminalStatus(task.status));
    const persistable = [...running, ...terminal].map(toPersisted);
    persistPortfolioAnalysisTasks(persistable);

    const primaryId = running[0]?.taskId
      ?? terminal[0]?.taskId
      ?? null;
    const nextSearch = applyPortfolioAnalysisTaskToSearch(searchParamsRef.current, primaryId);
    if (nextSearch) {
      setSearchParamsRef.current(nextSearch, { replace: true });
    }
  }, []);

  const upsertLocalTask = useCallback((incoming: TaskInfo) => {
    trackedIdsRef.current.add(incoming.taskId);
    setTasks((prev) => {
      const index = prev.findIndex((task) => task.taskId === incoming.taskId);
      if (index >= 0) {
        const next = [...prev];
        next[index] = mergeTask(prev[index], incoming);
        return next;
      }
      return [mergeTask(undefined, incoming), ...prev];
    });
  }, []);

  // Persist tracked tasks and primary URL task id after hydration (never inside setState).
  useEffect(() => {
    if (!hasHydrated) return;
    syncPersistence(tasks);
  }, [hasHydrated, syncPersistence, tasks]);

  /**
   * Drop a task the backend has confirmed is gone (or never confirmed exists).
   * Clears panel state, tracked id, session persistence, and `?task=` when needed.
   */
  const dropUnrecoverableTask = useCallback((taskId: string) => {
    trackedIdsRef.current.delete(taskId);
    setTasks((prev) => {
      const next = prev.filter((task) => task.taskId !== taskId);
      const persisted = removePersistedPortfolioAnalysisTask(
        readPersistedPortfolioAnalysisTasks(),
        taskId,
      );
      persistPortfolioAnalysisTasks(persisted);
      const primaryId = next.find((task) => isRunningStatus(task.status))?.taskId
        ?? next[0]?.taskId
        ?? null;
      const nextSearch = applyPortfolioAnalysisTaskToSearch(searchParamsRef.current, primaryId);
      if (nextSearch) {
        setSearchParamsRef.current(nextSearch, { replace: true });
      }
      return next;
    });
    setRunFlowTaskId((current) => (current === taskId ? null : current));
  }, []);

  const dismissTask = useCallback((taskId: string) => {
    dropUnrecoverableTask(taskId);
  }, [dropUnrecoverableTask]);

  const acceptTask = useCallback((
    accepted: TaskAccepted,
    stockCode: string,
    analysisPhase: AnalysisPhase,
  ) => {
    const info = acceptedToInfo(accepted, stockCode, analysisPhase);
    upsertLocalTask(info);
    persistPortfolioAnalysisTasks(
      upsertPersistedPortfolioAnalysisTask(readPersistedPortfolioAnalysisTasks(), toPersisted(info)),
    );
  }, [upsertLocalTask]);

  /**
   * Provisional panel entry so a recoverable restore/poll failure can be retried
   * without claiming the backend confirmed a queued task.
   */
  const keepRecoverablePlaceholder = useCallback((
    taskId: string,
    stockCode: string,
    analysisPhase?: AnalysisPhase,
  ) => {
    const existing = tasksRef.current.find((task) => task.taskId === taskId);
    if (existing) {
      // Already on the panel — leave last-known status; poll/SSE will refresh.
      trackedIdsRef.current.add(taskId);
      return;
    }
    // First restore under a transient failure: keep id tracked so the 2s poll can retry.
    upsertLocalTask({
      taskId,
      stockCode,
      status: 'pending',
      progress: 0,
      reportType: 'detailed',
      createdAt: new Date().toISOString(),
      originalQuery: stockCode,
      selectionSource: 'manual',
      messageCode: 'task.queued',
      messageParams: { stockCode },
      ...(analysisPhase ? { analysisPhase } : {}),
    });
  }, [upsertLocalTask]);

  const attachExistingTask = useCallback(async (
    taskId: string,
    stockCode: string,
    analysisPhase?: AnalysisPhase,
  ) => {
    trackedIdsRef.current.add(taskId);
    const placeholderStock = stockCode && stockCode !== taskId ? stockCode : taskId;

    try {
      const list = await analysisApi.getTasks({
        status: 'pending,processing,cancel_requested,completed,failed,cancelled,interrupted',
        limit: 100,
      });
      const fromList = list.tasks.find((task) => task.taskId === taskId);
      if (fromList) {
        upsertLocalTask({
          ...fromList,
          stockCode: fromList.stockCode || placeholderStock,
          analysisPhase: fromList.analysisPhase ?? analysisPhase,
        });
        return;
      }
    } catch {
      // Fall through to getStatus when the task list is unavailable.
    }

    try {
      const status = await analysisApi.getStatus(taskId);
      if (!status?.taskId || !status.status) {
        // Empty body is not evidence the task exists — treat as unrecoverable.
        dropUnrecoverableTask(taskId);
        return;
      }
      upsertLocalTask(taskStatusToInfo(status, {
        stockCode: placeholderStock,
        analysisPhase,
      }));
    } catch (error) {
      const parsed = getParsedApiError(error);
      if (isPermanentlyUnavailableResourceError(parsed)) {
        dropUnrecoverableTask(taskId);
        return;
      }
      // Transient/network/5xx: keep tracking + persistence; poll/SSE can recover.
      keepRecoverablePlaceholder(taskId, placeholderStock, analysisPhase);
    }
  }, [dropUnrecoverableTask, keepRecoverablePlaceholder, upsertLocalTask]);

  useEffect(() => {
    if (!enabled) return undefined;

    const fromSession = readPersistedPortfolioAnalysisTasks();
    const urlTaskId = readPortfolioAnalysisTaskIdFromSearch(searchParamsRef.current);
    const seed: PersistedPortfolioAnalysisTask[] = [...fromSession];
    if (urlTaskId && !seed.some((task) => task.taskId === urlTaskId)) {
      seed.unshift({ taskId: urlTaskId, stockCode: urlTaskId });
    }

    let cancelled = false;
    void (async () => {
      for (const item of seed) {
        if (cancelled) return;
        await attachExistingTask(item.taskId, item.stockCode, item.analysisPhase);
      }
      if (!cancelled) setHasHydrated(true);
    })();

    return () => {
      cancelled = true;
    };
  }, [attachExistingTask, enabled]);

  const applyStreamTask = useCallback((incoming: TaskInfo) => {
    if (!trackedIdsRef.current.has(incoming.taskId)) return;
    upsertLocalTask(incoming);
  }, [upsertLocalTask]);

  useTaskStream({
    enabled,
    onTaskCreated: applyStreamTask,
    onTaskStarted: applyStreamTask,
    onTaskProgress: applyStreamTask,
    onTaskCompleted: applyStreamTask,
    onTaskFailed: applyStreamTask,
  });

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      const running = tasksRef.current.filter((task) => isRunningStatus(task.status));
      if (running.length === 0) {
        timer = window.setTimeout(() => { void poll(); }, POLL_INTERVAL_MS);
        return;
      }
      await Promise.all(running.map(async (task) => {
        try {
          const status = await analysisApi.getStatus(task.taskId);
          if (cancelled) return;
          if (!status?.status) {
            // Resolved empty status is not a confirmed running task.
            dropUnrecoverableTask(task.taskId);
            return;
          }
          upsertLocalTask(taskStatusToInfo(status, {
            stockCode: task.stockCode,
            analysisPhase: task.analysisPhase,
            reportType: task.reportType,
          }));
        } catch (error) {
          if (cancelled) return;
          const parsed = getParsedApiError(error);
          if (isPermanentlyUnavailableResourceError(parsed)) {
            dropUnrecoverableTask(task.taskId);
            return;
          }
          // Recoverable poll failure: keep the last known panel state.
        }
      }));
      if (!cancelled) {
        timer = window.setTimeout(() => { void poll(); }, POLL_INTERVAL_MS);
      }
    };

    timer = window.setTimeout(() => { void poll(); }, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [dropUnrecoverableTask, enabled, upsertLocalTask]);

  const openRunFlow = useCallback((task: TaskInfo) => {
    setRunFlowTaskId(task.taskId);
  }, []);

  const closeRunFlow = useCallback(() => {
    setRunFlowTaskId(null);
  }, []);

  const runFlowDialog = useMemo<PortfolioRunFlowDialogState>(() => {
    if (!runFlowTaskId) return { open: false };
    const task = tasks.find((candidate) => candidate.taskId === runFlowTaskId);
    return {
      open: true,
      source: { type: 'task', taskId: runFlowTaskId },
      title: task?.stockName || task?.stockCode || runFlowTaskId,
      stockCode: task?.stockCode || '',
    };
  }, [runFlowTaskId, tasks]);

  return {
    tasks,
    acceptTask,
    attachExistingTask,
    dismissTask,
    openRunFlow,
    closeRunFlow,
    runFlowDialog,
  };
}

export default usePortfolioAnalysisTasks;
