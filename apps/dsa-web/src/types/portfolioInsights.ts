// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { PortfolioCostMethod } from './portfolio';

export type PortfolioBasketRequest = {
  stockCodes: string[];
  weights?: Record<string, number>;
  asOf?: string;
  lookbackTradingDays?: number;
  confidence?: number;
  horizonDays?: number;
  includeStress?: boolean;
  scenarioId?: string;
  sectorMap?: Record<string, string>;
  highCorrelationThreshold?: number;
  currency?: string;
};

export type RiskBlock = {
  status: string;
  statusMessage?: string | null;
};

export type PortfolioBasketResponse = {
  formulaVersion: 'portfolio_level_analysis_v1';
  analysisMode: 'portfolio_level_basket';
  snapshotKind: 'synthetic_basket_v1';
  asOf: string;
  currency: string;
  status: string;
  statusMessage?: string | null;
  disclaimer: string;
  requestedSymbols: string[];
  symbolsUsed: string[];
  symbolsRequestedCount: number;
  symbolsUsedCount: number;
  maxSymbols: number;
  weightingMode: string;
  weights: Array<{ symbol: string; weightPct: number }>;
  degradedSymbols: Array<{ stockCode: string; reason: string; detail?: string | null }>;
  annotations: string[];
  correlation: RiskBlock & { symbols: string[]; matrix: Array<Array<number | null>>; observationCount: number };
  correlationHighlights: Array<{
    left: string;
    right: string;
    correlation: number;
    absCorrelation: number;
    direction: 'positive' | 'negative';
  }>;
  concentration: RiskBlock & {
    hhi?: number | null;
    effectiveN?: number | null;
    diversificationScore?: number | null;
    topWeightPct?: number | null;
    positionCount: number;
  };
  var: RiskBlock & {
    confidence?: number | null;
    horizonDays?: number | null;
    varPct?: number | null;
    varValue?: number | null;
    observationCount: number;
  };
  sharedRiskExposures: Array<{
    kind: string;
    symbols: string[];
    size?: number | null;
    summary: string;
    sector?: string | null;
    topWeightPct?: number | null;
    rank?: number | null;
  }>;
  stanceDistribution: RiskBlock & {
    scoredCount: number;
    unanalyzedCount: number;
    averageScore?: number | null;
    byOperationAdvice: Record<string, number>;
    items: Array<Record<string, unknown>>;
    formulaVersion?: string | null;
  };
  health: RiskBlock & {
    score?: number | null;
    partialScore?: number | null;
    coverageRatio?: number | null;
    dataQuality?: Record<string, unknown> | null;
    disclaimer?: string | null;
  };
  stress?: (RiskBlock & { scenario?: Record<string, unknown> }) | null;
  riskMetricsStatus?: string | null;
  riskHistory: Record<string, unknown>;
  assumptions: Record<string, unknown>;
  calculatedAt: string;
};

export type StressShock =
  | { factor: 'market' | 'sector' | 'fx'; valuePct: number }
  | { factor: 'rate'; valueBp: number };

export type StressScenario = {
  id: string;
  name: string;
  description: string;
  category: 'market' | 'sector' | 'fx' | 'rate' | 'custom';
  shocks: StressShock[];
  requiresTargetSector: boolean;
  availability: 'ready' | 'requires_parameters';
  source: 'built_in' | 'yaml' | 'custom_api';
  version: number;
  scenarioHash: string;
};

export type StressScenarioListResponse = {
  scenarios: StressScenario[];
  simulationMethod: 'deterministic_factor_shock';
  historicalReplayAvailable: false;
};

export type PortfolioStressPresetQuery = {
  scenarioId: string;
  accountId?: number;
  asOf?: string;
  costMethod?: PortfolioCostMethod;
  rateSensitivityPctPer100bp?: number;
};

export type PortfolioStressCustomRequest = {
  accountId?: number;
  asOf?: string;
  costMethod?: PortfolioCostMethod;
  scenarioId?: string;
  targetSector?: string;
  sectorMap?: Record<string, string>;
  customShocks?: StressShock[];
  rateSensitivityPctPer100bp?: number;
};

