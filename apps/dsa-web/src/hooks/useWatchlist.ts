// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { systemConfigApi } from '../api/systemConfig';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { findMatchingStockCode, includesStockCode } from '../utils/stockCode';

export interface UseWatchlistReturn {
  watchlistCodes: string[];
  isLoading: boolean;
  isActioning: boolean;
  loadError: ParsedApiError | null;
  actionMessage: string | null;
  isInWatchlist: (stockCode: string) => boolean;
  addToWatchlist: (stockCode: string) => Promise<boolean>;
  removeFromWatchlist: (stockCode: string) => Promise<boolean>;
  toggleWatchlist: (stockCode: string) => Promise<boolean>;
  refresh: () => Promise<boolean>;
}

export interface UseWatchlistOptions {
  enabled?: boolean;
}

/** Exact-key cancellation must settle fetchStatus and restore the pre-fetch state. */
export const WATCHLIST_CANCEL = { silent: false, revert: true } as const;

/** Shared GET identity for Home, Workbench, and Decision Signals observers. */
export const WATCHLIST_QUERY_KEY = ['watchlist', 'codes'] as const;

/** Previous hook never retried, never polled, never focus-refetched, and always called axios offline. */
export const WATCHLIST_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

/**
 * Query cancellation owns stale-result rejection. The axios adapter currently
 * cannot consume Query's AbortSignal, so the shared query function must not
 * translate abort, observer lifetime, or hook generation into a silent
 * CancelledError. Doing so bypasses Query's settlement dispatch and can leave
 * a live successor observer attached to `fetchStatus: fetching` forever.
 */
export async function fetchWatchlistCodes(): Promise<string[]> {
  return systemConfigApi.getWatchlist();
}

export function useWatchlist({ enabled = true }: UseWatchlistOptions = {}): UseWatchlistReturn {
  const { t } = useUiLanguage();
  const queryClient = useQueryClient();
  const [isActioning, setIsActioning] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const messageTimerRef = useRef<number | null>(null);
  const mountedRef = useRef(true);

  const query = useQuery({
    queryKey: WATCHLIST_QUERY_KEY,
    queryFn: fetchWatchlistCodes,
    enabled,
    ...WATCHLIST_QUERY_SCHEDULE,
  });

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (messageTimerRef.current !== null) {
        window.clearTimeout(messageTimerRef.current);
      }
      const client = queryClient;
      queueMicrotask(() => {
        if (mountedRef.current) return;
        const remaining = client.getQueryCache()
          .find({ queryKey: WATCHLIST_QUERY_KEY, exact: true })
          ?.getObserversCount() ?? 0;
        if (remaining > 0) return;
        void client.cancelQueries(
          { queryKey: WATCHLIST_QUERY_KEY, exact: true },
          WATCHLIST_CANCEL,
        );
        client.removeQueries({ queryKey: WATCHLIST_QUERY_KEY, exact: true });
      });
    };
  }, [queryClient]);

  // Disable must cancel the exact in-flight GET so a later re-enable starts a
  // new request. Do not removeQueries here: other live observers share this
  // key. Last-observer unmount discards the row after a microtask instead.
  useEffect(() => {
    if (enabled) {
      return undefined;
    }
    void queryClient.cancelQueries(
      { queryKey: WATCHLIST_QUERY_KEY, exact: true },
      WATCHLIST_CANCEL,
    );
    return undefined;
  }, [enabled, queryClient]);

  const refresh = useCallback(async () => {
    try {
      await queryClient.fetchQuery({
        queryKey: WATCHLIST_QUERY_KEY,
        queryFn: fetchWatchlistCodes,
        ...WATCHLIST_QUERY_SCHEDULE,
      });
      return true;
    } catch (error) {
      if (isCancelledError(error)) {
        return false;
      }
      return false;
    }
  }, [queryClient]);

  const showMessage = useCallback((msg: string) => {
    if (messageTimerRef.current !== null) {
      window.clearTimeout(messageTimerRef.current);
    }
    setActionMessage(msg);
    messageTimerRef.current = window.setTimeout(() => {
      if (mountedRef.current) {
        setActionMessage(null);
      }
    }, 3000);
  }, []);

  const codes = useMemo(() => query.data ?? [], [query.data]);
  // Only the current initial GET blocks consumers. A settled empty list is
  // usable data, and a background remount/refresh must not disable the UI.
  const isLoading = enabled && query.data === undefined && query.isFetching;
  const loadError = query.error && !isCancelledError(query.error)
    ? getParsedApiError(query.error)
    : null;

  const isInWatchlist = useCallback(
    (stockCode: string) => includesStockCode(codes, stockCode),
    [codes],
  );

  const applyMutationResult = useCallback((result: string[]) => {
    void queryClient.cancelQueries(
      { queryKey: WATCHLIST_QUERY_KEY, exact: true },
      WATCHLIST_CANCEL,
    );
    queryClient.setQueryData(WATCHLIST_QUERY_KEY, result);
  }, [queryClient]);

  const addToWatchlist = useCallback(async (stockCode: string) => {
    if (!stockCode || isActioning) return false;
    setIsActioning(true);
    try {
      const result = await systemConfigApi.addToWatchlist(stockCode);
      if (mountedRef.current) {
        applyMutationResult(result);
        showMessage(t('chat.watchlistAdded', { stock: stockCode }));
      }
      return true;
    } catch {
      if (mountedRef.current) showMessage(t('chat.actionFailed'));
      return false;
    } finally {
      if (mountedRef.current) setIsActioning(false);
    }
  }, [applyMutationResult, isActioning, showMessage, t]);

  const removeFromWatchlist = useCallback(async (stockCode: string) => {
    if (!stockCode || isActioning) return false;
    setIsActioning(true);
    try {
      const result = await systemConfigApi.removeFromWatchlist(stockCode);
      if (mountedRef.current) {
        applyMutationResult(result);
        showMessage(t('chat.watchlistRemoved', { stock: stockCode }));
      }
      return true;
    } catch {
      if (mountedRef.current) showMessage(t('chat.actionFailed'));
      return false;
    } finally {
      if (mountedRef.current) setIsActioning(false);
    }
  }, [applyMutationResult, isActioning, showMessage, t]);

  const toggleWatchlist = useCallback(async (stockCode: string) => {
    const existingStockCode = findMatchingStockCode(codes, stockCode);
    if (existingStockCode) {
      return removeFromWatchlist(existingStockCode);
    }
    return addToWatchlist(stockCode);
  }, [codes, removeFromWatchlist, addToWatchlist]);

  return {
    watchlistCodes: codes,
    isLoading,
    isActioning,
    loadError,
    actionMessage,
    isInWatchlist,
    addToWatchlist,
    removeFromWatchlist,
    toggleWatchlist,
    refresh,
  };
}
