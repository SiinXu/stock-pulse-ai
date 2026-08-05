import { z } from 'zod';
import apiClient from './index';
import { createApiError, createParsedApiError } from './error';
import { toCamelCase } from './utils';
import type {
  DecisionSignalCreateRequest,
  DecisionSignalFeedbackItem,
  DecisionSignalFeedbackRequest,
  DecisionSignalItem,
  DecisionSignalLatestParams,
  DecisionSignalListParams,
  DecisionSignalListResponse,
  DecisionSignalMemoryFlagItem,
  DecisionSignalMemoryFlagUpdateRequest,
  DecisionSignalMutationResponse,
  DecisionSignalOutcomeItem,
  DecisionSignalOutcomeListParams,
  DecisionSignalOutcomeListResponse,
  DecisionSignalOutcomeRunRequest,
  DecisionSignalOutcomeRunResponse,
  DecisionSignalOutcomeStatsBucket,
  DecisionSignalOutcomeStatsParams,
  DecisionSignalOutcomeStatsResponse,
  DecisionSignalReassessRequest,
  DecisionSignalReassessBlockedError,
  DecisionSignalReassessResponse,
  DecisionSignalStatusUpdateRequest,
} from '../types/decisionSignals';

import type { components } from '../types/api.generated';

type OpenApiDecisionSignalItem = components['schemas']['DecisionSignalItem'];
type OpenApiDecisionSignalListResponse = components['schemas']['DecisionSignalListResponse'];
type OpenApiDecisionSignalOutcomeItem = components['schemas']['DecisionSignalOutcomeItem'];
type _AssertItemFields = keyof OpenApiDecisionSignalItem;
type _AssertListFields = keyof OpenApiDecisionSignalListResponse;
type _AssertOutcomeFields = keyof OpenApiDecisionSignalOutcomeItem;
const _itemFieldAnchor: _AssertItemFields = 'stock_code';
const _listFieldAnchor: _AssertListFields = 'page_size';
const _outcomeFieldAnchor: _AssertOutcomeFields = 'stock_return_pct';
void _itemFieldAnchor;
void _listFieldAnchor;
void _outcomeFieldAnchor;

const decisionSignalPresentationSchema = z.object({
  action: z.string(),
  label: z.string(),
  confidence: z.number().nullable().optional(),
  summary: z.string().nullable().optional(),
  risk: z.string().nullable().optional(),
  timestamp: z.string().nullable().optional(),
}).passthrough();

const decisionSignalItemSchema = z.object({
  id: z.number(),
  stockCode: z.string(),
  market: z.string(),
  sourceType: z.string(),
  triggerSource: z.string(),
  action: z.string(),
  planQuality: z.string(),
  status: z.string(),
  presentation: decisionSignalPresentationSchema,
  stockName: z.string().nullable().optional(),
  sourceAgent: z.string().nullable().optional(),
  sourceReportId: z.number().nullable().optional(),
  traceId: z.string().nullable().optional(),
  decisionProfile: z.string().nullable().optional(),
  marketPhase: z.string().nullable().optional(),
  actionLabel: z.string().nullable().optional(),
  confidence: z.number().nullable().optional(),
  score: z.number().nullable().optional(),
  horizon: z.string().nullable().optional(),
  entryLow: z.number().nullable().optional(),
  entryHigh: z.number().nullable().optional(),
  stopLoss: z.number().nullable().optional(),
  targetPrice: z.number().nullable().optional(),
  invalidation: z.string().nullable().optional(),
  watchConditions: z.string().nullable().optional(),
  reason: z.string().nullable().optional(),
  riskSummary: z.string().nullable().optional(),
  catalystSummary: z.string().nullable().optional(),
  evidence: z.unknown().optional(),
  dataQualitySummary: z.unknown().optional(),
  expiresAt: z.string().nullable().optional(),
  createdAt: z.string().nullable().optional(),
  updatedAt: z.string().nullable().optional(),
  metadata: z.unknown().optional(),
}).passthrough();

