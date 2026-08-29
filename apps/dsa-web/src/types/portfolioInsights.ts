// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { components, operations } from './api.generated';
import type { PortfolioCostMethod } from './portfolio';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type Override<T, U> = Omit<T, keyof U> & U;

type OpenApiBasketRequest = components['schemas']['PortfolioLevelAnalysisRequest'];
type OpenApiBasketResponse = components['schemas']['PortfolioLevelAnalysisResponse'];
type OpenApiScenarioList = components['schemas']['StressScenarioListResponse'];
type OpenApiScenarioSummary = components['schemas']['StressScenarioSummary'];
type OpenApiScenarioBlock = components['schemas']['StressScenarioBlock'];
type OpenApiStressRequest = components['schemas']['PortfolioStressTestRequest'];
type OpenApiStressResponse = components['schemas']['PortfolioStressTestResponse'];
type OpenApiRebalanceResponse = components['schemas']['PortfolioRebalancingResponse'];
type OpenApiMarketShock = components['schemas']['MarketStressShock'];
type OpenApiSectorShock = components['schemas']['SectorStressShock'];
type OpenApiFxShock = components['schemas']['FxStressShock'];
type OpenApiRateShock = components['schemas']['RateStressShock'];
type OpenApiImpact = components['schemas']['StressPositionImpact'];
type OpenApiHealth = components['schemas']['PortfolioLevelHealthBlock'];
type OpenApiCorrelation = components['schemas']['PortfolioCorrelationBlock'];
type OpenApiConcentration = components['schemas']['PortfolioConcentrationBlock'];
type OpenApiVaR = components['schemas']['PortfolioHistoricalVaRBlock'];
type OpenApiStance = components['schemas']['PortfolioLevelStanceDistribution'];
type OpenApiSuggestion = components['schemas']['PortfolioRebalanceSuggestion'];
type OpenApiBand = components['schemas']['PortfolioPositionBand'];
type OpenApiTarget = components['schemas']['PortfolioRebalanceTargetModel'];
type OpenApiCurrent = components['schemas']['PortfolioRebalanceCurrent'];
type OpenApiDrift = components['schemas']['PortfolioRebalanceDrift'];
type OpenApiBasketPost200 = operations['analyzePortfolioLevel']['responses']['200']['content']['application/json'];
type OpenApiScenarioGet200 = operations['listPortfolioStressScenarios']['responses']['200']['content']['application/json'];
type OpenApiStressGet200 = operations['getPortfolioStressTest']['responses']['200']['content']['application/json'];
type OpenApiStressPost200 = operations['postPortfolioStressTest']['responses']['200']['content']['application/json'];
type OpenApiRebalanceGet200 = operations['getPortfolioRebalancingRecommendations']['responses']['200']['content']['application/json'];
type OpenApiRebalanceQuery = NonNullable<operations['getPortfolioRebalancingRecommendations']['parameters']['query']>;

type _Assert<T extends true> = T;
type _BasketPostIsComponent = _Assert<OpenApiBasketPost200 extends OpenApiBasketResponse ? true : false>;
type _BasketComponentIsPost = _Assert<OpenApiBasketResponse extends OpenApiBasketPost200 ? true : false>;
type _ScenarioGetIsComponent = _Assert<OpenApiScenarioGet200 extends OpenApiScenarioList ? true : false>;
type _StressGetIsComponent = _Assert<OpenApiStressGet200 extends OpenApiStressResponse ? true : false>;
type _StressPostIsComponent = _Assert<OpenApiStressPost200 extends OpenApiStressResponse ? true : false>;
type _StressGetPostEq = _Assert<OpenApiStressGet200 extends OpenApiStressPost200 ? true : false>;
type _RebalanceGetIsComponent = _Assert<OpenApiRebalanceGet200 extends OpenApiRebalanceResponse ? true : false>;
type _PinKey<T, K extends keyof T> = K;
type _BasketFormulaKey = _PinKey<OpenApiBasketResponse, 'formula_version'>;
type _ExtractCodesAlreadyLanded = never;
type _BasketStockCodes = _PinKey<OpenApiBasketRequest, 'stock_codes'>;
type _StressCustomShocks = _PinKey<OpenApiStressRequest, 'custom_shocks'>;
type _RebalanceRiskTolerance = _PinKey<OpenApiRebalanceQuery, 'risk_tolerance'>;

