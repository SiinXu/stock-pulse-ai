// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Client for authenticated `/api/v1/skill-outcomes` endpoints.
 * Types are derived from generated OpenAPI components (no parallel hand-written schemas).
 * JSON responses fail closed via Zod at the camelCase boundary.
 */
import { z } from 'zod';
import type { components } from '../types/api.generated';
import apiClient from './index';
import { assertCamelCasePayload } from './parseCamelCasePayload';
import { toCamelCase } from './utils';

type Schemas = components['schemas'];

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? Array<CamelizeKeys<U>>
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

export type SkillOpinionOutcomeItemDto = Schemas['SkillOpinionOutcomeItem'];
export type SkillOpinionOutcomeListResponseDto = Schemas['SkillOpinionOutcomeListResponse'];
export type SkillOpinionOutcomeRunRequestDto = Schemas['SkillOpinionOutcomeRunRequest'];
export type SkillOpinionOutcomeRunResponseDto = Schemas['SkillOpinionOutcomeRunResponse'];
export type SkillOpinionPerformanceBucketItemDto = Schemas['SkillOpinionPerformanceBucketItem'];
export type SkillOpinionPerformanceStatsResponseDto = Schemas['SkillOpinionPerformanceStatsResponse'];
export type SkillOpinionSampleItemDto = Schemas['SkillOpinionSampleItem'];
export type SkillOpinionSampleListResponseDto = Schemas['SkillOpinionSampleListResponse'];

type _AssertOutcomeItem = keyof SkillOpinionOutcomeItemDto;
type _AssertOutcomeList = keyof SkillOpinionOutcomeListResponseDto;
type _AssertStats = keyof SkillOpinionPerformanceStatsResponseDto;
type _AssertSample = keyof SkillOpinionSampleItemDto;
type _AssertRun = keyof SkillOpinionOutcomeRunResponseDto;
const _outcomeItemAnchor: _AssertOutcomeItem = 'skill_opinion_sample_id';
const _outcomeListAnchor: _AssertOutcomeList = 'engine_version';
const _statsAnchor: _AssertStats = 'minimum_evaluated_sample_size';
const _sampleAnchor: _AssertSample = 'sample_schema_version';
const _runAnchor: _AssertRun = 'histories_scanned';
void _outcomeItemAnchor;
void _outcomeListAnchor;
void _statsAnchor;
void _sampleAnchor;
void _runAnchor;


export type SkillOutcomeItem = CamelizeKeys<SkillOpinionOutcomeItemDto>;
export type SkillOutcomeListResponse = CamelizeKeys<SkillOpinionOutcomeListResponseDto>;
export type SkillOutcomeRunRequest = CamelizeKeys<SkillOpinionOutcomeRunRequestDto>;
export type SkillOutcomeRunResponse = CamelizeKeys<SkillOpinionOutcomeRunResponseDto>;
export type SkillOutcomePerformanceBucket = CamelizeKeys<SkillOpinionPerformanceBucketItemDto>;
export type SkillOutcomePerformanceStats = CamelizeKeys<SkillOpinionPerformanceStatsResponseDto>;
export type SkillOutcomeSampleItem = CamelizeKeys<SkillOpinionSampleItemDto>;
export type SkillOutcomeSampleListResponse = CamelizeKeys<SkillOpinionSampleListResponseDto>;

export type SkillOutcomeListParams = {
  skillId?: string;
  stockCode?: string;
  horizon?: string;
  evalStatus?: string;
  sampleId?: number;
  analysisHistoryId?: number;
  engineVersion?: string;
  limit?: number;
  offset?: number;
};

export type SkillOutcomeStatsParams = {
  skillId?: string;
  skillIds?: string[];
  horizons?: string[];
  engineVersion?: string;
};

export type SkillOutcomeSampleListParams = {
  skillId?: string;
  stockCode?: string;
  analysisHistoryId?: number;
  limit?: number;
  offset?: number;
};


