// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings scheduled-tasks list GET.
// Do not import this hook from Shell, App, SettingsPage, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { scheduledTasksApi } from '../api/scheduledTasks';
import type {
  ScheduledTaskDefinitionSummary,
  ScheduledTaskListResponse,
} from '../types/scheduledTasks';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const SCHEDULED_TASKS_LIST_CANCEL = { silent: true, revert: false } as const;

/** Readonly two-element key. Never prefix-cancel or prefix-remove `['scheduled-tasks']`. */
export const SCHEDULED_TASKS_LIST_QUERY_KEY = ['scheduled-tasks', 'list'] as const;

/** Previous panel effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const SCHEDULED_TASKS_LIST_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type ScheduledTasksListLoadMode = 'initial' | 'refresh';

export type UseScheduledTasksListQueryResult = {
  items: ScheduledTaskDefinitionSummary[];
  isLoading: boolean;
  isRefreshing: boolean;
  loadError: ParsedApiError | null;
  load: (mode?: ScheduledTasksListLoadMode) => Promise<ScheduledTaskDefinitionSummary[] | undefined>;
  /** Panel-owned enable/disable patches the last-good roster before the follow-up GET. */
  setItems: Dispatch<SetStateAction<ScheduledTaskDefinitionSummary[]>>;
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfScheduledTasksListCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(SCHEDULED_TASKS_LIST_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchScheduledTasksList(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<ScheduledTaskListResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfScheduledTasksListCancelled(args.signal, stillActive());
    const response = await scheduledTasksApi.list({ limit: 200 });
    throwIfScheduledTasksListCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfScheduledTasksListCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useScheduledTasksListQuery(): UseScheduledTasksListQueryResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [items, setItems] = useState<ScheduledTaskDefinitionSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);

  const requestIdRef = useRef(0);

  const discardExactScheduledTasksListQuery = useCallback(() => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: SCHEDULED_TASKS_LIST_QUERY_KEY, exact: true },
      SCHEDULED_TASKS_LIST_CANCEL,
    );
    client.removeQueries({ queryKey: SCHEDULED_TASKS_LIST_QUERY_KEY, exact: true });
  }, []);

  const load = useCallback(async (mode: ScheduledTasksListLoadMode = 'initial') => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;

    setLoadError(null);
    if (mode === 'initial') {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactScheduledTasksListQuery();

    try {
      const next = await queryClientRef.current.fetchQuery({
        queryKey: SCHEDULED_TASKS_LIST_QUERY_KEY,
        queryFn: ({ signal }) => fetchScheduledTasksList({
          signal,
          stillActive,
        }),
        ...SCHEDULED_TASKS_LIST_QUERY_SCHEDULE,
      });
      if (!stillActive()) return undefined;
      setItems(next.items);
      return next.items;
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return undefined;
      // Keep a previously loaded roster on refresh so a transient GET
      // failure cannot wipe rows after a completed enable/disable.
      if (mode === 'initial') {
        setItems([]);
      }
      setLoadError(getParsedApiError(err));
      return undefined;
    } finally {
      if (stillActive()) {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    }
  }, [discardExactScheduledTasksListQuery]);

  useEffect(() => {
    void load('initial');
    return () => {
      requestIdRef.current += 1;
      discardExactScheduledTasksListQuery();
    };
  }, [load, discardExactScheduledTasksListQuery]);

  return {
    items,
    isLoading,
    isRefreshing,
    loadError,
    load,
    setItems,
  };
}
