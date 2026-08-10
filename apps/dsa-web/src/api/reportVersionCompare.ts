// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Client for `/api/v1/report-version-compare` (issue #188 / T18).
 */
import apiClient from './index';
import { toCamelCase } from './utils';

export type ReportVersionSeverity = 'major' | 'moderate' | 'minor' | 'none' | 'unknown';

export type ReportVersionCompareStatus =
  | 'ok'
  | 'engine_pending'
  | 'no_baseline'
  | 'incomparable';

export type ReportVersionRunItem = {
  runId: string;
  queryId: string;
  stockCode: string;
  stockName?: string | null;
  reportType?: string | null;
  createdAt?: string | null;
  modelUsed?: string | null;
  reportLanguage?: string | null;
  action?: string | null;
  actionLabel?: string | null;
  operationAdvice?: string | null;
  sentimentScore?: number | null;
  trendPrediction?: string | null;
  analysisSummary?: string | null;
  configFingerprint?: string | null;
  configComponents: Record<string, string>;
  configComplete: boolean;
  configMissingKeys: string[];
};

export type ReportVersionRunListResponse = {
  stockCode: string;
  total: number;
  page: number;
  limit: number;
  items: ReportVersionRunItem[];
};

export type ConfigComponentDiff = {
  key: string;
  baseValue?: string | null;
  targetValue?: string | null;
  changed: boolean;
};

export type ConfigFingerprintDiff = {
  baseFingerprint?: string | null;
  targetFingerprint?: string | null;
  identical: boolean;
  hasDifferences: boolean;
  comparisonStatus: 'identical' | 'different' | 'unknown';
  baseComplete: boolean;
  targetComplete: boolean;
  baseMissingKeys: string[];
  targetMissingKeys: string[];
  components: ConfigComponentDiff[];
};

export type ReportFieldDiff = {
  field: string;
  baseValue?: string | null;
  targetValue?: string | null;
  changed: boolean;
  severity: ReportVersionSeverity;
};

export type AnalysisValueChange = {
  field: string;
  baseValue?: string | number | boolean | null;
  targetValue?: string | number | boolean | null;
  delta?: string | number | boolean | null;
  direction: 'up' | 'down' | 'changed' | 'unavailable';
  comparable: boolean;
  unavailability?: {
    base?: string | null;
    target?: string | null;
  } | null;
};

export type AnalysisListChange = {
  field: string;
  added: string[];
  removed: string[];
  unchanged: string[];
  addedTotal: number;
  removedTotal: number;
  unchangedTotal: number;
  outputTruncated: boolean;
};

export type AnalysisDeltaPayload = {
  hasBaseline: boolean;
  baselineStatus:
    | 'ok'
    | 'missing_history'
    | 'missing_base'
    | 'missing_target'
    | 'incomparable_structure';
  baselineReason?: string | null;
  stockCode?: string | null;
  baseRecordId: number;
  targetRecordId: number;
  baseQueryId?: string | null;
  targetQueryId?: string | null;
  reportType?: string | null;
  hasMaterialChanges: boolean;
  conclusionChanges: AnalysisValueChange[];
  scoreChanges: AnalysisValueChange[];
  evidenceChanges: AnalysisListChange[];
  riskChanges: AnalysisListChange[];
};

export type ReportVersionCompareResponse = {
  status: ReportVersionCompareStatus;
  stockCode: string;
  baseRun: ReportVersionRunItem;
  targetRun: ReportVersionRunItem;
  configDiff: ConfigFingerprintDiff;
  fieldDiffs: ReportFieldDiff[];
  delta?: AnalysisDeltaPayload | null;
  engineStatus: 'ok' | 'engine_pending';
};

export type ListReportVersionRunsParams = {
  stockCode: string;
  page?: number;
  limit?: number;
  reportType?: string;
  signal?: AbortSignal;
};

export type CompareReportVersionsParams = {
  stockCode: string;
  baseRunId: string;
  targetRunId: string;
  signal?: AbortSignal;
};

export const reportVersionCompareApi = {
  listRuns: async (
    params: ListReportVersionRunsParams,
  ): Promise<ReportVersionRunListResponse> => {
    const queryParams: Record<string, string | number> = {
      stock_code: params.stockCode,
      page: params.page ?? 1,
      limit: params.limit ?? 50,
    };
    if (params.reportType) queryParams.report_type = params.reportType;

    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/report-version-compare/runs',
      { params: queryParams, signal: params.signal },
    );
    const data = toCamelCase<ReportVersionRunListResponse>(response.data);
    return {
      ...data,
      items: (data.items ?? []).map((item) => toCamelCase<ReportVersionRunItem>(item)),
    };
  },

  compare: async (
    params: CompareReportVersionsParams,
  ): Promise<ReportVersionCompareResponse> => {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/report-version-compare/compare',
      {
        params: {
          stock_code: params.stockCode,
          base_run_id: params.baseRunId,
          target_run_id: params.targetRunId,
        },
        signal: params.signal,
      },
    );
    const data = toCamelCase<ReportVersionCompareResponse>(response.data);
    return {
      ...data,
      baseRun: toCamelCase<ReportVersionRunItem>(data.baseRun),
      targetRun: toCamelCase<ReportVersionRunItem>(data.targetRun),
      configDiff: {
        ...toCamelCase<ConfigFingerprintDiff>(data.configDiff),
        components: (data.configDiff?.components ?? []).map((item) =>
          toCamelCase<ConfigComponentDiff>(item),
        ),
      },
      fieldDiffs: (data.fieldDiffs ?? []).map((item) => toCamelCase<ReportFieldDiff>(item)),
      delta: data.delta ? toCamelCase<AnalysisDeltaPayload>(data.delta) : data.delta,
    };
  },
};