export type StressPositionImpact = {
  positionKey: string;
  accountId: number;
  symbol: string;
  marketValue: number;
  weightPct: number;
  shockPct: number;
  pnl: number;
  stressedMarketValue: number;
  priceSource?: string | null;
  priceProvider?: string | null;
  priceDate?: string | null;
  priceStale: boolean;
  dataQuality: 'ok' | 'partial';
  limitations: string[];
};

export type PortfolioStressResponse = {
  asOf: string;
  calculatedAt: string;
  snapshotId: string;
  snapshotVersion: 'portfolio_snapshot_v1';
  accountId?: number | null;
  costMethod: PortfolioCostMethod;
  currency: string;
  status: 'ok' | 'empty_portfolio' | 'partial' | 'unavailable';
  statusMessage?: string | null;
  portfolioValue: number;
  authoritativePortfolioValue: number;
  reconciliationDelta: number;
  positionsUsed: number;
  excludedPositionCount: number;
  excludedKnownMarketValue: number;
  excludedUnknownValueCount: number;
  excludedPositions: Array<Record<string, unknown>>;
  simulationMethod: 'deterministic_factor_shock';
  historicalReplayAvailable: false;
  scenario: StressScenario & { targetSector?: string | null };
  assumptions: Record<string, unknown> & { simplifiedAssumptions: string[]; dataSource: string };
  snapshotFxStale: boolean;
  snapshotDataQuality: 'ok' | 'partial';
  snapshotLimitations: string[];
  missingData: string[];
  portfolioPnl?: number | null;
  portfolioPnlPct?: number | null;
  stressedPortfolioValue?: number | null;
  positionImpacts: StressPositionImpact[];
  topLosers: StressPositionImpact[];
  topWinners: StressPositionImpact[];
  concentration: RiskBlock & Record<string, unknown>;
};

export type RiskTolerance = 'conservative' | 'moderate' | 'aggressive';

export type PortfolioRebalanceQuery = {
  accountId?: number;
  asOf?: string;
  costMethod?: PortfolioCostMethod;
  riskTolerance?: RiskTolerance;
  driftThresholdPct?: number;
  confidence?: number;
  horizonDays?: number;
  lookbackTradingDays?: number;
};

export type PortfolioRebalancingResponse = {
  asOf: string;
  accountId?: number | null;
  costMethod: PortfolioCostMethod;
  currency: string;
  status: 'ok' | 'empty_portfolio' | 'insufficient_data' | 'refused';
  statusMessage?: string | null;
  disclaimer: string;
  riskTolerance: RiskTolerance;
  isSuggestionOnly: true;
  autoExecute: false;
  targetModel: {
    name: string;
    description: string;
    maxSingleWeightPct: number;
    bandMaxSingleWeightPct: number;
    softMaxSingleNameWeight: number;
    minEffectiveN: number;
    maxHhi: number;
    targetVarPctCeiling: number;
    notes: string[];
  };
  current: {
    portfolioValue: number;
    weights: Array<{ symbol: string; weightPct: number }>;
    riskStatus?: string | null;
    varPct?: number | null;
    hhi?: number | null;
    effectiveN?: number | null;
    diversificationScore?: number | null;
  };
  drift: {
    maxAbsWeightDriftPct: number;
    breaches: Array<{
      kind: string;
      symbol?: string | null;
      currentPct: number;
      limitPct: number;
      driftPct: number;
    }>;
  };
  suggestions: Array<{
    action: 'trim' | 'add' | 'hold';
    symbol: string;
    fromWeightPct: number;
    toWeightPct: number;
    deltaWeightPct: number;
    approxNotional: number;
    rationale: string;
    assumptions: string[];
    isSuggestionOnly: true;
    autoExecute: false;
  }>;
  positionBands: Array<{
    symbol: string;
    action: 'add' | 'reduce' | 'hold' | 'exit';
    currentWeightPct: number;
    targetWeightPctLow: number;
    targetWeightPctMid: number;
    targetWeightPctHigh: number;
    effectiveCapPct: number;
    signal: string;
    mode: string;
    rationale: string;
    assumptions: string[];
    isSuggestionOnly: true;
    autoExecute: false;
  }>;
  assumptions: Record<string, unknown> & {
    method: string;
    riskMetricsSource: string;
    taxAndTransactionCosts: string;
    recommendationHonesty: string;
  };
  riskMetricsSummary: {
    status: string;
    varStatus?: string | null;
    correlationStatus?: string | null;
    concentrationStatus?: string | null;
  };
};
