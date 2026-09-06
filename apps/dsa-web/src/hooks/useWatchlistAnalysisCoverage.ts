// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Research Analysis Workbench watchlist
// coverage fallback history lookups. Do not import this hook from Shell, App,
// first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { historyApi } from '../api/history';
import type { StockBarItem, TaskInfo } from '../types/analysis';
import type { HomeWatchlistRow } from '../types/watchlist';
import { getShanghaiDateKey, getTodayInShanghai } from '../utils/format';
import { normalizeStockCode } from '../utils/stockCode';
import { toStockBarItemFromHistoryItem } from '../utils/stockBar';

/** Upstream `ae19329d6` HomePage bound: at most four in-flight fallback `getList` calls. */
export const WATCHLIST_HISTORY_LOOKUP_CONCURRENCY = 4;

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const WATCHLIST_COVERAGE_CANCEL = { silent: true, revert: false } as const;

type WatchlistCoverageQueryKey = readonly unknown[];

export const WATCHLIST_COVERAGE_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

type WatchlistHistoryLookupRequest = {
  entries: Array<[string, string]>;
  signature: string;
};

type SettledCoverageLookup = {
  request: WatchlistHistoryLookupRequest;
  signature: string;
  items: ReadonlyMap<string, StockBarItem>;
  settledKeys: Set<string>;
  failedKeys: Set<string>;
};

type UseWatchlistAnalysisCoverageOptions = {
  watchlistCodes: readonly string[];
  stockBarItems: readonly StockBarItem[];
  isLoadingStockBar: boolean;
  isInitialStockBarLoadSettled: boolean;
  stockBarRefreshFailed: boolean;
  activeTasks: readonly TaskInfo[];
};

export type WatchlistAnalysisCoverage = {
  rows: HomeWatchlistRow[];
  analyzedTodayCount: number;
  pendingCodes: string[];
  isTodayStatusBlocked: boolean;
};

function getStockCodeKey(code?: string | null): string {
  const trimmed = (code ?? '').trim();
  return trimmed ? normalizeStockCode(trimmed).toUpperCase() : '';
}

function isAbortError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const name = 'name' in error ? String(error.name) : '';
  const code = 'code' in error ? String(error.code) : '';
  return name === 'AbortError' || name === 'CanceledError' || code === 'ERR_CANCELED';
}

export function buildWatchlistCoverageQueryKey(signature: string): WatchlistCoverageQueryKey {
  return ['watchlist', 'coverage', 'history', signature] as const;
}

export function throwIfWatchlistCoverageCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(WATCHLIST_COVERAGE_CANCEL);
  }
}

type WatchlistHistoryLookupResult = {
  key: string;
  item: StockBarItem | null;
  failed: boolean;
};

async function lookupWatchlistHistory(
  entries: Array<[string, string]>,
  isCanceled: () => boolean,
  signal: AbortSignal,
): Promise<WatchlistHistoryLookupResult[]> {
  const results: Array<WatchlistHistoryLookupResult | undefined> = new Array(entries.length);
  let nextIndex = 0;

  const runWorker = async () => {
    while (!isCanceled() && !signal.aborted) {
      const index = nextIndex;
      if (index >= entries.length) {
        return;
      }
      nextIndex += 1;
      const [key, code] = entries[index];
      try {
        throwIfWatchlistCoverageCancelled(signal, !isCanceled());
        const response = await historyApi.getList(
          { stockCode: code, limit: 1 },
          { signal },
        );
        throwIfWatchlistCoverageCancelled(signal, !isCanceled());
        results[index] = {
          key,
          item: response.items[0] ? toStockBarItemFromHistoryItem(response.items[0]) : null,
          failed: false,
        };
      } catch (error) {
        if (error instanceof CancelledError) throw error;
        throwIfWatchlistCoverageCancelled(signal, !isCanceled());
        if (isAbortError(error)) {
          throw new CancelledError(WATCHLIST_COVERAGE_CANCEL);
        }
        results[index] = { key, item: null, failed: true };
      }
    }
  };

  const workerCount = Math.min(WATCHLIST_HISTORY_LOOKUP_CONCURRENCY, entries.length);
  await Promise.all(Array.from({ length: workerCount }, () => runWorker()));
  throwIfWatchlistCoverageCancelled(signal, !isCanceled());
  return results.filter((entry): entry is WatchlistHistoryLookupResult => entry !== undefined);
}

