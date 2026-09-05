// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Home watchlist aggregate scores.
// Do not import this hook from Shell, App, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { watchlistScoresApi } from '../api/watchlistScores';
import type { WatchlistScoreItem, WatchlistScoreResponse } from '../types/watchlistScore';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const WATCHLIST_SCORES_CANCEL = { silent: true, revert: false } as const;

type WatchlistScoresQueryKey = readonly unknown[];

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

export function throwIfWatchlistScoresCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(WATCHLIST_SCORES_CANCEL);
  }
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
    if (error instanceof CancelledError) throw error;
    throwIfWatchlistScoresCancelled(args.signal, stillActive());
    throw error;
  }
}

/**
 * Load the current aggregate score projection for a bounded watchlist.
 *
 * `refreshKey` belongs to the caller's analysis/refresh lifecycle. A changed
 * canonical identity (`String(refreshKey)`) invalidates the previous result
 * immediately: display and sorting see an empty map until the matching request
 * succeeds, and a failed request never falls back to scores from an older
 * lifecycle generation. Number `1` and string `'1'` are one generation.
 * Reusing a prior signature (A→B→A or A→empty→A) starts a new generation and
 * must not read the earlier matching settled record.
 */
export function useWatchlistScores(
  stockCodes: readonly string[],
  refreshKey: string | number = '',
): UseWatchlistScoresResult {
  const queryClient = useQueryClient();
  const codesKey = JSON.stringify(stockCodes.map((code) => code.trim()).filter(Boolean));
  const refreshIdentity = String(refreshKey);
  const requestSignature = `${codesKey}\n${refreshIdentity}`;
  const [settledRequest, setSettledRequest] = useState<SettledScoreRequest | null>(null);
  const [seenSignature, setSeenSignature] = useState(requestSignature);
  const requestIdRef = useRef(0);
  const liveKeysRef = useRef<WatchlistScoresQueryKey[]>([]);

  if (seenSignature !== requestSignature) {
    setSeenSignature(requestSignature);
    setSettledRequest(null);
  }

  useEffect(() => {
    const discardLive = () => {
      for (const live of liveKeysRef.current) {
        void queryClient.cancelQueries(
          { queryKey: live, exact: true },
          WATCHLIST_SCORES_CANCEL,
        );
        queryClient.removeQueries({ queryKey: live, exact: true });
      }
      liveKeysRef.current = [];
    };
    const codes = JSON.parse(codesKey) as string[];
    if (codes.length === 0) {
      requestIdRef.current += 1;
      discardLive();
      return undefined;
    }

    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const key = buildWatchlistScoresQueryKey(codesKey, refreshIdentity);
    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardLive();
    liveKeysRef.current = [key];

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
        const requested = new Set(codes);
        const items = new Map<string, WatchlistScoreItem>();
        for (const item of response.items) {
          if (requested.has(item.stockCode)) items.set(item.stockCode, item);
        }
        setSettledRequest({ signature: requestSignature, status: 'ready', items });
      } catch (err) {
        if (requestIdRef.current !== requestId || err instanceof CancelledError) return;
        setSettledRequest({
          signature: requestSignature,
          status: 'error',
          items: new Map(),
        });
      }
    })();

    return () => {
      requestIdRef.current += 1;
      discardLive();
    };
  }, [codesKey, requestSignature, refreshIdentity, queryClient]);

  return useMemo(() => {
    const codes = JSON.parse(codesKey) as string[];
    if (codes.length === 0) {
      return { status: 'idle' as const, itemsByCode: new Map() };
    }
    if (!settledRequest || settledRequest.signature !== requestSignature) {
      return { status: 'loading' as const, itemsByCode: new Map() };
    }
    return {
      status: settledRequest.status,
      itemsByCode: settledRequest.items,
    };
  }, [codesKey, requestSignature, settledRequest]);
}

export default useWatchlistScores;
