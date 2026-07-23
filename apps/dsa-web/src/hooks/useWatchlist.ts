import { useCallback, useEffect, useRef, useState } from 'react';
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

export function useWatchlist({ enabled = true }: UseWatchlistOptions = {}): UseWatchlistReturn {
  const { t } = useUiLanguage();
  const [codes, setCodes] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(enabled);
  const [isActioning, setIsActioning] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);
  const messageTimerRef = useRef<number | null>(null);
  const refreshRequestIdRef = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      refreshRequestIdRef.current += 1;
      if (messageTimerRef.current !== null) {
        window.clearTimeout(messageTimerRef.current);
      }
    };
  }, []);

  const refresh = useCallback(async () => {
    const requestId = refreshRequestIdRef.current + 1;
    refreshRequestIdRef.current = requestId;
    if (mountedRef.current) setIsLoading(true);
    try {
      const result = await systemConfigApi.getWatchlist();
      if (mountedRef.current && refreshRequestIdRef.current === requestId) {
        setCodes(result);
        setLoadError(null);
      }
      return true;
    } catch (error) {
      if (mountedRef.current && refreshRequestIdRef.current === requestId) {
        setLoadError(getParsedApiError(error));
      }
      return false;
    } finally {
      if (mountedRef.current && refreshRequestIdRef.current === requestId) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      refreshRequestIdRef.current += 1;
      setIsLoading(false);
      return;
    }
    void refresh();
  }, [enabled, refresh]);

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

  const isInWatchlist = useCallback(
    (stockCode: string) => includesStockCode(codes, stockCode),
    [codes],
  );

  const addToWatchlist = useCallback(async (stockCode: string) => {
    if (!stockCode || isActioning) return false;
    setIsActioning(true);
    try {
      const result = await systemConfigApi.addToWatchlist(stockCode);
      if (mountedRef.current) {
        refreshRequestIdRef.current += 1;
        setCodes(result);
        setLoadError(null);
        setIsLoading(false);
        showMessage(t('chat.watchlistAdded', { stock: stockCode }));
      }
      return true;
    } catch {
      if (mountedRef.current) showMessage(t('chat.actionFailed'));
      return false;
    } finally {
      if (mountedRef.current) setIsActioning(false);
    }
  }, [isActioning, showMessage, t]);

  const removeFromWatchlist = useCallback(async (stockCode: string) => {
    if (!stockCode || isActioning) return false;
    setIsActioning(true);
    try {
      const result = await systemConfigApi.removeFromWatchlist(stockCode);
      if (mountedRef.current) {
        refreshRequestIdRef.current += 1;
        setCodes(result);
        setLoadError(null);
        setIsLoading(false);
        showMessage(t('chat.watchlistRemoved', { stock: stockCode }));
      }
      return true;
    } catch {
      if (mountedRef.current) showMessage(t('chat.actionFailed'));
      return false;
    } finally {
      if (mountedRef.current) setIsActioning(false);
    }
  }, [isActioning, showMessage, t]);

  const toggleWatchlist = useCallback(async (stockCode: string) => {
    const existingStockCode = findMatchingStockCode(codes, stockCode);
    if (existingStockCode) {
      return removeFromWatchlist(existingStockCode);
    } else {
      return addToWatchlist(stockCode);
    }
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
