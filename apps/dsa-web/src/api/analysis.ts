import { z } from 'zod';
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
import { serializeMarketReviewRegions } from '../utils/marketReviewRegion';
// Generated OpenAPI components document the backend snake_case contract for
// analysis task/status/list/market-review/run-flow responses.
import type { components } from '../types/api.generated';

type OpenApiAnalysisResultResponse = components['schemas']['AnalysisResultResponse'];
type OpenApiTaskAccepted = components['schemas']['TaskAccepted'];
type OpenApiBatchTaskAcceptedResponse = components['schemas']['BatchTaskAcceptedResponse'];
type OpenApiMarketReviewAccepted = components['schemas']['MarketReviewAccepted'];
type OpenApiTaskStatus = components['schemas']['TaskStatus'];
type OpenApiTaskListResponse = components['schemas']['TaskListResponse'];
type OpenApiRunFlowSnapshot = components['schemas']['RunFlowSnapshot'];
type OpenApiAnalysisReport = components['schemas']['AnalysisReport'];

type _AssertResultFields = keyof OpenApiAnalysisResultResponse;
type _AssertAcceptedFields = keyof OpenApiTaskAccepted;
type _AssertBatchFields = keyof OpenApiBatchTaskAcceptedResponse;
type _AssertMarketReviewFields = keyof OpenApiMarketReviewAccepted;
type _AssertTaskStatusFields = keyof OpenApiTaskStatus;
type _AssertTaskListFields = keyof OpenApiTaskListResponse;
type _AssertRunFlowFields = keyof OpenApiRunFlowSnapshot;
type _AssertReportFields = keyof OpenApiAnalysisReport;
const _resultFieldAnchor: _AssertResultFields = 'query_id';
const _acceptedFieldAnchor: _AssertAcceptedFields = 'task_id';
const _batchFieldAnchor: _AssertBatchFields = 'message';
const _marketReviewFieldAnchor: _AssertMarketReviewFields = 'send_notification';
const _taskStatusFieldAnchor: _AssertTaskStatusFields = 'task_id';
const _taskListFieldAnchor: _AssertTaskListFields = 'tasks';
const _runFlowFieldAnchor: _AssertRunFlowFields = 'generated_at';
const _reportFieldAnchor: _AssertReportFields = 'meta';
void _resultFieldAnchor;
void _acceptedFieldAnchor;
void _batchFieldAnchor;
void _marketReviewFieldAnchor;
void _taskStatusFieldAnchor;
void _taskListFieldAnchor;
void _runFlowFieldAnchor;
void _reportFieldAnchor;

/**
 * Zod schemas mirror the camelCase view of OpenAPI analysis schemas.
 * On success we return the pre-validated toCamelCase object (not schema output) so
 * valid payloads remain byte-identical to the previous unchecked cast path.
 */
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

const analysisResultSchema = z.object({
  queryId: z.string(),
  stockCode: z.string(),
  stockName: z.string().nullable().optional(),
  createdAt: z.string(),
  traceId: z.string().nullable().optional(),
  // OpenAPI marks report as unknown|null; validate shape when present.
  report: analysisReportSchema.nullable().optional(),
  diagnosticSummary: z.unknown().nullable().optional(),
}).passthrough();

const taskAcceptedSchema = z.object({
  taskId: z.string(),
  status: z.string(),
  messageCode: z.string(),
  analysisPhase: z.string(),
  message: z.string().nullable().optional(),
  messageParams: z.record(z.string(), z.unknown()).optional(),
  traceId: z.string().nullable().optional(),
}).passthrough();

const batchTaskAcceptedItemSchema = z.object({
  taskId: z.string(),
  stockCode: z.string(),
  status: z.string(),
  messageCode: z.string(),
  analysisPhase: z.string(),
  message: z.string().nullable().optional(),
  messageParams: z.record(z.string(), z.unknown()).optional(),
  traceId: z.string().nullable().optional(),
}).passthrough();

const batchDuplicateTaskItemSchema = z.object({
  stockCode: z.string(),
  existingTaskId: z.string(),
  message: z.string(),
}).passthrough();

const batchTaskAcceptedSchema = z.object({
  message: z.string(),
  accepted: z.array(batchTaskAcceptedItemSchema).optional(),
  duplicates: z.array(batchDuplicateTaskItemSchema).optional(),
}).passthrough();

