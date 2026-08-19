// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import {
  createUnanalyzedWatchlistScore,
  type WatchlistScoreLoadStatus,
} from '../../hooks/useWatchlistScores';
import type { WatchlistScoreItem } from '../../types/watchlistScore';

/**
 * Resolve the score shown for one row. Ready may fall back to unanalyzed.
 * Same-generation retry keeps last-known only while stale; loading/error
 * never invent an unanalyzed success.
 */
export function resolveWatchlistScoreStatusItem(params: {
  status: WatchlistScoreLoadStatus;
  stale?: boolean;
  item?: WatchlistScoreItem;
  stockCode?: string;
  itemsByCode?: ReadonlyMap<string, WatchlistScoreItem>;
}): WatchlistScoreItem | undefined {
  if (params.item) return params.item;
  const stockCode = params.stockCode;
  if (!stockCode) return undefined;
  if (params.status === 'ready') {
    return params.itemsByCode?.get(stockCode) ?? createUnanalyzedWatchlistScore(stockCode);
  }
  if (params.status === 'retrying' && params.stale) {
    return params.itemsByCode?.get(stockCode);
  }
  return undefined;
}
