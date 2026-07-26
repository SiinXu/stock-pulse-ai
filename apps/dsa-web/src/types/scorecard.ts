// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

export type ScorecardBucketStatus = 'ok' | 'insufficient_data' | string;

export interface ScorecardBucket {
  signalType: string;
  horizon: string;
  status: ScorecardBucketStatus;
  sampleSize: number;
  completed: number;
  hitRatePct: number | null;
  avgReturnPct: number | null;
}

export interface ScorecardOverall {
  status: ScorecardBucketStatus;
  sampleSize: number;
  completed: number;
  hitRatePct: number | null;
  avgReturnPct: number | null;
}

export interface ScorecardReturnBand {
  band: string;
  count: number;
  sharePct: number | null;
}

export interface ScorecardMiss {
  signalType: string;
  horizon: string;
  returnPct: number | null;
  anchorDate: string | null;
}

export interface SignalScorecardResponse {
  minSamples: number;
  overall: ScorecardOverall;
  bySignalTypeHorizon: ScorecardBucket[];
  returnDistribution: ScorecardReturnBand[];
  recentMisses: ScorecardMiss[];
}
