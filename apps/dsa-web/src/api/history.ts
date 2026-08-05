import { z } from 'zod';
import axios from 'axios';
import apiClient, { locallyRecoverableResourceConfig } from './index';
import { createApiError, createParsedApiError, getParsedApiError } from './error';
import { toCamelCase } from './utils';
import type {
  HistoryListResponse,
  HistoryItem,
  HistoryFilters,
  AnalysisReport,
  NewsIntelResponse,
  NewsIntelItem,
  RunDiagnosticSummary,
  StockBarResponse,
} from '../types/analysis';
import type { RunFlowSnapshot } from '../types/runFlow';
// Generated OpenAPI components document the backend snake_case contract for
// history list/detail/news/diagnostics/flow/delete/stock-bar responses.
import type { components } from '../types/api.generated';

type OpenApiHistoryListResponse = components['schemas']['HistoryListResponse'];
type OpenApiAnalysisReport = components['schemas']['AnalysisReport'];
type OpenApiNewsIntelResponse = components['schemas']['NewsIntelResponse'];
type OpenApiRunDiagnosticSummary = components['schemas']['RunDiagnosticSummaryResponse'];
type OpenApiRunFlowSnapshot = components['schemas']['RunFlowSnapshot'];
type OpenApiDeleteHistoryResponse = components['schemas']['DeleteHistoryResponse'];
type OpenApiStockBarResponse = components['schemas']['StockBarResponse'];
type OpenApiMarkdownReportResponse = components['schemas']['MarkdownReportResponse'];

type _AssertListFields = keyof OpenApiHistoryListResponse;
type _AssertReportFields = keyof OpenApiAnalysisReport;
type _AssertNewsFields = keyof OpenApiNewsIntelResponse;
type _AssertDiagFields = keyof OpenApiRunDiagnosticSummary;
type _AssertFlowFields = keyof OpenApiRunFlowSnapshot;
type _AssertDeleteFields = keyof OpenApiDeleteHistoryResponse;
type _AssertStockBarFields = keyof OpenApiStockBarResponse;
type _AssertMarkdownFields = keyof OpenApiMarkdownReportResponse;
const _listFieldAnchor: _AssertListFields = 'total';
const _reportFieldAnchor: _AssertReportFields = 'meta';
const _newsFieldAnchor: _AssertNewsFields = 'total';
const _diagFieldAnchor: _AssertDiagFields = 'copy_text';
const _flowFieldAnchor: _AssertFlowFields = 'generated_at';
const _deleteFieldAnchor: _AssertDeleteFields = 'deleted';
const _stockBarFieldAnchor: _AssertStockBarFields = 'total';
const _markdownFieldAnchor: _AssertMarkdownFields = 'content';
void _listFieldAnchor;
void _reportFieldAnchor;
void _newsFieldAnchor;
void _diagFieldAnchor;
void _flowFieldAnchor;
void _deleteFieldAnchor;
void _stockBarFieldAnchor;
void _markdownFieldAnchor;

// Cold Playwright / wkhtml renders of full history reports routinely exceed the
// global 30s axios default; keep that default and only stretch this endpoint.
export const SHARE_IMAGE_REQUEST_TIMEOUT_MS = 90_000;

/**
 * Zod schemas mirror the camelCase view of OpenAPI history schemas.
 * On success we return the pre-validated toCamelCase object (not schema output) so
 * valid payloads remain byte-identical to the previous unchecked cast path.
 */
const historyItemSchema = z.object({
  queryId: z.string(),
  stockCode: z.string(),
  id: z.number().nullable().optional(),
  stockName: z.string().nullable().optional(),
  reportType: z.string().nullable().optional(),
  region: z.string().nullable().optional(),
  trendPrediction: z.string().nullable().optional(),
  analysisSummary: z.string().nullable().optional(),
  sentimentScore: z.number().nullable().optional(),
  operationAdvice: z.string().nullable().optional(),
  action: z.string().nullable().optional(),
  actionLabel: z.string().nullable().optional(),
  currentPrice: z.number().nullable().optional(),
  changePct: z.number().nullable().optional(),
  volumeRatio: z.number().nullable().optional(),
  turnoverRate: z.number().nullable().optional(),
  modelUsed: z.string().nullable().optional(),
  marketPhaseSummary: z.unknown().nullable().optional(),
  createdAt: z.string().nullable().optional(),
}).passthrough();

