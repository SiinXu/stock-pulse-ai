// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { components, operations, paths } from './api.generated';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type OpenApiOutcomeItem = components['schemas']['SkillOpinionOutcomeItem'];
type OpenApiOutcomeListResponse = components['schemas']['SkillOpinionOutcomeListResponse'];
type OpenApiRunErrorItem = components['schemas']['SkillOpinionOutcomeRunErrorItem'];
type OpenApiRunRequest = components['schemas']['SkillOpinionOutcomeRunRequest'];
type OpenApiRunResponse = components['schemas']['SkillOpinionOutcomeRunResponse'];
type OpenApiPerformanceBucket = components['schemas']['SkillOpinionPerformanceBucketItem'];
type OpenApiPerformanceStats = components['schemas']['SkillOpinionPerformanceStatsResponse'];
type OpenApiSampleItem = components['schemas']['SkillOpinionSampleItem'];
type OpenApiSampleListResponse = components['schemas']['SkillOpinionSampleListResponse'];

type OpenApiListOp = operations['listSkillOpinionOutcomes'];
type OpenApiRunOp = operations['runSkillOpinionOutcomes'];
type OpenApiSamplesOp = operations['listSkillOpinionSamples'];
type OpenApiStatsOp = operations['getSkillOpinionOutcomeStats'];
type OpenApiPathListGet = paths['/api/v1/skill-outcomes']['get'];
type OpenApiPathRunPost = paths['/api/v1/skill-outcomes/run']['post'];
type OpenApiPathSamplesGet = paths['/api/v1/skill-outcomes/samples']['get'];
type OpenApiPathStatsGet = paths['/api/v1/skill-outcomes/stats']['get'];
type OpenApiList200 = OpenApiListOp['responses']['200']['content']['application/json'];
type OpenApiRun200 = OpenApiRunOp['responses']['200']['content']['application/json'];
type OpenApiSamples200 = OpenApiSamplesOp['responses']['200']['content']['application/json'];
type OpenApiStats200 = OpenApiStatsOp['responses']['200']['content']['application/json'];
type OpenApiRunBody = OpenApiRunOp['requestBody']['content']['application/json'];
type OpenApiListQuery = NonNullable<OpenApiListOp['parameters']['query']>;
type OpenApiStatsQuery = NonNullable<OpenApiStatsOp['parameters']['query']>;
type OpenApiSamplesQuery = NonNullable<OpenApiSamplesOp['parameters']['query']>;

type _Assert<T extends true> = T;
type _List200IsComponent = _Assert<OpenApiList200 extends OpenApiOutcomeListResponse ? true : false>;
type _ComponentIsList200 = _Assert<OpenApiOutcomeListResponse extends OpenApiList200 ? true : false>;
type _ListOpIsPath = _Assert<OpenApiListOp extends OpenApiPathListGet ? true : false>;
type _PathIsListOp = _Assert<OpenApiPathListGet extends OpenApiListOp ? true : false>;
type _Run200IsComponent = _Assert<OpenApiRun200 extends OpenApiRunResponse ? true : false>;
type _ComponentIsRun200 = _Assert<OpenApiRunResponse extends OpenApiRun200 ? true : false>;
type _RunOpIsPath = _Assert<OpenApiRunOp extends OpenApiPathRunPost ? true : false>;
type _PathIsRunOp = _Assert<OpenApiPathRunPost extends OpenApiRunOp ? true : false>;
type _RunBodyIsRequest = _Assert<OpenApiRunBody extends OpenApiRunRequest ? true : false>;
type _RequestIsRunBody = _Assert<OpenApiRunRequest extends OpenApiRunBody ? true : false>;
type _Samples200IsComponent = _Assert<OpenApiSamples200 extends OpenApiSampleListResponse ? true : false>;
type _ComponentIsSamples200 = _Assert<OpenApiSampleListResponse extends OpenApiSamples200 ? true : false>;
type _SamplesOpIsPath = _Assert<OpenApiSamplesOp extends OpenApiPathSamplesGet ? true : false>;
type _PathIsSamplesOp = _Assert<OpenApiPathSamplesGet extends OpenApiSamplesOp ? true : false>;
type _Stats200IsComponent = _Assert<OpenApiStats200 extends OpenApiPerformanceStats ? true : false>;
type _ComponentIsStats200 = _Assert<OpenApiPerformanceStats extends OpenApiStats200 ? true : false>;
type _StatsOpIsPath = _Assert<OpenApiStatsOp extends OpenApiPathStatsGet ? true : false>;
type _PathIsStatsOp = _Assert<OpenApiPathStatsGet extends OpenApiStatsOp ? true : false>;
type _ListGetNeverRequestBody = _Assert<OpenApiListOp extends { requestBody?: never } ? true : false>;
type _SamplesGetNeverRequestBody = _Assert<OpenApiSamplesOp extends { requestBody?: never } ? true : false>;
type _StatsGetNeverRequestBody = _Assert<OpenApiStatsOp extends { requestBody?: never } ? true : false>;
type _PathListPostNever = _Assert<
  paths['/api/v1/skill-outcomes']['post'] extends never | undefined ? true : false
