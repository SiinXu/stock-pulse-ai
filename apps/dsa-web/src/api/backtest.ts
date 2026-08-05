import { z } from 'zod';
import apiClient from './index';
import { createApiError, createParsedApiError } from './error';
import { toCamelCase } from './utils';
import type {
  BacktestRunRequest,
  BacktestRunResponse,
  BacktestResultsResponse,
  PerformanceMetrics,
  BacktestPhaseFilter,
} from '../types/backtest';

import type { components } from '../types/api.generated';

type OpenApiBacktestRunResponse = components['schemas']['BacktestRunResponse'];
type OpenApiBacktestResultItem = components['schemas']['BacktestResultItem'];
type OpenApiPerformanceMetrics = components['schemas']['PerformanceMetrics'];
type _AssertRunFields = keyof OpenApiBacktestRunResponse;
type _AssertResultFields = keyof OpenApiBacktestResultItem;
type _AssertMetricsFields = keyof OpenApiPerformanceMetrics;
const _runFieldAnchor: _AssertRunFields = 'applied_eval_window_days';
const _resultFieldAnchor: _AssertResultFields = 'analysis_history_id';
const _metricsFieldAnchor: _AssertMetricsFields = 'win_rate_pct';
void _runFieldAnchor;
void _resultFieldAnchor;
void _metricsFieldAnchor;

const backtestRunResponseSchema = z.object({
  processed: z.number(),
  saved: z.number(),
  completed: z.number(),
  insufficient: z.number(),
  errors: z.number(),
  appliedEvalWindowDays: z.number().nullable(),
  message: z.string().nullable().optional(),
  diagnostics: z.record(z.string(), z.unknown()).optional(),
}).passthrough();

const backtestResultItemSchema = z.object({
  analysisHistoryId: z.number(),
  code: z.string(),
  evalWindowDays: z.number(),
  engineVersion: z.string(),
  evalStatus: z.string(),
  stockName: z.string().nullable().optional(),
  analysisDate: z.string().nullable().optional(),
  evaluatedAt: z.string().nullable().optional(),
  operationAdvice: z.string().nullable().optional(),
  action: z.string().nullable().optional(),
  actionLabel: z.string().nullable().optional(),
  trendPrediction: z.string().nullable().optional(),
  marketPhase: z.string().nullable().optional(),
  marketPhaseSummary: z.unknown().nullable().optional(),
  positionRecommendation: z.string().nullable().optional(),
  startPrice: z.number().nullable().optional(),
  endClose: z.number().nullable().optional(),
  maxHigh: z.number().nullable().optional(),
  minLow: z.number().nullable().optional(),
  stockReturnPct: z.number().nullable().optional(),
  actualReturnPct: z.number().nullable().optional(),
  actualMovement: z.string().nullable().optional(),
  directionExpected: z.string().nullable().optional(),
  directionCorrect: z.boolean().nullable().optional(),
  outcome: z.string().nullable().optional(),
  stopLoss: z.number().nullable().optional(),
  takeProfit: z.number().nullable().optional(),
  hitStopLoss: z.boolean().nullable().optional(),
  hitTakeProfit: z.boolean().nullable().optional(),
  firstHit: z.string().nullable().optional(),
  firstHitDate: z.string().nullable().optional(),
  firstHitTradingDays: z.number().nullable().optional(),
  simulatedEntryPrice: z.number().nullable().optional(),
  simulatedExitPrice: z.number().nullable().optional(),
  simulatedExitReason: z.string().nullable().optional(),
  simulatedReturnPct: z.number().nullable().optional(),
  resolutionNotes: z.string().nullable().optional(),
}).passthrough();

const backtestResultsResponseSchema = z.object({
  total: z.number(),
  page: z.number(),
  limit: z.number(),
  items: z.array(backtestResultItemSchema).optional(),
}).passthrough();

