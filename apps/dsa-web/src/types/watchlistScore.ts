// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/** Per-factor contribution shown in score drill-down. */
export interface WatchlistScoreFactor {
  key: string;
  label: string;
  value: string | number;
  detail?: string | null;
}

export type WatchlistScoreStatus = 'scored' | 'unanalyzed';

export type WatchlistScoreSortMode = 'manual' | 'score_desc' | 'score_asc';

/** Mountable per-symbol score payload (contract B computed attribute). */
export interface WatchlistScoreItem {
  stockCode: string;
  status: WatchlistScoreStatus;
  /** 0-100 when scored; null when unanalyzed — never a fabricated 0. */
  score: number | null;
  asOf: string | null;
  ageDays: number | null;
  analysisId?: number | null;
  operationAdvice?: string | null;
  factors: WatchlistScoreFactor[];
  freshness: string;
}

export interface WatchlistScoreQueryCount {
  analysis: number;
  signals: number;
}

export interface WatchlistScoreResponse {
  scoringMode: string;
  sort: WatchlistScoreSortMode | string;
  items: WatchlistScoreItem[];
  queryCount: WatchlistScoreQueryCount;
  disclaimer: string;
}
