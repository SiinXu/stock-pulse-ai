// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef } from 'react';

/** Stable query key root for Analysis Workbench dashboard data refresh schedule. */
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

function createMountScheduleId(): string {
  return `m-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * TanStack Query schedule for Analysis Workbench dashboard data refresh.
 *
 * Behavior parity with the previous useDashboardLifecycle effects:
 * - First successful query run **per mount** uses non-silent history load +
 *   stock-bar load + active-task refresh (parallel fire; stock-bar settlement
 *   tracked). The query key includes a mount-scoped id so remount always misses
 *   cache and re-runs the non-silent path (same as mount useEffect).
 * - First vs silent is decided by Query cache for **this mount key only**:
 *   `previous === undefined` → initial; otherwise silent. Aborted first attempts
 *   leave cache empty, so retries stay on the initial path.
 * - When `loadInitialHistory` / `loadStockBar` / `refreshActiveTasks` identities
 *   change (old mount-effect deps), re-fire the non-silent initial loader bundle
 *   directly (same as the previous useEffect re-run).
 * - Later interval ticks and visibility restores use silent history refresh +
 *   stock-bar refresh + active-task refresh + optional dashboard callback.
 * - Interval: 30s; visibility: explicit `visibilitychange` listener on **active**
 *   schedule queries only; `refetchOnWindowFocus: false`.
 * - Errors remain on the existing store / page surfaces (`retry: false`).
 * - Loader callbacks are read from a ref so interval/visibility ticks never use
 *   a stale closure from the first render.
 * - Unmount removes this mount's schedule entry to avoid orphan cache rows.
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
  const mountScheduleIdRef = useRef<string | null>(null);
  if (mountScheduleIdRef.current === null) {
    mountScheduleIdRef.current = createMountScheduleId();
  }
  const queryKey = useMemo(
    () => [...DASHBOARD_DATA_REFRESH_QUERY_KEY, mountScheduleIdRef.current] as const,
    [],
  );

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

  // Track initial-path loader identities (parity with the old mount-effect deps).
  const initialLoaderIdentitiesRef = useRef({
    loadInitialHistory,
    loadStockBar,
    refreshActiveTasks,
  });

  const query = useQuery({
    queryKey,
    enabled,
    queryFn: async ({ client }): Promise<DashboardDataRefreshQueryResult> => {
      const loaders = loadersRef.current;
      const previous = client.getQueryData<DashboardDataRefreshQueryResult>(queryKey);
      if (previous === undefined) {
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

    const previous = initialLoaderIdentitiesRef.current;
    const loadersChanged =
      previous.loadInitialHistory !== loadInitialHistory
      || previous.loadStockBar !== loadStockBar
      || previous.refreshActiveTasks !== refreshActiveTasks;
    initialLoaderIdentitiesRef.current = {
      loadInitialHistory,
      loadStockBar,
      refreshActiveTasks,
    };
    if (!loadersChanged) {
      return;
    }

    // Parity with old mount useEffect: identity change re-runs non-silent loaders.
    const loaders = loadersRef.current;
    void loaders.loadInitialHistory();
    void loaders.refreshActiveTasks();
    void loaders.loadStockBar().finally(() => {
      loaders.onInitialStockBarSettled();
    });
  }, [enabled, loadInitialHistory, loadStockBar, refreshActiveTasks]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void queryClient.refetchQueries({
          queryKey: DASHBOARD_DATA_REFRESH_QUERY_KEY,
          type: 'active',
        });
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [enabled, queryClient]);

  useEffect(() => {
    return () => {
      queryClient.removeQueries({ queryKey, exact: true });
    };
  }, [queryClient, queryKey]);

  return query;
}

export default useDashboardDataRefreshQuery;
