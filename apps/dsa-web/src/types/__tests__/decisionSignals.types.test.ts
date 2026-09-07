// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as DecisionSignals from '../decisionSignals';
import type {
  DecisionSignalCreateRequest,
  DecisionSignalFeedbackItem,
  DecisionSignalFeedbackRequest,
  DecisionSignalItem,
  DecisionSignalListResponse,
  DecisionSignalOutcomeRunRequest,
  DecisionSignalOutcomeStatsResponse,
  DecisionSignalReassessRequest,
  DecisionSignalReassessResponse,
  DecisionSignalStatusUpdateRequest,
} from '../decisionSignals';

type OpenApiItem = components['schemas']['DecisionSignalItem'];
type OpenApiCreate = components['schemas']['DecisionSignalCreateRequest'];
type OpenApiList = components['schemas']['DecisionSignalListResponse'];
type OpenApiMutation = components['schemas']['DecisionSignalMutationResponse'];
type OpenApiStatus = components['schemas']['DecisionSignalStatusUpdateRequest'];
type OpenApiReassess = components['schemas']['DecisionSignalReassessRequest'];
type OpenApiReassessResponse = components['schemas']['DecisionSignalReassessResponse'];
type OpenApiFeedback = components['schemas']['DecisionSignalFeedbackItem'];
type OpenApiFeedbackRequest = components['schemas']['DecisionSignalFeedbackRequest'];
type OpenApiMemory = components['schemas']['DecisionSignalMemoryFlagItem'];
type OpenApiOutcomeRun = components['schemas']['DecisionSignalOutcomeRunRequest'];
type OpenApiStats = components['schemas']['DecisionSignalOutcomeStatsResponse'];

type OpenApiListOp = operations['listDecisionSignals'];
type OpenApiCreateOp = operations['createDecisionSignal'];
type OpenApiLatestOp = operations['getLatestDecisionSignals'];
type OpenApiGetOp = operations['getDecisionSignal'];
type OpenApiStatusOp = operations['updateDecisionSignalStatus'];
type OpenApiReassessOp = operations['reassessDecisionSignalPreview'];
type OpenApiFeedbackGetOp = operations['getDecisionSignalFeedback'];
type OpenApiFeedbackPutOp = operations['putDecisionSignalFeedback'];
type OpenApiMemoryGetOp = operations['getDecisionSignalMemoryFlag'];
type OpenApiMemoryPatchOp = operations['updateDecisionSignalMemoryFlag'];
type OpenApiOutcomeListOp = operations['listDecisionSignalOutcomes'];
type OpenApiOutcomeBySignalOp = operations['listDecisionSignalOutcomesBySignal'];
type OpenApiOutcomeRunOp = operations['runDecisionSignalOutcomes'];
type OpenApiStatsOp = operations['getDecisionSignalOutcomeStats'];

type OpenApiListPathGet = paths['/api/v1/decision-signals']['get'];
type OpenApiCreatePathPost = paths['/api/v1/decision-signals']['post'];
type OpenApiLatestPathGet = paths['/api/v1/decision-signals/latest/{stock_code}']['get'];
type OpenApiGetPathGet = paths['/api/v1/decision-signals/{signal_id}']['get'];
type OpenApiStatusPathPatch = paths['/api/v1/decision-signals/{signal_id}/status']['patch'];
type OpenApiReassessPathPost = paths['/api/v1/decision-signals/reassess']['post'];
type OpenApiFeedbackPathGet = paths['/api/v1/decision-signals/{signal_id}/feedback']['get'];
type OpenApiFeedbackPathPut = paths['/api/v1/decision-signals/{signal_id}/feedback']['put'];
type OpenApiMemoryPathGet = paths['/api/v1/decision-signals/{signal_id}/memory-flag']['get'];
type OpenApiMemoryPathPatch = paths['/api/v1/decision-signals/{signal_id}/memory-flag']['patch'];
type OpenApiOutcomeListPathGet = paths['/api/v1/decision-signals/outcomes']['get'];
type OpenApiOutcomeBySignalPathGet = paths['/api/v1/decision-signals/{signal_id}/outcomes']['get'];
type OpenApiOutcomeRunPathPost = paths['/api/v1/decision-signals/outcomes/run']['post'];
type OpenApiStatsPathGet = paths['/api/v1/decision-signals/outcomes/stats']['get'];