const finiteNumber = z.number().refine((value) => Number.isFinite(value), {
  message: 'non-finite number rejected',
});
const optionalFinite = finiteNumber.nullable().optional();

const skillOutcomeItemSchema = z
  .object({
    id: z.number().int(),
    skillOpinionSampleId: z.number().int(),
    analysisHistoryId: z.number().int(),
    stockCode: z.string(),
    skillId: z.string(),
    signal: z.string(),
    horizon: z.string(),
    engineVersion: z.string(),
    evalStatus: z.string(),
  })
  .passthrough();

const skillOutcomeListResponseSchema = z
  .object({
    total: z.number().int(),
    limit: z.number().int(),
    offset: z.number().int(),
    engineVersion: z.string(),
    items: z.array(skillOutcomeItemSchema).optional(),
  })
  .passthrough();

const skillOutcomePerformanceBucketSchema = z
  .object({
    skillId: z.string(),
    horizon: z.string(),
    engineVersion: z.string(),
    total: z.number().int(),
    pending: z.number().int(),
    evaluated: z.number().int(),
    observational: z.number().int(),
    unable: z.number().int(),
    hit: z.number().int(),
    miss: z.number().int(),
    sampleSufficient: z.boolean(),
    sampleStatus: z.string(),
    hitRatePct: optionalFinite,
    missRatePct: optionalFinite,
    avgDirectionalReturnPct: optionalFinite,
    unableRatePct: optionalFinite,
  })
  .passthrough();

const skillOutcomePerformanceStatsSchema = z
  .object({
    engineVersion: z.string(),
    minimumEvaluatedSampleSize: z.number().int(),
    buckets: z.array(skillOutcomePerformanceBucketSchema).optional(),
  })
  .passthrough();

const skillOutcomeSampleItemSchema = z
  .object({
    id: z.number().int(),
    analysisHistoryId: z.number().int(),
    stockCode: z.string(),
    skillId: z.string(),
    signal: z.string(),
    confidence: z.union([z.string(), finiteNumber]),
    sampleSchemaVersion: z.string(),
  })
  .passthrough();

const skillOutcomeSampleListResponseSchema = z
  .object({
    total: z.number().int(),
    limit: z.number().int(),
    offset: z.number().int(),
    items: z.array(skillOutcomeSampleItemSchema).optional(),
  })
  .passthrough();

const skillOutcomeRunErrorSchema = z
  .object({
    errorType: z.string(),
  })
  .passthrough();

const skillOutcomeRunResponseSchema = z
  .object({
    processedKeys: z.number().int(),
    created: z.number().int(),
    updated: z.number().int(),
    skipped: z.number().int(),
    failed: z.number().int(),
    historiesScanned: z.number().int(),
    samplesCreated: z.number().int(),
    limitUnit: z.string(),
    engineVersion: z.string(),
    items: z.array(skillOutcomeItemSchema).optional(),
    errors: z.array(skillOutcomeRunErrorSchema).optional(),
  })
  .passthrough();

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

function toStatsResponse(data: Record<string, unknown>): SkillOutcomePerformanceStats {
  const response = toCamelCase<SkillOutcomePerformanceStats>(data);
  const rawBuckets = data.buckets;
  response.buckets = Array.isArray(rawBuckets)
    ? rawBuckets.map((bucket) => toCamelCase<SkillOutcomePerformanceBucket>(bucket as Record<string, unknown>))
    : [];
  return assertCamelCasePayload<SkillOutcomePerformanceStats>(
    response,
    skillOutcomePerformanceStatsSchema,
    'SkillOpinionPerformanceStatsResponse',
    'skillOutcomes',
  );
}

