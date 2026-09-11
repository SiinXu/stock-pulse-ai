// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings scheduler overlap probe GET.
// Do not import this hook from Shell, App, SettingsPage, SystemSecuritySection,
// ScheduledTasksPanel, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { scheduledTasksApi } from '../api/scheduledTasks';
import type { ScheduledTaskListResponse } from '../types/scheduledTasks';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const SCHEDULED_TASKS_OVERLAP_CANCEL = { silent: true, revert: false } as const;

/** Readonly two-element key. Never prefix-cancel or prefix-remove `['scheduled-tasks']`. */
export const SCHEDULED_TASKS_OVERLAP_QUERY_KEY = ['scheduled-tasks', 'overlap'] as const;

/** Previous card effect never retried, never focus-refetched, and always called axios offline. */
export const SCHEDULED_TASKS_OVERLAP_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type UseScheduledTasksOverlapQueryOptions = {
  enabled: boolean;
  refreshToken: number;
};

export type UseScheduledTasksOverlapQueryResult = {
  hasEnabledVersionedTasks: boolean | null;
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfScheduledTasksOverlapCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(SCHEDULED_TASKS_OVERLAP_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

function mapHasEnabledVersionedTasks(response: ScheduledTaskListResponse): boolean {
  return (response.items?.length ?? 0) > 0 || (response.total ?? 0) > 0;
}

export async function fetchScheduledTasksOverlap(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<ScheduledTaskListResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfScheduledTasksOverlapCancelled(args.signal, stillActive());
    const response = await scheduledTasksApi.list({ enabled: true, limit: 1 });
    throwIfScheduledTasksOverlapCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfScheduledTasksOverlapCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useScheduledTasksOverlapQuery({
  enabled,
  refreshToken,
}: UseScheduledTasksOverlapQueryOptions): UseScheduledTasksOverlapQueryResult {
  const queryClient = useQueryClient();

  const [hasEnabledVersionedTasks, setHasEnabledVersionedTasks] = useState<boolean | null>(null);

  const requestIdRef = useRef(0);

  const discardExactOverlapQuery = useCallback(() => {
    void queryClient.cancelQueries(
      { queryKey: SCHEDULED_TASKS_OVERLAP_QUERY_KEY, exact: true },
      SCHEDULED_TASKS_OVERLAP_CANCEL,
    );
    queryClient.removeQueries({ queryKey: SCHEDULED_TASKS_OVERLAP_QUERY_KEY, exact: true });
  }, [queryClient]);

  const load = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;

    if (!enabled) {
      discardExactOverlapQuery();
      setHasEnabledVersionedTasks(null);
      return;
    }

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactOverlapQuery();

    try {
      const next = await queryClient.fetchQuery({
        queryKey: SCHEDULED_TASKS_OVERLAP_QUERY_KEY,
        queryFn: ({ signal }) => fetchScheduledTasksOverlap({
          signal,
          stillActive,
        }),
        ...SCHEDULED_TASKS_OVERLAP_QUERY_SCHEDULE,
      });
      if (!stillActive()) return;
      setHasEnabledVersionedTasks(mapHasEnabledVersionedTasks(next));
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return;
      // Fail soft: never last-good. A later 500 must drop true to null.
      setHasEnabledVersionedTasks(null);
    }
  }, [discardExactOverlapQuery, enabled, queryClient]);

  useEffect(() => {
    // Mount + refreshToken share one fetchQuery load; enabled:false fail-softs to null.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- established Settings fetchQuery schedule
    void load();
    return () => {
      requestIdRef.current += 1;
      discardExactOverlapQuery();
    };
  }, [load, refreshToken, discardExactOverlapQuery]);

  return {
    hasEnabledVersionedTasks,
  };
}