type OpenApiListGet200 = OpenApiListOp['responses']['200']['content']['application/json'];
type OpenApiCreatePost200 = OpenApiCreateOp['responses']['200']['content']['application/json'];
type OpenApiCreateBody = OpenApiCreateOp['requestBody']['content']['application/json'];
type OpenApiLatestGet200 = OpenApiLatestOp['responses']['200']['content']['application/json'];
type OpenApiGetGet200 = OpenApiGetOp['responses']['200']['content']['application/json'];
type OpenApiStatusPatch200 = OpenApiStatusOp['responses']['200']['content']['application/json'];
type OpenApiStatusBody = OpenApiStatusOp['requestBody']['content']['application/json'];
type OpenApiReassessPost200 = OpenApiReassessOp['responses']['200']['content']['application/json'];
type OpenApiReassessBody = OpenApiReassessOp['requestBody']['content']['application/json'];
type OpenApiFeedbackGet200 = OpenApiFeedbackGetOp['responses']['200']['content']['application/json'];
type OpenApiFeedbackPut200 = OpenApiFeedbackPutOp['responses']['200']['content']['application/json'];
type OpenApiFeedbackBody = OpenApiFeedbackPutOp['requestBody']['content']['application/json'];
type OpenApiMemoryGet200 = OpenApiMemoryGetOp['responses']['200']['content']['application/json'];
type OpenApiMemoryPatch200 = OpenApiMemoryPatchOp['responses']['200']['content']['application/json'];
type OpenApiMemoryBody = OpenApiMemoryPatchOp['requestBody']['content']['application/json'];
type OpenApiOutcomeListGet200 = OpenApiOutcomeListOp['responses']['200']['content']['application/json'];
type OpenApiOutcomeBySignalGet200 = OpenApiOutcomeBySignalOp['responses']['200']['content']['application/json'];
type OpenApiOutcomeRunPost200 = OpenApiOutcomeRunOp['responses']['200']['content']['application/json'];
type OpenApiOutcomeRunBody = OpenApiOutcomeRunOp['requestBody']['content']['application/json'];
type OpenApiStatsGet200 = OpenApiStatsOp['responses']['200']['content']['application/json'];

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

type _TwentyTwoComponents = _Assert<
  (
    | 'DecisionSignalItem'
    | 'DecisionSignalCreateRequest'
    | 'DecisionSignalListResponse'
    | 'DecisionSignalPresentation'
    | 'DecisionSignalMutationResponse'
    | 'DecisionSignalStatusUpdateRequest'
    | 'DecisionSignalWarning'
    | 'DecisionSignalReassessRequest'
    | 'DecisionSignalReassessResponse'
    | 'DecisionSignalPreview'
    | 'DecisionSignalFeedbackItem'
    | 'DecisionSignalFeedbackRequest'
    | 'DecisionSignalMemoryFlagItem'
    | 'DecisionSignalMemoryFlagRequest'
    | 'DecisionSignalOutcomeItem'
    | 'DecisionSignalOutcomeRunRequest'
    | 'DecisionSignalOutcomeRunResponse'
    | 'DecisionSignalOutcomeListResponse'
    | 'DecisionSignalOutcomeStatsResponse'
    | 'DecisionSignalOutcomeStatsBucket'
    | 'DecisionSignalProfileCalibration'
    | 'DecisionSignalProfileCalibrationBucket'
  ) extends keyof components['schemas'] ? true : false
>;

type _List200IsList = _Assert<OpenApiListGet200 extends OpenApiList ? true : false>;
type _ListIsList200 = _Assert<OpenApiList extends OpenApiListGet200 ? true : false>;
type _ListOpIsPath = _Assert<OpenApiListOp extends OpenApiListPathGet ? true : false>;
type _PathIsListOp = _Assert<OpenApiListPathGet extends OpenApiListOp ? true : false>;
type _ListGetNeverRequestBody = _Assert<OpenApiListOp extends { requestBody?: never } ? true : false>;
type _ListHas200 = _Assert<200 extends keyof OpenApiListOp['responses'] ? true : false>;
type _ListLacks201 = _Assert<201 extends keyof OpenApiListOp['responses'] ? false : true>;
type _Create200IsMutation = _Assert<OpenApiCreatePost200 extends OpenApiMutation ? true : false>;
type _MutationIsCreate200 = _Assert<OpenApiMutation extends OpenApiCreatePost200 ? true : false>;
type _CreateOpIsPath = _Assert<OpenApiCreateOp extends OpenApiCreatePathPost ? true : false>;
type _PathIsCreateOp = _Assert<OpenApiCreatePathPost extends OpenApiCreateOp ? true : false>;
type _CreateBodyIsRequest = _Assert<OpenApiCreateBody extends OpenApiCreate ? true : false>;
type _RequestIsCreateBody = _Assert<OpenApiCreate extends OpenApiCreateBody ? true : false>;
type _CreateHas200 = _Assert<200 extends keyof OpenApiCreateOp['responses'] ? true : false>;
type _CreateLacks201 = _Assert<201 extends keyof OpenApiCreateOp['responses'] ? false : true>;
type _Latest200IsList = _Assert<OpenApiLatestGet200 extends OpenApiList ? true : false>;
type _Get200IsItem = _Assert<OpenApiGetGet200 extends OpenApiItem ? true : false>;
type _ItemIsGet200 = _Assert<OpenApiItem extends OpenApiGetGet200 ? true : false>;
type _GetOpIsPath = _Assert<OpenApiGetOp extends OpenApiGetPathGet ? true : false>;
type _PathIsGetOp = _Assert<OpenApiGetPathGet extends OpenApiGetOp ? true : false>;
type _GetNeverRequestBody = _Assert<OpenApiGetOp extends { requestBody?: never } ? true : false>;
type _GetHas200 = _Assert<200 extends keyof OpenApiGetOp['responses'] ? true : false>;
type _GetLacks201 = _Assert<201 extends keyof OpenApiGetOp['responses'] ? false : true>;
type _Status200IsItem = _Assert<OpenApiStatusPatch200 extends OpenApiItem ? true : false>;
type _StatusBodyIsRequest = _Assert<OpenApiStatusBody extends OpenApiStatus ? true : false>;
type _Reassess200IsReassess = _Assert<OpenApiReassessPost200 extends OpenApiReassessResponse ? true : false>;
type _ReassessBodyIsRequest = _Assert<OpenApiReassessBody extends OpenApiReassess ? true : false>;
type _FeedbackGet200IsFeedback = _Assert<OpenApiFeedbackGet200 extends OpenApiFeedback ? true : false>;
type _FeedbackPut200IsFeedback = _Assert<OpenApiFeedbackPut200 extends OpenApiFeedback ? true : false>;
type _FeedbackBodyIsRequest = _Assert<OpenApiFeedbackBody extends OpenApiFeedbackRequest ? true : false>;
type _MemoryGet200IsMemory = _Assert<OpenApiMemoryGet200 extends OpenApiMemory ? true : false>;
type _MemoryPatch200IsMemory = _Assert<OpenApiMemoryPatch200 extends OpenApiMemory ? true : false>;
type _MemoryBodyIsRequest = _Assert<OpenApiMemoryBody extends components['schemas']['DecisionSignalMemoryFlagRequest'] ? true : false>;
type _OutcomeList200IsOutcomeList = _Assert<
  OpenApiOutcomeListGet200 extends components['schemas']['DecisionSignalOutcomeListResponse'] ? true : false
