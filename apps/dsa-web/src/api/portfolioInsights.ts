// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { z } from 'zod';
import apiClient, { locallyRecoverableResourceConfig } from './index';
import { createApiError, createParsedApiError } from './error';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { components, operations } from '../types/api.generated';
import type {
  PortfolioBasketRequest,
  PortfolioBasketResponse,
  PortfolioRebalanceQuery,
  PortfolioRebalancingResponse,
  PortfolioStressCustomRequest,
  PortfolioStressPresetQuery,
  PortfolioStressResponse,
  StressScenarioListResponse,
} from '../types/portfolioInsights';

type _BasketRequestAnchor = components['schemas']['PortfolioLevelAnalysisRequest'];
type _StressRequestAnchor = components['schemas']['PortfolioStressTestRequest'];
type _RebalanceQueryAnchor = NonNullable<operations['getPortfolioRebalancingRecommendations']['parameters']['query']>;
const _basketAnchor: keyof _BasketRequestAnchor = 'stock_codes';
const _stressAnchor: keyof _StressRequestAnchor = 'custom_shocks';
const _rebalanceAnchor: keyof _RebalanceQueryAnchor = 'risk_tolerance';
void _basketAnchor;
void _stressAnchor;
void _rebalanceAnchor;

const finite = z.number().refine(Number.isFinite, { message: 'non-finite number rejected' });
const optionalFinite = finite.nullable().optional();
const costMethodSchema = z.enum(['fifo', 'avg']);

