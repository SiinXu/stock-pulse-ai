// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as SkillOutcomes from '../skillOutcomes';
import type {
  SkillOutcomeItem,
  SkillOutcomeListParams,
  SkillOutcomeListResponse,
  SkillOutcomePerformanceBucket,
  SkillOutcomePerformanceStats,
  SkillOutcomeRunErrorItem,
  SkillOutcomeRunRequest,
  SkillOutcomeRunResponse,
  SkillOutcomeSampleItem,
  SkillOutcomeSampleListParams,
  SkillOutcomeSampleListResponse,
  SkillOutcomeStatsParams,
} from '../skillOutcomes';
import type * as ApiSkillOutcomes from '../../api/skillOutcomes';
import type { SkillOutcomeRunErrorItem as ApiSkillOutcomeRunErrorItem } from '../../api/skillOutcomes';

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
type SkillOutcomesApi = typeof import('../../api/skillOutcomes')['skillOutcomesApi'];

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type _Assert<T extends true> = T;
type IsOptional<T, K extends keyof T> = Partial<Pick<T, K>> extends Pick<T, K> ? true : false;
type HorizonLiteral = '1d' | '3d' | '5d' | '10d';

type _NineComponents = _Assert<
  (
    | 'SkillOpinionOutcomeItem'
    | 'SkillOpinionOutcomeListResponse'
    | 'SkillOpinionOutcomeRunErrorItem'
    | 'SkillOpinionOutcomeRunRequest'
    | 'SkillOpinionOutcomeRunResponse'
    | 'SkillOpinionPerformanceBucketItem'
    | 'SkillOpinionPerformanceStatsResponse'
    | 'SkillOpinionSampleItem'
    | 'SkillOpinionSampleListResponse'
  ) extends keyof components['schemas'] ? true : false
>;
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

type _UiHasSkillOpinionSampleId = _Assert<'skillOpinionSampleId' extends keyof SkillOutcomeItem ? true : false>;
type _UiHasAnalysisHistoryId = _Assert<'analysisHistoryId' extends keyof SkillOutcomeItem ? true : false>;
type _UiHasEvalStatus = _Assert<'evalStatus' extends keyof SkillOutcomeItem ? true : false>;
type _UiHasEngineVersion = _Assert<'engineVersion' extends keyof SkillOutcomeItem ? true : false>;
type _UiHasErrorType = _Assert<'errorType' extends keyof SkillOutcomeRunErrorItem ? true : false>;
type _UiHasHistoriesScanned = _Assert<'historiesScanned' extends keyof SkillOutcomeRunResponse ? true : false>;
type _UiHasHitRatePct = _Assert<'hitRatePct' extends keyof SkillOutcomePerformanceBucket ? true : false>;
type _UiHasMinimumEvaluatedSampleSize = _Assert<
  'minimumEvaluatedSampleSize' extends keyof SkillOutcomePerformanceStats ? true : false
>;
type _UiHasSampleSchemaVersion = _Assert<'sampleSchemaVersion' extends keyof SkillOutcomeSampleItem ? true : false>;
type _UiLacksSkillOpinionSampleIdSnake = _Assert<
  'skill_opinion_sample_id' extends keyof SkillOutcomeItem ? false : true
>;
type _UiLacksAnalysisHistoryIdSnake = _Assert<'analysis_history_id' extends keyof SkillOutcomeItem ? false : true>;
type _UiLacksEvalStatusSnake = _Assert<'eval_status' extends keyof SkillOutcomeItem ? false : true>;
type _UiLacksErrorTypeSnake = _Assert<'error_type' extends keyof SkillOutcomeRunErrorItem ? false : true>;
type _UiLacksHistoriesScannedSnake = _Assert<
  'histories_scanned' extends keyof SkillOutcomeRunResponse ? false : true
>;
type _UiLacksHitRatePctSnake = _Assert<'hit_rate_pct' extends keyof SkillOutcomePerformanceBucket ? false : true>;
type _UiLacksMinimumEvaluatedSampleSizeSnake = _Assert<
  'minimum_evaluated_sample_size' extends keyof SkillOutcomePerformanceStats ? false : true
>;
type _UiLacksSampleSchemaVersionSnake = _Assert<
  'sample_schema_version' extends keyof SkillOutcomeSampleItem ? false : true