>;
type _OutcomeBySignal200IsOutcomeList = _Assert<
  OpenApiOutcomeBySignalGet200 extends components['schemas']['DecisionSignalOutcomeListResponse'] ? true : false
>;
type _OutcomeRun200IsOutcomeRun = _Assert<
  OpenApiOutcomeRunPost200 extends components['schemas']['DecisionSignalOutcomeRunResponse'] ? true : false
>;
type _OutcomeRunBodyIsRequest = _Assert<OpenApiOutcomeRunBody extends OpenApiOutcomeRun ? true : false>;
type _Stats200IsStats = _Assert<OpenApiStatsGet200 extends OpenApiStats ? true : false>;
type _StatsGetNeverRequestBody = _Assert<OpenApiStatsOp extends { requestBody?: never } ? true : false>;
type _StatsHas200 = _Assert<200 extends keyof OpenApiStatsOp['responses'] ? true : false>;
type _StatsLacks201 = _Assert<201 extends keyof OpenApiStatsOp['responses'] ? false : true>;

type _PublicItemNotPath200 = _Assert<DecisionSignalItem extends OpenApiGetGet200 ? false : true>;
type _Path200NotPublicItem = _Assert<OpenApiGetGet200 extends DecisionSignalItem ? false : true>;
type _PublicListNotPath200 = _Assert<DecisionSignalListResponse extends OpenApiListGet200 ? false : true>;
type _Path200NotPublicList = _Assert<OpenApiListGet200 extends DecisionSignalListResponse ? false : true>;
type _PublicReassessNotPath200 = _Assert<DecisionSignalReassessResponse extends OpenApiReassessPost200 ? false : true>;
type _Path200NotPublicReassess = _Assert<OpenApiReassessPost200 extends DecisionSignalReassessResponse ? false : true>;
type _PublicStatsNotPath200 = _Assert<DecisionSignalOutcomeStatsResponse extends OpenApiStatsGet200 ? false : true>;
type _Path200NotPublicStats = _Assert<OpenApiStatsGet200 extends DecisionSignalOutcomeStatsResponse ? false : true>;

type _UiHasStockCode = _Assert<'stockCode' extends keyof DecisionSignalItem ? true : false>;
type _UiHasPageSize = _Assert<'pageSize' extends keyof DecisionSignalListResponse ? true : false>;
type _UiHasSourceType = _Assert<'sourceType' extends keyof DecisionSignalItem ? true : false>;
type _UiHasPlanQuality = _Assert<'planQuality' extends keyof DecisionSignalItem ? true : false>;
type _UiLacksStockCodeSnake = _Assert<'stock_code' extends keyof DecisionSignalItem ? false : true>;
type _UiLacksPageSizeSnake = _Assert<'page_size' extends keyof DecisionSignalListResponse ? false : true>;
type _UiLacksSourceTypeSnake = _Assert<'source_type' extends keyof DecisionSignalItem ? false : true>;
type _UiLacksPlanQualitySnake = _Assert<'plan_quality' extends keyof DecisionSignalItem ? false : true>;
type _GeneratedHasStockCodeSnake = _Assert<'stock_code' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasPageSizeSnake = _Assert<'page_size' extends keyof OpenApiList ? true : false>;
type _GeneratedHasSourceTypeSnake = _Assert<'source_type' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasPlanQualitySnake = _Assert<'plan_quality' extends keyof OpenApiItem ? true : false>;
type _GeneratedLacksStockCodeCamel = _Assert<'stockCode' extends keyof OpenApiItem ? false : true>;
type _GeneratedLacksPageSizeCamel = _Assert<'pageSize' extends keyof OpenApiList ? false : true>;
type _GeneratedLacksSourceTypeCamel = _Assert<'sourceType' extends keyof OpenApiItem ? false : true>;
type _GeneratedLacksPlanQualityCamel = _Assert<'planQuality' extends keyof OpenApiItem ? false : true>;

