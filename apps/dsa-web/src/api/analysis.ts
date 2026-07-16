import apiClient, { locallyRecoverableResourceConfig } from './index';
import {
  createApiError,
  createParsedApiError,
  parseApiError,
  type ParsedApiError,
} from './error';
import { toCamelCase } from './utils';
import type {
  AnalysisRequest,
  AnalysisResult,
  AnalyzeResponse,
  AnalyzeAsyncResponse,
  AnalysisReport,
  MarketReviewAccepted,
  MarketReviewRequest,
  TaskStatus,
  TaskListResponse,
} from '../types/analysis';
import type { RunFlowSnapshot } from '../types/runFlow';

// ============ API Interfaces ============

export const analysisApi = {
  /**
   * Trigger stock analysis.
   * @param data Analysis request payload
   * @returns Sync mode returns AnalysisResult; async mode returns accepted task payloads
   */
  analyze: async (data: AnalysisRequest): Promise<AnalyzeResponse> => {
    const requestData = {
      stock_code: data.stockCode,
      stock_codes: data.stockCodes,
      report_type: data.reportType || 'detailed',
      force_refresh: data.forceRefresh || false,
      async_mode: data.asyncMode || false,
      analysis_phase: data.analysisPhase || 'auto',
      stock_name: data.stockName,
      original_query: data.originalQuery,
      selection_source: data.selectionSource,
      skills: data.skills,
      report_language: data.reportLanguage,
      ...(data.notify !== undefined && { notify: data.notify }),
    };

    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/analysis/analyze',
      requestData
    );

    const result = toCamelCase<AnalyzeResponse>(response.data);

    // Ensure the sync analysis report payload is converted recursively.
    if ('report' in result && result.report) {
      result.report = toCamelCase<AnalysisReport>(result.report);
    }

    return result;
  },

  /**
   * Trigger analysis in async mode.
   * @param data Analysis request payload
   * @returns Accepted task payloads; throws DuplicateTaskError on 409
   */
  analyzeAsync: async (data: AnalysisRequest): Promise<AnalyzeAsyncResponse> => {
    const requestData = {
      stock_code: data.stockCode,
      stock_codes: data.stockCodes,
      report_type: data.reportType || 'detailed',
      force_refresh: data.forceRefresh || false,
      async_mode: true,
      analysis_phase: data.analysisPhase || 'auto',
      stock_name: data.stockName,
      original_query: data.originalQuery,
      selection_source: data.selectionSource,
      skills: data.skills,
      report_language: data.reportLanguage,
      ...(data.notify !== undefined && { notify: data.notify }),
    };

    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/analysis/analyze',
      requestData,
      {
        // Allow 202 accepted responses in addition to standard success codes.
        validateStatus: (status) => status === 200 || status === 202 || status === 409,
      }
    );

    // Handle duplicate submission compatibility.
    if (response.status === 409) {
      const responseLike = { status: response.status, data: response.data };
      const parsed = parseApiError({ response: responseLike });
      if (parsed.code !== 'duplicate_task') {
        throw createApiError(parsed, { response: responseLike });
      }
      const stockCode = String(
        parsed.params?.stock_code
          ?? parsed.params?.stockCode
          ?? data.stockCode
          ?? (data.stockCodes?.length === 1 ? data.stockCodes[0] : '')
          ?? '',
      );
      const existingTaskId = String(
        parsed.params?.existing_task_id
          ?? parsed.params?.existingTaskId
          ?? '',
      );
      throw new DuplicateTaskError(
        stockCode,
        existingTaskId,
        parsed,
      );
    }

    return toCamelCase<AnalyzeAsyncResponse>(response.data);
  },

  /**
   * Trigger market review in background mode.
   */
  triggerMarketReview: async (data: MarketReviewRequest = {}): Promise<MarketReviewAccepted> => {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/analysis/market-review',
      {
        send_notification: data.sendNotification ?? true,
        report_language: data.reportLanguage,
      },
      {
        validateStatus: (status) => status === 202 || status === 409,
      }
    );

    if (response.status === 409) {
      const responseLike = { status: response.status, data: response.data };
      throw createApiError(
        parseApiError({ response: responseLike }),
        { response: responseLike },
      );
    }

    return toCamelCase<MarketReviewAccepted>(response.data);
  },

  /**
   * Get async task status.
   * @param taskId Task ID
   */
  getStatus: async (taskId: string): Promise<TaskStatus> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/analysis/status/${taskId}`
    );

    const data = toCamelCase<TaskStatus>(response.data);

    // Ensure nested result payloads are converted recursively.
    if (data.result) {
      data.result = toCamelCase<AnalysisResult>(data.result);
      if (data.result.report) {
        data.result.report = toCamelCase<AnalysisReport>(data.result.report);
      }
    }

    return data;
  },

  /**
   * Get task list.
   * @param params Filter parameters
   */
  getTasks: async (params?: {
    status?: string;
    limit?: number;
  }): Promise<TaskListResponse> => {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/analysis/tasks',
      { params }
    );

    const data = toCamelCase<TaskListResponse>(response.data);

    return data;
  },

  /**
   * Get a run-flow snapshot for an active analysis task.
   * @param taskId Task ID
   */
  getTaskFlow: async (taskId: string): Promise<RunFlowSnapshot> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/analysis/tasks/${encodeURIComponent(taskId)}/flow`,
      locallyRecoverableResourceConfig(),
    );

    return toCamelCase<RunFlowSnapshot>(response.data);
  },

  /**
   * Get the SSE stream URL.
   */
  getTaskStreamUrl: (): string => {
    // Read API base URL from the shared client.
    const baseUrl = apiClient.defaults.baseURL || '';
    return `${baseUrl}/api/v1/analysis/tasks/stream`;
  },
};

// ============ Custom Error Classes ============

/**
 * Duplicate task error.
 */
export class DuplicateTaskError extends Error {
  readonly code = 'duplicate_task' as const;
  readonly stockCode: string;
  readonly existingTaskId: string;
  readonly params: Record<string, unknown>;
  readonly details?: unknown;
  readonly traceId?: string;
  readonly parsedError: ParsedApiError;

  constructor(stockCode: string, existingTaskId: string, error?: string | ParsedApiError) {
    const params = typeof error === 'string'
      ? { stock_code: stockCode, existing_task_id: existingTaskId }
      : { stock_code: stockCode, existing_task_id: existingTaskId, ...(error?.params ?? {}) };
    const parsed = typeof error === 'string' || error === undefined
      ? createParsedApiError({
        title: '任务已在运行',
        message: '该股票已有分析任务，请等待当前任务完成。',
        rawMessage: error || `股票 ${stockCode} 正在分析中`,
        status: 409,
        category: 'http_error',
        code: 'duplicate_task',
        params,
      })
      : { ...error, params };
    super(parsed.rawMessage);
    this.name = 'DuplicateTaskError';
    this.stockCode = stockCode;
    this.existingTaskId = existingTaskId;
    this.params = params;
    this.details = parsed.details;
    this.traceId = parsed.traceId;
    this.parsedError = parsed;
  }
}
