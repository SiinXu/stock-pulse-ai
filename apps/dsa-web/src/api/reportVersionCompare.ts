// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Client for `/api/v1/report-version-compare` (issue #188 / T18).
 * Response boundaries use OpenAPI-generated anchors + Zod fail-closed validation.
 */
import { z } from 'zod';
import type { components } from '../types/api.generated';
import apiClient from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';

type OpenApiRunItem = components['schemas']['ReportVersionRunItem'];
type OpenApiRunList = components['schemas']['ReportVersionRunListResponse'];
type OpenApiCompare = components['schemas']['ReportVersionCompareResponse'];
type _AssertRunItem = keyof OpenApiRunItem;
type _AssertRunList = keyof OpenApiRunList;
type _AssertCompare = keyof OpenApiCompare;
const _runItemAnchor: _AssertRunItem = 'run_id';
const _runListAnchor: _AssertRunList = 'stock_code';
const _compareAnchor: _AssertCompare = 'engine_status';
const _compareHonestyAnchor: _AssertCompare = 'optional_sections';
void _runItemAnchor;
void _runListAnchor;
void _compareAnchor;
void _compareHonestyAnchor;

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

export type OptionalSectionId = 'catalysts' | 'structured_risk' | 'multi_agent';

export type OptionalSectionComparisonStatus =
  | 'both_missing'
  | 'base_missing'
  | 'target_missing'
  | 'present_identical'
  | 'present_different';