type _UiPresentationOptional = _Assert<IsOptional<DecisionSignalItem, 'presentation'>>;
type _NaivePresentationRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiItem>, 'presentation'> extends false ? true : false
>;
type _UiPersistOptional = _Assert<IsOptional<DecisionSignalReassessRequest, 'persist'>>;
type _NaivePersistRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiReassess>, 'persist'> extends false ? true : false
>;
type _UiFeedbackSourceOptional = _Assert<IsOptional<DecisionSignalFeedbackRequest, 'source'>>;
type _NaiveFeedbackSourceRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiFeedbackRequest>, 'source'> extends false ? true : false
>;
type _UiForceOptional = _Assert<IsOptional<DecisionSignalOutcomeRunRequest, 'force'>>;
type _UiLimitOptional = _Assert<IsOptional<DecisionSignalOutcomeRunRequest, 'limit'>>;
type _NaiveForceRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiOutcomeRun>, 'force'> extends false ? true : false
>;
type _NaiveLimitRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiOutcomeRun>, 'limit'> extends false ? true : false
>;
type _UiItemsRequired = _Assert<IsOptional<DecisionSignalListResponse, 'items'> extends false ? true : false>;
type _NaiveItemsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiList>, 'items'>>;
type _UiWarningsRequired = _Assert<
  IsOptional<DecisionSignalReassessResponse, 'warnings'> extends false ? true : false
>;
type _NaiveWarningsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiReassessResponse>, 'warnings'>>;
type _UiBreakdownsRequired = _Assert<
  IsOptional<DecisionSignalOutcomeStatsResponse, 'breakdowns'> extends false ? true : false
>;
type _UiUnableReasonsRequired = _Assert<
  IsOptional<DecisionSignalOutcomeStatsResponse, 'unableReasons'> extends false ? true : false
>;
type _NaiveBreakdownsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiStats>, 'breakdowns'>>;
type _NaiveUnableReasonsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiStats>, 'unableReasons'>>;
type _UiLacksActorId = _Assert<'actorId' extends keyof DecisionSignalFeedbackItem ? false : true>;
type _NaiveHasActorId = _Assert<'actorId' extends keyof CamelizeKeys<OpenApiFeedback> ? true : false>;

type _CompileTimePins = [
  _TwentyTwoComponents,
  _List200IsList,
  _ListIsList200,
  _ListOpIsPath,
  _PathIsListOp,
  _ListGetNeverRequestBody,
  _ListHas200,
  _ListLacks201,
  _Create200IsMutation,
  _MutationIsCreate200,
  _CreateOpIsPath,
  _PathIsCreateOp,
  _CreateBodyIsRequest,
  _RequestIsCreateBody,
  _CreateHas200,
  _CreateLacks201,
  _Latest200IsList,
  _Get200IsItem,
  _ItemIsGet200,
  _GetOpIsPath,
  _PathIsGetOp,
  _GetNeverRequestBody,
  _GetHas200,
  _GetLacks201,
  _Status200IsItem,
  _StatusBodyIsRequest,
  _Reassess200IsReassess,
  _ReassessBodyIsRequest,
  _FeedbackGet200IsFeedback,
  _FeedbackPut200IsFeedback,
  _FeedbackBodyIsRequest,
  _MemoryGet200IsMemory,
  _MemoryPatch200IsMemory,
  _MemoryBodyIsRequest,
  _OutcomeList200IsOutcomeList,
  _OutcomeBySignal200IsOutcomeList,
  _OutcomeRun200IsOutcomeRun,
  _OutcomeRunBodyIsRequest,
  _Stats200IsStats,
  _StatsGetNeverRequestBody,
  _StatsHas200,
  _StatsLacks201,
  _PublicItemNotPath200,
  _Path200NotPublicItem,
  _PublicListNotPath200,
  _Path200NotPublicList,
  _PublicReassessNotPath200,
  _Path200NotPublicReassess,
  _PublicStatsNotPath200,
  _Path200NotPublicStats,
  _UiHasStockCode,
  _UiHasPageSize,
  _UiHasSourceType,
  _UiHasPlanQuality,
  _UiLacksStockCodeSnake,
  _UiLacksPageSizeSnake,
  _UiLacksSourceTypeSnake,
  _UiLacksPlanQualitySnake,
  _GeneratedHasStockCodeSnake,
  _GeneratedHasPageSizeSnake,
  _GeneratedHasSourceTypeSnake,
  _GeneratedHasPlanQualitySnake,
  _GeneratedLacksStockCodeCamel,
  _GeneratedLacksPageSizeCamel,
  _GeneratedLacksSourceTypeCamel,
  _GeneratedLacksPlanQualityCamel,
  _UiPresentationOptional,
  _NaivePresentationRequired,
  _UiPersistOptional,
  _NaivePersistRequired,
  _UiFeedbackSourceOptional,
  _NaiveFeedbackSourceRequired,
  _UiForceOptional,
  _UiLimitOptional,
  _NaiveForceRequired,
  _NaiveLimitRequired,
  _UiItemsRequired,
  _NaiveItemsOptional,
  _UiWarningsRequired,
  _NaiveWarningsOptional,
  _UiBreakdownsRequired,
  _UiUnableReasonsRequired,
  _NaiveBreakdownsOptional,
  _NaiveUnableReasonsOptional,
  _UiLacksActorId,
  _NaiveHasActorId,
];

