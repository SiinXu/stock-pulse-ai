// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

export type PortfolioHealthBand = 'healthy' | 'fair' | 'caution' | 'poor';
export type PortfolioHealthStatus = 'ok' | 'partial' | 'empty_portfolio' | 'unavailable';
export type PortfolioHealthDimensionName =
  | 'concentration'
  | 'risk_exposure'
  | 'diversification'
  | 'pnl'
  | 'cash_ratio';
export type PortfolioHealthDimensionKey =
  | 'concentration'
  | 'riskExposure'
  | 'diversification'
  | 'pnl'
  | 'cashRatio';

export type PortfolioHealthQuery = {
  accountId?: number;
  asOf?: string;
  costMethod?: 'fifo' | 'avg';
};

export type PortfolioHealthRefreshQuery = PortfolioHealthQuery & {
  persist?: boolean;
};

/** Compact Home-widget projection of GET /api/v1/portfolio/health. */
export type PortfolioHealthSummary = {
  accountId?: number | null;
  asOf: string;
  band?: PortfolioHealthBand | null;
  comparable: boolean;
  costMethod: 'fifo' | 'avg';
  coverageRatio: number;
  currency: string;
  score?: number | null;
  partialScore?: number | null;
  status: PortfolioHealthStatus;
  statusMessage?: string | null;
  disclaimer?: string;
};

export type PortfolioHealthDimension = {
  formula?: string | null;
  input?: Record<string, number>;
  reason?: string | null;
  score?: number | null;
  status: 'ok' | 'unavailable';
  statusMessage?: string | null;
};

export type PortfolioHealthInsight = {
  code: string;
  message: string;
  metric?: string | null;
  severity: 'info' | 'warning';
  source: 'rule' | 'rule+llm_polish';
  symbol?: string | null;
  threshold?: number | null;
  value?: number | null;
};

export type PortfolioHealthResponse = PortfolioHealthSummary & {
  bands: Array<{
    maxExclusive: number;
    minInclusive: number;
    name: PortfolioHealthBand;
  }>;
  config: {
    cashHighAlertPct: number;
    cashLowAlertPct: number;
    concentrationAlertPct: number;
    diversificationAlert: number;
    pnlLossAlertPct: number;
    source: 'shared_config';
    varAlertPct: number;
    weights: Record<PortfolioHealthDimensionKey, number>;
  };
  dataQuality: {
    fxStale: boolean;
    limitations: string[];
    missingPriceSymbols: string[];
    partialReasons: string[];
    riskMetricsStatus?: string | null;
    snapshotDataQuality?: string | null;
    status: 'ok' | 'partial' | 'empty' | 'unavailable';
  };
  dimensions: Record<PortfolioHealthDimensionKey, PortfolioHealthDimension>;
  effectiveWeights: Record<PortfolioHealthDimensionKey, number | null | undefined>;
  formulaVersion: 'portfolio_health_v2';
  inputs: {
    cashPct?: number | null;
    diversificationScore?: number | null;
    topWeightPct?: number | null;
    totalCash: number;
    totalEquity: number;
    totalMarketValue: number;
    unrealizedPnlPct?: number | null;
    varPct?: number | null;
  };
  insights: PortfolioHealthInsight[];
  llmCanModifyScore: false;
  persisted: boolean;
  provenance: {
    calculatedAt: string;
    configHash: string;
    fxProvenance?: Record<string, unknown>;
    priceProvenance?: Record<string, unknown>;
    riskHash: string;
    riskHistory?: Record<string, unknown>;
    snapshotHash: string;
  };
  scoreSource: 'rules';
  unavailableDimensions: PortfolioHealthDimensionName[];
  weights: Record<PortfolioHealthDimensionKey, number>;
};
