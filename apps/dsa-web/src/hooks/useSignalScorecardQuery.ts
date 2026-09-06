// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings Signal Scorecard public preview GET.
// Do not import this hook from Shell, App, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { scorecardApi } from '../api/scorecard';
import type { SignalScorecardResponse } from '../types/scorecard';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const SCORECARD_CANCEL = { silent: true, revert: false } as const;

/** Readonly two-element key. Never prefix-cancel or prefix-remove `['scorecard']`. */
export const SCORECARD_PUBLIC_QUERY_KEY = ['scorecard', 'public'] as const;

/** Previous panel effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const SCORECARD_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type SignalScorecardLoadMode = 'initial' | 'refresh';

export type UseSignalScorecardQueryResult = {
  data: SignalScorecardResponse | null;
  isLoading: boolean;
  isRefreshing: boolean;
  loadError: ParsedApiError | null;
  load: (mode?: SignalScorecardLoadMode) => Promise<void>;
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfScorecardCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(SCORECARD_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchPublicScorecard(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<SignalScorecardResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfScorecardCancelled(args.signal, stillActive());
    const response = await scorecardApi.getPublic();
    throwIfScorecardCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfScorecardCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useSignalScorecardQuery(
  publicEnabled: boolean,
): UseSignalScorecardQueryResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [data, setData] = useState<SignalScorecardResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);

  const requestIdRef = useRef(0);

  const discardExactPublicQuery = useCallback(() => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: SCORECARD_PUBLIC_QUERY_KEY, exact: true },
      SCORECARD_CANCEL,
    );
    client.removeQueries({ queryKey: SCORECARD_PUBLIC_QUERY_KEY, exact: true });
  }, []);

  const load = useCallback(async (mode: SignalScorecardLoadMode = 'initial') => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;

    if (!publicEnabled) {
      discardExactPublicQuery();
      setData(null);
      setLoadError(null);
      setIsLoading(false);
      setIsRefreshing(false);
      return;
    }

    setLoadError(null);
    if (mode === 'initial') {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactPublicQuery();

    try {
      const next = await queryClientRef.current.fetchQuery({
        queryKey: SCORECARD_PUBLIC_QUERY_KEY,
        queryFn: ({ signal }) => fetchPublicScorecard({
          signal,
          stillActive,
        }),
        ...SCORECARD_QUERY_SCHEDULE,
      });
      if (!stillActive()) return;
      setData(next);
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return;
      setData(null);
      setLoadError(getParsedApiError(err));
    } finally {
      if (stillActive()) {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    }
  }, [discardExactPublicQuery, publicEnabled]);

  useEffect(() => {
    void load('initial');
    return () => {
      requestIdRef.current += 1;
      discardExactPublicQuery();
    };
  }, [load, discardExactPublicQuery]);

  return {
    data,
    isLoading,
    isRefreshing,
    loadError,
    load,
  };
}