const itemBase = {
  id: 11,
  stockCode: '600519',
  market: 'cn' as const,
  sourceType: 'analysis' as const,
  triggerSource: 'api',
  action: 'watch' as const,
  planQuality: 'complete' as const,
  status: 'active' as const,
};

const createBase = {
  stockCode: '600519',
  market: 'cn' as const,
  sourceType: 'manual' as const,
  triggerSource: 'web',
  action: 'hold' as const,
};

const reassessBase = {
  sourceReportId: 3001,
  decisionProfile: 'balanced' as const,
};

const feedbackRequestBase = {
  feedbackValue: 'useful' as const,
};

const outcomeRunBase = {
  signalId: 11,
};

const listMissingItems = {
  total: 0,
  page: 1,
  pageSize: 20,
};

const statsMissingBags = {
  engineVersion: 'v1',
  statuses: ['active'] as Array<'active'>,
  total: 0,
  completed: 0,
  unable: 0,
  hit: 0,
  miss: 0,
  neutral: 0,
  sampleSufficient: false,
  minimumCompletedSampleSize: 30,
};

const reassessResponseMissingWarnings = {
  created: false,
};

const feedbackBase = {
  signalId: 11,
  feedbackValue: 'useful' as const,
};

const uiItem: DecisionSignalItem = itemBase;
void uiItem;
const uiCreate: DecisionSignalCreateRequest = createBase;
void uiCreate;
const uiReassess: DecisionSignalReassessRequest = reassessBase;
void uiReassess;
const uiFeedbackRequest: DecisionSignalFeedbackRequest = feedbackRequestBase;
void uiFeedbackRequest;
const uiOutcomeRun: DecisionSignalOutcomeRunRequest = outcomeRunBase;
void uiOutcomeRun;
const uiFeedback: DecisionSignalFeedbackItem = feedbackBase;
void uiFeedback;

// @ts-expect-error naive item requires generated presentation
const naiveItem: CamelizeKeys<OpenApiItem> = itemBase;
void naiveItem;

const naiveCreate: CamelizeKeys<OpenApiCreate> = createBase;
void naiveCreate;

// @ts-expect-error naive reassess requires generated-default persist
const naiveReassess: CamelizeKeys<OpenApiReassess> = reassessBase;
void naiveReassess;

// @ts-expect-error naive feedback request requires generated-default source
const naiveFeedbackRequest: CamelizeKeys<OpenApiFeedbackRequest> = feedbackRequestBase;
void naiveFeedbackRequest;

// @ts-expect-error naive outcome run requires generated-default force and limit
const naiveOutcomeRun: CamelizeKeys<OpenApiOutcomeRun> = outcomeRunBase;
void naiveOutcomeRun;

const naiveListMissing: CamelizeKeys<OpenApiList> = listMissingItems;
void naiveListMissing;
// @ts-expect-error public list items is required
const publicListMissing: DecisionSignalListResponse = listMissingItems;
void publicListMissing;

const naiveStatsMissing: CamelizeKeys<OpenApiStats> = statsMissingBags;
void naiveStatsMissing;
// @ts-expect-error public stats bags are required
const publicStatsMissing: DecisionSignalOutcomeStatsResponse = statsMissingBags;
void publicStatsMissing;

const naiveReassessMissing: CamelizeKeys<OpenApiReassessResponse> = reassessResponseMissingWarnings;
void naiveReassessMissing;
// @ts-expect-error public reassess warnings is required
const publicReassessMissing: DecisionSignalReassessResponse = reassessResponseMissingWarnings;
void publicReassessMissing;

// @ts-expect-error futureSignalFlag is not a public item field
const extraItem: DecisionSignalItem = { ...itemBase, futureSignalFlag: true };

// @ts-expect-error futureCreateFlag is not a public create field
const extraCreate: DecisionSignalCreateRequest = { ...createBase, futureCreateFlag: true };

const publicCreateMeta: DecisionSignalCreateRequest = {
  ...createBase,
  metadata: { taskId: 't1', futureMeta: true },
};
void publicCreateMeta;
const publicStatus: DecisionSignalStatusUpdateRequest = {
  status: 'closed',
  metadata: { futureMeta: true },
};
void publicStatus;