>;
type _GeneratedHasSkillOpinionSampleIdSnake = _Assert<
  'skill_opinion_sample_id' extends keyof OpenApiOutcomeItem ? true : false
>;
type _GeneratedHasSampleSchemaVersionSnake = _Assert<
  'sample_schema_version' extends keyof OpenApiSampleItem ? true : false
>;
type _GeneratedHasErrorTypeSnake = _Assert<'error_type' extends keyof OpenApiRunErrorItem ? true : false>;
type _GeneratedHasHistoriesScannedSnake = _Assert<
  'histories_scanned' extends keyof OpenApiRunResponse ? true : false
>;
type _GeneratedLacksSkillOpinionSampleIdCamel = _Assert<
  'skillOpinionSampleId' extends keyof OpenApiOutcomeItem ? false : true
>;
type _GeneratedLacksErrorTypeCamel = _Assert<'errorType' extends keyof OpenApiRunErrorItem ? false : true>;

type _ErrorItemNamed = _Assert<
  SkillOutcomeRunErrorItem extends CamelizeKeys<OpenApiRunErrorItem>
    ? CamelizeKeys<OpenApiRunErrorItem> extends SkillOutcomeRunErrorItem ? true : false
    : false
>;
type _ErrorItemIsErrorsItem = _Assert<
  SkillOutcomeRunErrorItem extends NonNullable<SkillOutcomeRunResponse['errors']>[number]
    ? NonNullable<SkillOutcomeRunResponse['errors']>[number] extends SkillOutcomeRunErrorItem ? true : false
    : false
>;
type _BucketNamed = _Assert<
  SkillOutcomePerformanceBucket extends CamelizeKeys<OpenApiPerformanceBucket>
    ? CamelizeKeys<OpenApiPerformanceBucket> extends SkillOutcomePerformanceBucket ? true : false
    : false
>;
type _BucketIsStatsItem = _Assert<
  SkillOutcomePerformanceBucket extends NonNullable<SkillOutcomePerformanceStats['buckets']>[number]
    ? NonNullable<SkillOutcomePerformanceStats['buckets']>[number] extends SkillOutcomePerformanceBucket
      ? true : false
    : false
>;
type _NaiveEqualsPublicItem = _Assert<
  SkillOutcomeItem extends CamelizeKeys<OpenApiOutcomeItem>
    ? CamelizeKeys<OpenApiOutcomeItem> extends SkillOutcomeItem ? true : false
    : false
>;
type _LimitRequired = _Assert<IsOptional<SkillOutcomeRunRequest, 'limit'> extends false ? true : false>;
type _GeneratedLimitRequired = _Assert<IsOptional<OpenApiRunRequest, 'limit'> extends false ? true : false>;
type MissingLimit = Omit<SkillOutcomeRunRequest, 'limit'>;
type _MissingLimitRejected = _Assert<MissingLimit extends SkillOutcomeRunRequest ? false : true>;
type _HorizonsOptional = _Assert<IsOptional<SkillOutcomeRunRequest, 'horizons'>>;
type HorizonsValue = Exclude<SkillOutcomeRunRequest['horizons'], undefined>;
type _HorizonsClosed = _Assert<
  HorizonsValue extends HorizonLiteral[] | null
    ? HorizonLiteral[] | null extends HorizonsValue ? true : false
    : false
>;
type _HorizonsNotStringArray = _Assert<
  string[] extends HorizonsValue ? false : true
>;
type _PublicNotGeneratedSnake = _Assert<SkillOutcomeItem extends OpenApiOutcomeItem ? false : true>;

type _ListQueryHasSkillIdSnake = _Assert<'skill_id' extends keyof OpenApiListQuery ? true : false>;
type _ListQueryLacksSkillIdCamel = _Assert<'skillId' extends keyof OpenApiListQuery ? false : true>;
type _PublicListHasSkillId = _Assert<'skillId' extends keyof SkillOutcomeListParams ? true : false>;
type _PublicListHasStockCode = _Assert<'stockCode' extends keyof SkillOutcomeListParams ? true : false>;
type _PublicListHasEvalStatus = _Assert<'evalStatus' extends keyof SkillOutcomeListParams ? true : false>;
type _PublicListHasSampleId = _Assert<'sampleId' extends keyof SkillOutcomeListParams ? true : false>;
type _PublicListHasAnalysisHistoryId = _Assert<
  'analysisHistoryId' extends keyof SkillOutcomeListParams ? true : false
