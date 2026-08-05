import axios from 'axios';
import apiClient, { locallyRecoverableResourceConfig } from './index';
import { createApiError, getParsedApiError } from './error';
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

// Cold Playwright / wkhtml renders of full history reports routinely exceed the
// global 30s axios default; keep that default and only stretch this endpoint.
export const SHARE_IMAGE_REQUEST_TIMEOUT_MS = 90_000;

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

    const data = toCamelCase<{ total: number; page: number; limit: number; items: HistoryItem[] }>(response.data);
    return {
      total: data.total,
      page: data.page,
      limit: data.limit,
      items: data.items.map(item => toCamelCase<HistoryItem>(item)),
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
    return toCamelCase<AnalysisReport>(response.data);
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

    const data = toCamelCase<NewsIntelResponse>(response.data);
    return {
      total: data.total,
      items: (data.items || []).map(item => toCamelCase<NewsIntelItem>(item)),
    };
  },

  /**
   * Get the Markdown format content of the historical report
   * @param recordId Analysis historical record primary key ID
   * @returns Markdown Complete report content in the format.
   */
  getMarkdown: async (recordId: number): Promise<string> => {
    const response = await apiClient.get<{ content: string }>(`/api/v1/history/${recordId}/markdown`);
    return response.data.content;
  },

  /**
   * Generate a share PNG for a history record.
   * Uses a longer per-request timeout than the global 30s default because cold
   * Playwright/wkhtml renders of full reports commonly exceed that bound.
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
    return toCamelCase<RunDiagnosticSummary>(response.data);
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
    return toCamelCase<RunFlowSnapshot>(response.data);
  },

  /**
   * Batch delete historical records
   * @param recordIds Analysis historical record key list
   */
  deleteRecords: async (recordIds: number[]): Promise<{ deleted: number }> => {
    const response = await apiClient.delete<Record<string, unknown>>('/api/v1/history', {
      data: { record_ids: recordIds },
    });

    return toCamelCase<{ deleted: number }>(response.data);
  },

  /**
   * Delete all historical records by stock code.
   * @param stockCode Stock Code
   */
  deleteByCode: async (stockCode: string): Promise<{ deleted: number }> => {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/history/by-code/${encodeURIComponent(stockCode)}`);
    return toCamelCase<{ deleted: number }>(response.data);
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

    const data = toCamelCase<{ total: number; items: unknown[] }>(response.data);
    return {
      total: data.total,
      items: data.items.map(item => toCamelCase<Record<string, unknown>>(item) as unknown as typeof data.items[0]),
    } as StockBarResponse;
  },
};
