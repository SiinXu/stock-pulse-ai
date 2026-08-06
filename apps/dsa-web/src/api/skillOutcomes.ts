// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Client for authenticated `/api/v1/skill-outcomes` endpoints.
 * Types are derived from generated OpenAPI components (no parallel hand-written schemas).
 */
import type { components } from '../types/api.generated';
import apiClient from './index';
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
  return response;
}

function toOutcomeListResponse(data: Record<string, unknown>): SkillOutcomeListResponse {
  const response = toCamelCase<SkillOutcomeListResponse>(data);
  const rawItems = data.items;
  response.items = Array.isArray(rawItems)
    ? rawItems.map((item) => toCamelCase<SkillOutcomeItem>(item as Record<string, unknown>))
    : [];
  return response;
}

function toSampleListResponse(data: Record<string, unknown>): SkillOutcomeSampleListResponse {
  const response = toCamelCase<SkillOutcomeSampleListResponse>(data);
  const rawItems = data.items;
  response.items = Array.isArray(rawItems)
    ? rawItems.map((item) => toCamelCase<SkillOutcomeSampleItem>(item as Record<string, unknown>))
    : [];
  return response;
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
  return response;
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