type _OpenApiAnchors = [
  _BasketPostIsComponent,
  _BasketComponentIsPost,
  _ScenarioGetIsComponent,
  _StressGetIsComponent,
  _StressPostIsComponent,
  _StressGetPostEq,
  _RebalanceGetIsComponent,
  _BasketFormulaKey,
  _ExtractCodesAlreadyLanded,
  _BasketStockCodes,
  _StressCustomShocks,
  _RebalanceRiskTolerance,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type PortfolioBasketRequest = _BindOpenApiAnchors<{
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
}>;

export type RiskBlock = {
  status: string;
  statusMessage?: string | null;
};

export type PortfolioBasketResponse = Override<CamelizeKeys<OpenApiBasketResponse>, {
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
  correlation: Override<CamelizeKeys<OpenApiCorrelation>, {
    status: string;
    statusMessage?: string | null;
    symbols: string[];
    matrix: Array<Array<number | null>>;
    observationCount: number;
  }>;
  correlationHighlights: Array<{
    left: string;
    right: string;
    correlation: number;
    absCorrelation: number;
    direction: 'positive' | 'negative';
  }>;
  concentration: Override<CamelizeKeys<OpenApiConcentration>, {
    status: string;
    statusMessage?: string | null;
    hhi?: number | null;
    effectiveN?: number | null;
    diversificationScore?: number | null;
    topWeightPct?: number | null;
    positionCount: number;
  }>;
  var: Override<CamelizeKeys<OpenApiVaR>, {
    status: string;
    statusMessage?: string | null;
    confidence?: number | null;
    horizonDays?: number | null;
    varPct?: number | null;
    varValue?: number | null;
    observationCount: number;
  }>;
  sharedRiskExposures: Array<{
    kind: string;
    symbols: string[];
    size?: number | null;
    summary: string;
    sector?: string | null;
    topWeightPct?: number | null;
    rank?: number | null;
  }>;
  stanceDistribution: Override<CamelizeKeys<OpenApiStance>, {
    status: string;
    statusMessage?: string | null;
    scoredCount: number;
    unanalyzedCount: number;
    averageScore?: number | null;
    byOperationAdvice: Record<string, number>;
    items: Array<Record<string, unknown>>;
    formulaVersion?: string | null;
  }>;
  health: Override<CamelizeKeys<OpenApiHealth>, {
    status: string;
    statusMessage?: string | null;
    score?: number | null;
    partialScore?: number | null;
    coverageRatio?: number | null;
    dataQuality?: Record<string, unknown> | null;
    disclaimer?: string | null;
  }>;
  stress?: (RiskBlock & { scenario?: Record<string, unknown> }) | null;
  riskMetricsStatus?: string | null;
  riskHistory: Record<string, unknown>;
  assumptions: Record<string, unknown>;
  calculatedAt: string;
}>;

export type StressShock =
  | CamelizeKeys<OpenApiMarketShock>
  | CamelizeKeys<OpenApiSectorShock>
  | CamelizeKeys<OpenApiFxShock>
  | CamelizeKeys<OpenApiRateShock>;

export type StressScenario = CamelizeKeys<OpenApiScenarioSummary>;

export type StressScenarioListResponse = Override<CamelizeKeys<OpenApiScenarioList>, {
  scenarios: StressScenario[];
  simulationMethod: 'deterministic_factor_shock';
  historicalReplayAvailable: false;
}>;

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

export type StressPositionImpact = Override<Partial<CamelizeKeys<OpenApiImpact>>, {
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
}>;

export type PortfolioStressResponse = Override<CamelizeKeys<OpenApiStressResponse>, {
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
  scenario: CamelizeKeys<OpenApiScenarioBlock>;
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
}>;

export type RiskTolerance = NonNullable<OpenApiRebalanceQuery['risk_tolerance']>;

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

export type PortfolioRebalancingResponse = Override<CamelizeKeys<OpenApiRebalanceResponse>, {
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
  targetModel: Override<CamelizeKeys<OpenApiTarget>, {
    name: string;
    description: string;
    maxSingleWeightPct: number;
    bandMaxSingleWeightPct: number;
    softMaxSingleNameWeight: number;
    minEffectiveN: number;
    maxHhi: number;
    targetVarPctCeiling: number;
    notes: string[];
  }>;
  current: Override<CamelizeKeys<OpenApiCurrent>, {
    portfolioValue: number;
    weights: Array<{ symbol: string; weightPct: number }>;
    riskStatus?: string | null;
    varPct?: number | null;
    hhi?: number | null;
    effectiveN?: number | null;
    diversificationScore?: number | null;
  }>;
  drift: Override<CamelizeKeys<OpenApiDrift>, {
    maxAbsWeightDriftPct: number;
    breaches: Array<{
      kind: string;
      symbol?: string | null;
      currentPct: number;
      limitPct: number;
      driftPct: number;
    }>;
  }>;
  suggestions: Array<Override<CamelizeKeys<OpenApiSuggestion>, {
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
  }>>;
  positionBands: Array<Override<CamelizeKeys<OpenApiBand>, {
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
  }>>;
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
}>;
