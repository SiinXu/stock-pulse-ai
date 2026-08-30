// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Token Usage dashboard loads.
// Do not import this hook from Shell, App, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { usageApi, type UsageDashboard, type UsagePeriod } from '../api/usage';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const TOKEN_USAGE_CANCEL = { silent: true, revert: false } as const;

export const TOKEN_USAGE_DASHBOARD_QUERY_KEY_ROOT = ['usage', 'dashboard'] as const;

export const TOKEN_USAGE_DASHBOARD_LIMIT = 50;

/** Readonly query-key tuple. `readonly unknown[][]` is ReadonlyArray<unknown[]>, not this. */
type TokenUsageDashboardQueryKey = readonly unknown[];

type UsageDashboardSnapshot = { period: UsagePeriod; dashboard: UsageDashboard };

/** Previous page effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const TOKEN_USAGE_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type UseTokenUsageQueryResult = {
  dashboard: UsageDashboard | null;
  loading: boolean;
  error: unknown | null;
  load: () => Promise<void>;
};

export function buildTokenUsageDashboardQueryKey(
  period: UsagePeriod,
): TokenUsageDashboardQueryKey {
  return ['usage', 'dashboard', period] as const;
}

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfTokenUsageCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(TOKEN_USAGE_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

function sameQueryKey(
  left: TokenUsageDashboardQueryKey,
  right: TokenUsageDashboardQueryKey,
): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

export async function fetchTokenUsageDashboard(args: {
  period: UsagePeriod;
  signal?: AbortSignal;
  stillActive?: () => boolean;
}): Promise<UsageDashboard> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfTokenUsageCancelled(args.signal, stillActive());
    const response = await usageApi.getDashboard({
      period: args.period,
      limit: TOKEN_USAGE_DASHBOARD_LIMIT,
    });
    throwIfTokenUsageCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfTokenUsageCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useTokenUsageQuery(period: UsagePeriod): UseTokenUsageQueryResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [snapshot, setSnapshot] = useState<UsageDashboardSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown | null>(null);

  const requestIdRef = useRef(0);
  const periodRef = useRef(period);
  const liveKeysRef = useRef<TokenUsageDashboardQueryKey[]>([]);
  periodRef.current = period;

  const discardExactQuery = useCallback((key: TokenUsageDashboardQueryKey) => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: key, exact: true },
      TOKEN_USAGE_CANCEL,
    );
    client.removeQueries({ queryKey: key, exact: true });
    liveKeysRef.current = liveKeysRef.current.filter((live) => !sameQueryKey(live, key));
  }, []);

  const discardLiveKeys = useCallback((
    predicate: (key: TokenUsageDashboardQueryKey) => boolean,
  ) => {
    for (const live of [...liveKeysRef.current]) {
      if (predicate(live)) discardExactQuery(live);
    }
  }, [discardExactQuery]);

  const load = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const periodAtStart = periodRef.current;
    const key = buildTokenUsageDashboardQueryKey(periodAtStart);

    setLoading(true);
    setError(null);

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    // Period-key change also exact-removes the abandoned period key.
    discardLiveKeys(() => true);
    liveKeysRef.current = [...liveKeysRef.current, key];

    try {
      const response = await queryClientRef.current.fetchQuery({
        queryKey: key,
        queryFn: ({ signal }) => fetchTokenUsageDashboard({
          period: periodAtStart,
          signal,
          stillActive: () => requestIdRef.current === requestId,
        }),
        ...TOKEN_USAGE_QUERY_SCHEDULE,
      });
      if (requestIdRef.current !== requestId) return;
      setSnapshot({ period: periodAtStart, dashboard: response });
    } catch (err) {
      if (requestIdRef.current !== requestId || isCancelledError(err)) return;
      setError(err);
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  }, [discardLiveKeys]);

  useLayoutEffect(() => {
    setLoading(true);
    setError(null);
  }, [period]);

  useEffect(() => {
    void load();
    return () => {
      requestIdRef.current += 1;
      discardLiveKeys(() => true);
    };
  }, [load, period, discardLiveKeys]);

  return {
    dashboard: snapshot?.period === period ? snapshot.dashboard : null,
    loading,
    error,
    load,
  };
}