const decisionSignalListResponseSchema = z.object({
  total: z.number(),
  page: z.number(),
  pageSize: z.number(),
  items: z.array(decisionSignalItemSchema).optional(),
}).passthrough();

const decisionSignalMutationResponseSchema = z.object({
  created: z.boolean(),
  item: decisionSignalItemSchema,
}).passthrough();

const decisionSignalPreviewSchema = z.object({
  action: z.string(),
  metadata: z.record(z.string(), z.unknown()),
  confidence: z.number().nullable().optional(),
  entryHigh: z.number().nullable().optional(),
  entryLow: z.number().nullable().optional(),
  horizon: z.string().nullable().optional(),
  invalidation: z.string().nullable().optional(),
  reason: z.string().nullable().optional(),
  riskSummary: z.string().nullable().optional(),
  score: z.number().nullable().optional(),
  stopLoss: z.number().nullable().optional(),
  targetPrice: z.number().nullable().optional(),
  watchConditions: z.string().nullable().optional(),
}).passthrough();

const decisionSignalWarningSchema = z.object({
  code: z.string(),
  message: z.string().nullable().optional(),
  params: z.record(z.string(), z.unknown()).nullable().optional(),
}).passthrough();

const decisionSignalReassessResponseSchema = z.object({
  created: z.boolean(),
  preview: decisionSignalPreviewSchema.nullable().optional(),
  item: decisionSignalItemSchema.nullable().optional(),
  persistStatus: z.string().nullable().optional(),
  warnings: z.array(decisionSignalWarningSchema).optional(),
  blockedReason: z.string().nullable().optional(),
}).passthrough();

const decisionSignalOutcomeItemSchema = z.object({
  id: z.number(),
  signalId: z.number(),
  horizon: z.string(),
  engineVersion: z.string(),
  evalStatus: z.string(),
  holdingState: z.string(),
  action: z.string().nullable().optional(),
  anchorDate: z.string().nullable().optional(),
  createdAt: z.string().nullable().optional(),
  dataQualityLevel: z.string().nullable().optional(),
  directionCorrect: z.boolean().nullable().optional(),
  directionExpected: z.string().nullable().optional(),
  endClose: z.number().nullable().optional(),
  evalWindowDays: z.number().nullable().optional(),
  market: z.string().nullable().optional(),
  marketPhase: z.string().nullable().optional(),
  maxHigh: z.number().nullable().optional(),
  minLow: z.number().nullable().optional(),
  outcome: z.string().nullable().optional(),
  planQuality: z.string().nullable().optional(),
  sourceAgent: z.string().nullable().optional(),
  sourceType: z.string().nullable().optional(),
  startPrice: z.number().nullable().optional(),
  stockReturnPct: z.number().nullable().optional(),
  unableReason: z.string().nullable().optional(),
  updatedAt: z.string().nullable().optional(),
}).passthrough();

const decisionSignalOutcomeListResponseSchema = z.object({
  total: z.number(),
  page: z.number(),
  pageSize: z.number(),
  items: z.array(decisionSignalOutcomeItemSchema).optional(),
}).passthrough();

const decisionSignalOutcomeRunResponseSchema = z.object({
  created: z.number(),
  engineVersion: z.string(),
  evaluated: z.number(),
  skipped: z.number(),
  updated: z.number(),
  items: z.array(decisionSignalOutcomeItemSchema).optional(),
}).passthrough();

const decisionSignalOutcomeStatsBucketSchema = z.object({
  dimension: z.string(),
  value: z.string(),
  total: z.number(),
  completed: z.number(),
  hit: z.number(),
  miss: z.number(),
  neutral: z.number(),
  unable: z.number(),
  hitRatePct: z.number().nullable().optional(),
  avgStockReturnPct: z.number().nullable().optional(),
  unableReasons: z.record(z.string(), z.number()).optional(),
}).passthrough();

