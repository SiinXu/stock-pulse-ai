// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings Kronos status GET.
// Do not import this hook from Shell, App, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { systemConfigApi } from '../api/systemConfig';
import type { KronosStatusResponse } from '../types/systemConfig';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const KRONOS_STATUS_CANCEL = { silent: true, revert: false } as const;

/** Readonly two-element key. Never prefix-cancel or prefix-remove `['kronos']`. */
export const KRONOS_STATUS_QUERY_KEY = ['kronos', 'status'] as const;

/** Previous panel effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const KRONOS_STATUS_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type UseKronosStatusQueryResult = {
  status: KronosStatusResponse | null;
  isLoading: boolean;
  error: ParsedApiError | null;
  refresh: () => Promise<void>;
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfKronosStatusCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(KRONOS_STATUS_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchKronosStatus(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<KronosStatusResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfKronosStatusCancelled(args.signal, stillActive());
    const response = await systemConfigApi.getKronosStatus();
    throwIfKronosStatusCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfKronosStatusCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useKronosStatusQuery(): UseKronosStatusQueryResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [status, setStatus] = useState<KronosStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);

  const requestIdRef = useRef(0);

  const discardExactKronosQuery = useCallback(() => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: KRONOS_STATUS_QUERY_KEY, exact: true },
      KRONOS_STATUS_CANCEL,
    );
    client.removeQueries({ queryKey: KRONOS_STATUS_QUERY_KEY, exact: true });
  }, []);

  const refresh = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;

    setIsLoading(true);
    setError(null);

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactKronosQuery();

    try {
      const next = await queryClientRef.current.fetchQuery({
        queryKey: KRONOS_STATUS_QUERY_KEY,
        queryFn: ({ signal }) => fetchKronosStatus({
          signal,
          stillActive,
        }),
        ...KRONOS_STATUS_QUERY_SCHEDULE,
      });
      if (!stillActive()) return;
      setStatus(next);
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return;
      setStatus(null);
      setError(getParsedApiError(err));
    } finally {
      if (stillActive()) {
        setIsLoading(false);
      }
    }
  }, [discardExactKronosQuery]);

  useEffect(() => {
    void refresh();
    return () => {
      requestIdRef.current += 1;
      discardExactKronosQuery();
    };
  }, [refresh, discardExactKronosQuery]);

  return {
    status,
    isLoading,
    error,
    refresh,
  };
}
