// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';

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
 * - First successful query run uses non-silent history load + stock-bar load +
 *   active-task refresh (parallel fire; stock-bar settlement is tracked).
 * - Interval ticks and visibility restores use silent history refresh + stock-bar
 *   refresh + active-task refresh + optional dashboard callback.
 * - Interval: 30s; visibility: explicit `visibilitychange` listener (page never
 *   used window-focus alone); `refetchOnWindowFocus: false` keeps that contract.
 * - Errors remain on the existing store / page surfaces (`retry: false`).
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
  const query = useQuery({
    queryKey: DASHBOARD_DATA_REFRESH_QUERY_KEY,
    enabled,
    queryFn: async ({ client }): Promise<DashboardDataRefreshQueryResult> => {
      const previous = client.getQueryData<DashboardDataRefreshQueryResult>(
        DASHBOARD_DATA_REFRESH_QUERY_KEY,
      );
      if (previous === undefined) {
        void loadInitialHistory();
        void refreshActiveTasks();
        try {
          await loadStockBar();
        } finally {
          onInitialStockBarSettled();
        }
      } else {
        void refreshHistory(true);
        void refreshStockBar();
        void refreshActiveTasks();
        onDashboardDataRefresh?.();
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