const historyListResponseSchema = z.object({
  total: z.number(),
  page: z.number(),
  limit: z.number(),
  items: z.array(historyItemSchema).optional(),
}).passthrough();

const reportMetaSchema = z.object({
  queryId: z.string(),
  stockCode: z.string(),
  stockName: z.string().nullable().optional(),
  reportType: z.string().nullable().optional(),
  reportLanguage: z.string().nullable().optional(),
  createdAt: z.string().nullable().optional(),
  currentPrice: z.number().nullable().optional(),
  changePct: z.number().nullable().optional(),
  modelUsed: z.string().nullable().optional(),
  id: z.number().nullable().optional(),
  marketPhaseSummary: z.unknown().nullable().optional(),
}).passthrough();

const reportSummarySchema = z.object({
  analysisSummary: z.string().nullable().optional(),
  operationAdvice: z.string().nullable().optional(),
  action: z.string().nullable().optional(),
  actionLabel: z.string().nullable().optional(),
  trendPrediction: z.string().nullable().optional(),
  sentimentScore: z.number().nullable().optional(),
  sentimentLabel: z.string().nullable().optional(),
}).passthrough();

const analysisReportSchema = z.object({
  meta: reportMetaSchema,
  summary: reportSummarySchema,
  strategy: z.unknown().nullable().optional(),
  details: z.unknown().nullable().optional(),
}).passthrough();

const newsIntelItemSchema = z.object({
  title: z.string(),
  snippet: z.string(),
  url: z.string(),
}).passthrough();

const newsIntelResponseSchema = z.object({
  total: z.number(),
  items: z.array(newsIntelItemSchema).optional(),
}).passthrough();

const markdownReportResponseSchema = z.object({
  content: z.string(),
}).passthrough();

const runDiagnosticComponentSchema = z.object({
  key: z.string(),
  label: z.string(),
  status: z.string(),
  message: z.string(),
  details: z.record(z.string(), z.unknown()).nullable().optional(),
}).passthrough();

const runDiagnosticSummarySchema = z.object({
  status: z.string(),
  statusLabel: z.string(),
  reason: z.string(),
  copyText: z.string(),
  components: z.record(z.string(), runDiagnosticComponentSchema).optional(),
  traceId: z.string().nullable().optional(),
  taskId: z.string().nullable().optional(),
  queryId: z.string().nullable().optional(),
  stockCode: z.string().nullable().optional(),
  triggerSource: z.string().nullable().optional(),
}).passthrough();

const runFlowSummarySchema = z.object({
  dataSourceCount: z.number(),
  eventCount: z.number(),
  failedAttempts: z.number(),
  fallbackCount: z.number(),
  elapsedMs: z.number().nullable().optional(),
  bottleneckNodeId: z.string().nullable().optional(),
  model: z.string().nullable().optional(),
}).passthrough();

const runFlowSnapshotSchema = z.object({
  taskId: z.string(),
  stockCode: z.string(),
  status: z.string(),
  generatedAt: z.string(),
  schemaVersion: z.string().optional(),
  summary: runFlowSummarySchema,
  stockName: z.string().nullable().optional(),
  traceId: z.string().nullable().optional(),
  lanes: z.array(z.unknown()).optional(),
  nodes: z.array(z.unknown()).optional(),
  edges: z.array(z.unknown()).optional(),
  events: z.array(z.unknown()).optional(),
}).passthrough();

const deleteHistoryResponseSchema = z.object({
  deleted: z.number(),
}).passthrough();

const stockBarItemSchema = z.object({
  id: z.number(),
  stockCode: z.string(),
  analysisCount: z.number(),
  stockName: z.string().nullable().optional(),
  reportType: z.string().nullable().optional(),
  sentimentScore: z.number().nullable().optional(),
  operationAdvice: z.string().nullable().optional(),
  action: z.string().nullable().optional(),
  actionLabel: z.string().nullable().optional(),
  lastAnalysisTime: z.string().nullable().optional(),
  modelUsed: z.string().nullable().optional(),
  marketPhaseSummary: z.unknown().nullable().optional(),
}).passthrough();

