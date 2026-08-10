// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// CamelCase client types for GET /api/v1/portfolio/risk-metrics (OpenAPI getPortfolioRiskMetrics).

import type { components } from './api.generated';

type OpenApiRiskMetrics = components['schemas']['PortfolioRiskMetricsResponse'];
type OpenApiAssumptions = components['schemas']['PortfolioRiskAssumptions'];
type OpenApiVaR = components['schemas']['PortfolioHistoricalVaRBlock'];
type OpenApiCorrelation = components['schemas']['PortfolioCorrelationBlock'];
type OpenApiConcentration = components['schemas']['PortfolioConcentrationBlock'];
type OpenApiHistory = components['schemas']['PortfolioRiskHistoryMeta'];
type OpenApiWeight = components['schemas']['PortfolioRiskWeightItem'];

/** Compile-time anchors against generated snake_case OpenAPI field names. */
type _AssertRiskMetrics = keyof OpenApiRiskMetrics;
type _AssertAssumptions = keyof OpenApiAssumptions;
type _AssertVaR = keyof OpenApiVaR;
type _AssertCorrelation = keyof OpenApiCorrelation;
type _AssertConcentration = keyof OpenApiConcentration;
const _riskMetricsAnchor: _AssertRiskMetrics = 'portfolio_value';
const _assumptionsAnchor: _AssertAssumptions = 'var_method';
const _varAnchor: _AssertVaR = 'var_pct';
const _correlationAnchor: _AssertCorrelation = 'matrix';
const _concentrationAnchor: _AssertConcentration = 'diversification_score';
void _riskMetricsAnchor;
void _assumptionsAnchor;
void _varAnchor;
void _correlationAnchor;
void _concentrationAnchor;

export type PortfolioRiskMetricsStatus =
  | 'ok'
  | 'empty_portfolio'
  | 'insufficient_history'
  | 'partial'
  | string;

export type PortfolioRiskBlockStatus =
  | 'ok'
  | 'empty_portfolio'
  | 'insufficient_history'
  | 'unavailable'
  | string;

export type PortfolioRiskWeightItem = {
  symbol: string;
  weightPct: number;
};

export type PortfolioRiskAssumptions = {
  varMethod: string;
  confidence: number;
  horizonDays: number;
  lookbackTradingDays: number;
  minReturnObservations: number;
  minCorrelationObservations: number;
  returnDefinition: string;
  portfolioAggregation: string;
  cashExcluded: boolean;
  weightBasis: string;
  horizonScaling: string;
  distributionAssumption: string;
  correlationMethod: string;
  concentrationMetrics: string;
  dataSource: string;
  providerCallsOnHotPath: boolean;
};

export type PortfolioHistoricalVaRBlock = {
  status: PortfolioRiskBlockStatus;
  statusMessage?: string | null;
  confidence?: number | null;
  horizonDays?: number | null;
  varPct?: number | null;
  varValue?: number | null;
  observationCount: number;
  percentileUsed?: number | null;
  oneDayVarPct?: number | null;
};

export type PortfolioCorrelationBlock = {
  status: PortfolioRiskBlockStatus;
  statusMessage?: string | null;
  symbols: string[];
  matrix: Array<Array<number | null>>;
  observationCount: number;
};

export type PortfolioConcentrationBlock = {
  status: PortfolioRiskBlockStatus;
  hhi?: number | null;
  effectiveN?: number | null;
  diversificationScore?: number | null;
  topWeightPct?: number | null;
  positionCount: number;
  weights: PortfolioRiskWeightItem[];
};

export type PortfolioRiskHistoryMeta = {
  alignedTradingDays: number;
  lookbackTradingDaysRequested: number;
  priceSeriesSymbols: string[];
  alignedStart?: string | null;
  alignedEnd?: string | null;
};

export type PortfolioRiskMetricsResponse = {
  asOf: string;
  accountId?: number | null;
  costMethod: string;
  currency: string;
  status: PortfolioRiskMetricsStatus;
  statusMessage?: string | null;
  portfolioValue: number;
  positionsUsed: number;
  assumptions: PortfolioRiskAssumptions;
  var: PortfolioHistoricalVaRBlock;
  correlation: PortfolioCorrelationBlock;
  concentration: PortfolioConcentrationBlock;
  history?: PortfolioRiskHistoryMeta | null;
};

export type PortfolioRiskMetricsQuery = {
  accountId?: number;
  asOf?: string;
  costMethod?: 'fifo' | 'avg' | string;
  confidence?: number;
  horizonDays?: number;
  lookbackTradingDays?: number;
};

// Keep OpenApi* aliases referenced so dead-code elimination does not drop anchors.
export type {
  OpenApiRiskMetrics,
  OpenApiAssumptions,
  OpenApiVaR,
  OpenApiCorrelation,
  OpenApiConcentration,
  OpenApiHistory,
  OpenApiWeight,
};
