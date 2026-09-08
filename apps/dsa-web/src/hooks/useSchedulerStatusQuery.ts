// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings scheduler status GET.
// Do not import this hook from Shell, App, SettingsPage, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { systemConfigApi } from '../api/systemConfig';
import type { SchedulerStatusResponse } from '../types/systemConfig';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const SCHEDULER_STATUS_CANCEL = { silent: true, revert: false } as const;

/** Readonly two-element key. Never prefix-cancel or prefix-remove `['scheduler']`. */
export const SCHEDULER_STATUS_QUERY_KEY = ['scheduler', 'status'] as const;

/** Previous card effect never retried, never focus-refetched, and always called axios offline. */
export const SCHEDULER_STATUS_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type UseSchedulerStatusQueryOptions = {
  enabled: boolean;
  refreshToken: number;
};

export type UseSchedulerStatusQueryResult = {
  status: SchedulerStatusResponse | null;
  isRefreshingStatus: boolean;
  statusError: ParsedApiError | null;
  refresh: () => Promise<void>;
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfSchedulerStatusCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(SCHEDULER_STATUS_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchSchedulerStatus(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<SchedulerStatusResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfSchedulerStatusCancelled(args.signal, stillActive());
    const response = await systemConfigApi.getSchedulerStatus();
    throwIfSchedulerStatusCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfSchedulerStatusCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useSchedulerStatusQuery({
  enabled,
  refreshToken,
}: UseSchedulerStatusQueryOptions): UseSchedulerStatusQueryResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [status, setStatus] = useState<SchedulerStatusResponse | null>(null);
  const [isRefreshingStatus, setIsRefreshingStatus] = useState(false);
  const [statusError, setStatusError] = useState<ParsedApiError | null>(null);

  const requestIdRef = useRef(0);

  const discardExactSchedulerQuery = useCallback(() => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: SCHEDULER_STATUS_QUERY_KEY, exact: true },
      SCHEDULER_STATUS_CANCEL,
    );
    client.removeQueries({ queryKey: SCHEDULER_STATUS_QUERY_KEY, exact: true });
  }, []);

  const refresh = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;

    if (!enabled) {
      discardExactSchedulerQuery();
      setStatus(null);
      setStatusError(null);
      setIsRefreshingStatus(false);
      return;
    }

    setStatusError(null);
    setIsRefreshingStatus(true);

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactSchedulerQuery();

    try {
      const next = await queryClientRef.current.fetchQuery({
        queryKey: SCHEDULER_STATUS_QUERY_KEY,
        queryFn: ({ signal }) => fetchSchedulerStatus({
          signal,
          stillActive,
        }),
        ...SCHEDULER_STATUS_QUERY_SCHEDULE,
      });
      if (!stillActive()) return;
      setStatus(next);
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return;
      setStatusError(getParsedApiError(err));
    } finally {
      if (stillActive()) {
        setIsRefreshingStatus(false);
      }
    }
  }, [discardExactSchedulerQuery, enabled]);

  useEffect(() => {
    void refresh();
    return () => {
      requestIdRef.current += 1;
      discardExactSchedulerQuery();
    };
  }, [refresh, refreshToken, discardExactSchedulerQuery]);

  return {
    status,
    isRefreshingStatus,
    statusError,
    refresh,
  };
}
