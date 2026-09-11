// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings scheduled-task run history GET.
// Do not import this hook from Shell, App, SettingsPage, SystemSecuritySection,
// ScheduledTasksPanel, SchedulerSettingsCard, hooks/index.ts, first-paint barrels,
// generation-backend files, Local Models files, intelligence-sources files,
// NotificationChannels files, Chat, Backtest, Workbench, StockScreening, or
// LLMChannelEditor.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { scheduledTasksApi } from '../api/scheduledTasks';
import type {
  ScheduledTaskRunItem,
  ScheduledTaskRunListResponse,
} from '../types/scheduledTasks';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const SCHEDULED_TASK_RUN_HISTORY_CANCEL = { silent: true, revert: false } as const;

/** Previous history loader never retried, never polled, never focus-refetched, and always called axios offline. */
export const SCHEDULED_TASK_RUN_HISTORY_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

const INITIAL_LIMIT = 10;

export type ScheduledTaskRunHistoryQueryKey = readonly [
  'scheduled-tasks',
  'runs',
  string,
  number,
];

export type UseScheduledTaskRunHistoryQueryResult = {
  runs: ScheduledTaskRunItem[];
  total: number;
  limit: number;
  isLoading: boolean;
  error: ParsedApiError | null;
  load: (requestedLimit: number) => Promise<ScheduledTaskRunListResponse | undefined>;
};

/** Readonly four-element key. Never prefix-cancel or prefix-remove `['scheduled-tasks']`. */
export function buildScheduledTaskRunHistoryQueryKey(
  taskId: string,
  limit: number,
): ScheduledTaskRunHistoryQueryKey {
  return ['scheduled-tasks', 'runs', taskId, limit] as const;
}

function sameQueryKey(
  left: ScheduledTaskRunHistoryQueryKey,
  right: ScheduledTaskRunHistoryQueryKey,
): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfScheduledTaskRunHistoryCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(SCHEDULED_TASK_RUN_HISTORY_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchScheduledTaskRunHistory(args: {
  taskId: string;
  limit: number;
  signal?: AbortSignal;
  stillActive?: () => boolean;
}): Promise<ScheduledTaskRunListResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfScheduledTaskRunHistoryCancelled(args.signal, stillActive());
    const response = await scheduledTasksApi.listRuns(args.taskId, { limit: args.limit });
    throwIfScheduledTaskRunHistoryCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfScheduledTaskRunHistoryCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useScheduledTaskRunHistoryQuery(
  taskId: string,
): UseScheduledTaskRunHistoryQueryResult {
  const queryClient = useQueryClient();

  const [runs, setRuns] = useState<ScheduledTaskRunItem[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(INITIAL_LIMIT);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);

  const requestIdRef = useRef(0);
  const liveKeyRef = useRef<ScheduledTaskRunHistoryQueryKey | null>(null);
  const pendingDiscardKeyRef = useRef<ScheduledTaskRunHistoryQueryKey | null>(null);
  const [trackedTaskId, setTrackedTaskId] = useState(taskId);

  if (trackedTaskId !== taskId) {
    setTrackedTaskId(taskId);
    requestIdRef.current += 1;
    pendingDiscardKeyRef.current = liveKeyRef.current;
    liveKeyRef.current = null;
    setRuns([]);
    setTotal(0);
    setLimit(INITIAL_LIMIT);
    setError(null);
    setIsLoading(false);
  }

  const discardExactQuery = useCallback((key: ScheduledTaskRunHistoryQueryKey) => {
    void queryClient.cancelQueries(
      { queryKey: key, exact: true },
      SCHEDULED_TASK_RUN_HISTORY_CANCEL,
    );
    queryClient.removeQueries({ queryKey: key, exact: true });
  }, [queryClient]);

  const load = useCallback(async (requestedLimit: number) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;
    const key = buildScheduledTaskRunHistoryQueryKey(taskId, requestedLimit);

    setError(null);
    setIsLoading(true);

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    // Key-changing loads exact-remove the previous live key, then the successor key.
    const previous = liveKeyRef.current;
    if (previous) discardExactQuery(previous);
    if (!previous || !sameQueryKey(previous, key)) {
      discardExactQuery(key);
    }
    liveKeyRef.current = key;

    try {
      const next = await queryClient.fetchQuery({
        queryKey: key,
        queryFn: ({ signal }) => fetchScheduledTaskRunHistory({
          taskId,
          limit: requestedLimit,
          signal,
          stillActive,
        }),
        ...SCHEDULED_TASK_RUN_HISTORY_QUERY_SCHEDULE,
      });
      if (!stillActive()) return undefined;
      setRuns(next.items);
      setTotal(next.total);
      setLimit(requestedLimit);
      setError(null);
      return next;
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return undefined;
      setError(getParsedApiError(err));
      return undefined;
    } finally {
      if (stillActive()) {
        setIsLoading(false);
      }
    }
  }, [discardExactQuery, queryClient, taskId]);

  useEffect(() => {
    const pending = pendingDiscardKeyRef.current;
    pendingDiscardKeyRef.current = null;
    if (pending) discardExactQuery(pending);
  }, [discardExactQuery, taskId]);

  useEffect(() => () => {
    requestIdRef.current += 1;
    const previous = liveKeyRef.current;
    liveKeyRef.current = null;
    if (previous) discardExactQuery(previous);
  }, [discardExactQuery]);

  return {
    runs,
    total,
    limit,
    isLoading,
    error,
    load,
  };
}
