// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useQuery } from '@tanstack/react-query';
import type { HistoryListResponse } from '../types/analysis';

/** Stable query key for market-review history list polling. */
export const MARKET_REVIEW_HISTORY_QUERY_KEY = ['market-review', 'history'] as const;

/** Matches the previous hand-rolled setInterval cadence on MarketReviewPage. */
export const MARKET_REVIEW_HISTORY_REFETCH_INTERVAL_MS = 30_000;

export type MarketReviewHistoryQueryResult = {
  ok: true;
};

type UseMarketReviewHistoryQueryOptions = {
  loadMarketReviewHistory: () => Promise<void>;
  refreshMarketReviewHistory: (silent?: boolean) => Promise<HistoryListResponse | null>;
};

/**
 * Pilot TanStack Query adapter for Market Review history list fetch/poll.
 *
 * Behavior parity with the previous page-local useEffect:
 * - First successful fetch uses the non-silent store load (loading UI).
 * - Interval and window-focus refetches use silent refresh.
 * - Interval: 30s; focus/visibility: QueryClient refetchOnWindowFocus.
 * - Errors remain on the existing store error surface (retry: false).
 *
 * Presentation and selection state stay in the stock pool store; this hook only
 * owns the fetch/poll schedule.
 */
export function useMarketReviewHistoryQuery({
  loadMarketReviewHistory,
  refreshMarketReviewHistory,
}: UseMarketReviewHistoryQueryOptions) {
  return useQuery({
    queryKey: MARKET_REVIEW_HISTORY_QUERY_KEY,
    queryFn: async ({ client }): Promise<MarketReviewHistoryQueryResult> => {
      const previous = client.getQueryData<MarketReviewHistoryQueryResult>(
        MARKET_REVIEW_HISTORY_QUERY_KEY,
      );
      if (previous === undefined) {
        await loadMarketReviewHistory();
      } else {
        await refreshMarketReviewHistory(true);
      }
      return { ok: true };
    },
    refetchInterval: MARKET_REVIEW_HISTORY_REFETCH_INTERVAL_MS,
    refetchOnWindowFocus: true,
    retry: false,
  });
}

export default useMarketReviewHistoryQuery;