const stockBarResponseSchema = z.object({
  total: z.number(),
  items: z.array(stockBarItemSchema).optional(),
}).passthrough();

function parseCamelCasePayload<T>(
  data: unknown,
  schema: z.ZodTypeAny,
  label: string,
): T {
  const camel = toCamelCase<unknown>(data);
  const result = schema.safeParse(camel);
  if (!result.success) {
    const issueSummary = result.error.issues
      .slice(0, 5)
      .map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`)
      .join('; ');
    if (import.meta.env.DEV) {
      console.error(`[history] response validation failed (${label})`, result.error.issues);
    }
    throw createApiError(
      createParsedApiError({
        title: '响应校验失败',
        message: `接口响应未通过校验（${label}）。${issueSummary}`,
        rawMessage: result.error.message,
        category: 'unknown',
        code: 'api_response_validation_failed',
        params: { label, issues: issueSummary },
        details: result.error.issues,
      }),
    );
  }
  return camel as T;
}

async function rethrowShareImageBlobError(error: unknown): Promise<never> {
  if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
    const contentType = String(error.response.headers?.['content-type'] ?? '');
    const looksJson = contentType.includes('json') || contentType.includes('text');
    if (looksJson || error.response.status >= 400) {
      try {
        const text = await error.response.data.text();
        const data = text ? JSON.parse(text) as unknown : undefined;
        const hydrated = {
          ...error,
          response: {
            ...error.response,
            data,
          },
        };
        throw createApiError(getParsedApiError(hydrated), {
          response: hydrated.response,
          code: error.code,
          cause: error,
        });
      } catch (parseOrApiError) {
        if (parseOrApiError instanceof Error && parseOrApiError.name === 'ApiRequestError') {
          throw parseOrApiError;
        }
        // Fall through when the body is not JSON.
      }
    }
  }
  throw error;
}

// ============ API Interface ============

export interface GetHistoryListParams extends HistoryFilters {
  page?: number;
  limit?: number;
}

export const historyApi = {
  /**
   * Get the history analysis list
   * @param params Filtering and pagination parameters
   */
  getList: async (params: GetHistoryListParams = {}): Promise<HistoryListResponse> => {
    const { stockCode, reportType, startDate, endDate, page = 1, limit = 20 } = params;

    const queryParams: Record<string, string | number> = { page, limit };
    if (stockCode) queryParams.stock_code = stockCode;
    if (reportType) queryParams.report_type = reportType;
    if (startDate) queryParams.start_date = startDate;
    if (endDate) queryParams.end_date = endDate;

    const response = await apiClient.get<Record<string, unknown>>('/api/v1/history', {
      params: queryParams,
    });

    const data = parseCamelCasePayload<{
      total: number;
      page: number;
      limit: number;
      items?: HistoryItem[];
    }>(response.data, historyListResponseSchema, 'HistoryListResponse');

    // OpenAPI marks items optional; consumers always expect an array.
    // Map items through toCamelCase for nested parity with the prior path.
    const items = (data.items ?? []).map((item) => toCamelCase<HistoryItem>(item));
    return {
      total: data.total,
      page: data.page,
      limit: data.limit,
      items,
    };
  },

  /**
   * Get details of the historical report
   * @param recordId Analysis historical record primary key ID (Use ID instead of query_id, because query_id may be repeated in batch analysis)
   */
  getDetail: async (recordId: number): Promise<AnalysisReport> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/history/${recordId}`,
      locallyRecoverableResourceConfig(),
    );
    return parseCamelCasePayload<AnalysisReport>(
      response.data,
      analysisReportSchema,
      'AnalysisReport',
    );
  },

  /**
   * Get historical report related news
   * @param recordId Analysis historical record primary key ID
   * @param limit Return count limit
   */
  getNews: async (recordId: number, limit = 20): Promise<NewsIntelResponse> => {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/history/${recordId}/news`, {
      params: { limit },
    });

    const data = parseCamelCasePayload<NewsIntelResponse>(
      response.data,
      newsIntelResponseSchema,
      'NewsIntelResponse',
    );
    return {
      total: data.total,
      items: (data.items || []).map((item) => toCamelCase<NewsIntelItem>(item)),
    };
  },

  /**
   * Get the Markdown format content of the historical report
   * @param recordId Analysis historical record primary key ID
   * @returns Markdown Complete report content in the format.
   */
  getMarkdown: async (recordId: number): Promise<string> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/history/${recordId}/markdown`,
    );
    const data = parseCamelCasePayload<{ content: string }>(
      response.data,
      markdownReportResponseSchema,
      'MarkdownReportResponse',
    );
    return data.content;
  },

  /**
   * Generate a share PNG for a history record.
   * Uses a longer per-request timeout than the global 30s default because cold
   * Playwright/wkhtml renders of full reports commonly exceed that bound.
   * Binary blob response — no JSON schema validation (OpenAPI binary content).
   */
  getShareImage: async (recordId: number): Promise<Blob> => {
    try {
      const response = await apiClient.get<Blob>(`/api/v1/history/${recordId}/share-image`, {
        responseType: 'blob',
        timeout: SHARE_IMAGE_REQUEST_TIMEOUT_MS,
      });
      return response.data;
    } catch (error) {
      // responseType: 'blob' makes error bodies Blobs; rehydrate JSON so ParsedApiError
      // can surface share_image_* codes and install/length guidance.
      throw await rethrowShareImageBlobError(error);
    }
  },

  /**
   * Get historical report run diagnostic summary
   * @param recordId Analysis historical record primary key ID
   */
  getDiagnostics: async (recordId: number): Promise<RunDiagnosticSummary> => {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/history/${recordId}/diagnostics`);
    return parseCamelCasePayload<RunDiagnosticSummary>(
      response.data,
      runDiagnosticSummarySchema,
      'RunDiagnosticSummaryResponse',
    );
  },

  /**
   * Get historical report run snapshot
   * @param recordId Analysis historical record primary key ID
   */
  getRecordFlow: async (recordId: number): Promise<RunFlowSnapshot> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/history/${recordId}/flow`,
      locallyRecoverableResourceConfig(),
    );
    return parseCamelCasePayload<RunFlowSnapshot>(
      response.data,
      runFlowSnapshotSchema,
      'RunFlowSnapshot',
    );
  },

  /**
   * Batch delete historical records
   * @param recordIds Analysis historical record key list
   */
  deleteRecords: async (recordIds: number[]): Promise<{ deleted: number }> => {
    const response = await apiClient.delete<Record<string, unknown>>('/api/v1/history', {
      data: { record_ids: recordIds },
    });

    return parseCamelCasePayload<{ deleted: number }>(
      response.data,
      deleteHistoryResponseSchema,
      'DeleteHistoryResponse',
    );
  },

  /**
   * Delete all historical records by stock code.
   * @param stockCode Stock Code
   */
  deleteByCode: async (stockCode: string): Promise<{ deleted: number }> => {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/history/by-code/${encodeURIComponent(stockCode)}`);
    return parseCamelCasePayload<{ deleted: number }>(
      response.data,
      deleteHistoryResponseSchema,
      'DeleteHistoryResponse',
    );
  },

  /**
   * Get the list of individual stock columns (no duplicate stocks, not including market review).
   */
  getStockBarList: async (params: {
    startDate?: string;
    endDate?: string;
    limit?: number;
  } = {}): Promise<StockBarResponse> => {
    const queryParams: Record<string, string | number> = {};
    if (params.startDate) queryParams.start_date = params.startDate;
    if (params.endDate) queryParams.end_date = params.endDate;
    if (params.limit) queryParams.limit = params.limit;

    const response = await apiClient.get<Record<string, unknown>>('/api/v1/history/stocks', {
      params: queryParams,
    });

    const data = parseCamelCasePayload<{ total: number; items?: unknown[] }>(
      response.data,
      stockBarResponseSchema,
      'StockBarResponse',
    );
    return {
      total: data.total,
      items: (data.items ?? []).map(
        (item) => toCamelCase<Record<string, unknown>>(item) as unknown as StockBarResponse['items'][number],
      ),
    };
  },
};
