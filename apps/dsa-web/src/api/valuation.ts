// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import apiClient from './index';
import { createApiError, getParsedApiError } from './error';
import { parseCamelCasePayload } from './parseCamelCasePayload';

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
    return parseCamelCasePayload<ValuationEstimate>(
      response.data,
      valuationEstimateSchema,
      'ValuationEstimateResponse',
      'valuation',
    );
  } catch (error) {
    throw createApiError(getParsedApiError(error), { cause: error });
  }
}


const peerMetricCellSchema = z.object({
  value: z.number().nullable().optional(),
  status: z.string().optional(),
  missingReason: z.string().optional().nullable(),
  currency: z.string().nullable().optional(),
  nativeValue: z.number().nullable().optional(),
  nativeCurrency: z.string().nullable().optional(),
  fx: z.record(z.string(), z.unknown()).optional(),
}).passthrough();

const peerCanvasRowSchema = z.object({
  stockCode: z.string(),
  role: z.string().optional(),
  currency: z.string().optional().nullable(),
  nativeCurrency: z.string().optional().nullable(),
  metrics: z.record(z.string(), peerMetricCellSchema).optional(),
  dataStatus: z.string().optional(),
  missingMetrics: z.array(z.string()).optional(),
}).passthrough();

const peerValuationCanvasSchema = z.object({
  schemaVersion: z.string().optional(),
  status: z.string(),
  stockCode: z.string().optional().nullable(),
  baseCurrency: z.string().optional().nullable(),
  fxStale: z.boolean().optional().nullable(),
  peerSet: z.record(z.string(), z.unknown()).optional().nullable(),
  metrics: z.array(z.string()).optional(),
  multipleMetrics: z.array(z.string()).optional().nullable(),
  currencyMetrics: z.array(z.string()).optional().nullable(),
  rows: z.array(peerCanvasRowSchema).optional(),
  medians: z.record(z.string(), z.unknown()).optional().nullable(),
  relativeSummary: z.record(z.string(), z.unknown()).optional().nullable(),
  heatmapCells: z.array(z.record(z.string(), z.unknown())).optional().nullable(),
  valuationStatus: z.string().optional().nullable(),
  disclaimer: z.string().optional().nullable(),
  reason: z.string().optional().nullable(),
  message: z.string().optional().nullable(),
}).passthrough();

export type PeerValuationCanvas = z.infer<typeof peerValuationCanvasSchema>;

export type PeerValuationCanvasParams = {
  stockCode: string;
  peerSource?: 'custom' | 'industry';
  peerCodes?: string[];
  industryLabel?: string | null;
  baseCurrency?: string | null;
};

export async function buildPeerValuationCanvas(
  params: PeerValuationCanvasParams,
): Promise<PeerValuationCanvas> {
  try {
    const response = await apiClient.post('/api/v1/valuation/peer-canvas', {
      stock_code: params.stockCode,
      peer_source: params.peerSource ?? 'custom',
      peer_codes: params.peerCodes,
      industry_label: params.industryLabel ?? undefined,
      base_currency: params.baseCurrency ?? undefined,
    });
    return parseCamelCasePayload<PeerValuationCanvas>(
      response.data,
      peerValuationCanvasSchema,
      'PeerValuationCanvasResponse',
      'valuation',
    );
  } catch (error) {
    throw createApiError(getParsedApiError(error), { cause: error });
  }
}