>;
type _PublicListHasEngineVersion = _Assert<'engineVersion' extends keyof SkillOutcomeListParams ? true : false>;
type _PublicListLacksSkillIdSnake = _Assert<'skill_id' extends keyof SkillOutcomeListParams ? false : true>;
type _PublicListRejectsNullSkillId = _Assert<{ skillId: null } extends SkillOutcomeListParams ? false : true>;
type _GeneratedListAcceptsNullSkillId = _Assert<{ skill_id: null } extends OpenApiListQuery ? true : false>;
type _CamelizedListQueryAcceptsNull = _Assert<
  { skillId: null } extends CamelizeKeys<OpenApiListQuery> ? true : false
>;
type _CamelizedListQueryIsNotPublic = _Assert<
  CamelizeKeys<OpenApiListQuery> extends SkillOutcomeListParams ? false : true
>;
type _PublicStatsHasSkillIds = _Assert<'skillIds' extends keyof SkillOutcomeStatsParams ? true : false>;
type _PublicStatsLacksSkillIdsSnake = _Assert<'skill_ids' extends keyof SkillOutcomeStatsParams ? false : true>;
type _StatsQueryHasSkillIdsSnake = _Assert<'skill_ids' extends keyof OpenApiStatsQuery ? true : false>;
type _StatsQueryLacksSkillIdCamel = _Assert<'skillId' extends keyof OpenApiStatsQuery ? false : true>;
type _CamelizedStatsQueryIsNotPublic = _Assert<
  CamelizeKeys<OpenApiStatsQuery> extends SkillOutcomeStatsParams ? false : true
>;
type _PublicSamplesHasAnalysisHistoryId = _Assert<
  'analysisHistoryId' extends keyof SkillOutcomeSampleListParams ? true : false
>;
type _SamplesQueryHasAnalysisHistoryIdSnake = _Assert<
  'analysis_history_id' extends keyof OpenApiSamplesQuery ? true : false
>;
type _SamplesQueryLacksSkillIdCamel = _Assert<'skillId' extends keyof OpenApiSamplesQuery ? false : true>;
type _CamelizedSamplesQueryIsNotPublic = _Assert<
  CamelizeKeys<OpenApiSamplesQuery> extends SkillOutcomeSampleListParams ? false : true
>;

type SampleOutcomeFixture = {
  id: 1;
  skillOpinionSampleId: 9;
  analysisHistoryId: 100;
  stockCode: 'AAPL';
  skillId: 'momentum';
  signal: 'buy';
  horizon: '5d';
  engineVersion: 'skill-opinion-outcome-v1';
  evalStatus: 'pending';
  outcome: null;
  directionCorrect: null;
  unableReason: null;
  analysisDate: '2026-08-01';
  startTradeDate: null;
  endTradeDate: null;
  startPrice: null;
  endClose: null;
  stockReturnPct: null;
  directionalReturnPct: null;
  createdAt: null;
  updatedAt: null;
};
type _SampleOutcomeAssignable = _Assert<SampleOutcomeFixture extends SkillOutcomeItem ? true : false>;
type SnakeOutcome = {
  id: 1;
  skill_opinion_sample_id: 9;
  analysis_history_id: 100;
  stock_code: 'AAPL';
  skill_id: 'momentum';
  signal: 'buy';
  horizon: '5d';
  engine_version: 'skill-opinion-outcome-v1';
  eval_status: 'pending';
};
type _SnakeMatchesGenerated = _Assert<SnakeOutcome extends OpenApiOutcomeItem ? true : false>;
type _SnakeDoesNotMatchUi = _Assert<SnakeOutcome extends SkillOutcomeItem ? false : true>;
type ListOutcomesArg = NonNullable<Parameters<SkillOutcomesApi['listOutcomes']>[0]>;
type RunOutcomesArg = NonNullable<Parameters<SkillOutcomesApi['runOutcomes']>[0]>;
type _ListParamsEqual = _Assert<
  ListOutcomesArg extends SkillOutcomeListParams
    ? SkillOutcomeListParams extends ListOutcomesArg ? true : false
    : false
