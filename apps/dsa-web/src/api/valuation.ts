// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import apiClient from './index';
import { createApiError, getParsedApiError } from './error';
import { toCamelCase } from './utils';

const sensitivityRowSchema = z.object({
  growthRate: z.number().optional(),
  discountRate: z.number().optional(),
  terminalGrowthRate: z.number().optional(),
  equityValue: z.number().optional(),
}).passthrough();

const dcfSchema = z.object({
  status: z.string().optional(),
  equityValue: z.number().optional().nullable(),
  enterpriseValue: z.number().optional().nullable(),
  intrinsicValuePerShare: z.number().optional().nullable(),
  assumptions: z.record(z.string(), z.unknown()).optional(),
  sensitivity: z.object({
    rows: z.array(sensitivityRowSchema).optional(),
    equityValueLow: z.number().optional().nullable(),
    equityValueMid: z.number().optional().nullable(),
    equityValueHigh: z.number().optional().nullable(),
  }).passthrough().optional(),
  market: z.record(z.string(), z.unknown()).optional(),
  message: z.string().optional(),
  reason: z.string().optional(),
}).passthrough();

const valuationEstimateSchema = z.object({
  schemaVersion: z.string().optional(),
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
    return valuationEstimateSchema.parse(toCamelCase(response.data) as unknown);
  } catch (error) {
    throw createApiError(getParsedApiError(error), { cause: error });
  }
}
