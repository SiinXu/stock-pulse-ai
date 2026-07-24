// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useEffect, useMemo, useState } from 'react';
import { historyApi } from '../api/history';
import type { StockBarItem, TaskInfo } from '../types/analysis';
import type { HomeWatchlistRow } from '../types/watchlist';
import { getShanghaiDateKey, getTodayInShanghai } from '../utils/format';
import { normalizeStockCode } from '../utils/stockCode';
import { toStockBarItemFromHistoryItem } from '../utils/stockBar';

type WatchlistHistoryLookupRequest = {
  entries: Array<[string, string]>;
  signature: string;
};

type WatchlistHistoryLookupState = {
  request: WatchlistHistoryLookupRequest | null;
  signature: string;
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

export function useWatchlistAnalysisCoverage({
  watchlistCodes,
  stockBarItems,
  isLoadingStockBar,
  isInitialStockBarLoadSettled,
  stockBarRefreshFailed,
  activeTasks,
}: UseWatchlistAnalysisCoverageOptions): WatchlistAnalysisCoverage {
  const [historyItemsByCode, setHistoryItemsByCode] = useState<Map<string, StockBarItem>>(
    () => new Map(),
  );
  const [historyLookup, setHistoryLookup] = useState<WatchlistHistoryLookupState>({
    request: null,
    signature: '',
    settledKeys: new Set(),
    failedKeys: new Set(),
  });
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

  useEffect(() => {
    if (!canLookupHistory || lookupRequest.entries.length === 0) return undefined;

    const missingKeys = lookupRequest.entries.map(([key]) => key);
    let active = true;
    void Promise.all(lookupRequest.entries.map(async ([key, code]) => {
      try {
        const response = await historyApi.getList({ stockCode: code, limit: 1 });
        return {
          key,
          item: response.items[0] ? toStockBarItemFromHistoryItem(response.items[0]) : null,
          failed: false,
        };
      } catch {
        return { key, item: null, failed: true };
      }
    })).then((results) => {
      if (!active) return;
      const nextItems = new Map<string, StockBarItem>();
      const failedKeys = new Set<string>();
      for (const result of results) {
        if (result.failed) failedKeys.add(result.key);
        else if (result.item) nextItems.set(result.key, result.item);
      }
      setHistoryItemsByCode(nextItems);
      setHistoryLookup({
        request: lookupRequest,
        signature: lookupRequest.signature,
        settledKeys: new Set(missingKeys),
        failedKeys,
      });
    });

    return () => {
      active = false;
    };
  }, [canLookupHistory, lookupRequest]);

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
    const isCurrentHistoryLookup = historyLookup.request === lookupRequest
      && historyLookup.signature === missingHistorySignature;
    const latestItem = key
      ? stockBarItemByCode.get(key)
        ?? (isCurrentHistoryLookup ? historyItemsByCode.get(key) : undefined)
      : undefined;
    const missingFromStockBar = Boolean(key && !stockBarItemByCode.has(key));
    const isTodayStatusUnknown = Boolean(
      stockBarRefreshFailed
      || (
        missingFromStockBar
        && canLookupHistory
        && isCurrentHistoryLookup
        && historyLookup.failedKeys.has(key)
      ),
    );
    const isTodayStatusLoading = Boolean(
      missingFromStockBar
      && !isTodayStatusUnknown
      && (
        !canLookupHistory
        || !isCurrentHistoryLookup
        || !historyLookup.settledKeys.has(key)
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
    historyItemsByCode,
    historyLookup,
    lookupRequest,
    missingHistorySignature,
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
