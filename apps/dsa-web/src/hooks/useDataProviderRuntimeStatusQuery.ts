// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings data-provider runtime status GET.
// Do not import this hook from Shell, App, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { systemConfigApi } from '../api/systemConfig';
import type { DataProviderRuntimeStatusResponse } from '../types/systemConfig';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const DATA_PROVIDER_RUNTIME_CANCEL = { silent: true, revert: false } as const;

/** Readonly two-element key. Never prefix-cancel or prefix-remove `['data-providers']`. */
export const DATA_PROVIDER_RUNTIME_STATUS_QUERY_KEY = ['data-providers', 'runtime-status'] as const;

/** Previous panel effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const DATA_PROVIDER_RUNTIME_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type UseDataProviderRuntimeStatusQueryResult = {
  status: DataProviderRuntimeStatusResponse | null;
  isLoading: boolean;
  error: ParsedApiError | null;
  refresh: () => Promise<void>;
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfDataProviderRuntimeCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(DATA_PROVIDER_RUNTIME_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchDataProviderRuntimeStatus(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<DataProviderRuntimeStatusResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfDataProviderRuntimeCancelled(args.signal, stillActive());
    const response = await systemConfigApi.getDataProviderRuntimeStatus();
    throwIfDataProviderRuntimeCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfDataProviderRuntimeCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useDataProviderRuntimeStatusQuery(): UseDataProviderRuntimeStatusQueryResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [status, setStatus] = useState<DataProviderRuntimeStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);

  const requestIdRef = useRef(0);

  const discardExactRuntimeQuery = useCallback(() => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: DATA_PROVIDER_RUNTIME_STATUS_QUERY_KEY, exact: true },
      DATA_PROVIDER_RUNTIME_CANCEL,
    );
    client.removeQueries({ queryKey: DATA_PROVIDER_RUNTIME_STATUS_QUERY_KEY, exact: true });
  }, []);

  const refresh = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;

    setIsLoading(true);
    setError(null);

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactRuntimeQuery();

    try {
      const next = await queryClientRef.current.fetchQuery({
        queryKey: DATA_PROVIDER_RUNTIME_STATUS_QUERY_KEY,
        queryFn: ({ signal }) => fetchDataProviderRuntimeStatus({
          signal,
          stillActive,
        }),
        ...DATA_PROVIDER_RUNTIME_QUERY_SCHEDULE,
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
  }, [discardExactRuntimeQuery]);

  useEffect(() => {
    void refresh();
    return () => {
      requestIdRef.current += 1;
      discardExactRuntimeQuery();
    };
  }, [refresh, discardExactRuntimeQuery]);

  return {
    status,
    isLoading,
    error,
    refresh,
  };
}
