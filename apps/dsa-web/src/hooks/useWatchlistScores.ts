// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useEffect, useMemo, useRef, useState } from 'react';
import { watchlistScoresApi } from '../api/watchlistScores';
import type { WatchlistScoreItem } from '../types/watchlistScore';

export type WatchlistScoreLoadStatus = 'idle' | 'loading' | 'ready' | 'error';

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
  const codesKey = JSON.stringify(stockCodes.map((code) => code.trim()).filter(Boolean));
  const requestSignature = `${codesKey}\n${String(refreshKey)}`;
  const requestIdRef = useRef(0);
  const [settledRequest, setSettledRequest] = useState<SettledScoreRequest | null>(null);

  useEffect(() => {
    const codes = JSON.parse(codesKey) as string[];
    if (codes.length === 0) return undefined;

    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const controller = new AbortController();
    void watchlistScoresApi.score({
      stockCodes: codes,
      sort: 'manual',
      signal: controller.signal,
    }).then((response) => {
      if (requestIdRef.current !== requestId) return;
      const requestedCodes = new Set(codes);
      const items = new Map<string, WatchlistScoreItem>();
      for (const item of response.items) {
        if (requestedCodes.has(item.stockCode)) items.set(item.stockCode, item);
      }
      setSettledRequest({ signature: requestSignature, status: 'ready', items });
    }).catch(() => {
      if (requestIdRef.current !== requestId) return;
      setSettledRequest({
        signature: requestSignature,
        status: 'error',
        items: new Map(),
      });
    });

    return () => {
      controller.abort();
      requestIdRef.current += 1;
    };
  }, [codesKey, requestSignature]);

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
