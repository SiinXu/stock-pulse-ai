import { z } from 'zod';
import apiClient from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { StockFieldTrustResponse, StockHistoryResponse, StockQuote } from '../types/stocks';
// Generated OpenAPI components document the backend snake_case contract for
// StockQuote / StockHistoryResponse / ExtractFromImageResponse. Runtime
// validation below targets the camelCase shape consumers already use after
// toCamelCase conversion.
import type { components, operations } from '../types/api.generated';

type OpenApiStockQuote = components['schemas']['StockQuote'];
type OpenApiStockHistoryResponse = components['schemas']['StockHistoryResponse'];
type OpenApiStockFieldTrustResponse = components['schemas']['StockFieldTrustResponse'];
type OpenApiExtractResponse = components['schemas']['ExtractFromImageResponse'];
type OpenApiExtractItem = components['schemas']['ExtractItem'];
type OpenApiExtractBody = operations['extract_from_image_api_v1_stocks_extract_from_image_post']['responses']['200']['content']['application/json'];
type OpenApiParseBody = operations['parse_import_api_v1_stocks_parse_import_post']['responses']['200']['content']['application/json'];

// Compile-time anchor: hand-written camelCase types stay aligned with OpenAPI
// field sets (rename detection is structural; extra optional UI fields are fine).
type _AssertQuoteFields = keyof OpenApiStockQuote;
type _AssertHistoryFields = keyof OpenApiStockHistoryResponse;
type _AssertTrustFields = keyof OpenApiStockFieldTrustResponse;
const _quoteFieldAnchor: _AssertQuoteFields = 'stock_code';
const _historyFieldAnchor: _AssertHistoryFields = 'stock_code';
const _trustFieldAnchor: _AssertTrustFields = 'stock_code';
const _extractCodesAnchor: keyof OpenApiExtractResponse = 'codes';
const _extractRawTextAnchor: keyof OpenApiExtractResponse = 'raw_text';
const _extractItemAnchor: keyof OpenApiExtractItem = 'confidence';
void _quoteFieldAnchor;
void _historyFieldAnchor;
void _trustFieldAnchor;
void _extractCodesAnchor;
void _extractRawTextAnchor;
void _extractItemAnchor;

type _AssertExtractIsComponent = OpenApiExtractBody extends OpenApiExtractResponse
  ? OpenApiExtractResponse extends OpenApiExtractBody
    ? true
    : never
  : never;
type _AssertParseIsComponent = OpenApiParseBody extends OpenApiExtractResponse
  ? OpenApiExtractResponse extends OpenApiParseBody
    ? true
    : never
  : never;
const _extractBodyIsComponent: _AssertExtractIsComponent = true;
const _parseBodyIsComponent: _AssertParseIsComponent = true;
void _extractBodyIsComponent;
void _parseBodyIsComponent;

function toStockCodePath(stockCode: string): string {
  const trimmed = stockCode.trim();
  if (!trimmed) throw new Error('Stock code is required');
  if (trimmed.includes('/')) {
    throw new Error(
      'Stock code cannot contain "/" because the backend route accepts a single path segment; use 600519, HK00700, or AAPL.',
    );
  }
  return encodeURIComponent(trimmed);
}

/**
 * Zod schemas mirror the camelCase view of OpenAPI StockQuote / StockHistoryResponse.
 * On success we return the pre-validated toCamelCase object (not schema output) so
 * valid payloads remain byte-identical to the previous unchecked cast path.
 */
const stockQuoteSchema = z.object({
  stockCode: z.string(),
  stockName: z.string().nullable().optional(),
  currentPrice: z.number(),
  change: z.number().nullable().optional(),
  changePercent: z.number().nullable().optional(),
  open: z.number().nullable().optional(),
  high: z.number().nullable().optional(),
  low: z.number().nullable().optional(),
  prevClose: z.number().nullable().optional(),
  volume: z.number().nullable().optional(),
  amount: z.number().nullable().optional(),
  updateTime: z.string().nullable().optional(),
}).passthrough();

