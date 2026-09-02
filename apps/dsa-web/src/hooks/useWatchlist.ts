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

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const WATCHLIST_CANCEL = { silent: true, revert: false } as const;

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
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key cancel/remove.
 *
 * Do not fence this shared queryFn on a single observer's mounted lifetime.
 * Home, Workbench, and Decision Signals share the exact key and replace each
 * other on route change. A silent cancel from the departing observer leaves
 * fetchStatus fetching, so the arriving observer never settles and Workbench
 * Pending only stays disabled.
 */
export function throwIfWatchlistCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(WATCHLIST_CANCEL);
  }
}

export async function fetchWatchlistCodes(args?: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
}): Promise<string[]> {
  const stillActive = args?.stillActive ?? (() => true);
  try {
    throwIfWatchlistCancelled(args?.signal, stillActive());
    const result = await systemConfigApi.getWatchlist();
    throwIfWatchlistCancelled(args?.signal, stillActive());
    return result;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfWatchlistCancelled(args?.signal, stillActive());
    throw error;
  }
}

export function useWatchlist({ enabled = true }: UseWatchlistOptions = {}): UseWatchlistReturn {
  const { t } = useUiLanguage();
  const queryClient = useQueryClient();
  const [isActioning, setIsActioning] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const messageTimerRef = useRef<number | null>(null);
  const mountedRef = useRef(true);
  const enabledRef = useRef(enabled);
  const generationRef = useRef(0);
  const [suppressFetchLoading, setSuppressFetchLoading] = useState(false);
  enabledRef.current = enabled;

  const query = useQuery({
    queryKey: WATCHLIST_QUERY_KEY,
    queryFn: ({ signal }) => {
      const startedAt = generationRef.current;
      return fetchWatchlistCodes({
        signal,
        stillActive: () => (
          enabledRef.current
          && generationRef.current === startedAt
        ),
      });
    },
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
        generationRef.current += 1;
        void client.cancelQueries(
          { queryKey: WATCHLIST_QUERY_KEY, exact: true },
          WATCHLIST_CANCEL,
        );
        client.removeQueries({ queryKey: WATCHLIST_QUERY_KEY, exact: true });
      });
    };
  }, [queryClient]);

  // Disable must cancel the exact in-flight GET so a later re-enable starts a
  // new generation. Do not removeQueries here: other live observers share this
  // key. Last-observer unmount discards the row after a microtask instead.
  useEffect(() => {
    if (enabled) {
      return undefined;
    }
    generationRef.current += 1;
    void queryClient.cancelQueries(
      { queryKey: WATCHLIST_QUERY_KEY, exact: true },
      WATCHLIST_CANCEL,
    );
    return undefined;
  }, [enabled, queryClient]);

  useEffect(() => {
    if (!query.isFetching) {
      setSuppressFetchLoading(false);
    }
  }, [query.isFetching]);

  const refresh = useCallback(async () => {
    setSuppressFetchLoading(false);
    try {
      await queryClient.fetchQuery({
        queryKey: WATCHLIST_QUERY_KEY,
        queryFn: ({ signal }) => {
          const startedAt = generationRef.current;
          return fetchWatchlistCodes({
            signal,
            stillActive: () => generationRef.current === startedAt,
          });
        },
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
  const isLoading = enabled && query.isFetching && !suppressFetchLoading;
  const loadError = query.error && !isCancelledError(query.error)
    ? getParsedApiError(query.error)
    : null;

  const isInWatchlist = useCallback(
    (stockCode: string) => includesStockCode(codes, stockCode),
    [codes],
  );

  const applyMutationResult = useCallback((result: string[]) => {
    generationRef.current += 1;
    void queryClient.cancelQueries(
      { queryKey: WATCHLIST_QUERY_KEY, exact: true },
      WATCHLIST_CANCEL,
    );
    queryClient.setQueryData(WATCHLIST_QUERY_KEY, result);
    setSuppressFetchLoading(true);
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
