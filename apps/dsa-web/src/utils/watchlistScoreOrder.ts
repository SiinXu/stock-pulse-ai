// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { WatchlistScoreItem, WatchlistScoreSortMode } from '../types/watchlistScore';

/**
 * Order watchlist rows by AI score view.
 * Default `manual` preserves the caller's input order and must never be
 * overridden by score sorting unless the user opts into a score view.
 */
export function orderWatchlistByScore<T extends { code?: string; stockCode?: string }>(
  rows: readonly T[],
  scoresByCode: ReadonlyMap<string, WatchlistScoreItem> | Readonly<Record<string, WatchlistScoreItem>>,
  mode: WatchlistScoreSortMode = 'manual',
): T[] {
  const list = [...rows];
  if (mode === 'manual') {
    return list;
  }

  const lookup = (row: T): WatchlistScoreItem | undefined => {
    const code = String(row.stockCode ?? row.code ?? '');
    if (scoresByCode instanceof Map) {
      return scoresByCode.get(code);
    }
    return (scoresByCode as Readonly<Record<string, WatchlistScoreItem>>)[code];
  };

  const reverse = mode === 'score_desc';
  list.sort((left, right) => {
    const leftScore = lookup(left);
    const rightScore = lookup(right);
    const leftScored = leftScore?.status === 'scored' && typeof leftScore.score === 'number' ? 0 : 1;
    const rightScored = rightScore?.status === 'scored' && typeof rightScore.score === 'number' ? 0 : 1;
    if (leftScored !== rightScored) {
      return leftScored - rightScored;
    }
    if (leftScored === 1) {
      return 0;
    }
    const leftValue = leftScore?.score ?? 0;
    const rightValue = rightScore?.score ?? 0;
    return reverse ? rightValue - leftValue : leftValue - rightValue;
  });
  return list;
}