const stockHistoryCandleSchema = z.object({
  date: z.string(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  volume: z.number().nullable().optional(),
  amount: z.number().nullable().optional(),
  changePercent: z.number().nullable().optional(),
}).passthrough();

// OpenAPI StockHistoryResponse.required = ["stock_code","period"]; data is optional.
const stockHistoryResponseSchema = z.object({
  stockCode: z.string(),
  stockName: z.string().nullable().optional(),
  period: z.string(),
  data: z.array(stockHistoryCandleSchema).optional(),
}).passthrough();

const fieldTrustEntrySchema = z.object({
  field: z.string().min(1),
  value: z.number().finite().nullable().optional(),
  source: z.string().nullable().optional(),
  origin: z.enum(['primary', 'supplement', 'unknown']),
  providerTimestamp: z.string().nullable().optional(),
  staleSeconds: z.number().int().nonnegative().nullable().optional(),
  isStale: z.boolean().nullable().optional(),
  staleness: z.enum(['fresh', 'stale', 'unknown']),
  conflict: z.boolean(),
}).passthrough();

const fieldTrustConflictSchema = z.object({
  field: z.string().min(1),
  severity: z.string().min(1),
  relativeDifference: z.number().finite().nullable().optional(),
  threshold: z.number().finite().nullable().optional(),
  values: z.array(z.object({
    provider: z.string().min(1),
    value: z.number().finite(),
  }).passthrough()),
}).passthrough();

const fieldTrustConflictCheckSchema = z.object({
  primaryProvider: z.string().nullable().optional(),
  secondaryProvider: z.string().nullable().optional(),
  status: z.enum(['evaluated', 'skipped']),
  reason: z.string().nullable().optional(),
}).passthrough();

const fieldTrustProviderHealthSchema = z.object({
  provider: z.string().min(1),
  status: z.enum(['ok', 'failed', 'empty', 'unavailable']),
  role: z.enum(['primary', 'supplement', 'attempted']),
  circuitState: z.string().nullable().optional(),
  available: z.boolean().nullable().optional(),
  healthScore: z.number().finite().nullable().optional(),
}).passthrough();

const fieldTrustAnalysisInputSchema = z.object({
  schemaVersion: z.literal('field_trust_analysis_input/1.0'),
  confidence: z.enum(['high', 'medium', 'low']),
  gaps: z.array(z.object({
    code: z.string().min(1),
    field: z.string().nullable().optional(),
    detail: z.string().nullable().optional(),
  }).passthrough()),
  conflictCount: z.number().int().nonnegative(),
  failedProviderCount: z.number().int().nonnegative(),
}).passthrough();

const stockFieldTrustResponseSchema = z.object({
  schemaVersion: z.literal('field_trust_view/1.0'),
  stockCode: z.string().min(1),
  status: z.enum(['ok', 'degraded', 'unavailable']),
  metadataPresent: z.boolean(),
  quoteSource: z.string().nullable().optional(),
  fetchedAt: z.string().nullable().optional(),
  providerTimestamp: z.string().nullable().optional(),
  staleSeconds: z.number().int().nonnegative().nullable().optional(),
  isStale: z.boolean().nullable().optional(),
  fallbackFrom: z.string().nullable().optional(),
  dataQuality: z.string().nullable().optional(),
  missingFields: z.array(z.string()),
  fields: z.array(fieldTrustEntrySchema),
  conflicts: z.array(fieldTrustConflictSchema),
  conflictChecks: z.array(fieldTrustConflictCheckSchema),
  providerHealth: z.array(fieldTrustProviderHealthSchema),
  analysisInput: fieldTrustAnalysisInputSchema.nullable().optional(),
  message: z.string().nullable().optional(),
}).passthrough();

const extractItemSchema = z.object({
  code: z.string().nullable().optional(),
  name: z.string().nullable().optional(),
  confidence: z.string().optional(),
}).passthrough();

const extractFromImageResponseSchema = z.object({
  codes: z.array(z.string()),
  items: z.array(extractItemSchema).optional(),
  rawText: z.string().nullable().optional(),
}).passthrough();

export type ExtractItem = {
  code?: string | null;
  name?: string | null;
  confidence: string;
};

export type ExtractFromImageResponse = {
  codes: string[];
  items?: ExtractItem[];
  rawText?: string | null;
};

function parseExtractResponse(data: unknown): ExtractFromImageResponse {
  return parseCamelCasePayload<ExtractFromImageResponse>(
    data,
    extractFromImageResponseSchema,
    'ExtractFromImageResponse',
    'stocks',
  );
}

export const stocksApi = {
  async getFieldTrust(stockCode: string): Promise<StockFieldTrustResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/stocks/${toStockCodePath(stockCode)}/trust`,
    );
    return parseCamelCasePayload<StockFieldTrustResponse>(
      response.data,
      stockFieldTrustResponseSchema,
      'StockFieldTrustResponse',
      'stocks',
    );
  },

  async getQuote(stockCode: string): Promise<StockQuote> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/stocks/${toStockCodePath(stockCode)}/quote`,
    );
    return parseCamelCasePayload<StockQuote>(response.data, stockQuoteSchema, 'StockQuote', 'stocks');
  },

  // The backend only implements daily candles; weekly/monthly are aggregated
  // client-side, so this always requests the daily series.
  async getDailyHistory(stockCode: string, days = 30): Promise<StockHistoryResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/stocks/${toStockCodePath(stockCode)}/history`,
      { params: { period: 'daily', days } },
    );
    const history = parseCamelCasePayload<StockHistoryResponse>(
      response.data,
      stockHistoryResponseSchema,
      'StockHistoryResponse',
      'stocks',
    );
    // OpenAPI marks data optional; consumers always expect an array.
    if (!Array.isArray(history.data)) {
      return { ...history, data: [] };
    }
    return history;
  },

  async extractFromImage(file: File): Promise<ExtractFromImageResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const headers: { [key: string]: string | undefined } = { 'Content-Type': undefined };
    const response = await apiClient.post(
      '/api/v1/stocks/extract-from-image',
      formData,
      {
        headers,
        timeout: 60000, // Vision API can be slow; 60s
      },
    );

    return parseExtractResponse(response.data);
  },

  async parseImport(file?: File, text?: string): Promise<ExtractFromImageResponse> {
    if (file) {
      const formData = new FormData();
      formData.append('file', file);
      const headers: { [key: string]: string | undefined } = { 'Content-Type': undefined };
      const response = await apiClient.post('/api/v1/stocks/parse-import', formData, { headers });
      return parseExtractResponse(response.data);
    }
    if (text) {
      const response = await apiClient.post('/api/v1/stocks/parse-import', { text });
      return parseExtractResponse(response.data);
    }
    throw new Error('请提供文件或粘贴文本');
  },
};