function invalidRequest(label: string, issues: z.ZodIssue[]): never {
  const summary = issues.map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`).join('; ');
  throw createApiError(createParsedApiError({
    title: '请求参数无效',
    message: `${label} failed validation. ${summary}`,
    rawMessage: summary,
    category: 'missing_params',
    code: 'invalid_params',
    params: { label, issues: summary },
    details: issues,
  }));
}

function validate<T>(schema: z.ZodType<T>, value: unknown, label: string): T {
  const result = schema.safeParse(value);
  if (!result.success) return invalidRequest(label, result.error.issues);
  return result.data;
}

const basketRequestSchema = z.object({
  stockCodes: z.array(z.string().trim().min(1).max(16)).min(1).max(20)
    .refine((items) => new Set(items.map((item) => item.toUpperCase())).size === items.length, 'duplicate symbols rejected'),
  weights: z.record(z.string(), finite.nonnegative()).optional(),
  asOf: z.string().min(1).optional(),
  lookbackTradingDays: z.number().int().min(60).max(1000).optional(),
  confidence: finite.refine((value) => value > 0.5 && value < 1).optional(),
  horizonDays: z.number().int().positive().optional(),
  includeStress: z.boolean().optional(),
  scenarioId: z.string().min(1).max(64).optional(),
  sectorMap: z.record(z.string(), z.string().min(1).max(80)).optional(),
  highCorrelationThreshold: finite.min(0).max(1).optional(),
  currency: z.string().trim().min(3).max(8).optional(),
}).strict().superRefine((request, context) => {
  if (!request.weights) return;
  const symbols = new Set(request.stockCodes.map((item) => item.toUpperCase()));
  for (const key of Object.keys(request.weights)) {
    if (!symbols.has(key.toUpperCase())) {
      context.addIssue({ code: 'custom', path: ['weights', key], message: 'weight key is not in stockCodes' });
    }
  }
});

const weightSchema = z.object({ symbol: z.string(), weightPct: finite }).passthrough();
const basketResponseSchema = z.object({
  formulaVersion: z.literal('portfolio_level_analysis_v1'),
  analysisMode: z.literal('portfolio_level_basket'),
  snapshotKind: z.literal('synthetic_basket_v1'),
  asOf: z.string(),
  currency: z.string(),
  status: z.string(),
  statusMessage: z.string().nullable().optional(),
  disclaimer: z.string(),
  requestedSymbols: z.array(z.string()),
  symbolsUsed: z.array(z.string()).optional(),
  symbolsRequestedCount: z.number().int(),
  symbolsUsedCount: z.number().int(),
  maxSymbols: z.number().int().positive(),
  weightingMode: z.string(),
  weights: z.array(weightSchema).optional(),
  degradedSymbols: z.array(z.object({ stockCode: z.string(), reason: z.string(), detail: z.string().nullable().optional() }).passthrough()).optional(),
  annotations: z.array(z.string()).optional(),
  correlationHighlights: z.array(z.object({
    left: z.string(), right: z.string(), correlation: finite, absCorrelation: finite,
    direction: z.enum(['positive', 'negative']),
  }).passthrough()).optional(),
  sharedRiskExposures: z.array(z.object({
    kind: z.string(), symbols: z.array(z.string()).optional(), size: z.number().int().nullable().optional(),
    summary: z.string(), sector: z.string().nullable().optional(), topWeightPct: optionalFinite, rank: z.number().int().nullable().optional(),
  }).passthrough()).optional(),
  stanceDistribution: z.object({
    status: z.string(), statusMessage: z.string().nullable().optional(), scoredCount: z.number().int(),
    unanalyzedCount: z.number().int(), averageScore: optionalFinite,
    byOperationAdvice: z.record(z.string(), z.number().int()).optional(),
  }).passthrough(),
  health: z.object({
    status: z.string().nullable().optional(), statusMessage: z.string().nullable().optional(),
    score: optionalFinite, partialScore: optionalFinite, coverageRatio: optionalFinite,
  }).passthrough(),
  stress: z.object({ status: z.string(), statusMessage: z.string().nullable().optional(), scenario: z.record(z.string(), z.unknown()).optional() }).passthrough().nullable().optional(),
  calculatedAt: z.string(),
}).passthrough();

const shockSchema = z.discriminatedUnion('factor', [
  z.object({ factor: z.enum(['market', 'sector', 'fx']), valuePct: finite.min(-100).max(100) }),
  z.object({ factor: z.literal('rate'), valueBp: finite.min(-1000).max(1000) }),
]);
const scenarioSchema = z.object({
  id: z.string(), name: z.string(), description: z.string(),
  category: z.enum(['market', 'sector', 'fx', 'rate', 'custom']),
  shocks: z.array(shockSchema).min(1), requiresTargetSector: z.boolean(),
  availability: z.enum(['ready', 'requires_parameters']),
  source: z.enum(['built_in', 'yaml', 'custom_api']), version: z.number().int().positive(), scenarioHash: z.string(),
}).passthrough();
const scenarioListSchema = z.object({
  scenarios: z.array(scenarioSchema).optional(),
  simulationMethod: z.literal('deterministic_factor_shock'),
  historicalReplayAvailable: z.literal(false),
}).passthrough();

const impactSchema = z.object({
  positionKey: z.string(), accountId: z.number().int(), symbol: z.string(), marketValue: finite,
  weightPct: finite, shockPct: finite, pnl: finite, stressedMarketValue: finite,
  dataQuality: z.enum(['ok', 'partial']), limitations: z.array(z.string()).optional(),
}).passthrough();
const stressResponseSchema = z.object({
  asOf: z.string(), calculatedAt: z.string(), accountId: z.number().int().nullable().optional(),
  costMethod: costMethodSchema, currency: z.string(),
  status: z.enum(['ok', 'empty_portfolio', 'partial', 'unavailable']),
  statusMessage: z.string().nullable().optional(), portfolioValue: finite, positionsUsed: z.number().int(),
  excludedPositionCount: z.number().int(), portfolioPnl: optionalFinite, portfolioPnlPct: optionalFinite,
  stressedPortfolioValue: optionalFinite, scenario: scenarioSchema.extend({ targetSector: z.string().nullable().optional() }),
  positionImpacts: z.array(impactSchema).optional(), topLosers: z.array(impactSchema).optional(),
  topWinners: z.array(impactSchema).optional(), snapshotLimitations: z.array(z.string()).optional(),
  missingData: z.array(z.string()).optional(),
}).passthrough();

const presetQuerySchema = z.object({
  scenarioId: z.string().min(1).max(64), accountId: z.number().int().positive().optional(),
  asOf: z.string().min(1).optional(), costMethod: costMethodSchema.optional(),
  rateSensitivityPctPer100bp: finite.positive().max(20).optional(),
}).strict();
const customStressRequestSchema = z.object({
  accountId: z.number().int().positive().optional(), asOf: z.string().min(1).optional(),
  costMethod: costMethodSchema.optional(), scenarioId: z.string().min(1).max(64).optional(),
  targetSector: z.string().min(1).max(80).optional(),
  sectorMap: z.record(z.string(), z.string().min(1).max(80)).optional(),
  customShocks: z.array(shockSchema).min(1).max(16).optional(),
  rateSensitivityPctPer100bp: finite.positive().max(20).optional(),
}).strict().refine((request) => Boolean(request.scenarioId) !== Boolean(request.customShocks), {
  message: 'exactly one of scenarioId and customShocks is required',
});

const suggestionSchema = z.object({
  action: z.enum(['trim', 'add', 'hold']), symbol: z.string(), fromWeightPct: finite,
  toWeightPct: finite, deltaWeightPct: finite, approxNotional: finite, rationale: z.string(),
  assumptions: z.array(z.string()).optional(), isSuggestionOnly: z.boolean(), autoExecute: z.literal(false),
}).passthrough();
const bandSchema = z.object({
  symbol: z.string(), action: z.enum(['add', 'reduce', 'hold', 'exit']), currentWeightPct: finite,
  targetWeightPctLow: finite, targetWeightPctMid: finite, targetWeightPctHigh: finite,
  effectiveCapPct: finite, signal: z.string(), mode: z.string(), rationale: z.string(),
  isSuggestionOnly: z.boolean(), autoExecute: z.literal(false),
}).passthrough();
const rebalanceResponseSchema = z.object({
  asOf: z.string(), accountId: z.number().int().nullable().optional(), costMethod: z.string(), currency: z.string(),
  status: z.enum(['ok', 'empty_portfolio', 'insufficient_data', 'refused']), statusMessage: z.string().nullable().optional(),
  disclaimer: z.string(), riskTolerance: z.enum(['conservative', 'moderate', 'aggressive']),
  isSuggestionOnly: z.literal(true), autoExecute: z.literal(false),
  targetModel: z.object({ name: z.string(), description: z.string(), maxSingleWeightPct: finite, minEffectiveN: finite, maxHhi: finite, targetVarPctCeiling: finite }).passthrough(),
  current: z.object({ portfolioValue: finite, varPct: optionalFinite, hhi: optionalFinite, effectiveN: optionalFinite }).passthrough(),
  drift: z.object({ maxAbsWeightDriftPct: finite, breaches: z.array(z.object({ kind: z.string(), symbol: z.string().nullable().optional(), currentPct: finite, limitPct: finite, driftPct: finite }).passthrough()).optional() }).passthrough(),
  suggestions: z.array(suggestionSchema).optional(), positionBands: z.array(bandSchema).optional(),
}).passthrough();
const rebalanceQuerySchema = z.object({
  accountId: z.number().int().positive().optional(), asOf: z.string().min(1).optional(),
  costMethod: costMethodSchema.optional(), riskTolerance: z.enum(['conservative', 'moderate', 'aggressive']).optional(),
  driftThresholdPct: finite.min(0).max(100).optional(), confidence: finite.refine((value) => value > 0.5 && value < 1).optional(),
  horizonDays: z.number().int().positive().optional(), lookbackTradingDays: z.number().int().min(60).max(1000).optional(),
}).strict();

function normalizeBasket(parsed: PortfolioBasketResponse): PortfolioBasketResponse {
  return {
    ...parsed, symbolsUsed: parsed.symbolsUsed ?? [], weights: parsed.weights ?? [],
    degradedSymbols: parsed.degradedSymbols ?? [], annotations: parsed.annotations ?? [],
    correlationHighlights: parsed.correlationHighlights ?? [],
    sharedRiskExposures: (parsed.sharedRiskExposures ?? []).map((item) => ({ ...item, symbols: item.symbols ?? [] })),
    stanceDistribution: { ...parsed.stanceDistribution, byOperationAdvice: parsed.stanceDistribution.byOperationAdvice ?? {} },
  };
}

function normalizeStress(parsed: PortfolioStressResponse): PortfolioStressResponse {
  return { ...parsed, positionImpacts: parsed.positionImpacts ?? [], topLosers: parsed.topLosers ?? [], topWinners: parsed.topWinners ?? [], snapshotLimitations: parsed.snapshotLimitations ?? [], missingData: parsed.missingData ?? [] };
}

function normalizeRebalance(parsed: PortfolioRebalancingResponse): PortfolioRebalancingResponse {
  return { ...parsed, drift: { ...parsed.drift, breaches: parsed.drift.breaches ?? [] }, suggestions: parsed.suggestions ?? [], positionBands: parsed.positionBands ?? [] };
}

function camelShockToSnake(shock: { factor: string; valuePct?: number; valueBp?: number }) {
  return shock.factor === 'rate'
    ? { factor: shock.factor, value_bp: shock.valueBp }
    : { factor: shock.factor, value_pct: shock.valuePct };
}

export const portfolioInsightsApi = {
  async analyzeBasket(request: PortfolioBasketRequest): Promise<PortfolioBasketResponse> {
    const body = validate(basketRequestSchema, request, 'Portfolio basket request');
    const response = await apiClient.post<unknown>('/api/v1/analysis/portfolio', {
      stock_codes: body.stockCodes.map((item) => item.toUpperCase()), weights: body.weights,
      as_of: body.asOf, lookback_trading_days: body.lookbackTradingDays ?? 252,
      confidence: body.confidence ?? 0.95, horizon_days: body.horizonDays ?? 1,
      include_stress: body.includeStress ?? true, scenario_id: body.scenarioId ?? 'market_down_10',
      sector_map: body.sectorMap, high_correlation_threshold: body.highCorrelationThreshold ?? 0.7,
      currency: (body.currency ?? 'CNY').toUpperCase(),
    });
    return normalizeBasket(parseCamelCasePayload<PortfolioBasketResponse>(response.data, basketResponseSchema, 'PortfolioLevelAnalysisResponse', 'portfolioInsights'));
  },

  async listStressScenarios(): Promise<StressScenarioListResponse> {
    const response = await apiClient.get<unknown>('/api/v1/portfolio/stress-test/scenarios', locallyRecoverableResourceConfig());
    const parsed = parseCamelCasePayload<StressScenarioListResponse>(response.data, scenarioListSchema, 'StressScenarioListResponse', 'portfolioInsights');
    return { ...parsed, scenarios: parsed.scenarios ?? [] };
  },

  async runStressPreset(query: PortfolioStressPresetQuery): Promise<PortfolioStressResponse> {
    const value = validate(presetQuerySchema, query, 'Portfolio stress preset query');
    const response = await apiClient.get<unknown>('/api/v1/portfolio/stress-test', { params: {
      scenario_id: value.scenarioId, account_id: value.accountId, as_of: value.asOf,
      cost_method: value.costMethod ?? 'fifo', rate_sensitivity_pct_per_100bp: value.rateSensitivityPctPer100bp,
    } });
    return normalizeStress(parseCamelCasePayload<PortfolioStressResponse>(response.data, stressResponseSchema, 'PortfolioStressTestResponse', 'portfolioInsights'));
  },

  async runStressCustom(request: PortfolioStressCustomRequest): Promise<PortfolioStressResponse> {
    const value = validate(customStressRequestSchema, request, 'Portfolio custom stress request');
    const response = await apiClient.post<unknown>('/api/v1/portfolio/stress-test', {
      account_id: value.accountId, as_of: value.asOf, cost_method: value.costMethod ?? 'fifo',
      scenario_id: value.scenarioId, target_sector: value.targetSector, sector_map: value.sectorMap,
      custom_shocks: value.customShocks?.map(camelShockToSnake),
      rate_sensitivity_pct_per_100bp: value.rateSensitivityPctPer100bp,
    });
    return normalizeStress(parseCamelCasePayload<PortfolioStressResponse>(response.data, stressResponseSchema, 'PortfolioStressTestResponse', 'portfolioInsights'));
  },

  async getRebalancing(query: PortfolioRebalanceQuery = {}): Promise<PortfolioRebalancingResponse> {
    const value = validate(rebalanceQuerySchema, query, 'Portfolio rebalancing query');
    const response = await apiClient.get<unknown>('/api/v1/portfolio/rebalancing-recommendations', { params: {
      account_id: value.accountId, as_of: value.asOf, cost_method: value.costMethod ?? 'fifo',
      risk_tolerance: value.riskTolerance ?? 'moderate', drift_threshold_pct: value.driftThresholdPct ?? 5,
      confidence: value.confidence ?? 0.95, horizon_days: value.horizonDays ?? 1,
      lookback_trading_days: value.lookbackTradingDays ?? 252,
    } });
    return normalizeRebalance(parseCamelCasePayload<PortfolioRebalancingResponse>(response.data, rebalanceResponseSchema, 'PortfolioRebalancingResponse', 'portfolioInsights'));
  },
};