>;
type _RunParamsEqual = _Assert<
  RunOutcomesArg extends SkillOutcomeRunRequest
    ? SkillOutcomeRunRequest extends RunOutcomesArg ? true : false
    : false
>;

type _CompileTimePins = [
  _NineComponents, _List200IsComponent, _ComponentIsList200, _ListOpIsPath, _PathIsListOp,
  _Run200IsComponent, _ComponentIsRun200, _RunOpIsPath, _PathIsRunOp, _RunBodyIsRequest,
  _RequestIsRunBody, _Samples200IsComponent, _ComponentIsSamples200, _SamplesOpIsPath,
  _PathIsSamplesOp, _Stats200IsComponent, _ComponentIsStats200, _StatsOpIsPath, _PathIsStatsOp,
  _ListGetNeverRequestBody, _SamplesGetNeverRequestBody, _StatsGetNeverRequestBody,
  _PathListPostNever, _PathListPutNever, _PathListDeleteNever, _PathListPatchNever,
  _PathRunGetNever, _PathRunPutNever, _PathRunDeleteNever, _PathRunPatchNever,
  _PathSamplesPostNever, _PathSamplesPutNever, _PathSamplesDeleteNever, _PathSamplesPatchNever,
  _PathStatsPostNever, _PathStatsPutNever, _PathStatsDeleteNever, _PathStatsPatchNever,
  _RunQueryNever, _RunHeaderNever, _RunPathNever, _RunCookieNever, _UiHasSkillOpinionSampleId,
  _UiHasAnalysisHistoryId, _UiHasEvalStatus, _UiHasEngineVersion, _UiHasErrorType,
  _UiHasHistoriesScanned, _UiHasHitRatePct, _UiHasMinimumEvaluatedSampleSize,
  _UiHasSampleSchemaVersion, _UiLacksSkillOpinionSampleIdSnake, _UiLacksAnalysisHistoryIdSnake,
  _UiLacksEvalStatusSnake, _UiLacksErrorTypeSnake, _UiLacksHistoriesScannedSnake,
  _UiLacksHitRatePctSnake, _UiLacksMinimumEvaluatedSampleSizeSnake, _UiLacksSampleSchemaVersionSnake,
  _GeneratedHasSkillOpinionSampleIdSnake, _GeneratedHasSampleSchemaVersionSnake, _GeneratedHasErrorTypeSnake,
  _GeneratedHasHistoriesScannedSnake, _GeneratedLacksSkillOpinionSampleIdCamel,
  _GeneratedLacksErrorTypeCamel, _ErrorItemNamed, _ErrorItemIsErrorsItem, _BucketNamed,
  _BucketIsStatsItem, _NaiveEqualsPublicItem, _LimitRequired, _GeneratedLimitRequired,
  _MissingLimitRejected, _HorizonsOptional, _HorizonsClosed, _HorizonsNotStringArray,
  _PublicNotGeneratedSnake, _ListQueryHasSkillIdSnake, _ListQueryLacksSkillIdCamel,
  _PublicListHasSkillId, _PublicListHasStockCode, _PublicListHasEvalStatus, _PublicListHasSampleId,
  _PublicListHasAnalysisHistoryId, _PublicListHasEngineVersion, _PublicListLacksSkillIdSnake,
  _PublicListRejectsNullSkillId, _GeneratedListAcceptsNullSkillId, _CamelizedListQueryAcceptsNull,
  _CamelizedListQueryIsNotPublic, _PublicStatsHasSkillIds, _PublicStatsLacksSkillIdsSnake,
  _StatsQueryHasSkillIdsSnake, _StatsQueryLacksSkillIdCamel, _CamelizedStatsQueryIsNotPublic,
  _PublicSamplesHasAnalysisHistoryId, _SamplesQueryHasAnalysisHistoryIdSnake,
  _SamplesQueryLacksSkillIdCamel, _CamelizedSamplesQueryIsNotPublic, _SampleOutcomeAssignable,
  _SnakeMatchesGenerated, _SnakeDoesNotMatchUi, _ListParamsEqual, _RunParamsEqual,
];

