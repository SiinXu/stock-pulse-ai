// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Typed client for portfolio health read and explicit refresh operations.

import { z } from 'zod';
import apiClient, { locallyRecoverableResourceConfig } from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import { createApiError, createParsedApiError } from './error';
import type { operations } from '../types/api.generated';
import type {
  PortfolioHealthQuery,
  PortfolioHealthRefreshQuery,
  PortfolioHealthResponse,
} from '../types/portfolioHealth';

type OpenApiGetQuery = NonNullable<operations['getPortfolioHealth']['parameters']['query']>;
type OpenApiRefreshQuery = NonNullable<operations['refreshPortfolioHealth']['parameters']['query']>;
const _getQueryAnchor: keyof OpenApiGetQuery = 'cost_method';
const _refreshQueryAnchor: keyof OpenApiRefreshQuery = 'persist';
void _getQueryAnchor;
void _refreshQueryAnchor;

const finiteNumber = z.number().refine(Number.isFinite, {
  message: 'non-finite number rejected',
});
const optionalFinite = finiteNumber.nullable().optional();

const portfolioHealthBandSchema = z.enum(['healthy', 'fair', 'caution', 'poor']);
const portfolioHealthStatusSchema = z.enum([
  'ok',
  'partial',
  'empty_portfolio',
  'unavailable',
]);

const portfolioHealthDimensionNameSchema = z.enum([
  'concentration',
  'risk_exposure',
  'diversification',
  'pnl',
  'cash_ratio',
]);

const weightsSchema = z.object({
  concentration: finiteNumber,
  riskExposure: finiteNumber,
  diversification: finiteNumber,
  pnl: finiteNumber,
  cashRatio: finiteNumber,
});

const effectiveWeightsSchema = z.object({
  concentration: optionalFinite,
  riskExposure: optionalFinite,
  diversification: optionalFinite,
  pnl: optionalFinite,
  cashRatio: optionalFinite,
});

const dimensionSchema = z.object({
  formula: z.string().nullable().optional(),
  input: z.record(z.string(), finiteNumber).optional(),
  reason: z.string().nullable().optional(),
  score: optionalFinite,
  status: z.enum(['ok', 'unavailable']),
  statusMessage: z.string().nullable().optional(),
}).passthrough();

export const portfolioHealthResponseSchema = z
  .object({
    accountId: z.number().int().nullable().optional(),
    asOf: z.string().min(1),
    band: portfolioHealthBandSchema.nullable().optional(),
    bands: z.array(z.object({
      maxExclusive: finiteNumber,
      minInclusive: finiteNumber,
      name: portfolioHealthBandSchema,
    }).passthrough()).optional().default([]),
    comparable: z.boolean(),
    config: z.object({
      cashHighAlertPct: finiteNumber,
      cashLowAlertPct: finiteNumber,
      concentrationAlertPct: finiteNumber,
      diversificationAlert: finiteNumber,
      pnlLossAlertPct: finiteNumber,
      source: z.literal('shared_config'),
      varAlertPct: finiteNumber,
      weights: weightsSchema,
    }).passthrough(),
    costMethod: z.enum(['fifo', 'avg']),
    coverageRatio: finiteNumber,
    currency: z.string().min(1),
    dataQuality: z.object({
      fxStale: z.boolean(),
      limitations: z.array(z.string()).optional().default([]),
      missingPriceSymbols: z.array(z.string()).optional().default([]),
      partialReasons: z.array(z.string()).optional().default([]),
      riskMetricsStatus: z.string().nullable().optional(),
      snapshotDataQuality: z.string().nullable().optional(),
      status: z.enum(['ok', 'partial', 'empty', 'unavailable']),
    }).passthrough(),
    dimensions: z.object({
      concentration: dimensionSchema,
      riskExposure: dimensionSchema,
      diversification: dimensionSchema,
      pnl: dimensionSchema,
      cashRatio: dimensionSchema,
    }),
    status: portfolioHealthStatusSchema,
    statusMessage: z.string().nullable().optional(),
    disclaimer: z.string(),
    effectiveWeights: effectiveWeightsSchema,
    formulaVersion: z.literal('portfolio_health_v2'),
    inputs: z.object({
      cashPct: optionalFinite,
      diversificationScore: optionalFinite,
      topWeightPct: optionalFinite,
      totalCash: finiteNumber,
      totalEquity: finiteNumber,
      totalMarketValue: finiteNumber,
      unrealizedPnlPct: optionalFinite,
      varPct: optionalFinite,
    }).passthrough(),
    insights: z.array(z.object({
      code: z.string(),
      message: z.string(),
      metric: z.string().nullable().optional(),
      severity: z.enum(['info', 'warning']),
      source: z.enum(['rule', 'rule+llm_polish']),
      symbol: z.string().nullable().optional(),
      threshold: optionalFinite,
      value: optionalFinite,
    }).passthrough()).optional().default([]),
    llmCanModifyScore: z.literal(false),
    partialScore: optionalFinite,
    persisted: z.boolean(),
    provenance: z.object({
      calculatedAt: z.string().min(1),
      configHash: z.string(),
      fxProvenance: z.record(z.string(), z.unknown()).optional(),
      priceProvenance: z.record(z.string(), z.unknown()).optional(),
      riskHash: z.string(),
      riskHistory: z.record(z.string(), z.unknown()).optional(),
      snapshotHash: z.string(),
    }).passthrough(),
    score: optionalFinite,
    scoreSource: z.literal('rules'),
    unavailableDimensions: z.array(portfolioHealthDimensionNameSchema).optional().default([]),
    weights: weightsSchema,
  })
  .passthrough();