export type OptionalSectionPresence = {
  section: OptionalSectionId;
  basePresent: boolean;
  targetPresent: boolean;
  comparisonStatus: OptionalSectionComparisonStatus;
  baseItemCount: number;
  targetItemCount: number;
  basePreview: string[];
  targetPreview: string[];
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
  optionalSections: OptionalSectionPresence[];
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


const finiteNumber = z.number().refine((value) => Number.isFinite(value), {
  message: 'non-finite number rejected',
});

const reportVersionRunItemSchema = z
  .object({
    runId: z.string(),
    queryId: z.string(),
    stockCode: z.string(),
    stockName: z.string().nullable().optional(),
    reportType: z.string().nullable().optional(),
    createdAt: z.string().nullable().optional(),
    modelUsed: z.string().nullable().optional(),
    reportLanguage: z.string().nullable().optional(),
    action: z.string().nullable().optional(),
    actionLabel: z.string().nullable().optional(),
    operationAdvice: z.string().nullable().optional(),
    sentimentScore: finiteNumber.nullable().optional(),
    trendPrediction: z.string().nullable().optional(),
    analysisSummary: z.string().nullable().optional(),
    configFingerprint: z.string().nullable().optional(),
    configComponents: z.record(z.string(), z.string()).optional(),
    configComplete: z.boolean().optional(),
    configMissingKeys: z.array(z.string()).optional(),
  })
  .passthrough();

const reportVersionRunListResponseSchema = z
  .object({
    stockCode: z.string(),
    total: z.number().int(),
    page: z.number().int(),
    limit: z.number().int(),
    items: z.array(reportVersionRunItemSchema).optional(),
  })
  .passthrough();

const configComponentDiffSchema = z
  .object({
    key: z.string(),
    baseValue: z.string().nullable().optional(),
    targetValue: z.string().nullable().optional(),
    changed: z.boolean().optional(),
  })
  .passthrough();

const configFingerprintDiffSchema = z
  .object({
    baseFingerprint: z.string().nullable().optional(),
    targetFingerprint: z.string().nullable().optional(),
    identical: z.boolean().optional(),
    hasDifferences: z.boolean().optional(),
    comparisonStatus: z.string().optional(),
    baseComplete: z.boolean().optional(),
    targetComplete: z.boolean().optional(),
    baseMissingKeys: z.array(z.string()).optional(),
    targetMissingKeys: z.array(z.string()).optional(),
    components: z.array(configComponentDiffSchema).optional(),
  })
  .passthrough();

const reportFieldDiffSchema = z
  .object({
    field: z.string(),
    baseValue: z.unknown().optional(),
    targetValue: z.unknown().optional(),
    changed: z.boolean().optional(),
    severity: z.string().optional(),
  })
  .passthrough();

const analysisValueChangeSchema = z
  .object({
    field: z.string(),
    baseValue: z.unknown().optional(),
    targetValue: z.unknown().optional(),
    delta: z.unknown().optional(),
    direction: z.string().optional(),
    comparable: z.boolean().optional(),
    unavailability: z
      .object({
        base: z.string().nullable().optional(),
        target: z.string().nullable().optional(),
      })
      .passthrough()
      .nullable()
      .optional(),
  })
  .passthrough();

const analysisListChangeSchema = z
  .object({
    field: z.string(),
    added: z.array(z.string()).optional(),
    removed: z.array(z.string()).optional(),
    unchanged: z.array(z.string()).optional(),
    addedTotal: z.number().int().optional(),
    removedTotal: z.number().int().optional(),
    unchangedTotal: z.number().int().optional(),
    outputTruncated: z.boolean().optional(),
  })
  .passthrough();

const optionalSectionPresenceSchema = z
  .object({
    section: z.string(),
    basePresent: z.boolean().optional(),
    targetPresent: z.boolean().optional(),
    comparisonStatus: z.string(),
    baseItemCount: z.number().int().optional(),
    targetItemCount: z.number().int().optional(),
    basePreview: z.array(z.string()).optional(),
    targetPreview: z.array(z.string()).optional(),
  })
  .passthrough();

const analysisDeltaPayloadSchema = z
  .object({
    hasBaseline: z.boolean().optional(),
    baselineStatus: z.string(),
    baselineReason: z.string().nullable().optional(),
    stockCode: z.string().nullable().optional(),
    baseRecordId: z.number().int(),
    targetRecordId: z.number().int(),
    baseQueryId: z.string().nullable().optional(),
    targetQueryId: z.string().nullable().optional(),
    reportType: z.string().nullable().optional(),
    hasMaterialChanges: z.boolean().optional(),
    conclusionChanges: z.array(analysisValueChangeSchema).optional(),
    scoreChanges: z.array(analysisValueChangeSchema).optional(),
    evidenceChanges: z.array(analysisListChangeSchema).optional(),
    riskChanges: z.array(analysisListChangeSchema).optional(),
  })
  .passthrough();

const reportVersionCompareResponseSchema = z
  .object({
    status: z.string(),
    stockCode: z.string(),
    baseRun: reportVersionRunItemSchema,
    targetRun: reportVersionRunItemSchema,
    configDiff: configFingerprintDiffSchema,
    fieldDiffs: z.array(reportFieldDiffSchema).optional(),
    optionalSections: z.array(optionalSectionPresenceSchema).optional(),
    delta: analysisDeltaPayloadSchema.nullable().optional(),
    engineStatus: z.string(),
  })
  .passthrough();

function normalizeRunItem(item: ReportVersionRunItem): ReportVersionRunItem {
  return {
    ...item,
    configComponents: item.configComponents ?? {},
    configComplete: item.configComplete ?? false,
    configMissingKeys: item.configMissingKeys ?? [],
  };
}

function normalizeOptionalSection(row: OptionalSectionPresence): OptionalSectionPresence {
  return {
    ...row,
    basePresent: row.basePresent ?? false,
    targetPresent: row.targetPresent ?? false,
    baseItemCount: row.baseItemCount ?? 0,
    targetItemCount: row.targetItemCount ?? 0,
    basePreview: row.basePreview ?? [],
    targetPreview: row.targetPreview ?? [],
  };
}

function normalizeConfigDiff(diff: ConfigFingerprintDiff): ConfigFingerprintDiff {
  return {
    ...diff,
    components: diff.components ?? [],
    baseMissingKeys: diff.baseMissingKeys ?? [],
    targetMissingKeys: diff.targetMissingKeys ?? [],
    identical: diff.identical ?? false,
    hasDifferences: diff.hasDifferences ?? false,
    comparisonStatus: diff.comparisonStatus ?? 'unknown',
    baseComplete: diff.baseComplete ?? false,
    targetComplete: diff.targetComplete ?? false,
  };
}

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
    const parsed = parseCamelCasePayload<ReportVersionRunListResponse>(
      response.data,
      reportVersionRunListResponseSchema,
      'ReportVersionRunListResponse',
      'reportVersionCompare',
    );
    return {
      ...parsed,
      items: (parsed.items ?? []).map((item) => normalizeRunItem(item)),
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
    const parsed = parseCamelCasePayload<ReportVersionCompareResponse>(
      response.data,
      reportVersionCompareResponseSchema,
      'ReportVersionCompareResponse',
      'reportVersionCompare',
    );
    return {
      ...parsed,
      baseRun: normalizeRunItem(parsed.baseRun),
      targetRun: normalizeRunItem(parsed.targetRun),
      configDiff: normalizeConfigDiff(parsed.configDiff),
      fieldDiffs: parsed.fieldDiffs ?? [],
      optionalSections: (parsed.optionalSections ?? []).map((item) => (
        normalizeOptionalSection(item)
      )),
    };
  },
};
