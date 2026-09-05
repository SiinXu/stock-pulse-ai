// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Home watchlist aggregate scores.
// Do not import this hook from Shell, App, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { watchlistScoresApi } from '../api/watchlistScores';
import type { WatchlistScoreItem, WatchlistScoreResponse } from '../types/watchlistScore';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const WATCHLIST_SCORES_CANCEL = { silent: true, revert: false } as const;

export const WATCHLIST_SCORES_QUERY_KEY_ROOT = ['watchlist', 'scores'] as const;

/** Readonly query-key tuple. `readonly unknown[][]` is ReadonlyArray<unknown[]>, not this. */
type WatchlistScoresQueryKey = readonly unknown[];

/** Previous effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const WATCHLIST_SCORES_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type WatchlistScoreLoadStatus = 'idle' | 'loading' | 'retrying' | 'ready' | 'error';

type SettledScoreRequest = {
  signature: string;
  status: 'ready' | 'error';
  items: ReadonlyMap<string, WatchlistScoreItem>;
};

export type UseWatchlistScoresResult = {
  status: WatchlistScoreLoadStatus;
  itemsByCode: ReadonlyMap<string, WatchlistScoreItem>;
};

export function createUnanalyzedWatchlistScore(stockCode: string): WatchlistScoreItem {
  return {
    stockCode,
    status: 'unanalyzed',
    score: null,
    asOf: null,
    ageDays: null,
    analysisId: null,
    operationAdvice: null,
    factors: [],
    freshness: 'none',
    degradedReasons: [],
  };
}

export function buildWatchlistScoresQueryKey(
  codesKey: string,
  refreshKey: string | number,
): WatchlistScoresQueryKey {
  return ['watchlist', 'scores', codesKey, String(refreshKey)] as const;
}

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfWatchlistScoresCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(WATCHLIST_SCORES_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

function sameQueryKey(
  left: WatchlistScoresQueryKey,
  right: WatchlistScoresQueryKey,
): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function filterRequestedItems(
  codes: readonly string[],
  response: WatchlistScoreResponse,
): Map<string, WatchlistScoreItem> {
  const requestedCodes = new Set(codes);
  const items = new Map<string, WatchlistScoreItem>();
  for (const item of response.items) {
    if (requestedCodes.has(item.stockCode)) items.set(item.stockCode, item);
  }
  return items;
}

export async function fetchWatchlistScores(args: {
  stockCodes: string[];
  signal?: AbortSignal;
  stillActive?: () => boolean;
}): Promise<WatchlistScoreResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfWatchlistScoresCancelled(args.signal, stillActive());
    const response = await watchlistScoresApi.score({
      stockCodes: args.stockCodes,
      sort: 'manual',
      signal: args.signal,
    });
    throwIfWatchlistScoresCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfWatchlistScoresCancelled(args.signal, stillActive());
    throw error;
  }
}

/**
 * Load the current aggregate score projection for a bounded watchlist.
 *
 * `refreshKey` belongs to the caller's analysis/refresh lifecycle. A changed
 * key invalidates the previous result immediately: display and sorting see an
 * empty map until the matching request succeeds, and a failed request never
 * falls back to scores from an older lifecycle generation.
 */
export function useWatchlistScores(
  stockCodes: readonly string[],
  refreshKey: string | number = '',
): UseWatchlistScoresResult {
  const queryClient = useQueryClient();

  const codesKey = JSON.stringify(stockCodes.map((code) => code.trim()).filter(Boolean));
  const requestSignature = `${codesKey}\n${String(refreshKey)}`;
  const [settledRequest, setSettledRequest] = useState<SettledScoreRequest | null>(null);

  const requestIdRef = useRef(0);
  const liveKeysRef = useRef<WatchlistScoresQueryKey[]>([]);

  const discardExactQuery = useCallback((key: WatchlistScoresQueryKey) => {
    void queryClient.cancelQueries(
      { queryKey: key, exact: true },
      WATCHLIST_SCORES_CANCEL,
    );
    queryClient.removeQueries({ queryKey: key, exact: true });
    liveKeysRef.current = liveKeysRef.current.filter((live) => !sameQueryKey(live, key));
  }, [queryClient]);

  const discardLiveKeys = useCallback((
    predicate: (key: WatchlistScoresQueryKey) => boolean,
  ) => {
    for (const live of [...liveKeysRef.current]) {
      if (predicate(live)) discardExactQuery(live);
    }
  }, [discardExactQuery]);

  useEffect(() => {
    const codes = JSON.parse(codesKey) as string[];
    if (codes.length === 0) {
      requestIdRef.current += 1;
      discardLiveKeys(() => true);
      return undefined;
    }

    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const key = buildWatchlistScoresQueryKey(codesKey, refreshKey);

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    // Key change also exact-removes the abandoned scores key.
    discardLiveKeys(() => true);
    liveKeysRef.current = [...liveKeysRef.current, key];

    void (async () => {
      try {
        const response = await queryClient.fetchQuery({
          queryKey: key,
          queryFn: ({ signal }) => fetchWatchlistScores({
            stockCodes: codes,
            signal,
            stillActive: () => requestIdRef.current === requestId,
          }),
          ...WATCHLIST_SCORES_QUERY_SCHEDULE,
        });
        if (requestIdRef.current !== requestId) return;
        setSettledRequest({
          signature: requestSignature,
          status: 'ready',
          items: filterRequestedItems(codes, response),
        });
      } catch (err) {
        if (requestIdRef.current !== requestId || isCancelledError(err)) return;
        setSettledRequest({
          signature: requestSignature,
          status: 'error',
          items: new Map(),
        });
      }
    })();

    return () => {
      requestIdRef.current += 1;
      discardLiveKeys(() => true);
    };
  }, [codesKey, requestSignature, refreshKey, discardLiveKeys, queryClient]);

  return useMemo(() => {
    const codes = JSON.parse(codesKey) as string[];
    if (codes.length === 0) {
      return { status: 'idle', itemsByCode: new Map() };
    }
    if (!settledRequest || settledRequest.signature !== requestSignature) {
      return { status: 'loading', itemsByCode: new Map() };
    }
    return {
      status: settledRequest.status,
      itemsByCode: settledRequest.items,
    };
  }, [codesKey, requestSignature, settledRequest]);
}

export default useWatchlistScores;
