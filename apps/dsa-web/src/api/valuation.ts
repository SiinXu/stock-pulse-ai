// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import type { components } from '../types/api.generated';
import apiClient from './index';
import { createApiError, getParsedApiError, isApiRequestError } from './error';
import { parseCamelCasePayload } from './parseCamelCasePayload';

type OpenApiValuationEstimate = components['schemas']['ValuationEstimateResponse'];
type _AssertValuation = keyof OpenApiValuationEstimate;
const _valuationAnchor: _AssertValuation = 'schema_version';
void _valuationAnchor;

const finiteNumber = z.number().refine((value) => Number.isFinite(value), {
  message: 'non-finite number rejected',
});
const optionalFinite = finiteNumber.nullable().optional();

const sensitivityRowSchema = z.object({
  growthRate: optionalFinite,
  discountRate: optionalFinite,
  terminalGrowthRate: optionalFinite,
  equityValue: optionalFinite,
}).passthrough();

const dcfSchema = z.object({
  status: z.string().optional(),
  equityValue: optionalFinite,
  enterpriseValue: optionalFinite,
  intrinsicValuePerShare: optionalFinite,
  assumptions: z.record(z.string(), z.unknown()).optional(),
  sensitivity: z.object({
    rows: z.array(sensitivityRowSchema).optional(),
    equityValueLow: optionalFinite,
    equityValueMid: optionalFinite,
    equityValueHigh: optionalFinite,
  }).passthrough().optional(),
  market: z.record(z.string(), z.unknown()).optional(),
  message: z.string().optional(),
  reason: z.string().optional(),
}).passthrough();

const valuationEstimateSchema = z.object({
  schemaVersion: z.string(),
  status: z.string(),
  stockCode: z.string(),
  dcf: dcfSchema.optional(),
  relative: z.record(z.string(), z.unknown()).optional(),
  fundamentalsSnapshot: z.record(z.string(), z.unknown()).optional().nullable(),
  disclaimer: z.string().optional().nullable(),
  reason: z.string().optional().nullable(),
  message: z.string().optional().nullable(),
}).passthrough();

export type ValuationEstimate = z.infer<typeof valuationEstimateSchema>;

export type ValuationEstimateParams = {
  stockCode: string;
  growthRate?: number | null;
  discountRate?: number | null;
  terminalGrowthRate?: number | null;
  projectionYears?: number | null;
  peerCodes?: string[];
};

export async function estimateStockValuation(params: ValuationEstimateParams): Promise<ValuationEstimate> {
  try {
    const response = await apiClient.post('/api/v1/valuation/estimate', {
      stock_code: params.stockCode,
      growth_rate: params.growthRate ?? undefined,
      discount_rate: params.discountRate ?? undefined,
      terminal_growth_rate: params.terminalGrowthRate ?? undefined,
      projection_years: params.projectionYears ?? undefined,
      peer_codes: params.peerCodes,
    });
    return parseCamelCasePayload<ValuationEstimate>(
      response.data,
      valuationEstimateSchema,
      'ValuationEstimateResponse',
      'valuation',
    );
  } catch (error) {
    // Preserve fail-closed validation errors from parseCamelCasePayload.
    if (isApiRequestError(error)) throw error;
    throw createApiError(getParsedApiError(error), { cause: error });
  }
}