export function useWatchlistAnalysisCoverage({
  watchlistCodes,
  stockBarItems,
  isLoadingStockBar,
  isInitialStockBarLoadSettled,
  stockBarRefreshFailed,
  activeTasks,
}: UseWatchlistAnalysisCoverageOptions): WatchlistAnalysisCoverage {
  const queryClient = useQueryClient();
  const [settledLookup, setSettledLookup] = useState<SettledCoverageLookup | null>(null);
  const requestIdRef = useRef(0);
  const liveKeysRef = useRef<WatchlistCoverageQueryKey[]>([]);
  const codesByNormalized = useMemo(() => {
    const result = new Map<string, string>();
    for (const code of watchlistCodes) {
      const key = getStockCodeKey(code);
      if (!key || key === 'MARKET' || result.has(key)) continue;
      result.set(key, code);
    }
    return Array.from(result.entries());
  }, [watchlistCodes]);

  const stockBarItemByCode = useMemo(() => {
    const result = new Map<string, StockBarItem>();
    for (const item of stockBarItems) {
      if (item.stockCode === 'MARKET') continue;
      const key = getStockCodeKey(item.stockCode);
      if (key) result.set(key, item);
    }
    return result;
  }, [stockBarItems]);

  const canLookupHistory = !isLoadingStockBar && isInitialStockBarLoadSettled;
  const missingHistoryEntries = useMemo(
    () => canLookupHistory
      ? codesByNormalized.filter(([key]) => !stockBarItemByCode.has(key))
      : [],
    [canLookupHistory, codesByNormalized, stockBarItemByCode],
  );
  const missingHistorySignature = useMemo(
    () => missingHistoryEntries.map(([key]) => key).join('\n'),
    [missingHistoryEntries],
  );
  const lookupRequest = useMemo<WatchlistHistoryLookupRequest>(() => ({
    entries: missingHistoryEntries,
    signature: missingHistorySignature,
  }), [missingHistoryEntries, missingHistorySignature]);
  const [seenSignature, setSeenSignature] = useState(missingHistorySignature);

  if (seenSignature !== missingHistorySignature) {
    setSeenSignature(missingHistorySignature);
    setSettledLookup(null);
  }

  useEffect(() => {
    const discardLive = () => {
      for (const live of liveKeysRef.current) {
        void queryClient.cancelQueries(
          { queryKey: live, exact: true },
          WATCHLIST_COVERAGE_CANCEL,
        );
        queryClient.removeQueries({ queryKey: live, exact: true });
      }
      liveKeysRef.current = [];
    };

    if (!canLookupHistory || lookupRequest.entries.length === 0) {
      requestIdRef.current += 1;
      discardLive();
      return undefined;
    }

    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const request = lookupRequest;
    const key = buildWatchlistCoverageQueryKey(request.signature);
    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardLive();
    liveKeysRef.current = [key];

    void (async () => {
      try {
        const results = await queryClient.fetchQuery({
          queryKey: key,
          queryFn: ({ signal }) => lookupWatchlistHistory(
            request.entries,
            () => requestIdRef.current !== requestId,
            signal,
          ),
          ...WATCHLIST_COVERAGE_QUERY_SCHEDULE,
        });
        if (requestIdRef.current !== requestId) return;
        const nextItems = new Map<string, StockBarItem>();
        const failedKeys = new Set<string>();
        for (const result of results) {
          if (result.failed) failedKeys.add(result.key);
          else if (result.item) nextItems.set(result.key, result.item);
        }
        setSettledLookup({
          request,
          signature: request.signature,
          items: nextItems,
          settledKeys: new Set(request.entries.map(([entryKey]) => entryKey)),
          failedKeys,
        });
      } catch (err) {
        if (requestIdRef.current !== requestId || err instanceof CancelledError || isAbortError(err)) {
          return;
        }
      }
    })();

    return () => {
      requestIdRef.current += 1;
      discardLive();
    };
  }, [canLookupHistory, lookupRequest, missingHistorySignature, queryClient]);

  const activeTaskByCode = useMemo(() => {
    const result = new Map<string, TaskInfo>();
    for (const task of activeTasks) {
      if (!['pending', 'processing', 'cancel_requested'].includes(task.status)) continue;
      if (task.reportType === 'market_review') continue;
      const key = getStockCodeKey(task.stockCode);
      if (key) result.set(key, task);
    }
    return result;
  }, [activeTasks]);

  const todayDateKey = getTodayInShanghai();
  const rows = useMemo<HomeWatchlistRow[]>(() => watchlistCodes.map((code) => {
    const key = getStockCodeKey(code);
    const isCurrentHistoryLookup = Boolean(
      settledLookup
      && settledLookup.request === lookupRequest
      && settledLookup.signature === missingHistorySignature
    );
    const latestItem = key
      ? stockBarItemByCode.get(key)
        ?? (isCurrentHistoryLookup ? settledLookup?.items.get(key) : undefined)
      : undefined;
    const missingFromStockBar = Boolean(key && !stockBarItemByCode.has(key));
    const isTodayStatusUnknown = Boolean(
      stockBarRefreshFailed
      || (
        missingFromStockBar
        && canLookupHistory
        && isCurrentHistoryLookup
        && settledLookup?.failedKeys.has(key)
      ),
    );
    const isTodayStatusLoading = Boolean(
      missingFromStockBar
      && !isTodayStatusUnknown
      && (
        !canLookupHistory
        || !isCurrentHistoryLookup
        || !settledLookup?.settledKeys.has(key)
      ),
    );
    return {
      code,
      latestItem,
      analyzedToday: (
        !isTodayStatusLoading
        && !isTodayStatusUnknown
        && getShanghaiDateKey(latestItem?.lastAnalysisTime) === todayDateKey
      ),
      isTodayStatusLoading,
      isTodayStatusUnknown,
      activeTask: key ? activeTaskByCode.get(key) : undefined,
    };
  }), [
    activeTaskByCode,
    canLookupHistory,
    lookupRequest,
    missingHistorySignature,
    settledLookup,
    stockBarItemByCode,
    stockBarRefreshFailed,
    todayDateKey,
    watchlistCodes,
  ]);

  return useMemo(() => ({
    rows,
    analyzedTodayCount: rows.filter((row) => row.analyzedToday).length,
    pendingCodes: rows
      .filter((row) => !row.analyzedToday && !row.isTodayStatusLoading && !row.isTodayStatusUnknown)
      .map((row) => row.code),
    isTodayStatusBlocked: rows.some((row) => row.isTodayStatusLoading || row.isTodayStatusUnknown),
  }), [rows]);
}

export default useWatchlistAnalysisCoverage;
