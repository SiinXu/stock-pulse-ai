// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { watchlistScoresApi } from '../api/watchlistScores';
import type { WatchlistScoreItem } from '../types/watchlistScore';
import type { UseWatchlistScoresResult, WatchlistScoreLoadStatus } from './useWatchlistScores';

type SettledScoreRequest = {
  signature: string;
  retryNonce: number;
  status: 'ready' | 'error';
  items: ReadonlyMap<string, WatchlistScoreItem>;
};

export type UseWatchlistScoreSessionResult = UseWatchlistScoresResult & {
  status: WatchlistScoreLoadStatus;
  stale: boolean;
  retry: () => void;
};

function isAbortError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const name = 'name' in error ? String(error.name) : '';
  const code = 'code' in error ? String(error.code) : '';
  return name === 'AbortError' || name === 'CanceledError' || code === 'ERR_CANCELED';
}

/**
 * Same contract as useWatchlistScores, plus same-signature retry.
 * Last-known ready items stay visible only while that retry is in flight
 * and marked stale. A failed retry is error with an empty map.
 */
export function useWatchlistScoreSession(
  stockCodes: readonly string[],
  refreshKey: string | number = '',
): UseWatchlistScoreSessionResult {
  const codesKey = JSON.stringify(stockCodes.map((code) => code.trim()).filter(Boolean));
  const requestSignature = `${codesKey}\n${String(refreshKey)}`;
  const requestIdRef = useRef(0);
  const [retryNonce, setRetryNonce] = useState(0);
  const [settledRequest, setSettledRequest] = useState<SettledScoreRequest | null>(null);

  const retry = useCallback(() => {
    setRetryNonce((nonce) => nonce + 1);
  }, []);

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
      setSettledRequest({
        signature: requestSignature,
        retryNonce,
        status: 'ready',
        items,
      });
    }).catch((error: unknown) => {
      if (requestIdRef.current !== requestId) return;
      if (controller.signal.aborted || isAbortError(error)) return;
      setSettledRequest({
        signature: requestSignature,
        retryNonce,
        status: 'error',
        items: new Map(),
      });
    });

    return () => {
      controller.abort();
      requestIdRef.current += 1;
    };
  }, [codesKey, requestSignature, retryNonce]);

  return useMemo(() => {
    const codes = JSON.parse(codesKey) as string[];
    if (codes.length === 0) {
      return { status: 'idle' as const, itemsByCode: new Map(), stale: false, retry };
    }
    if (!settledRequest || settledRequest.signature !== requestSignature) {
      return { status: 'loading' as const, itemsByCode: new Map(), stale: false, retry };
    }
    if (retryNonce !== settledRequest.retryNonce) {
      const keepLastKnown = settledRequest.status === 'ready';
      return {
        status: 'retrying' as const,
        itemsByCode: keepLastKnown ? settledRequest.items : new Map(),
        stale: keepLastKnown,
        retry,
      };
    }
    return {
      status: settledRequest.status,
      itemsByCode: settledRequest.items,
      stale: false,
      retry,
    };
  }, [codesKey, requestSignature, retry, retryNonce, settledRequest]);
}

export default useWatchlistScoreSession;
