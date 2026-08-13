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

type OpenApiPeerValuationCanvas = components['schemas']['PeerValuationCanvasResponse'];
type _AssertPeerCanvas = keyof OpenApiPeerValuationCanvas;
const _peerCanvasAnchor: _AssertPeerCanvas = 'status';
void _peerCanvasAnchor;

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
    // Preserve fail-closed validation errors from parseCamelCasePayload.
    if (isApiRequestError(error)) throw error;
    throw createApiError(getParsedApiError(error), { cause: error });
  }
}