const naiveBadStatus: CamelizeKeys<OpenApiItem> = {
  ...itemBase,
  presentation: { action: 'hold', label: 'Hold' },
  status: 'not-a-status',
};
void naiveBadStatus;
// @ts-expect-error not-a-status is not a public DecisionSignalStatus
const publicBadStatus: DecisionSignalItem = { ...itemBase, status: 'not-a-status' };

// @ts-expect-error stock_code is not a public camelCase field
const publicSnake: DecisionSignalItem = { ...itemBase, stock_code: '600519' };

const naiveFeedbackActor: CamelizeKeys<OpenApiFeedback> = { ...feedbackBase, actorId: 'user-1' };
void naiveFeedbackActor;
// @ts-expect-error actorId is not a public feedback field
const publicFeedbackActor: DecisionSignalFeedbackItem = { ...feedbackBase, actorId: 'user-1' };

void extraItem;
void extraCreate;
void publicBadStatus;
void publicSnake;
void publicFeedbackActor;

describe('decisionSignals OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    expect({ ...DecisionSignals }).toEqual({});
    expect(Object.keys(DecisionSignals)).toEqual([]);
    expect(Object.getOwnPropertyNames(DecisionSignals)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates path JSON to named generated components, keeps GET requestBody never, and uses 200 not 201', () => {
    expectTypeOf<OpenApiListGet200>().toEqualTypeOf<OpenApiList>();
    expectTypeOf<OpenApiCreatePost200>().toEqualTypeOf<OpenApiMutation>();
    expectTypeOf<OpenApiCreateBody>().toEqualTypeOf<OpenApiCreate>();
    expectTypeOf<OpenApiLatestGet200>().toEqualTypeOf<OpenApiList>();
    expectTypeOf<OpenApiGetGet200>().toEqualTypeOf<OpenApiItem>();
    expectTypeOf<OpenApiStatusPatch200>().toEqualTypeOf<OpenApiItem>();
    expectTypeOf<OpenApiStatusBody>().toEqualTypeOf<OpenApiStatus>();
    expectTypeOf<OpenApiReassessPost200>().toEqualTypeOf<OpenApiReassessResponse>();
    expectTypeOf<OpenApiReassessBody>().toEqualTypeOf<OpenApiReassess>();
    expectTypeOf<OpenApiFeedbackGet200>().toEqualTypeOf<OpenApiFeedback>();
    expectTypeOf<OpenApiFeedbackPut200>().toEqualTypeOf<OpenApiFeedback>();
    expectTypeOf<OpenApiFeedbackBody>().toEqualTypeOf<OpenApiFeedbackRequest>();
    expectTypeOf<OpenApiMemoryGet200>().toEqualTypeOf<OpenApiMemory>();
    expectTypeOf<OpenApiMemoryPatch200>().toEqualTypeOf<OpenApiMemory>();
    expectTypeOf<OpenApiOutcomeListGet200>().toEqualTypeOf<
      components['schemas']['DecisionSignalOutcomeListResponse']
    >();
    expectTypeOf<OpenApiOutcomeBySignalGet200>().toEqualTypeOf<
      components['schemas']['DecisionSignalOutcomeListResponse']
    >();
    expectTypeOf<OpenApiOutcomeRunPost200>().toEqualTypeOf<
      components['schemas']['DecisionSignalOutcomeRunResponse']
    >();
    expectTypeOf<OpenApiOutcomeRunBody>().toEqualTypeOf<OpenApiOutcomeRun>();
    expectTypeOf<OpenApiStatsGet200>().toEqualTypeOf<OpenApiStats>();
    expectTypeOf<OpenApiListOp>().toEqualTypeOf<OpenApiListPathGet>();
    expectTypeOf<OpenApiCreateOp>().toEqualTypeOf<OpenApiCreatePathPost>();
    expectTypeOf<OpenApiLatestOp>().toEqualTypeOf<OpenApiLatestPathGet>();
    expectTypeOf<OpenApiGetOp>().toEqualTypeOf<OpenApiGetPathGet>();
    expectTypeOf<OpenApiStatusOp>().toEqualTypeOf<OpenApiStatusPathPatch>();
    expectTypeOf<OpenApiReassessOp>().toEqualTypeOf<OpenApiReassessPathPost>();
    expectTypeOf<OpenApiFeedbackGetOp>().toEqualTypeOf<OpenApiFeedbackPathGet>();
    expectTypeOf<OpenApiFeedbackPutOp>().toEqualTypeOf<OpenApiFeedbackPathPut>();
    expectTypeOf<OpenApiMemoryGetOp>().toEqualTypeOf<OpenApiMemoryPathGet>();
    expectTypeOf<OpenApiMemoryPatchOp>().toEqualTypeOf<OpenApiMemoryPathPatch>();
    expectTypeOf<OpenApiOutcomeListOp>().toEqualTypeOf<OpenApiOutcomeListPathGet>();
    expectTypeOf<OpenApiOutcomeBySignalOp>().toEqualTypeOf<OpenApiOutcomeBySignalPathGet>();
    expectTypeOf<OpenApiOutcomeRunOp>().toEqualTypeOf<OpenApiOutcomeRunPathPost>();
    expectTypeOf<OpenApiStatsOp>().toEqualTypeOf<OpenApiStatsPathGet>();
    type ListNeverBody = OpenApiListOp extends { requestBody?: never } ? true : false;
    type LatestNeverBody = OpenApiLatestOp extends { requestBody?: never } ? true : false;
    type GetNeverBody = OpenApiGetOp extends { requestBody?: never } ? true : false;
    type FeedbackGetNeverBody = OpenApiFeedbackGetOp extends { requestBody?: never } ? true : false;
    type MemoryGetNeverBody = OpenApiMemoryGetOp extends { requestBody?: never } ? true : false;
    type OutcomeListNeverBody = OpenApiOutcomeListOp extends { requestBody?: never } ? true : false;
    type OutcomeBySignalNeverBody = OpenApiOutcomeBySignalOp extends { requestBody?: never } ? true : false;
    type StatsNeverBody = OpenApiStatsOp extends { requestBody?: never } ? true : false;
    type ListHas201 = 201 extends keyof OpenApiListOp['responses'] ? true : false;
    type CreateHas201 = 201 extends keyof OpenApiCreateOp['responses'] ? true : false;
    type GetHas201 = 201 extends keyof OpenApiGetOp['responses'] ? true : false;
    type ReassessHas201 = 201 extends keyof OpenApiReassessOp['responses'] ? true : false;
    type StatsHas201 = 201 extends keyof OpenApiStatsOp['responses'] ? true : false;
    expectTypeOf<ListNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<LatestNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<GetNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<FeedbackGetNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<MemoryGetNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<OutcomeListNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<OutcomeBySignalNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<StatsNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<ListHas201>().toEqualTypeOf<false>();
    expectTypeOf<CreateHas201>().toEqualTypeOf<false>();
    expectTypeOf<GetHas201>().toEqualTypeOf<false>();
    expectTypeOf<ReassessHas201>().toEqualTypeOf<false>();
    expectTypeOf<StatsHas201>().toEqualTypeOf<false>();
  });

  it('does not claim public Override types equal path 200 JSON', () => {
    type PublicItemExtendsPath = DecisionSignalItem extends OpenApiGetGet200 ? true : false;
    type PathExtendsPublicItem = OpenApiGetGet200 extends DecisionSignalItem ? true : false;
    type PublicListExtendsPath = DecisionSignalListResponse extends OpenApiListGet200 ? true : false;
    type PathExtendsPublicList = OpenApiListGet200 extends DecisionSignalListResponse ? true : false;
    type PublicReassessExtendsPath = DecisionSignalReassessResponse extends OpenApiReassessPost200 ? true : false;
    type PathExtendsPublicReassess = OpenApiReassessPost200 extends DecisionSignalReassessResponse ? true : false;
    type PublicStatsExtendsPath = DecisionSignalOutcomeStatsResponse extends OpenApiStatsGet200 ? true : false;
    type PathExtendsPublicStats = OpenApiStatsGet200 extends DecisionSignalOutcomeStatsResponse ? true : false;
    expectTypeOf<PublicItemExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicItem>().toEqualTypeOf<false>();
    expectTypeOf<PublicListExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicList>().toEqualTypeOf<false>();
    expectTypeOf<PublicReassessExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicReassess>().toEqualTypeOf<false>();
    expectTypeOf<PublicStatsExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicStats>().toEqualTypeOf<false>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof DecisionSignalItem>().not.toMatchTypeOf<'stock_code' | 'source_type' | 'plan_quality'>();
    expectTypeOf<keyof DecisionSignalListResponse>().not.toMatchTypeOf<'page_size'>();
    expectTypeOf<keyof OpenApiItem>().not.toMatchTypeOf<'stockCode' | 'sourceType' | 'planQuality'>();
    expectTypeOf<keyof OpenApiList>().not.toMatchTypeOf<'pageSize'>();
  });

  it('keeps UI presentation optional so rolling-upgrade fixtures assign', () => {
    type UiPresentationOptional = IsOptional<DecisionSignalItem, 'presentation'>;
    type NaivePresentationOptional = IsOptional<CamelizeKeys<OpenApiItem>, 'presentation'>;
    expectTypeOf<UiPresentationOptional>().toEqualTypeOf<true>();
    expectTypeOf<NaivePresentationOptional>().toEqualTypeOf<false>();
    expectTypeOf(itemBase).toMatchTypeOf<DecisionSignalItem>();
    expectTypeOf(itemBase).not.toMatchTypeOf<CamelizeKeys<OpenApiItem>>();
  });

  it('keeps UI reassess persist, feedback source, and outcome force/limit optional', () => {
    type UiPersistOptional = IsOptional<DecisionSignalReassessRequest, 'persist'>;
    type NaivePersistOptional = IsOptional<CamelizeKeys<OpenApiReassess>, 'persist'>;
    type UiSourceOptional = IsOptional<DecisionSignalFeedbackRequest, 'source'>;
    type NaiveSourceOptional = IsOptional<CamelizeKeys<OpenApiFeedbackRequest>, 'source'>;
    type UiForceOptional = IsOptional<DecisionSignalOutcomeRunRequest, 'force'>;
    type UiLimitOptional = IsOptional<DecisionSignalOutcomeRunRequest, 'limit'>;
    type NaiveForceOptional = IsOptional<CamelizeKeys<OpenApiOutcomeRun>, 'force'>;
    type NaiveLimitOptional = IsOptional<CamelizeKeys<OpenApiOutcomeRun>, 'limit'>;
    expectTypeOf<UiPersistOptional>().toEqualTypeOf<true>();
    expectTypeOf<NaivePersistOptional>().toEqualTypeOf<false>();
    expectTypeOf<UiSourceOptional>().toEqualTypeOf<true>();
    expectTypeOf<NaiveSourceOptional>().toEqualTypeOf<false>();
    expectTypeOf<UiForceOptional>().toEqualTypeOf<true>();
    expectTypeOf<UiLimitOptional>().toEqualTypeOf<true>();
    expectTypeOf<NaiveForceOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveLimitOptional>().toEqualTypeOf<false>();
    expectTypeOf(reassessBase).toMatchTypeOf<DecisionSignalReassessRequest>();
    expectTypeOf(reassessBase).not.toMatchTypeOf<CamelizeKeys<OpenApiReassess>>();
    expectTypeOf(feedbackRequestBase).toMatchTypeOf<DecisionSignalFeedbackRequest>();
    expectTypeOf(feedbackRequestBase).not.toMatchTypeOf<CamelizeKeys<OpenApiFeedbackRequest>>();
    expectTypeOf(outcomeRunBase).toMatchTypeOf<DecisionSignalOutcomeRunRequest>();
    expectTypeOf(outcomeRunBase).not.toMatchTypeOf<CamelizeKeys<OpenApiOutcomeRun>>();
  });

  it('keeps UI list items, reassess warnings, and stats bags required', () => {
    expectTypeOf(listMissingItems).not.toMatchTypeOf<DecisionSignalListResponse>();
    expectTypeOf(listMissingItems).toMatchTypeOf<CamelizeKeys<OpenApiList>>();
    expectTypeOf(reassessResponseMissingWarnings).not.toMatchTypeOf<DecisionSignalReassessResponse>();
    expectTypeOf(reassessResponseMissingWarnings).toMatchTypeOf<CamelizeKeys<OpenApiReassessResponse>>();
    expectTypeOf(statsMissingBags).not.toMatchTypeOf<DecisionSignalOutcomeStatsResponse>();
    expectTypeOf(statsMissingBags).toMatchTypeOf<CamelizeKeys<OpenApiStats>>();
    type UiItemsOptional = IsOptional<DecisionSignalListResponse, 'items'>;
    type NaiveItemsOptional = IsOptional<CamelizeKeys<OpenApiList>, 'items'>;
    type UiWarningsOptional = IsOptional<DecisionSignalReassessResponse, 'warnings'>;
    type NaiveWarningsOptional = IsOptional<CamelizeKeys<OpenApiReassessResponse>, 'warnings'>;
    type UiBreakdownsOptional = IsOptional<DecisionSignalOutcomeStatsResponse, 'breakdowns'>;
    type UiUnableReasonsOptional = IsOptional<DecisionSignalOutcomeStatsResponse, 'unableReasons'>;
    expectTypeOf<UiItemsOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveItemsOptional>().toEqualTypeOf<true>();
    expectTypeOf<UiWarningsOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveWarningsOptional>().toEqualTypeOf<true>();
    expectTypeOf<UiBreakdownsOptional>().toEqualTypeOf<false>();
    expectTypeOf<UiUnableReasonsOptional>().toEqualTypeOf<false>();
  });

  it("rejects 'not-a-status' on UI status while naive CamelizeKeys accepts string", () => {
    expectTypeOf({ ...itemBase, status: 'not-a-status' }).not.toMatchTypeOf<DecisionSignalItem>();
    expectTypeOf({
      ...itemBase,
      presentation: { action: 'hold' as const, label: 'Hold' },
      status: 'not-a-status',
    }).toMatchTypeOf<CamelizeKeys<OpenApiItem>>();
    expectTypeOf<'not-a-status'>().not.toMatchTypeOf<DecisionSignalItem['status']>();
    expectTypeOf<'not-a-status'>().toMatchTypeOf<CamelizeKeys<OpenApiItem>['status']>();
  });

  it('omits generated-only feedback actorId from the public surface', () => {
    type UiHasActorId = 'actorId' extends keyof DecisionSignalFeedbackItem ? true : false;
    type NaiveHasActorId = 'actorId' extends keyof CamelizeKeys<OpenApiFeedback> ? true : false;
    expectTypeOf<UiHasActorId>().toEqualTypeOf<false>();
    expectTypeOf<NaiveHasActorId>().toEqualTypeOf<true>();
    expectTypeOf(feedbackBase).toMatchTypeOf<DecisionSignalFeedbackItem>();
    expectTypeOf({ ...feedbackBase, actorId: 'user-1' }).toMatchTypeOf<CamelizeKeys<OpenApiFeedback>>();
  });
});