describe('skillOutcomes OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    expect({ ...SkillOutcomes }).toEqual({});
    expect(Object.keys(SkillOutcomes)).toEqual([]);
    expect(Object.getOwnPropertyNames(SkillOutcomes)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('re-exports the public camelCase names from api/skillOutcomes', () => {
    expectTypeOf<ApiSkillOutcomes.SkillOutcomeItem>().toEqualTypeOf<SkillOutcomeItem>();
    expectTypeOf<ApiSkillOutcomes.SkillOutcomeListResponse>().toEqualTypeOf<SkillOutcomeListResponse>();
    expectTypeOf<ApiSkillOutcomes.SkillOutcomeRunErrorItem>().toEqualTypeOf<SkillOutcomeRunErrorItem>();
    expectTypeOf<ApiSkillOutcomes.SkillOutcomeRunRequest>().toEqualTypeOf<SkillOutcomeRunRequest>();
    expectTypeOf<ApiSkillOutcomes.SkillOutcomeRunResponse>().toEqualTypeOf<SkillOutcomeRunResponse>();
    expectTypeOf<ApiSkillOutcomes.SkillOutcomePerformanceBucket>().toEqualTypeOf<
      SkillOutcomePerformanceBucket
    >();
    expectTypeOf<ApiSkillOutcomes.SkillOutcomePerformanceStats>().toEqualTypeOf<
      SkillOutcomePerformanceStats
    >();
    expectTypeOf<ApiSkillOutcomes.SkillOutcomeSampleItem>().toEqualTypeOf<SkillOutcomeSampleItem>();
    expectTypeOf<ApiSkillOutcomes.SkillOutcomeSampleListResponse>().toEqualTypeOf<
      SkillOutcomeSampleListResponse
    >();
    expectTypeOf<ApiSkillOutcomes.SkillOutcomeListParams>().toEqualTypeOf<SkillOutcomeListParams>();
    expectTypeOf<ApiSkillOutcomes.SkillOutcomeStatsParams>().toEqualTypeOf<SkillOutcomeStatsParams>();
    expectTypeOf<ApiSkillOutcomes.SkillOutcomeSampleListParams>().toEqualTypeOf<
      SkillOutcomeSampleListParams
    >();
    expectTypeOf<ApiSkillOutcomeRunErrorItem>().toEqualTypeOf<SkillOutcomeRunErrorItem>();
  });

  it('equates GET/POST 200 JSON to generated components and ops to their paths', () => {
    expectTypeOf<OpenApiList200>().toEqualTypeOf<OpenApiOutcomeListResponse>();
    expectTypeOf<OpenApiListOp>().toEqualTypeOf<OpenApiPathListGet>();
    expectTypeOf<OpenApiRun200>().toEqualTypeOf<OpenApiRunResponse>();
    expectTypeOf<OpenApiRunOp>().toEqualTypeOf<OpenApiPathRunPost>();
    expectTypeOf<OpenApiRunBody>().toEqualTypeOf<OpenApiRunRequest>();
    expectTypeOf<OpenApiSamples200>().toEqualTypeOf<OpenApiSampleListResponse>();
    expectTypeOf<OpenApiSamplesOp>().toEqualTypeOf<OpenApiPathSamplesGet>();
    expectTypeOf<OpenApiStats200>().toEqualTypeOf<OpenApiPerformanceStats>();
    expectTypeOf<OpenApiStatsOp>().toEqualTypeOf<OpenApiPathStatsGet>();
  });

  it('keeps GET requestBody never and unused methods never', () => {
    type ListGetNeverBody = OpenApiListOp extends { requestBody?: never } ? true : false;
    type ListPostNever = paths['/api/v1/skill-outcomes']['post'] extends never | undefined ? true : false;
    type ListPutNever = paths['/api/v1/skill-outcomes']['put'] extends never | undefined ? true : false;
    type ListDeleteNever = paths['/api/v1/skill-outcomes']['delete'] extends never | undefined
      ? true : false;
    type ListPatchNever = paths['/api/v1/skill-outcomes']['patch'] extends never | undefined ? true : false;
    type RunGetNever = paths['/api/v1/skill-outcomes/run']['get'] extends never | undefined ? true : false;
    type RunPutNever = paths['/api/v1/skill-outcomes/run']['put'] extends never | undefined ? true : false;
    type RunDeleteNever = paths['/api/v1/skill-outcomes/run']['delete'] extends never | undefined
      ? true : false;
    type RunPatchNever = paths['/api/v1/skill-outcomes/run']['patch'] extends never | undefined
      ? true : false;
    type RunQueryNever = OpenApiRunOp['parameters']['query'] extends never | undefined ? true : false;
    type RunHeaderNever = OpenApiRunOp['parameters']['header'] extends never | undefined ? true : false;
    type RunPathNever = OpenApiRunOp['parameters']['path'] extends never | undefined ? true : false;
    type RunCookieNever = OpenApiRunOp['parameters']['cookie'] extends never | undefined ? true : false;
    expectTypeOf<ListGetNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<ListPostNever>().toEqualTypeOf<true>();
    expectTypeOf<ListPutNever>().toEqualTypeOf<true>();
    expectTypeOf<ListDeleteNever>().toEqualTypeOf<true>();
    expectTypeOf<ListPatchNever>().toEqualTypeOf<true>();
    expectTypeOf<RunGetNever>().toEqualTypeOf<true>();
    expectTypeOf<RunPutNever>().toEqualTypeOf<true>();
    expectTypeOf<RunDeleteNever>().toEqualTypeOf<true>();
    expectTypeOf<RunPatchNever>().toEqualTypeOf<true>();
    expectTypeOf<RunQueryNever>().toEqualTypeOf<true>();
    expectTypeOf<RunHeaderNever>().toEqualTypeOf<true>();
    expectTypeOf<RunPathNever>().toEqualTypeOf<true>();
    expectTypeOf<RunCookieNever>().toEqualTypeOf<true>();
  });

  it('keeps UI keys camelCase and generated keys snake_case', () => {
    expectTypeOf<keyof SkillOutcomeItem>().not.toMatchTypeOf<
      'skill_opinion_sample_id' | 'analysis_history_id' | 'eval_status'
    >();
    expectTypeOf<keyof SkillOutcomeRunErrorItem>().not.toMatchTypeOf<'error_type'>();
    expectTypeOf<keyof SkillOutcomeRunResponse>().not.toMatchTypeOf<'histories_scanned'>();
    expectTypeOf<keyof OpenApiOutcomeItem>().not.toMatchTypeOf<'skillOpinionSampleId' | 'analysisHistoryId'>();
    expectTypeOf<'skillOpinionSampleId'>().toMatchTypeOf<keyof SkillOutcomeItem>();
    expectTypeOf<'analysisHistoryId'>().toMatchTypeOf<keyof SkillOutcomeItem>();
    expectTypeOf<'evalStatus'>().toMatchTypeOf<keyof SkillOutcomeItem>();
    expectTypeOf<'errorType'>().toMatchTypeOf<keyof SkillOutcomeRunErrorItem>();
    expectTypeOf<'historiesScanned'>().toMatchTypeOf<keyof SkillOutcomeRunResponse>();
    expectTypeOf<'hitRatePct'>().toMatchTypeOf<keyof SkillOutcomePerformanceBucket>();
    expectTypeOf<'minimumEvaluatedSampleSize'>().toMatchTypeOf<keyof SkillOutcomePerformanceStats>();
    expectTypeOf<'sampleSchemaVersion'>().toMatchTypeOf<keyof SkillOutcomeSampleItem>();
  });

  it('names nested run errors SkillOutcomeRunErrorItem without an Override', () => {
    expectTypeOf<SkillOutcomeRunErrorItem>().toEqualTypeOf<CamelizeKeys<OpenApiRunErrorItem>>();
    expectTypeOf<SkillOutcomeRunErrorItem>().toEqualTypeOf<
      NonNullable<SkillOutcomeRunResponse['errors']>[number]
    >();
    expectTypeOf<SkillOutcomeItem>().toEqualTypeOf<CamelizeKeys<OpenApiOutcomeItem>>();
    expectTypeOf<SkillOutcomeItem>().not.toEqualTypeOf<components['schemas']['SkillOpinionOutcomeItem']>();
    expectTypeOf<Omit<SkillOutcomeRunRequest, 'limit'>>().not.toMatchTypeOf<SkillOutcomeRunRequest>();
    expectTypeOf<string[]>().not.toMatchTypeOf<Exclude<SkillOutcomeRunRequest['horizons'], undefined>>();
  });

  it('keeps handwritten query bags off CamelizeKeys nullability', () => {
    expectTypeOf<'skillId'>().toMatchTypeOf<keyof SkillOutcomeListParams>();
    expectTypeOf<'skill_id'>().toMatchTypeOf<keyof OpenApiListQuery>();
    expectTypeOf<keyof OpenApiListQuery>().not.toMatchTypeOf<'skillId'>();
    expectTypeOf({ skillId: null }).toMatchTypeOf<CamelizeKeys<OpenApiListQuery>>();
    expectTypeOf({ skillId: null }).not.toMatchTypeOf<SkillOutcomeListParams>();
    expectTypeOf<CamelizeKeys<OpenApiListQuery>>().not.toMatchTypeOf<SkillOutcomeListParams>();
    expectTypeOf<CamelizeKeys<OpenApiStatsQuery>>().not.toMatchTypeOf<SkillOutcomeStatsParams>();
    expectTypeOf<CamelizeKeys<OpenApiSamplesQuery>>().not.toMatchTypeOf<SkillOutcomeSampleListParams>();
  });

  it('accepts playground camelCase fixtures and rejects snake_case', () => {
    const sampleOutcome = {
      id: 1,
      skillOpinionSampleId: 9,
      analysisHistoryId: 100,
      stockCode: 'AAPL',
      skillId: 'momentum',
      signal: 'buy',
      horizon: '5d',
      engineVersion: 'skill-opinion-outcome-v1',
      evalStatus: 'pending',
      outcome: null,
      directionCorrect: null,
      unableReason: null,
      analysisDate: '2026-08-01',
      startTradeDate: null,
      endTradeDate: null,
      startPrice: null,
      endClose: null,
      stockReturnPct: null,
      directionalReturnPct: null,
      createdAt: null,
      updatedAt: null,
    };
    const sampleRow = {
      id: 9,
      analysisHistoryId: 100,
      stockCode: 'AAPL',
      skillId: 'momentum',
      skillVersion: '1',
      signal: 'buy',
      confidence: 0.82,
      horizon: '5d',
      dataQualityLevel: null,
      opinionCreatedAt: null,
      sampleSchemaVersion: 'v1',
      createdAt: null,
    };
    const insufficientBucket = {
      skillId: 'momentum',
      horizon: '5d',
      engineVersion: 'skill-opinion-outcome-v1',
      total: 12,
      pending: 2,
      evaluated: 8,
      observational: 1,
      unable: 1,
      hit: 5,
      miss: 3,
      sampleSufficient: false,
      sampleStatus: 'insufficient',
      hitRatePct: null,
      missRatePct: null,
      avgDirectionalReturnPct: null,
      unableRatePct: null,
    };
    expectTypeOf(sampleOutcome).toMatchTypeOf<SkillOutcomeItem>();
    expectTypeOf(sampleRow).toMatchTypeOf<SkillOutcomeSampleItem>();
    expectTypeOf(insufficientBucket).toMatchTypeOf<SkillOutcomePerformanceBucket>();
    const snake = {
      id: 1,
      skill_opinion_sample_id: 9,
      analysis_history_id: 100,
      stock_code: 'AAPL',
      skill_id: 'momentum',
      signal: 'buy',
      horizon: '5d',
      engine_version: 'skill-opinion-outcome-v1',
      eval_status: 'pending',
    };
    expectTypeOf(snake).toMatchTypeOf<OpenApiOutcomeItem>();
    expectTypeOf(snake).not.toMatchTypeOf<SkillOutcomeItem>();
    expectTypeOf<NonNullable<Parameters<SkillOutcomesApi['listOutcomes']>[0]>>().toEqualTypeOf<
      SkillOutcomeListParams
    >();
    expectTypeOf<NonNullable<Parameters<SkillOutcomesApi['runOutcomes']>[0]>>().toEqualTypeOf<
      SkillOutcomeRunRequest
    >();
  });
});