function toOutcomeListResponse(data: Record<string, unknown>): SkillOutcomeListResponse {
  const response = toCamelCase<SkillOutcomeListResponse>(data);
  const rawItems = data.items;
  response.items = Array.isArray(rawItems)
    ? rawItems.map((item) => toCamelCase<SkillOutcomeItem>(item as Record<string, unknown>))
    : [];
  return assertCamelCasePayload<SkillOutcomeListResponse>(
    response,
    skillOutcomeListResponseSchema,
    'SkillOpinionOutcomeListResponse',
    'skillOutcomes',
  );
}

function toSampleListResponse(data: Record<string, unknown>): SkillOutcomeSampleListResponse {
  const response = toCamelCase<SkillOutcomeSampleListResponse>(data);
  const rawItems = data.items;
  response.items = Array.isArray(rawItems)
    ? rawItems.map((item) => toCamelCase<SkillOutcomeSampleItem>(item as Record<string, unknown>))
    : [];
  return assertCamelCasePayload<SkillOutcomeSampleListResponse>(
    response,
    skillOutcomeSampleListResponseSchema,
    'SkillOpinionSampleListResponse',
    'skillOutcomes',
  );
}

function toRunResponse(data: Record<string, unknown>): SkillOutcomeRunResponse {
  const response = toCamelCase<SkillOutcomeRunResponse>(data);
  const rawItems = data.items;
  response.items = Array.isArray(rawItems)
    ? rawItems.map((item) => toCamelCase<SkillOutcomeItem>(item as Record<string, unknown>))
    : [];
  const rawErrors = data.errors;
  response.errors = Array.isArray(rawErrors)
    ? rawErrors.map((item) => toCamelCase(item as Record<string, unknown>))
    : [];
  return assertCamelCasePayload<SkillOutcomeRunResponse>(
    response,
    skillOutcomeRunResponseSchema,
    'SkillOpinionOutcomeRunResponse',
    'skillOutcomes',
  );
}

function toSnakeRunPayload(payload: SkillOutcomeRunRequest): SkillOpinionOutcomeRunRequestDto {
  return omitUndefined({
    sample_id: payload.sampleId,
    analysis_history_id: payload.analysisHistoryId,
    skill_id: payload.skillId,
    stock_code: payload.stockCode,
    horizons: payload.horizons,
    limit: payload.limit ?? 100,
  }) as SkillOpinionOutcomeRunRequestDto;
}

export const skillOutcomesApi = {
  async getStats(params: SkillOutcomeStatsParams = {}): Promise<SkillOutcomePerformanceStats> {
    const query = serializeRepeatedQueryParams(omitUndefined({
      skill_id: params.skillId,
      skill_ids: params.skillIds,
      horizons: params.horizons,
      engine_version: params.engineVersion,
    }));
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/skill-outcomes/stats${query ? `?${query}` : ''}`,
    );
    return toStatsResponse(response.data);
  },

  async listOutcomes(params: SkillOutcomeListParams = {}): Promise<SkillOutcomeListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/skill-outcomes', {
      params: omitUndefined({
        skill_id: params.skillId,
        stock_code: params.stockCode,
        horizon: params.horizon,
        eval_status: params.evalStatus,
        sample_id: params.sampleId,
        analysis_history_id: params.analysisHistoryId,
        engine_version: params.engineVersion,
        limit: params.limit ?? 50,
        offset: params.offset ?? 0,
      }),
    });
    return toOutcomeListResponse(response.data);
  },

  async listSamples(params: SkillOutcomeSampleListParams = {}): Promise<SkillOutcomeSampleListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/skill-outcomes/samples', {
      params: omitUndefined({
        skill_id: params.skillId,
        stock_code: params.stockCode,
        analysis_history_id: params.analysisHistoryId,
        limit: params.limit ?? 50,
        offset: params.offset ?? 0,
      }),
    });
    return toSampleListResponse(response.data);
  },

  async runOutcomes(payload: SkillOutcomeRunRequest = { limit: 100 }): Promise<SkillOutcomeRunResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/skill-outcomes/run',
      toSnakeRunPayload(payload),
    );
    return toRunResponse(response.data);
  },
};