// Discriminate analyze responses: async accepted, batch accepted, or sync result.
const analyzeResponseSchema = z.union([
  taskAcceptedSchema,
  batchTaskAcceptedSchema,
  analysisResultSchema,
]);

const analyzeAsyncResponseSchema = z.union([
  taskAcceptedSchema,
  batchTaskAcceptedSchema,
]);

const marketReviewAcceptedSchema = z.object({
  status: z.string(),
  message: z.string(),
  messageCode: z.string(),
  sendNotification: z.boolean(),
  region: z.string(),
  messageParams: z.record(z.string(), z.unknown()).optional(),
  taskId: z.string().nullable().optional(),
  traceId: z.string().nullable().optional(),
}).passthrough();

const taskStatusSchema = z.object({
  taskId: z.string(),
  status: z.string(),
  messageCode: z.string(),
  progress: z.number().nullable().optional(),
  message: z.string().nullable().optional(),
  messageParams: z.record(z.string(), z.unknown()).optional(),
  result: analysisResultSchema.nullable().optional(),
  marketReviewReport: z.string().nullable().optional(),
  marketReviewPayload: z.unknown().nullable().optional(),
  region: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  stockName: z.string().nullable().optional(),
  originalQuery: z.string().nullable().optional(),
  selectionSource: z.string().nullable().optional(),
  analysisPhase: z.string().nullable().optional(),
  skills: z.array(z.string()).nullable().optional(),
  traceId: z.string().nullable().optional(),
}).passthrough();

const taskInfoSchema = z.object({
  taskId: z.string(),
  stockCode: z.string(),
  status: z.string(),
  progress: z.number(),
  reportType: z.string(),
  createdAt: z.string(),
  messageCode: z.string(),
  analysisPhase: z.string(),
  stockName: z.string().nullable().optional(),
  message: z.string().nullable().optional(),
  messageParams: z.record(z.string(), z.unknown()).optional(),
  startedAt: z.string().nullable().optional(),
  completedAt: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  originalQuery: z.string().nullable().optional(),
  selectionSource: z.string().nullable().optional(),
  skills: z.array(z.string()).nullable().optional(),
  region: z.string().nullable().optional(),
  traceId: z.string().nullable().optional(),
}).passthrough();

const taskListResponseSchema = z.object({
  total: z.number(),
  pending: z.number(),
  processing: z.number(),
  tasks: z.array(taskInfoSchema),
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
  schemaVersion: z.string(),
  summary: runFlowSummarySchema,
  stockName: z.string().nullable().optional(),
  traceId: z.string().nullable().optional(),
  lanes: z.array(z.unknown()).optional(),
  nodes: z.array(z.unknown()).optional(),
  edges: z.array(z.unknown()).optional(),
  events: z.array(z.unknown()).optional(),
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
      console.error(`[analysis] response validation failed (${label})`, result.error.issues);
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

    const result = parseCamelCasePayload<AnalyzeResponse>(
      response.data,
      analyzeResponseSchema,
      'AnalyzeResponse',
    );

    // Ensure the sync analysis report payload is converted recursively.
    // toCamelCase already walks nested objects; re-apply only when present for
    // parity with the pre-validation path that re-assigned report.
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

    return parseCamelCasePayload<AnalyzeAsyncResponse>(
      response.data,
      analyzeAsyncResponseSchema,
      'AnalyzeAsyncResponse',
    );
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
        ...(data.regions !== undefined && { region: serializeMarketReviewRegions(data.regions) }),
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

    return parseCamelCasePayload<MarketReviewAccepted>(
      response.data,
      marketReviewAcceptedSchema,
      'MarketReviewAccepted',
    );
  },

  /**
   * Get async task status.
   * @param taskId Task ID
   */
  getStatus: async (taskId: string): Promise<TaskStatus> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/analysis/status/${taskId}`
    );

    const data = parseCamelCasePayload<TaskStatus>(
      response.data,
      taskStatusSchema,
      'TaskStatus',
    );

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

    return parseCamelCasePayload<TaskListResponse>(
      response.data,
      taskListResponseSchema,
      'TaskListResponse',
    );
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

    return parseCamelCasePayload<RunFlowSnapshot>(
      response.data,
      runFlowSnapshotSchema,
      'RunFlowSnapshot',
    );
  },

  /**
   * Get the SSE stream URL.
   * Documented skip for issue #721: SSE/streaming surfaces stay unvalidated
   * (EventSource URL helper only; no JSON response body).
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