>;
type _PathListPutNever = _Assert<
  paths['/api/v1/skill-outcomes']['put'] extends never | undefined ? true : false
>;
type _PathListDeleteNever = _Assert<
  paths['/api/v1/skill-outcomes']['delete'] extends never | undefined ? true : false
>;
type _PathListPatchNever = _Assert<
  paths['/api/v1/skill-outcomes']['patch'] extends never | undefined ? true : false
>;
type _PathRunGetNever = _Assert<
  paths['/api/v1/skill-outcomes/run']['get'] extends never | undefined ? true : false
>;
type _PathRunPutNever = _Assert<
  paths['/api/v1/skill-outcomes/run']['put'] extends never | undefined ? true : false
>;
type _PathRunDeleteNever = _Assert<
  paths['/api/v1/skill-outcomes/run']['delete'] extends never | undefined ? true : false
>;
type _PathRunPatchNever = _Assert<
  paths['/api/v1/skill-outcomes/run']['patch'] extends never | undefined ? true : false
>;
type _PathSamplesPostNever = _Assert<
  paths['/api/v1/skill-outcomes/samples']['post'] extends never | undefined ? true : false
>;
type _PathSamplesPutNever = _Assert<
  paths['/api/v1/skill-outcomes/samples']['put'] extends never | undefined ? true : false
>;
type _PathSamplesDeleteNever = _Assert<
  paths['/api/v1/skill-outcomes/samples']['delete'] extends never | undefined ? true : false
>;
type _PathSamplesPatchNever = _Assert<
  paths['/api/v1/skill-outcomes/samples']['patch'] extends never | undefined ? true : false
>;
type _PathStatsPostNever = _Assert<
  paths['/api/v1/skill-outcomes/stats']['post'] extends never | undefined ? true : false
>;
type _PathStatsPutNever = _Assert<
  paths['/api/v1/skill-outcomes/stats']['put'] extends never | undefined ? true : false
>;
type _PathStatsDeleteNever = _Assert<
  paths['/api/v1/skill-outcomes/stats']['delete'] extends never | undefined ? true : false
>;
type _PathStatsPatchNever = _Assert<
  paths['/api/v1/skill-outcomes/stats']['patch'] extends never | undefined ? true : false
>;
type _RunQueryNever = _Assert<
  OpenApiRunOp['parameters']['query'] extends never | undefined ? true : false
>;
type _RunHeaderNever = _Assert<
  OpenApiRunOp['parameters']['header'] extends never | undefined ? true : false
>;
type _RunPathNever = _Assert<
  OpenApiRunOp['parameters']['path'] extends never | undefined ? true : false
>;
type _RunCookieNever = _Assert<
  OpenApiRunOp['parameters']['cookie'] extends never | undefined ? true : false
>;
type _ListQueryHasSkillIdSnake = _Assert<'skill_id' extends keyof OpenApiListQuery ? true : false>;
type _ListQueryHasStockCodeSnake = _Assert<'stock_code' extends keyof OpenApiListQuery ? true : false>;
type _ListQueryHasHorizonSnake = _Assert<'horizon' extends keyof OpenApiListQuery ? true : false>;
type _ListQueryHasEvalStatusSnake = _Assert<'eval_status' extends keyof OpenApiListQuery ? true : false>;
type _ListQueryHasSampleIdSnake = _Assert<'sample_id' extends keyof OpenApiListQuery ? true : false>;
type _ListQueryHasAnalysisHistoryIdSnake = _Assert<
  'analysis_history_id' extends keyof OpenApiListQuery ? true : false
