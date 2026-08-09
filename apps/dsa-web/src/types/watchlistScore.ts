// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

export type WatchlistScoreFactorKey = 'analysis_sentiment' | 'decision_signal';
export type WatchlistScoreFactorStatus = 'applied' | 'ignored';
export type WatchlistScoreDegradationReason =
  | 'invalid_sentiment'
  | 'inactive_signal'
  | 'expired_signal'
  | 'incoherent_signal_source'
  | 'unknown_signal_action'
  | 'invalid_signal_confidence';

export interface WatchlistScoreFactorSource {
  id: number | null;
  sourceReportId: number | null;
  profile: string | null;
  asOf: string | null;
  expiresAt: string | null;
  formulaVersion: 'watchlist_score_v1';
}

export interface WatchlistScoreFactor {
  key: WatchlistScoreFactorKey;
  status: WatchlistScoreFactorStatus;
  value: string | number | null;
  params: Record<string, string | number | boolean | null>;
  reason: WatchlistScoreDegradationReason | null;
  source: WatchlistScoreFactorSource;
}

export type WatchlistScoreStatus = 'scored' | 'unanalyzed';
export type WatchlistScoreSortMode = 'manual' | 'score_desc' | 'score_asc';
export type WatchlistScoreFreshness = 'none' | 'unknown' | 'today' | 'recent' | 'stale_week' | 'stale';

export interface WatchlistScoreItem {
  stockCode: string;
  status: WatchlistScoreStatus;
  score: number | null;
  asOf: string | null;
  ageDays: number | null;
  analysisId: number | null;
  operationAdvice: string | null;
  factors: WatchlistScoreFactor[];
  freshness: WatchlistScoreFreshness;
  degradedReasons: WatchlistScoreDegradationReason[];
}

export interface WatchlistScoreResponse {
  formulaVersion: 'watchlist_score_v1';
  scoringMode: 'aggregate_existing';
  sort: WatchlistScoreSortMode;
  items: WatchlistScoreItem[];
  queryCount: { analysis: number; signals: number };
  sourceRows: { analysis: number; signals: number };
  disclaimerKey: 'watchlist_score.disclaimer';
}
