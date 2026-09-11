// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings scheduled-task getStatus fan-out.
// Do not import this hook from Shell, App, SettingsPage, SystemSecuritySection,
// SchedulerSettingsCard, ScheduledTaskRunHistory, hooks/index.ts, first-paint barrels,
// generation-backend files, Local Models files, intelligence-sources files,
// NotificationChannels files, Chat, Backtest, Workbench, StockScreening, or
// LLMChannelEditor.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { scheduledTasksApi } from '../api/scheduledTasks';
import type {
  ScheduledTaskDefinitionSummary,
  ScheduledTaskRunItem,
  ScheduledTaskStatusResponse,
} from '../types/scheduledTasks';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const SCHEDULED_TASK_LATEST_RUNS_CANCEL = { silent: true, revert: false } as const;

/** Readonly two-element key. Never prefix-cancel or prefix-remove `['scheduled-tasks']`. */
export const SCHEDULED_TASK_LATEST_RUNS_QUERY_KEY = ['scheduled-tasks', 'latest-runs'] as const;

/** Previous panel fan-out never retried, never polled, never focus-refetched, and always called axios offline. */
export const SCHEDULED_TASK_LATEST_RUNS_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type ScheduledTaskLatestRunsMap = Record<string, ScheduledTaskRunItem | null>;

export type UseScheduledTaskLatestRunsQueryResult = {
  latestRuns: ScheduledTaskLatestRunsMap;
  loadLatestRuns: (definitions: ScheduledTaskDefinitionSummary[]) => Promise<void>;
  refreshLatestRun: (taskId: string) => Promise<void>;
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfScheduledTaskLatestRunsCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(SCHEDULED_TASK_LATEST_RUNS_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

function mapFulfilledLatestRuns(
  results: PromiseSettledResult<readonly [string, ScheduledTaskRunItem | null]>[],
): ScheduledTaskLatestRunsMap {
  const next: ScheduledTaskLatestRunsMap = {};
  for (const result of results) {
    if (result.status === 'fulfilled') {
      const [taskId, latestRun] = result.value;
      next[taskId] = latestRun;
    }
  }
  return next;
}

export async function fetchScheduledTaskLatestRuns(args: {
  taskIds: string[];
  signal?: AbortSignal;
  stillActive?: () => boolean;
}): Promise<ScheduledTaskLatestRunsMap> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfScheduledTaskLatestRunsCancelled(args.signal, stillActive());
    const results = await Promise.allSettled(
      args.taskIds.map(async (taskId) => {
        const status: ScheduledTaskStatusResponse = await scheduledTasksApi.getStatus(taskId);
        return [taskId, status.latestRun] as const;
      }),
    );
    throwIfScheduledTaskLatestRunsCancelled(args.signal, stillActive());
    return mapFulfilledLatestRuns(results);
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfScheduledTaskLatestRunsCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useScheduledTaskLatestRunsQuery(): UseScheduledTaskLatestRunsQueryResult {
  const queryClient = useQueryClient();

  const [latestRuns, setLatestRuns] = useState<ScheduledTaskLatestRunsMap>({});
  const requestIdRef = useRef(0);

  const discardExactLatestRunsQuery = useCallback(() => {
    void queryClient.cancelQueries(
      { queryKey: SCHEDULED_TASK_LATEST_RUNS_QUERY_KEY, exact: true },
      SCHEDULED_TASK_LATEST_RUNS_CANCEL,
    );
    queryClient.removeQueries({ queryKey: SCHEDULED_TASK_LATEST_RUNS_QUERY_KEY, exact: true });
  }, [queryClient]);

  const loadLatestRuns = useCallback(async (definitions: ScheduledTaskDefinitionSummary[]) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;

    if (definitions.length === 0) {
      discardExactLatestRunsQuery();
      if (stillActive()) {
        setLatestRuns({});
      }
      return;
    }

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactLatestRunsQuery();

    try {
      const next = await queryClient.fetchQuery({
        queryKey: SCHEDULED_TASK_LATEST_RUNS_QUERY_KEY,
        queryFn: ({ signal }) => fetchScheduledTaskLatestRuns({
          taskIds: definitions.map((task) => task.id),
          signal,
          stillActive,
        }),
        ...SCHEDULED_TASK_LATEST_RUNS_QUERY_SCHEDULE,
      });
      if (!stillActive()) return;
      setLatestRuns(next);
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return;
    }
  }, [discardExactLatestRunsQuery, queryClient]);

  const refreshLatestRun = useCallback(async (taskId: string) => {
    try {
      const status = await scheduledTasksApi.getStatus(taskId);
      setLatestRuns((current) => ({
        ...current,
        [taskId]: status.latestRun,
      }));
    } catch {
      // Fail-soft: list and enable/disable remain authoritative.
    }
  }, []);

  useEffect(() => () => {
    requestIdRef.current += 1;
    discardExactLatestRunsQuery();
  }, [discardExactLatestRunsQuery]);

  return {
    latestRuns,
    loadLatestRuns,
    refreshLatestRun,
  };
}
