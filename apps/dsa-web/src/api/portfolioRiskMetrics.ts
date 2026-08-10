// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Typed client for GET /api/v1/portfolio/risk-metrics (operation_id getPortfolioRiskMetrics).

import { z } from 'zod';
import apiClient from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type {
  PortfolioRiskMetricsQuery,
  PortfolioRiskMetricsResponse,
} from '../types/portfolioRiskMetrics';

/** Reject NaN and ±Infinity at the response boundary (never silent zeros). */
const finiteNumber = z.number().refine((value) => Number.isFinite(value), {
  message: 'non-finite number rejected',
});

const optionalFinite = finiteNumber.nullable().optional();

const portfolioRiskWeightItemSchema = z
  .object({
    symbol: z.string(),
    weightPct: finiteNumber,
  })
  .passthrough();

const portfolioRiskAssumptionsSchema = z
  .object({
    varMethod: z.string(),
    confidence: finiteNumber,
    horizonDays: z.number().int(),
    lookbackTradingDays: z.number().int(),
    minReturnObservations: z.number().int(),
    minCorrelationObservations: z.number().int(),
    returnDefinition: z.string(),
    portfolioAggregation: z.string(),
    cashExcluded: z.boolean(),
    weightBasis: z.string(),
    horizonScaling: z.string(),
    distributionAssumption: z.string(),
    correlationMethod: z.string(),
    concentrationMetrics: z.string(),
    dataSource: z.string(),
    providerCallsOnHotPath: z.boolean(),
  })
  .passthrough();

const portfolioHistoricalVaRBlockSchema = z
  .object({
    status: z.string(),
    statusMessage: z.string().nullable().optional(),
    confidence: optionalFinite,
    horizonDays: z.number().int().nullable().optional(),
    varPct: optionalFinite,
    varValue: optionalFinite,
    observationCount: z.number().int(),
    percentileUsed: optionalFinite,
    oneDayVarPct: optionalFinite,
  })
  .passthrough();

const portfolioCorrelationBlockSchema = z
  .object({
    status: z.string(),
    statusMessage: z.string().nullable().optional(),
    symbols: z.array(z.string()).optional(),
    matrix: z
      .array(z.array(finiteNumber.nullable()))
      .optional(),
    observationCount: z.number().int(),
  })
  .passthrough();

const portfolioConcentrationBlockSchema = z
  .object({
    status: z.string(),
    hhi: optionalFinite,
    effectiveN: optionalFinite,
    diversificationScore: optionalFinite,
    topWeightPct: optionalFinite,
    positionCount: z.number().int(),
    weights: z.array(portfolioRiskWeightItemSchema).optional(),
  })
  .passthrough();

const portfolioRiskHistoryMetaSchema = z
  .object({
    alignedTradingDays: z.number().int(),
    lookbackTradingDaysRequested: z.number().int(),
    priceSeriesSymbols: z.array(z.string()).optional(),
    alignedStart: z.string().nullable().optional(),
    alignedEnd: z.string().nullable().optional(),
  })
  .passthrough();

const portfolioRiskMetricsResponseSchema = z
  .object({
    asOf: z.string(),
    accountId: z.number().int().nullable().optional(),
    costMethod: z.string(),
    currency: z.string(),
    status: z.string(),
    statusMessage: z.string().nullable().optional(),
    portfolioValue: finiteNumber,
    positionsUsed: z.number().int(),
    assumptions: portfolioRiskAssumptionsSchema,
    var: portfolioHistoricalVaRBlockSchema,
    correlation: portfolioCorrelationBlockSchema,
    concentration: portfolioConcentrationBlockSchema,
    history: portfolioRiskHistoryMetaSchema.nullable().optional(),
  })
  .passthrough();

function buildRiskMetricsParams(
  query: PortfolioRiskMetricsQuery,
): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (query.accountId != null) {
    params.account_id = query.accountId;
  }
  if (query.asOf) {
    params.as_of = query.asOf;
  }
  if (query.costMethod) {
    params.cost_method = query.costMethod;
  }
  if (query.confidence != null && Number.isFinite(query.confidence)) {
    params.confidence = query.confidence;
  }
  if (query.horizonDays != null && Number.isFinite(query.horizonDays)) {
    params.horizon_days = query.horizonDays;
  }
  if (query.lookbackTradingDays != null && Number.isFinite(query.lookbackTradingDays)) {
    params.lookback_trading_days = query.lookbackTradingDays;
  }
  return params;
}

function normalizeRiskMetrics(
  parsed: PortfolioRiskMetricsResponse,
): PortfolioRiskMetricsResponse {
  return {
    ...parsed,
    correlation: {
      ...parsed.correlation,
      symbols: Array.isArray(parsed.correlation.symbols) ? parsed.correlation.symbols : [],
      matrix: Array.isArray(parsed.correlation.matrix) ? parsed.correlation.matrix : [],
    },
    concentration: {
      ...parsed.concentration,
      weights: Array.isArray(parsed.concentration.weights) ? parsed.concentration.weights : [],
    },
    history: parsed.history
      ? {
          ...parsed.history,
          priceSeriesSymbols: Array.isArray(parsed.history.priceSeriesSymbols)
            ? parsed.history.priceSeriesSymbols
            : [],
        }
      : parsed.history,
  };
}

/**
 * Fetch portfolio risk metrics (historical VaR, correlation, concentration).
 * Never invents silent zeros: non-finite numerics fail validation.
 */
export async function getPortfolioRiskMetrics(
  query: PortfolioRiskMetricsQuery = {},
): Promise<PortfolioRiskMetricsResponse> {
  const response = await apiClient.get<Record<string, unknown>>(
    '/api/v1/portfolio/risk-metrics',
    { params: buildRiskMetricsParams(query) },
  );
  const parsed = parseCamelCasePayload<PortfolioRiskMetricsResponse>(
    response.data,
    portfolioRiskMetricsResponseSchema,
    'PortfolioRiskMetricsResponse',
    'portfolioRiskMetrics',
  );
  return normalizeRiskMetrics(parsed);
}

export const portfolioRiskMetricsApi = {
  getRiskMetrics: getPortfolioRiskMetrics,
};

export {
  portfolioRiskMetricsResponseSchema,
  finiteNumber as portfolioRiskFiniteNumberSchema,
};