export const portfolioHealthQuerySchema = z.object({
  accountId: z.number().int().positive().optional(),
  asOf: z.string().min(1).optional(),
  costMethod: z.enum(['fifo', 'avg']).optional(),
}).strict();

const portfolioHealthRefreshQuerySchema = portfolioHealthQuerySchema.extend({
  persist: z.boolean().optional(),
});

function invalidQueryError(issues: z.ZodIssue[]): never {
  const summary = issues
    .map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`)
    .join('; ');
  throw createApiError(createParsedApiError({
    title: '请求参数无效',
    message: `Portfolio health query failed validation. ${summary}`,
    rawMessage: summary,
    category: 'missing_params',
    code: 'invalid_params',
    params: { issues: summary },
    details: issues,
  }));
}

function buildParams(query: PortfolioHealthRefreshQuery): Record<string, string | number | boolean> {
  const params: Record<string, string | number | boolean> = {};
  if (query.accountId != null) params.account_id = query.accountId;
  if (query.asOf) params.as_of = query.asOf;
  if (query.costMethod) params.cost_method = query.costMethod;
  if (query.persist != null) params.persist = query.persist;
  return params;
}

function parseResponse(data: unknown): PortfolioHealthResponse {
  const parsed = parseCamelCasePayload<PortfolioHealthResponse>(
    data,
    portfolioHealthResponseSchema,
    'PortfolioHealthResponse',
    'portfolioHealth',
  );
  return {
    ...parsed,
    bands: Array.isArray(parsed.bands) ? parsed.bands : [],
    dataQuality: {
      ...parsed.dataQuality,
      limitations: Array.isArray(parsed.dataQuality.limitations)
        ? parsed.dataQuality.limitations
        : [],
      missingPriceSymbols: Array.isArray(parsed.dataQuality.missingPriceSymbols)
        ? parsed.dataQuality.missingPriceSymbols
        : [],
      partialReasons: Array.isArray(parsed.dataQuality.partialReasons)
        ? parsed.dataQuality.partialReasons
        : [],
    },
    insights: Array.isArray(parsed.insights) ? parsed.insights : [],
    unavailableDimensions: Array.isArray(parsed.unavailableDimensions)
      ? parsed.unavailableDimensions
      : [],
  };
}

export const portfolioHealthApi = {
  /**
   * Read-only stored daily snapshot. Never computes or persists.
   * 404 means no snapshot yet (empty / not refreshed).
   */
  async getSummary(query: PortfolioHealthQuery = {}): Promise<PortfolioHealthResponse | null> {
    const result = portfolioHealthQuerySchema.safeParse(query);
    if (!result.success) return invalidQueryError(result.error.issues);
    try {
      const response = await apiClient.get<unknown>(
        '/api/v1/portfolio/health',
        { ...locallyRecoverableResourceConfig(), params: buildParams(result.data) },
      );
      return parseResponse(response.data);
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 404) return null;
      throw error;
    }
  },

  /** Compute and persist the current daily snapshot after an explicit user action. */
  async refresh(query: PortfolioHealthRefreshQuery = {}): Promise<PortfolioHealthResponse> {
    const result = portfolioHealthRefreshQuerySchema.safeParse(query);
    if (!result.success) return invalidQueryError(result.error.issues);
    const response = await apiClient.post<unknown>(
      '/api/v1/portfolio/health/refresh',
      undefined,
      { params: buildParams({ ...result.data, persist: result.data.persist ?? true }) },
    );
    return parseResponse(response.data);
  },
};