const decisionSignalOutcomeStatsResponseSchema = z.object({
  engineVersion: z.string(),
  total: z.number(),
  completed: z.number(),
  unable: z.number(),
  hit: z.number(),
  miss: z.number(),
  neutral: z.number(),
  avgStockReturnPct: z.number().nullable().optional(),
  hitRatePct: z.number().nullable().optional(),
  horizons: z.array(z.string()).nullable().optional(),
  statuses: z.array(z.string()).optional(),
  unableReasons: z.record(z.string(), z.number()).optional(),
  breakdowns: z.record(z.string(), z.array(decisionSignalOutcomeStatsBucketSchema)).optional(),
}).passthrough();

const decisionSignalFeedbackItemSchema = z.object({
  signalId: z.number(),
  feedbackValue: z.string().nullable().optional(),
  note: z.string().nullable().optional(),
  reasonCode: z.string().nullable().optional(),
  source: z.string().nullable().optional(),
  createdAt: z.string().nullable().optional(),
  updatedAt: z.string().nullable().optional(),
}).passthrough();

const decisionSignalMemoryFlagItemSchema = z.object({
  signalId: z.number(),
  memorable: z.boolean().optional(),
  ignored: z.boolean().optional(),
  createdAt: z.string().nullable().optional(),
  updatedAt: z.string().nullable().optional(),
}).passthrough();

