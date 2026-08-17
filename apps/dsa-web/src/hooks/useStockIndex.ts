/**
 * useStockIndex Hook
 *
 * Manage stock index loading and state
 */

import { useState, useEffect } from 'react';
import type { StockIndexItem } from '../types/stockIndex';
import type { IndexLoadResult } from '../utils/stockIndexLoader';

export interface UseStockIndexResult {
  /** Stock index data */
  index: StockIndexItem[];
  /** Is loading */
  loading: boolean;
  /** Load error */
  error: Error | null;
  /** Whether fallback mode is used */
  fallback: boolean;
  /** Is loaded */
  loaded: boolean;
}

/**
 * Stock index loading Hook.
 *
 * `enabled` defaults to true so existing call sites (StockAutocomplete,
 * DecisionSignalsPage) keep mount-time loading. The command palette
 * passes `isOpen` so a closed palette does not fetch.
 *
 * @returns Index state and data
 */
export function useStockIndex(enabled = true): UseStockIndexResult {
  const [index, setIndex] = useState<StockIndexItem[]>([]);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<Error | null>(null);
  const [fallback, setFallback] = useState(false);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    let mounted = true;

    async function load() {
      setLoading(true);
      setError(null);

      const { loadStockIndex } = await import('../utils/stockIndexLoader');
      const result: IndexLoadResult = await loadStockIndex();

      if (!mounted) {
        return;
      }
      setIndex(result.data);
      setFallback(result.fallback);
      setError(result.error ?? null);
      setLoading(false);
    }

    void load();

    return () => {
      mounted = false;
    };
  }, [enabled]);

  return {
    index,
    loading,
    error,
    fallback,  // Whether fallback
    loaded: enabled && !loading,
  };
}

/**
 * Get default exported Hook
 */
export default useStockIndex;
