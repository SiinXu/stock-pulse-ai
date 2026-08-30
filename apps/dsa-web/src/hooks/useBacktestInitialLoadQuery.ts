// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// TanStack Query schedule adapter for the Backtest page mount load.
// Schedule only: the page keeps ownership of its filter/window state and of
// its unmount cancellation, so this migration cannot change either.

import { useQuery } from '@tanstack/react-query';

/** Stable query key for the Backtest page mount load. */
export const BACKTEST_INITIAL_LOAD_QUERY_KEY = ['backtest', 'initial-load'] as const;

export type BacktestInitialLoadQueryResult = {
  ok: true;
};

type UseBacktestInitialLoadQueryOptions = {
  /** Runs the same sequence the previous mount effect ran. */
  loadInitial: () => Promise<void>;
  /** Invoked when the query is aborted, mirroring the effect's generation bump. */
  onCancelInFlight?: () => void;
};

/**
 * Parity with the previous mount `useEffect(..., [])`:
 * - Runs once per mount, no interval poll, no window-focus refetch.
 * - `retry: false`, so a failure surfaces once on the page's own error state.
 * - `staleTime: 0` and `networkMode: 'always'` keep the previous behavior of
 *   always hitting axios, including offline where the page renders its own error.
 * - Unmount cancellation stays in the page's own cleanup effect; this hook only
 *   schedules, so the three generation refs and the run abort are untouched.
 */
export function useBacktestInitialLoadQuery({
  loadInitial,
  onCancelInFlight,
}: UseBacktestInitialLoadQueryOptions) {
  return useQuery({
    queryKey: BACKTEST_INITIAL_LOAD_QUERY_KEY,
    queryFn: async ({ signal }): Promise<BacktestInitialLoadQueryResult> => {
      const onAbort = () => {
        onCancelInFlight?.();
      };
      if (signal.aborted) {
        onAbort();
        return { ok: true };
      }
      signal.addEventListener('abort', onAbort);
      try {
        await loadInitial();
        return { ok: true };
      } finally {
        signal.removeEventListener('abort', onAbort);
      }
    },
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 0,
    networkMode: 'always',
  });
}

export default useBacktestInitialLoadQuery;