function parseValidatedPayload<T>(
  camel: unknown,
  schema: z.ZodTypeAny,
  label: string,
): T {
  const result = schema.safeParse(camel);
  if (!result.success) {
    const issueSummary = result.error.issues
      .slice(0, 5)
      .map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`)
      .join('; ');
    if (import.meta.env.DEV) {
      console.error(`[decisionSignals] response validation failed (${label})`, result.error.issues);
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

function omitUndefined(input: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(input).filter(([, value]) => value !== undefined),
  );
}

function serializeRepeatedQueryParams(params: Record<string, unknown>): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    const values = Array.isArray(value) ? value : [value];
    for (const item of values) {
      if (item === undefined || item === null || item === '') continue;
      searchParams.append(key, String(item));
    }
  }
  return searchParams.toString();
}

function toDecisionSignalItem(data: Record<string, unknown>): DecisionSignalItem {
  const item = toCamelCase<DecisionSignalItem>(data);
  if ('evidence' in data) item.evidence = data.evidence;
  if ('data_quality_summary' in data) item.dataQualitySummary = data.data_quality_summary;
  if ('metadata' in data) item.metadata = data.metadata;
  return parseValidatedPayload<DecisionSignalItem>(item, decisionSignalItemSchema, 'DecisionSignalItem');
}

function toDecisionSignalMutationResponse(data: Record<string, unknown>): DecisionSignalMutationResponse {
  const response = toCamelCase<DecisionSignalMutationResponse>(data);
  response.item = toDecisionSignalItem(data.item as Record<string, unknown>);
  return parseValidatedPayload(response, decisionSignalMutationResponseSchema, 'DecisionSignalMutationResponse');
}

function toDecisionSignalReassessResponse(data: Record<string, unknown>): DecisionSignalReassessResponse {
  const rawPreview = data.preview;
  if (rawPreview !== null && rawPreview !== undefined
    && (typeof rawPreview !== 'object' || Array.isArray(rawPreview))) {
    throw createApiError(
      createParsedApiError({
        title: '响应校验失败',
        message: '接口响应未通过校验（DecisionSignalReassessResponse）。preview: Expected object, received non-object',
        rawMessage: 'preview must be an object or null',
        category: 'unknown',
        code: 'api_response_validation_failed',
        params: {
          label: 'DecisionSignalReassessResponse',
          issues: 'preview: Expected object, received non-object',
        },
      }),
    );
  }

  let preview: DecisionSignalReassessResponse['preview'] = null;
  if (rawPreview) {
    const previewCamel = toCamelCase<NonNullable<DecisionSignalReassessResponse['preview']>>(rawPreview);
    previewCamel.metadata = (rawPreview as Record<string, unknown>).metadata as Record<string, unknown> ?? {};
    preview = parseValidatedPayload(previewCamel, decisionSignalPreviewSchema, 'DecisionSignalPreview');
  }

  const response: DecisionSignalReassessResponse = {
    created: Boolean(data.created),
    preview,
    item: data.item
      ? toDecisionSignalItem(data.item as Record<string, unknown>)
      : (data.item === null ? null : undefined),
    persistStatus: (data.persist_status as DecisionSignalReassessResponse['persistStatus']) ?? null,
    warnings: Array.isArray(data.warnings)
      ? data.warnings.map((warning) => toCamelCase(warning as Record<string, unknown>))
      : [],
    blockedReason: (data.blocked_reason as string | null | undefined) ?? null,
  };
  return parseValidatedPayload(response, decisionSignalReassessResponseSchema, 'DecisionSignalReassessResponse');
}

export function getDecisionSignalReassessBlockedError(
  error: unknown,
): DecisionSignalReassessBlockedError | null {
  if (!error || typeof error !== 'object') return null;
  const response = (error as { response?: { data?: unknown } }).response;
  const data = response?.data;
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
  const payload = data as Record<string, unknown>;
  if (payload.error !== 'guardrail_blocked' || typeof payload.blocked_reason !== 'string') return null;
  const warnings = Array.isArray(payload.warnings)
    ? payload.warnings.filter((warning): warning is Record<string, unknown> => (
      Boolean(warning) && typeof warning === 'object' && !Array.isArray(warning)
    )).filter((warning) => typeof warning.code === 'string').map((warning) => ({
      code: warning.code as string,
      message: typeof warning.message === 'string' ? warning.message : undefined,
      params: warning.params && typeof warning.params === 'object' && !Array.isArray(warning.params)
        ? warning.params as Record<string, unknown>
        : undefined,
    }))
    : [];
  return { blockedReason: payload.blocked_reason, warnings };
}

function toDecisionSignalListResponse(data: Record<string, unknown>): DecisionSignalListResponse {
  if ('items' in data && data.items !== undefined && !Array.isArray(data.items)) {
    return parseValidatedPayload(
      { total: data.total, page: data.page, pageSize: data.page_size, items: data.items },
      decisionSignalListResponseSchema,
      'DecisionSignalListResponse',
    );
  }
  const items = Array.isArray(data.items)
    ? data.items.map((item) => toDecisionSignalItem(item as Record<string, unknown>))
    : [];
  const response: DecisionSignalListResponse = {
    total: data.total as number,
    page: data.page as number,
    pageSize: data.page_size as number,
    items,
  };
  return parseValidatedPayload(response, decisionSignalListResponseSchema, 'DecisionSignalListResponse');
}

function toDecisionSignalOutcomeItem(data: Record<string, unknown>): DecisionSignalOutcomeItem {
  const item = toCamelCase<DecisionSignalOutcomeItem>(data);
  return parseValidatedPayload(item, decisionSignalOutcomeItemSchema, 'DecisionSignalOutcomeItem');
}

function toDecisionSignalOutcomeListResponse(data: Record<string, unknown>): DecisionSignalOutcomeListResponse {
  if ('items' in data && data.items !== undefined && !Array.isArray(data.items)) {
    return parseValidatedPayload(
      { total: data.total, page: data.page, pageSize: data.page_size, items: data.items },
      decisionSignalOutcomeListResponseSchema,
      'DecisionSignalOutcomeListResponse',
    );
  }
  const items = Array.isArray(data.items)
    ? data.items.map((item) => toDecisionSignalOutcomeItem(item as Record<string, unknown>))
    : [];
  const response: DecisionSignalOutcomeListResponse = {
    total: data.total as number,
    page: data.page as number,
    pageSize: data.page_size as number,
    items,
  };
  return parseValidatedPayload(response, decisionSignalOutcomeListResponseSchema, 'DecisionSignalOutcomeListResponse');
}

function toDecisionSignalOutcomeRunResponse(data: Record<string, unknown>): DecisionSignalOutcomeRunResponse {
  if ('items' in data && data.items !== undefined && !Array.isArray(data.items)) {
    return parseValidatedPayload(
      toCamelCase(data),
      decisionSignalOutcomeRunResponseSchema,
      'DecisionSignalOutcomeRunResponse',
    );
  }
  const items = Array.isArray(data.items)
    ? data.items.map((item) => toDecisionSignalOutcomeItem(item as Record<string, unknown>))
    : [];
  const response: DecisionSignalOutcomeRunResponse = {
    created: data.created as number,
    engineVersion: data.engine_version as string,
    evaluated: data.evaluated as number,
    skipped: data.skipped as number,
    updated: data.updated as number,
    items,
  };
  return parseValidatedPayload(response, decisionSignalOutcomeRunResponseSchema, 'DecisionSignalOutcomeRunResponse');
}

function toDecisionSignalStatsBucket(data: Record<string, unknown>): DecisionSignalOutcomeStatsBucket {
  const bucket = toCamelCase<DecisionSignalOutcomeStatsBucket>(data);
  bucket.unableReasons = (data.unable_reasons as Record<string, number> | undefined) ?? {};
  return parseValidatedPayload(bucket, decisionSignalOutcomeStatsBucketSchema, 'DecisionSignalOutcomeStatsBucket');
}

function toDecisionSignalOutcomeStatsResponse(data: Record<string, unknown>): DecisionSignalOutcomeStatsResponse {
  const response = toCamelCase<DecisionSignalOutcomeStatsResponse>(data);
  response.unableReasons = (data.unable_reasons as Record<string, number> | undefined) ?? {};
  const rawBreakdowns = data.breakdowns as Record<string, unknown[]> | undefined;
  response.breakdowns = {};
  if (rawBreakdowns && typeof rawBreakdowns === 'object') {
    for (const [dimension, buckets] of Object.entries(rawBreakdowns)) {
      response.breakdowns[dimension] = Array.isArray(buckets)
        ? buckets.map((bucket) => toDecisionSignalStatsBucket(bucket as Record<string, unknown>))
        : [];
    }
  }
  return parseValidatedPayload(response, decisionSignalOutcomeStatsResponseSchema, 'DecisionSignalOutcomeStatsResponse');
}

function toDecisionSignalFeedbackItem(data: Record<string, unknown>): DecisionSignalFeedbackItem {
  const item = toCamelCase<DecisionSignalFeedbackItem>(data);
  return parseValidatedPayload(item, decisionSignalFeedbackItemSchema, 'DecisionSignalFeedbackItem');
}

function toDecisionSignalMemoryFlagItem(data: Record<string, unknown>): DecisionSignalMemoryFlagItem {
  const item = toCamelCase<DecisionSignalMemoryFlagItem>(data);
  return parseValidatedPayload(item, decisionSignalMemoryFlagItemSchema, 'DecisionSignalMemoryFlagItem');
}

function toSnakeCreatePayload(payload: DecisionSignalCreateRequest): Record<string, unknown> {
  return omitUndefined({
    stock_code: payload.stockCode,
    stock_name: payload.stockName,
    market: payload.market,
    source_type: payload.sourceType,
    source_agent: payload.sourceAgent,
    source_report_id: payload.sourceReportId,
    trace_id: payload.traceId,
    decision_profile: payload.decisionProfile,
    market_phase: payload.marketPhase,
    trigger_source: payload.triggerSource,
    action: payload.action,
    action_label: payload.actionLabel,
    confidence: payload.confidence,
    score: payload.score,
    horizon: payload.horizon,
    entry_low: payload.entryLow,
    entry_high: payload.entryHigh,
    stop_loss: payload.stopLoss,
    target_price: payload.targetPrice,
    invalidation: payload.invalidation,
    watch_conditions: payload.watchConditions,
    reason: payload.reason,
    risk_summary: payload.riskSummary,
    catalyst_summary: payload.catalystSummary,
    evidence: payload.evidence,
    data_quality_summary: payload.dataQualitySummary,
    plan_quality: payload.planQuality,
    status: payload.status,
    expires_at: payload.expiresAt,
    metadata: payload.metadata,
    report_language: payload.reportLanguage,
  });
}

function toSnakeOutcomeRunPayload(payload: DecisionSignalOutcomeRunRequest): Record<string, unknown> {
  return omitUndefined({
    signal_id: payload.signalId,
    horizons: payload.horizons,
    force: payload.force,
    market: payload.market,
    stock_code: payload.stockCode,
    action: payload.action,
    source_type: payload.sourceType,
    status: payload.status,
    limit: payload.limit,
  });
}

function toSnakeReassessPayload(payload: DecisionSignalReassessRequest): Record<string, unknown> {
  return {
    source_report_id: payload.sourceReportId,
    decision_profile: payload.decisionProfile,
    persist: payload.persist ?? false,
  };
}

function toListParams(params: DecisionSignalListParams = {}): Record<string, string | number | boolean> {
  return omitUndefined({
    market: params.market,
    stock_code: params.stockCode,
    action: params.action,
    market_phase: params.marketPhase,
    decision_profile: params.decisionProfile,
    source_type: params.sourceType,
    source_report_id: params.sourceReportId,
    trace_id: params.traceId,
    trigger_source: params.triggerSource,
    status: params.status,
    created_from: params.createdFrom,
    created_to: params.createdTo,
    expires_from: params.expiresFrom,
    expires_to: params.expiresTo,
    holding_only: params.holdingOnly,
    account_id: params.accountId,
    page: params.page,
    page_size: params.pageSize,
  }) as Record<string, string | number | boolean>;
}

function toOutcomeListParams(params: DecisionSignalOutcomeListParams = {}): Record<string, string | number> {
  return omitUndefined({
    signal_id: params.signalId,
    horizon: params.horizon,
    engine_version: params.engineVersion,
    eval_status: params.evalStatus,
    outcome: params.outcome,
    page: params.page,
    page_size: params.pageSize,
  }) as Record<string, string | number>;
}

function toOutcomeStatsParams(params: DecisionSignalOutcomeStatsParams = {}): Record<string, string | string[]> {
  return omitUndefined({
    horizons: params.horizons,
    engine_version: params.engineVersion,
    statuses: params.statuses,
  }) as Record<string, string | string[]>;
}

function toLatestParams(params: DecisionSignalLatestParams = {}): Record<string, string | number> {
  return omitUndefined({
    market: params.market,
    limit: params.limit,
  }) as Record<string, string | number>;
}

function toSnakeStatusPayload(payload: DecisionSignalStatusUpdateRequest): Record<string, unknown> {
  return omitUndefined({
    status: payload.status,
    metadata: payload.metadata,
  });
}

function toSnakeFeedbackPayload(payload: DecisionSignalFeedbackRequest): Record<string, unknown> {
  return omitUndefined({
    feedback_value: payload.feedbackValue,
    reason_code: payload.reasonCode,
    note: payload.note,
    source: payload.source,
  });
}

function toSnakeMemoryFlagPayload(
  payload: DecisionSignalMemoryFlagUpdateRequest,
): Record<string, unknown> {
  return omitUndefined({
    memorable: payload.memorable,
    ignored: payload.ignored,
  });
}

function toLatestStockCodePath(stockCode: string): string {
  if (stockCode.includes('/')) {
    throw new Error(
      'DecisionSignal latest stockCode cannot contain "/" because the backend route accepts a single path segment; use 00700, HK00700, or 00700.HK.',
    );
  }
  return encodeURIComponent(stockCode);
}

export const decisionSignalsApi = {
  async create(payload: DecisionSignalCreateRequest): Promise<DecisionSignalMutationResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/decision-signals',
      toSnakeCreatePayload(payload),
    );
    return toDecisionSignalMutationResponse(response.data);
  },

  async list(params: DecisionSignalListParams = {}): Promise<DecisionSignalListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/decision-signals', {
      params: toListParams(params),
    });
    return toDecisionSignalListResponse(response.data);
  },

  async get(signalId: number): Promise<DecisionSignalItem> {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/decision-signals/${signalId}`);
    return toDecisionSignalItem(response.data);
  },

  async getLatest(
    stockCode: string,
    params: DecisionSignalLatestParams = {},
  ): Promise<DecisionSignalListResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/decision-signals/latest/${toLatestStockCodePath(stockCode)}`,
      { params: toLatestParams(params) },
    );
    return toDecisionSignalListResponse(response.data);
  },

  async reassess(payload: DecisionSignalReassessRequest): Promise<DecisionSignalReassessResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/decision-signals/reassess',
      toSnakeReassessPayload(payload),
    );
    return toDecisionSignalReassessResponse(response.data);
  },

  async updateStatus(
    signalId: number,
    payload: DecisionSignalStatusUpdateRequest,
  ): Promise<DecisionSignalItem> {
    const response = await apiClient.patch<Record<string, unknown>>(
      `/api/v1/decision-signals/${signalId}/status`,
      toSnakeStatusPayload(payload),
    );
    return toDecisionSignalItem(response.data);
  },

  async runOutcomes(payload: DecisionSignalOutcomeRunRequest): Promise<DecisionSignalOutcomeRunResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/decision-signals/outcomes/run',
      toSnakeOutcomeRunPayload(payload),
    );
    return toDecisionSignalOutcomeRunResponse(response.data);
  },

  async listOutcomes(params: DecisionSignalOutcomeListParams = {}): Promise<DecisionSignalOutcomeListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/decision-signals/outcomes', {
      params: toOutcomeListParams(params),
    });
    return toDecisionSignalOutcomeListResponse(response.data);
  },

  async getOutcomeStats(
    params: DecisionSignalOutcomeStatsParams = {},
  ): Promise<DecisionSignalOutcomeStatsResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/decision-signals/outcomes/stats', {
      params: toOutcomeStatsParams(params),
      paramsSerializer: {
        serialize: serializeRepeatedQueryParams,
      },
    });
    return toDecisionSignalOutcomeStatsResponse(response.data);
  },

  async getSignalOutcomes(signalId: number): Promise<DecisionSignalOutcomeListResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/decision-signals/${signalId}/outcomes`,
    );
    return toDecisionSignalOutcomeListResponse(response.data);
  },

  async getFeedback(signalId: number): Promise<DecisionSignalFeedbackItem> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/decision-signals/${signalId}/feedback`,
    );
    return toDecisionSignalFeedbackItem(response.data);
  },

  async putFeedback(
    signalId: number,
    payload: DecisionSignalFeedbackRequest,
  ): Promise<DecisionSignalFeedbackItem> {
    const response = await apiClient.put<Record<string, unknown>>(
      `/api/v1/decision-signals/${signalId}/feedback`,
      toSnakeFeedbackPayload(payload),
    );
    return toDecisionSignalFeedbackItem(response.data);
  },

  async getMemoryFlag(signalId: number): Promise<DecisionSignalMemoryFlagItem> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/decision-signals/${signalId}/memory-flag`,
    );
    return toDecisionSignalMemoryFlagItem(response.data);
  },

  async updateMemoryFlag(
    signalId: number,
    payload: DecisionSignalMemoryFlagUpdateRequest,
  ): Promise<DecisionSignalMemoryFlagItem> {
    const response = await apiClient.patch<Record<string, unknown>>(
      `/api/v1/decision-signals/${signalId}/memory-flag`,
      toSnakeMemoryFlagPayload(payload),
    );
    return toDecisionSignalMemoryFlagItem(response.data);
  },
};
