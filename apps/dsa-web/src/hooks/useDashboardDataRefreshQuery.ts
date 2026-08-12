// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

/** Stable query key for Analysis Workbench dashboard data refresh schedule. */
export const DASHBOARD_DATA_REFRESH_QUERY_KEY = ['dashboard', 'data-refresh'] as const;

/** Matches the previous hand-rolled setInterval cadence in useDashboardLifecycle. */
export const DASHBOARD_DATA_REFRESH_INTERVAL_MS = 30_000;

export type DashboardDataRefreshQueryResult = {
  ok: true;
};

type UseDashboardDataRefreshQueryOptions = {
  enabled: boolean;
  loadInitialHistory: () => Promise<void>;
  refreshHistory: (silent?: boolean) => Promise<unknown>;
  loadStockBar: () => Promise<void>;
  refreshStockBar: () => Promise<void>;
  refreshActiveTasks: () => Promise<void>;
  onDashboardDataRefresh?: () => void;
  /** Fired when the first stock-bar load settles (success or failure). */
  onInitialStockBarSettled: () => void;
};

/**
 * TanStack Query schedule for Analysis Workbench dashboard data refresh.
 *
 * Behavior parity with the previous useDashboardLifecycle effects:
 * - First successful query run **on this mount** uses non-silent history load +
 *   stock-bar load + active-task refresh (parallel fire; stock-bar settlement
 *   tracked). Mount-local ref — not Query cache — decides first vs silent so a
 *   remount still runs the non-silent initial path even if cache retains `{ok}`.
 * - Later interval ticks and visibility restores use silent history refresh +
 *   stock-bar refresh + active-task refresh + optional dashboard callback.
 * - Interval: 30s; visibility: explicit `visibilitychange` listener;
 *   `refetchOnWindowFocus: false`.
 * - Errors remain on the existing store / page surfaces (`retry: false`).
 * - Loader callbacks are read from a ref so interval/visibility ticks never use
 *   a stale closure from the first render.
 *
 * Task SSE + disconnected 2s polling stay in useDashboardLifecycle (custom).
 */
export function useDashboardDataRefreshQuery({
  enabled,
  loadInitialHistory,
  refreshHistory,
  loadStockBar,
  refreshStockBar,
  refreshActiveTasks,
  onDashboardDataRefresh,
  onInitialStockBarSettled,
}: UseDashboardDataRefreshQueryOptions) {
  const queryClient = useQueryClient();
  /** Mount-scoped: false until this hook instance has started its initial load. */
  const hasStartedInitialLoadRef = useRef(false);
  const loadersRef = useRef({
    loadInitialHistory,
    refreshHistory,
    loadStockBar,
    refreshStockBar,
    refreshActiveTasks,
    onDashboardDataRefresh,
    onInitialStockBarSettled,
  });
  loadersRef.current = {
    loadInitialHistory,
    refreshHistory,
    loadStockBar,
    refreshStockBar,
    refreshActiveTasks,
    onDashboardDataRefresh,
    onInitialStockBarSettled,
  };

  const query = useQuery({
    queryKey: DASHBOARD_DATA_REFRESH_QUERY_KEY,
    enabled,
    queryFn: async (): Promise<DashboardDataRefreshQueryResult> => {
      const loaders = loadersRef.current;
      if (!hasStartedInitialLoadRef.current) {
        hasStartedInitialLoadRef.current = true;
        void loaders.loadInitialHistory();
        void loaders.refreshActiveTasks();
        try {
          await loaders.loadStockBar();
        } finally {
          loaders.onInitialStockBarSettled();
        }
      } else {
        void loaders.refreshHistory(true);
        void loaders.refreshStockBar();
        void loaders.refreshActiveTasks();
        loaders.onDashboardDataRefresh?.();
      }
      return { ok: true };
    },
    refetchInterval: DASHBOARD_DATA_REFRESH_INTERVAL_MS,
    refetchOnWindowFocus: false,
    retry: false,
  });

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void queryClient.refetchQueries({ queryKey: DASHBOARD_DATA_REFRESH_QUERY_KEY });
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [enabled, queryClient]);

  return query;
}

export default useDashboardDataRefreshQuery;