>;
type _ListQueryHasEngineVersionSnake = _Assert<'engine_version' extends keyof OpenApiListQuery ? true : false>;
type _ListQueryHasLimitSnake = _Assert<'limit' extends keyof OpenApiListQuery ? true : false>;
type _ListQueryHasOffsetSnake = _Assert<'offset' extends keyof OpenApiListQuery ? true : false>;
type _ListQueryLacksSkillIdCamel = _Assert<'skillId' extends keyof OpenApiListQuery ? false : true>;
type _StatsQueryHasSkillIdSnake = _Assert<'skill_id' extends keyof OpenApiStatsQuery ? true : false>;
type _StatsQueryHasSkillIdsSnake = _Assert<'skill_ids' extends keyof OpenApiStatsQuery ? true : false>;
type _StatsQueryHasHorizonsSnake = _Assert<'horizons' extends keyof OpenApiStatsQuery ? true : false>;
type _StatsQueryHasEngineVersionSnake = _Assert<'engine_version' extends keyof OpenApiStatsQuery ? true : false>;
type _StatsQueryLacksSkillIdCamel = _Assert<'skillId' extends keyof OpenApiStatsQuery ? false : true>;
type _SamplesQueryHasSkillIdSnake = _Assert<'skill_id' extends keyof OpenApiSamplesQuery ? true : false>;
type _SamplesQueryHasStockCodeSnake = _Assert<'stock_code' extends keyof OpenApiSamplesQuery ? true : false>;
type _SamplesQueryHasAnalysisHistoryIdSnake = _Assert<
  'analysis_history_id' extends keyof OpenApiSamplesQuery ? true : false
>;
type _SamplesQueryHasLimitSnake = _Assert<'limit' extends keyof OpenApiSamplesQuery ? true : false>;
type _SamplesQueryHasOffsetSnake = _Assert<'offset' extends keyof OpenApiSamplesQuery ? true : false>;
type _SamplesQueryLacksSkillIdCamel = _Assert<'skillId' extends keyof OpenApiSamplesQuery ? false : true>;

type _OpenApiAnchors = [
  _List200IsComponent,
  _ComponentIsList200,
  _ListOpIsPath,
  _PathIsListOp,
  _Run200IsComponent,
  _ComponentIsRun200,
  _RunOpIsPath,
  _PathIsRunOp,
  _RunBodyIsRequest,
  _RequestIsRunBody,
  _Samples200IsComponent,
  _ComponentIsSamples200,
  _SamplesOpIsPath,
  _PathIsSamplesOp,
  _Stats200IsComponent,
  _ComponentIsStats200,
  _StatsOpIsPath,
  _PathIsStatsOp,
  _ListGetNeverRequestBody,
  _SamplesGetNeverRequestBody,
  _StatsGetNeverRequestBody,
  _PathListPostNever,
  _PathListPutNever,
  _PathListDeleteNever,
  _PathListPatchNever,
  _PathRunGetNever,
  _PathRunPutNever,
  _PathRunDeleteNever,
  _PathRunPatchNever,
  _PathSamplesPostNever,
  _PathSamplesPutNever,
  _PathSamplesDeleteNever,
  _PathSamplesPatchNever,
  _PathStatsPostNever,
  _PathStatsPutNever,
  _PathStatsDeleteNever,
  _PathStatsPatchNever,
  _RunQueryNever,
  _RunHeaderNever,
  _RunPathNever,
  _RunCookieNever,
  _ListQueryHasSkillIdSnake,
  _ListQueryHasStockCodeSnake,
  _ListQueryHasHorizonSnake,
  _ListQueryHasEvalStatusSnake,
  _ListQueryHasSampleIdSnake,
  _ListQueryHasAnalysisHistoryIdSnake,
  _ListQueryHasEngineVersionSnake,
  _ListQueryHasLimitSnake,
  _ListQueryHasOffsetSnake,
  _ListQueryLacksSkillIdCamel,
  _StatsQueryHasSkillIdSnake,
  _StatsQueryHasSkillIdsSnake,
  _StatsQueryHasHorizonsSnake,
  _StatsQueryHasEngineVersionSnake,
  _StatsQueryLacksSkillIdCamel,
  _SamplesQueryHasSkillIdSnake,
  _SamplesQueryHasStockCodeSnake,
  _SamplesQueryHasAnalysisHistoryIdSnake,
  _SamplesQueryHasLimitSnake,
  _SamplesQueryHasOffsetSnake,
  _SamplesQueryLacksSkillIdCamel,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type SkillOutcomeItem = _BindOpenApiAnchors<CamelizeKeys<OpenApiOutcomeItem>>;
export type SkillOutcomeListResponse = CamelizeKeys<OpenApiOutcomeListResponse>;
export type SkillOutcomeRunErrorItem = CamelizeKeys<OpenApiRunErrorItem>;
export type SkillOutcomeRunRequest = CamelizeKeys<OpenApiRunRequest>;
export type SkillOutcomeRunResponse = CamelizeKeys<OpenApiRunResponse>;
export type SkillOutcomePerformanceBucket = CamelizeKeys<OpenApiPerformanceBucket>;
export type SkillOutcomePerformanceStats = CamelizeKeys<OpenApiPerformanceStats>;
export type SkillOutcomeSampleItem = CamelizeKeys<OpenApiSampleItem>;
export type SkillOutcomeSampleListResponse = CamelizeKeys<OpenApiSampleListResponse>;

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