const performanceMetricsSchema = z.object({
  scope: z.string(),
  evalWindowDays: z.number(),
  engineVersion: z.string(),
  totalEvaluations: z.number(),
  completedCount: z.number(),
  insufficientCount: z.number(),
  longCount: z.number(),
  cashCount: z.number(),
  winCount: z.number(),
  lossCount: z.number(),
  neutralCount: z.number(),
  code: z.string().nullable().optional(),
  computedAt: z.string().nullable().optional(),
  directionAccuracyPct: z.number().nullable().optional(),
  winRatePct: z.number().nullable().optional(),
  neutralRatePct: z.number().nullable().optional(),
  avgStockReturnPct: z.number().nullable().optional(),
  avgSimulatedReturnPct: z.number().nullable().optional(),
  stopLossTriggerRate: z.number().nullable().optional(),
  takeProfitTriggerRate: z.number().nullable().optional(),
  ambiguousRate: z.number().nullable().optional(),
  avgDaysToFirstHit: z.number().nullable().optional(),
  adviceBreakdown: z.record(z.string(), z.unknown()).optional(),
  diagnostics: z.record(z.string(), z.unknown()).optional(),
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
      console.error(`[backtest] response validation failed (${label})`, result.error.issues);
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


// ============ API ============

export const backtestApi = {
  /**
   * Trigger backtest evaluation
   */
  run: async (params: BacktestRunRequest = {}): Promise<BacktestRunResponse> => {
    const requestData: Record<string, unknown> = {};
    if (params.code?.trim()) requestData.code = params.code.trim();
    if (params.force) requestData.force = params.force;
    if (params.evalWindowDays != null) requestData.eval_window_days = params.evalWindowDays;
    if (params.minAgeDays != null) requestData.min_age_days = params.minAgeDays;
    if (params.analysisDateFrom) requestData.analysis_date_from = params.analysisDateFrom;
    if (params.analysisDateTo) requestData.analysis_date_to = params.analysisDateTo;
    if (params.limit != null) requestData.limit = params.limit;

    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/backtest/run',
      requestData,
    );
    return parseCamelCasePayload<BacktestRunResponse>(response.data, backtestRunResponseSchema, 'BacktestRunResponse');
  },

  /**
   * Get paginated backtest results
   */
  getResults: async (params: {
    code?: string;
    evalWindowDays?: number;
    analysisDateFrom?: string;
    analysisDateTo?: string;
    analysisPhase?: BacktestPhaseFilter;
    page?: number;
    limit?: number;
  } = {}): Promise<BacktestResultsResponse> => {
    const { code, evalWindowDays, analysisDateFrom, analysisDateTo, analysisPhase, page = 1, limit = 20 } = params;

    const queryParams: Record<string, string | number> = { page, limit };
    if (code) queryParams.code = code;
    if (evalWindowDays) queryParams.eval_window_days = evalWindowDays;
    if (analysisDateFrom) queryParams.analysis_date_from = analysisDateFrom;
    if (analysisDateTo) queryParams.analysis_date_to = analysisDateTo;
    if (analysisPhase && analysisPhase !== 'all') queryParams.analysis_phase = analysisPhase;

    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/backtest/results',
      { params: queryParams },
    );

    const data = parseCamelCasePayload<BacktestResultsResponse>(
      response.data,
      backtestResultsResponseSchema,
      'BacktestResultsResponse',
    );
    return {
      total: data.total,
      page: data.page,
      limit: data.limit,
      items: Array.isArray(data.items) ? data.items : [],
    };
  },

  /**
   * Get overall performance metrics
   */
  getOverallPerformance: async (params: {
    evalWindowDays?: number;
    analysisDateFrom?: string;
    analysisDateTo?: string;
    analysisPhase?: BacktestPhaseFilter;
  } = {}): Promise<PerformanceMetrics | null> => {
    try {
      const queryParams: Record<string, string | number> = {};
      if (params.evalWindowDays) queryParams.eval_window_days = params.evalWindowDays;
      if (params.analysisDateFrom) queryParams.analysis_date_from = params.analysisDateFrom;
      if (params.analysisDateTo) queryParams.analysis_date_to = params.analysisDateTo;
      if (params.analysisPhase && params.analysisPhase !== 'all') queryParams.analysis_phase = params.analysisPhase;
      const response = await apiClient.get<Record<string, unknown>>(
        '/api/v1/backtest/performance',
        { params: queryParams },
      );
      return parseCamelCasePayload<PerformanceMetrics>(response.data, performanceMetricsSchema, 'PerformanceMetrics');
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { status?: number } };
        if (axiosErr.response?.status === 404) return null;
      }
      throw err;
    }
  },

  /**
   * Get per-stock performance metrics
   */
  getStockPerformance: async (code: string, params: {
    evalWindowDays?: number;
    analysisDateFrom?: string;
    analysisDateTo?: string;
    analysisPhase?: BacktestPhaseFilter;
  } = {}): Promise<PerformanceMetrics | null> => {
    try {
      const queryParams: Record<string, string | number> = {};
      if (params.evalWindowDays) queryParams.eval_window_days = params.evalWindowDays;
      if (params.analysisDateFrom) queryParams.analysis_date_from = params.analysisDateFrom;
      if (params.analysisDateTo) queryParams.analysis_date_to = params.analysisDateTo;
      if (params.analysisPhase && params.analysisPhase !== 'all') queryParams.analysis_phase = params.analysisPhase;
      const response = await apiClient.get<Record<string, unknown>>(
        `/api/v1/backtest/performance/${encodeURIComponent(code)}`,
        { params: queryParams },
      );
      return parseCamelCasePayload<PerformanceMetrics>(response.data, performanceMetricsSchema, 'PerformanceMetrics');
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { status?: number } };
        if (axiosErr.response?.status === 404) return null;
      }
      throw err;
    }
  },
};
