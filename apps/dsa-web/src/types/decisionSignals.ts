// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { components, operations, paths } from './api.generated';
import type { DecisionAction, MarketPhaseValue, ReportLanguage } from './analysis';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type Override<T, U> = Omit<T, keyof U> & U;

type OpenApiItem = components['schemas']['DecisionSignalItem'];
type OpenApiCreate = components['schemas']['DecisionSignalCreateRequest'];
type OpenApiList = components['schemas']['DecisionSignalListResponse'];
type OpenApiPresentation = components['schemas']['DecisionSignalPresentation'];
type OpenApiMutation = components['schemas']['DecisionSignalMutationResponse'];
type OpenApiStatus = components['schemas']['DecisionSignalStatusUpdateRequest'];
type OpenApiWarning = components['schemas']['DecisionSignalWarning'];
type OpenApiReassess = components['schemas']['DecisionSignalReassessRequest'];
type OpenApiReassessResponse = components['schemas']['DecisionSignalReassessResponse'];
type OpenApiPreview = components['schemas']['DecisionSignalPreview'];
type OpenApiFeedback = components['schemas']['DecisionSignalFeedbackItem'];
type OpenApiFeedbackRequest = components['schemas']['DecisionSignalFeedbackRequest'];
type OpenApiMemory = components['schemas']['DecisionSignalMemoryFlagItem'];
type OpenApiMemoryRequest = components['schemas']['DecisionSignalMemoryFlagRequest'];
type OpenApiOutcome = components['schemas']['DecisionSignalOutcomeItem'];
type OpenApiOutcomeRun = components['schemas']['DecisionSignalOutcomeRunRequest'];
type OpenApiOutcomeRunResponse = components['schemas']['DecisionSignalOutcomeRunResponse'];
type OpenApiOutcomeList = components['schemas']['DecisionSignalOutcomeListResponse'];
type OpenApiStats = components['schemas']['DecisionSignalOutcomeStatsResponse'];
type OpenApiStatsBucket = components['schemas']['DecisionSignalOutcomeStatsBucket'];
type OpenApiCalibration = components['schemas']['DecisionSignalProfileCalibration'];
type OpenApiCalibrationBucket = components['schemas']['DecisionSignalProfileCalibrationBucket'];
type OpenApiCalibrationBreakdowns = components['schemas']['DecisionSignalProfileCalibrationBreakdowns'];

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

type _Assert<T extends true> = T;
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
type _ListIsLatest200 = _Assert<OpenApiList extends OpenApiLatestGet200 ? true : false>;
type _LatestOpIsPath = _Assert<OpenApiLatestOp extends OpenApiLatestPathGet ? true : false>;
type _PathIsLatestOp = _Assert<OpenApiLatestPathGet extends OpenApiLatestOp ? true : false>;
type _LatestGetNeverRequestBody = _Assert<OpenApiLatestOp extends { requestBody?: never } ? true : false>;
type _LatestHas200 = _Assert<200 extends keyof OpenApiLatestOp['responses'] ? true : false>;
type _LatestLacks201 = _Assert<201 extends keyof OpenApiLatestOp['responses'] ? false : true>;
type _Get200IsItem = _Assert<OpenApiGetGet200 extends OpenApiItem ? true : false>;
type _ItemIsGet200 = _Assert<OpenApiItem extends OpenApiGetGet200 ? true : false>;
type _GetOpIsPath = _Assert<OpenApiGetOp extends OpenApiGetPathGet ? true : false>;
type _PathIsGetOp = _Assert<OpenApiGetPathGet extends OpenApiGetOp ? true : false>;
type _GetNeverRequestBody = _Assert<OpenApiGetOp extends { requestBody?: never } ? true : false>;
type _GetHas200 = _Assert<200 extends keyof OpenApiGetOp['responses'] ? true : false>;
type _GetLacks201 = _Assert<201 extends keyof OpenApiGetOp['responses'] ? false : true>;
type _Status200IsItem = _Assert<OpenApiStatusPatch200 extends OpenApiItem ? true : false>;
type _ItemIsStatus200 = _Assert<OpenApiItem extends OpenApiStatusPatch200 ? true : false>;
type _StatusOpIsPath = _Assert<OpenApiStatusOp extends OpenApiStatusPathPatch ? true : false>;
type _PathIsStatusOp = _Assert<OpenApiStatusPathPatch extends OpenApiStatusOp ? true : false>;
type _StatusBodyIsRequest = _Assert<OpenApiStatusBody extends OpenApiStatus ? true : false>;
type _RequestIsStatusBody = _Assert<OpenApiStatus extends OpenApiStatusBody ? true : false>;
type _StatusHas200 = _Assert<200 extends keyof OpenApiStatusOp['responses'] ? true : false>;
type _StatusLacks201 = _Assert<201 extends keyof OpenApiStatusOp['responses'] ? false : true>;
type _Reassess200IsReassess = _Assert<OpenApiReassessPost200 extends OpenApiReassessResponse ? true : false>;
type _ReassessIsReassess200 = _Assert<OpenApiReassessResponse extends OpenApiReassessPost200 ? true : false>;
type _ReassessOpIsPath = _Assert<OpenApiReassessOp extends OpenApiReassessPathPost ? true : false>;
type _PathIsReassessOp = _Assert<OpenApiReassessPathPost extends OpenApiReassessOp ? true : false>;
type _ReassessBodyIsRequest = _Assert<OpenApiReassessBody extends OpenApiReassess ? true : false>;
type _RequestIsReassessBody = _Assert<OpenApiReassess extends OpenApiReassessBody ? true : false>;
type _ReassessHas200 = _Assert<200 extends keyof OpenApiReassessOp['responses'] ? true : false>;
type _ReassessLacks201 = _Assert<201 extends keyof OpenApiReassessOp['responses'] ? false : true>;
type _FeedbackGet200IsFeedback = _Assert<OpenApiFeedbackGet200 extends OpenApiFeedback ? true : false>;
type _FeedbackIsFeedbackGet200 = _Assert<OpenApiFeedback extends OpenApiFeedbackGet200 ? true : false>;
type _FeedbackGetOpIsPath = _Assert<OpenApiFeedbackGetOp extends OpenApiFeedbackPathGet ? true : false>;
type _PathIsFeedbackGetOp = _Assert<OpenApiFeedbackPathGet extends OpenApiFeedbackGetOp ? true : false>;
type _FeedbackGetNeverRequestBody = _Assert<OpenApiFeedbackGetOp extends { requestBody?: never } ? true : false>;
type _FeedbackGetHas200 = _Assert<200 extends keyof OpenApiFeedbackGetOp['responses'] ? true : false>;
type _FeedbackGetLacks201 = _Assert<201 extends keyof OpenApiFeedbackGetOp['responses'] ? false : true>;
type _FeedbackPut200IsFeedback = _Assert<OpenApiFeedbackPut200 extends OpenApiFeedback ? true : false>;
type _FeedbackIsFeedbackPut200 = _Assert<OpenApiFeedback extends OpenApiFeedbackPut200 ? true : false>;
type _FeedbackPutOpIsPath = _Assert<OpenApiFeedbackPutOp extends OpenApiFeedbackPathPut ? true : false>;
type _PathIsFeedbackPutOp = _Assert<OpenApiFeedbackPathPut extends OpenApiFeedbackPutOp ? true : false>;
type _FeedbackBodyIsRequest = _Assert<OpenApiFeedbackBody extends OpenApiFeedbackRequest ? true : false>;
type _RequestIsFeedbackBody = _Assert<OpenApiFeedbackRequest extends OpenApiFeedbackBody ? true : false>;
type _FeedbackPutHas200 = _Assert<200 extends keyof OpenApiFeedbackPutOp['responses'] ? true : false>;
type _FeedbackPutLacks201 = _Assert<201 extends keyof OpenApiFeedbackPutOp['responses'] ? false : true>;
type _MemoryGet200IsMemory = _Assert<OpenApiMemoryGet200 extends OpenApiMemory ? true : false>;
type _MemoryIsMemoryGet200 = _Assert<OpenApiMemory extends OpenApiMemoryGet200 ? true : false>;
type _MemoryGetOpIsPath = _Assert<OpenApiMemoryGetOp extends OpenApiMemoryPathGet ? true : false>;
type _PathIsMemoryGetOp = _Assert<OpenApiMemoryPathGet extends OpenApiMemoryGetOp ? true : false>;
type _MemoryGetNeverRequestBody = _Assert<OpenApiMemoryGetOp extends { requestBody?: never } ? true : false>;
type _MemoryGetHas200 = _Assert<200 extends keyof OpenApiMemoryGetOp['responses'] ? true : false>;
type _MemoryGetLacks201 = _Assert<201 extends keyof OpenApiMemoryGetOp['responses'] ? false : true>;
type _MemoryPatch200IsMemory = _Assert<OpenApiMemoryPatch200 extends OpenApiMemory ? true : false>;
type _MemoryIsMemoryPatch200 = _Assert<OpenApiMemory extends OpenApiMemoryPatch200 ? true : false>;
type _MemoryPatchOpIsPath = _Assert<OpenApiMemoryPatchOp extends OpenApiMemoryPathPatch ? true : false>;
type _PathIsMemoryPatchOp = _Assert<OpenApiMemoryPathPatch extends OpenApiMemoryPatchOp ? true : false>;
type _MemoryBodyIsRequest = _Assert<OpenApiMemoryBody extends OpenApiMemoryRequest ? true : false>;
type _RequestIsMemoryBody = _Assert<OpenApiMemoryRequest extends OpenApiMemoryBody ? true : false>;
type _MemoryPatchHas200 = _Assert<200 extends keyof OpenApiMemoryPatchOp['responses'] ? true : false>;
type _MemoryPatchLacks201 = _Assert<201 extends keyof OpenApiMemoryPatchOp['responses'] ? false : true>;
type _OutcomeList200IsOutcomeList = _Assert<OpenApiOutcomeListGet200 extends OpenApiOutcomeList ? true : false>;
type _OutcomeListIsOutcomeList200 = _Assert<OpenApiOutcomeList extends OpenApiOutcomeListGet200 ? true : false>;
type _OutcomeListOpIsPath = _Assert<OpenApiOutcomeListOp extends OpenApiOutcomeListPathGet ? true : false>;
type _PathIsOutcomeListOp = _Assert<OpenApiOutcomeListPathGet extends OpenApiOutcomeListOp ? true : false>;
type _OutcomeListGetNeverRequestBody = _Assert<OpenApiOutcomeListOp extends { requestBody?: never } ? true : false>;
type _OutcomeListHas200 = _Assert<200 extends keyof OpenApiOutcomeListOp['responses'] ? true : false>;
type _OutcomeListLacks201 = _Assert<201 extends keyof OpenApiOutcomeListOp['responses'] ? false : true>;
type _OutcomeBySignal200IsOutcomeList = _Assert<
  OpenApiOutcomeBySignalGet200 extends OpenApiOutcomeList ? true : false
>;
type _OutcomeListIsOutcomeBySignal200 = _Assert<
  OpenApiOutcomeList extends OpenApiOutcomeBySignalGet200 ? true : false
>;
type _OutcomeBySignalOpIsPath = _Assert<OpenApiOutcomeBySignalOp extends OpenApiOutcomeBySignalPathGet ? true : false>;
type _PathIsOutcomeBySignalOp = _Assert<OpenApiOutcomeBySignalPathGet extends OpenApiOutcomeBySignalOp ? true : false>;
type _OutcomeBySignalGetNeverRequestBody = _Assert<
  OpenApiOutcomeBySignalOp extends { requestBody?: never } ? true : false
>;
type _OutcomeBySignalHas200 = _Assert<200 extends keyof OpenApiOutcomeBySignalOp['responses'] ? true : false>;
type _OutcomeBySignalLacks201 = _Assert<201 extends keyof OpenApiOutcomeBySignalOp['responses'] ? false : true>;
type _OutcomeRun200IsOutcomeRun = _Assert<OpenApiOutcomeRunPost200 extends OpenApiOutcomeRunResponse ? true : false>;
type _OutcomeRunIsOutcomeRun200 = _Assert<OpenApiOutcomeRunResponse extends OpenApiOutcomeRunPost200 ? true : false>;
type _OutcomeRunOpIsPath = _Assert<OpenApiOutcomeRunOp extends OpenApiOutcomeRunPathPost ? true : false>;
type _PathIsOutcomeRunOp = _Assert<OpenApiOutcomeRunPathPost extends OpenApiOutcomeRunOp ? true : false>;
type _OutcomeRunBodyIsRequest = _Assert<OpenApiOutcomeRunBody extends OpenApiOutcomeRun ? true : false>;
type _RequestIsOutcomeRunBody = _Assert<OpenApiOutcomeRun extends OpenApiOutcomeRunBody ? true : false>;
type _OutcomeRunHas200 = _Assert<200 extends keyof OpenApiOutcomeRunOp['responses'] ? true : false>;
type _OutcomeRunLacks201 = _Assert<201 extends keyof OpenApiOutcomeRunOp['responses'] ? false : true>;
type _Stats200IsStats = _Assert<OpenApiStatsGet200 extends OpenApiStats ? true : false>;
type _StatsIsStats200 = _Assert<OpenApiStats extends OpenApiStatsGet200 ? true : false>;
type _StatsOpIsPath = _Assert<OpenApiStatsOp extends OpenApiStatsPathGet ? true : false>;
type _PathIsStatsOp = _Assert<OpenApiStatsPathGet extends OpenApiStatsOp ? true : false>;
type _StatsGetNeverRequestBody = _Assert<OpenApiStatsOp extends { requestBody?: never } ? true : false>;
type _StatsHas200 = _Assert<200 extends keyof OpenApiStatsOp['responses'] ? true : false>;
type _StatsLacks201 = _Assert<201 extends keyof OpenApiStatsOp['responses'] ? false : true>;

type _OpenApiAnchors = [
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
  _ListIsLatest200,
  _LatestOpIsPath,
  _PathIsLatestOp,
  _LatestGetNeverRequestBody,
  _LatestHas200,
  _LatestLacks201,
  _Get200IsItem,
  _ItemIsGet200,
  _GetOpIsPath,
  _PathIsGetOp,
  _GetNeverRequestBody,
  _GetHas200,
  _GetLacks201,
  _Status200IsItem,
  _ItemIsStatus200,
  _StatusOpIsPath,
  _PathIsStatusOp,
  _StatusBodyIsRequest,
  _RequestIsStatusBody,
  _StatusHas200,
  _StatusLacks201,
  _Reassess200IsReassess,
  _ReassessIsReassess200,
  _ReassessOpIsPath,
  _PathIsReassessOp,
  _ReassessBodyIsRequest,
  _RequestIsReassessBody,
  _ReassessHas200,
  _ReassessLacks201,
  _FeedbackGet200IsFeedback,
  _FeedbackIsFeedbackGet200,
  _FeedbackGetOpIsPath,
  _PathIsFeedbackGetOp,
  _FeedbackGetNeverRequestBody,
  _FeedbackGetHas200,
  _FeedbackGetLacks201,
  _FeedbackPut200IsFeedback,
  _FeedbackIsFeedbackPut200,
  _FeedbackPutOpIsPath,
  _PathIsFeedbackPutOp,
  _FeedbackBodyIsRequest,
  _RequestIsFeedbackBody,
  _FeedbackPutHas200,
  _FeedbackPutLacks201,
  _MemoryGet200IsMemory,
  _MemoryIsMemoryGet200,
  _MemoryGetOpIsPath,
  _PathIsMemoryGetOp,
  _MemoryGetNeverRequestBody,
  _MemoryGetHas200,
  _MemoryGetLacks201,
  _MemoryPatch200IsMemory,
  _MemoryIsMemoryPatch200,
  _MemoryPatchOpIsPath,
  _PathIsMemoryPatchOp,
  _MemoryBodyIsRequest,
  _RequestIsMemoryBody,
  _MemoryPatchHas200,
  _MemoryPatchLacks201,
  _OutcomeList200IsOutcomeList,
  _OutcomeListIsOutcomeList200,
  _OutcomeListOpIsPath,
  _PathIsOutcomeListOp,
  _OutcomeListGetNeverRequestBody,
  _OutcomeListHas200,
  _OutcomeListLacks201,
  _OutcomeBySignal200IsOutcomeList,
  _OutcomeListIsOutcomeBySignal200,
  _OutcomeBySignalOpIsPath,
  _PathIsOutcomeBySignalOp,
  _OutcomeBySignalGetNeverRequestBody,
  _OutcomeBySignalHas200,
  _OutcomeBySignalLacks201,
  _OutcomeRun200IsOutcomeRun,
  _OutcomeRunIsOutcomeRun200,
  _OutcomeRunOpIsPath,
  _PathIsOutcomeRunOp,
  _OutcomeRunBodyIsRequest,
  _RequestIsOutcomeRunBody,
  _OutcomeRunHas200,
  _OutcomeRunLacks201,
  _Stats200IsStats,
  _StatsIsStats200,
  _StatsOpIsPath,
  _PathIsStatsOp,
  _StatsGetNeverRequestBody,
  _StatsHas200,
  _StatsLacks201,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

/**
 * Opaque JSON fields are passed through without inner key-name conversion.
 * Only the containing DecisionSignal API field is mapped between camelCase and snake_case.
 */
export type DecisionSignalOpaqueJson = unknown;

export type DecisionSignalSourceType = 'analysis' | 'agent' | 'alert' | 'market_review' | 'manual';
export type DecisionSignalStatus = 'active' | 'expired' | 'invalidated' | 'closed' | 'archived';
export type DecisionSignalPlanQuality = 'complete' | 'partial' | 'minimal' | 'unknown';
export type DecisionSignalHorizon = 'intraday' | '1d' | '3d' | '5d' | '10d' | 'swing' | 'long';
export type DecisionSignalMarket = 'cn' | 'hk' | 'us' | 'jp' | 'kr' | 'tw';
export type DecisionSignalOutcomeEvalStatus = 'completed' | 'unable';
export type DecisionSignalOutcomeValue = 'hit' | 'miss' | 'neutral';
export type DecisionSignalFeedbackValue = 'useful' | 'not_useful';
export type DecisionSignalFeedbackSource = 'web' | 'api';
export type DecisionProfile = 'conservative' | 'balanced' | 'aggressive';
export type DecisionProfileDisplay = DecisionProfile | 'unknown';
export type DecisionSignalPersistStatus = 'created' | 'existing' | 'refreshed';

export type DecisionSignalPresentation = Override<CamelizeKeys<OpenApiPresentation>, {
  action: DecisionAction;
}>;

export type DecisionSignalItem = Override<CamelizeKeys<OpenApiItem>, {
  market: DecisionSignalMarket;
  sourceType: DecisionSignalSourceType;
  action: DecisionAction;
  marketPhase?: MarketPhaseValue | null;
  horizon?: DecisionSignalHorizon | null;
  evidence?: DecisionSignalOpaqueJson;
  dataQualitySummary?: DecisionSignalOpaqueJson;
  planQuality: DecisionSignalPlanQuality;
  status: DecisionSignalStatus;
  metadata?: DecisionSignalOpaqueJson;
  /** Optional only for rolling upgrades from servers predating the canonical presentation contract. */
  presentation?: DecisionSignalPresentation;
}>;

export type DecisionSignalCreateRequest = Override<CamelizeKeys<OpenApiCreate>, {
  invalidation?: unknown;
  watchConditions?: unknown;
  reason?: unknown;
  riskSummary?: unknown;
  catalystSummary?: unknown;
  metadata?: Record<string, unknown> | null;
  reportLanguage?: ReportLanguage | null;
}>;

export interface DecisionSignalListParams {
  market?: DecisionSignalMarket;
  stockCode?: string;
  action?: DecisionAction;
  marketPhase?: MarketPhaseValue;
  decisionProfile?: DecisionProfileDisplay;
  sourceType?: DecisionSignalSourceType;
  sourceReportId?: number;
  traceId?: string;
  triggerSource?: string;
  status?: DecisionSignalStatus;
  createdFrom?: string;
  createdTo?: string;
  expiresFrom?: string;
  expiresTo?: string;
  holdingOnly?: boolean;
  accountId?: number;
  page?: number;
  pageSize?: number;
}

export interface DecisionSignalLatestParams {
  market?: DecisionSignalMarket;
  limit?: number;
}

export type DecisionSignalStatusUpdateRequest = Override<CamelizeKeys<OpenApiStatus>, {
  metadata?: Record<string, unknown> | null;
}>;

export type DecisionSignalMutationResponse = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiMutation>, {
  item: DecisionSignalItem;
}>>;

export type DecisionSignalWarning = Override<CamelizeKeys<OpenApiWarning>, {
  params?: Record<string, unknown> | null;
}>;

export type DecisionSignalReassessRequest = Override<CamelizeKeys<OpenApiReassess>, {
  persist?: boolean;
}>;

export type DecisionSignalReassessPreview = Override<CamelizeKeys<OpenApiPreview>, {
  action: DecisionAction;
  horizon?: DecisionSignalHorizon | null;
  metadata: Record<string, unknown>;
}>;

export type DecisionSignalReassessResponse = Override<CamelizeKeys<OpenApiReassessResponse>, {
  preview?: DecisionSignalReassessPreview | null;
  item?: DecisionSignalItem | null;
  warnings: DecisionSignalWarning[];
  persistStatus?: DecisionSignalPersistStatus | null;
}>;

export interface DecisionSignalReassessBlockedError {
  blockedReason: string;
  warnings: DecisionSignalWarning[];
}

export type DecisionSignalListResponse = Override<CamelizeKeys<OpenApiList>, {
  items: DecisionSignalItem[];
}>;

export type DecisionSignalOutcomeItem = Override<CamelizeKeys<OpenApiOutcome>, {
  horizon: DecisionSignalHorizon;
  evalStatus: DecisionSignalOutcomeEvalStatus;
  outcome?: DecisionSignalOutcomeValue | null;
  action?: DecisionAction | null;
  market?: DecisionSignalMarket | null;
  marketPhase?: MarketPhaseValue | null;
  sourceType?: DecisionSignalSourceType | null;
  planQuality?: DecisionSignalPlanQuality | null;
  holdingState: 'holding' | 'empty' | 'unknown';
}>;

export type DecisionSignalOutcomeRunRequest = Override<CamelizeKeys<OpenApiOutcomeRun>, {
  signalId?: number;
  horizons?: DecisionSignalHorizon[];
  force?: boolean;
  market?: DecisionSignalMarket;
  stockCode?: string;
  action?: DecisionAction;
  sourceType?: DecisionSignalSourceType;
  status?: DecisionSignalStatus;
  limit?: number;
}>;

export type DecisionSignalOutcomeRunResponse = Override<CamelizeKeys<OpenApiOutcomeRunResponse>, {
  items: DecisionSignalOutcomeItem[];
}>;

export interface DecisionSignalOutcomeListParams {
  signalId?: number;
  horizon?: DecisionSignalHorizon;
  engineVersion?: string;
  evalStatus?: DecisionSignalOutcomeEvalStatus;
  outcome?: DecisionSignalOutcomeValue;
  page?: number;
  pageSize?: number;
}

export type DecisionSignalOutcomeListResponse = Override<CamelizeKeys<OpenApiOutcomeList>, {
  items: DecisionSignalOutcomeItem[];
}>;

export type DecisionSignalOutcomeStatsBucket = Override<CamelizeKeys<OpenApiStatsBucket>, {
  unableReasons: Record<string, number>;
}>;

export type DecisionSignalProfileCalibrationBucket = Override<CamelizeKeys<OpenApiCalibrationBucket>, {
  dimensions: Record<string, string>;
  hitRatePct: number | null;
  avgStockReturnPct: number | null;
  missRatePct: number | null;
  unableRatePct: number | null;
  maxAdverseExcursionPct: number | null;
}>;

export type DecisionSignalProfileCalibrationBreakdowns = Override<CamelizeKeys<OpenApiCalibrationBreakdowns>, {
  decisionProfile: DecisionSignalProfileCalibrationBucket[];
  decisionProfileAction: DecisionSignalProfileCalibrationBucket[];
  decisionProfileHorizon: DecisionSignalProfileCalibrationBucket[];
  decisionProfileMarketPhase: DecisionSignalProfileCalibrationBucket[];
  decisionProfileDataQualityLevel: DecisionSignalProfileCalibrationBucket[];
  profileSource: DecisionSignalProfileCalibrationBucket[];
}>;

export type DecisionSignalProfileCalibration = Override<CamelizeKeys<OpenApiCalibration>, {
  breakdowns: DecisionSignalProfileCalibrationBreakdowns;
}>;

export type DecisionSignalOutcomeStatsResponse = Override<CamelizeKeys<OpenApiStats>, {
  horizons?: DecisionSignalHorizon[] | null;
  statuses: DecisionSignalStatus[];
  unableReasons: Record<string, number>;
  breakdowns: Record<string, DecisionSignalOutcomeStatsBucket[]>;
  profileCalibration?: DecisionSignalProfileCalibration;
}>;

export interface DecisionSignalOutcomeStatsParams {
  horizons?: DecisionSignalHorizon[];
  engineVersion?: string;
  statuses?: DecisionSignalStatus[];
}

export type DecisionSignalFeedbackItem = Omit<CamelizeKeys<OpenApiFeedback>, 'actorId' | 'provenanceSource'>;

export type DecisionSignalFeedbackRequest = Override<CamelizeKeys<OpenApiFeedbackRequest>, {
  source?: DecisionSignalFeedbackSource;
}>;

export type DecisionSignalMemoryFlagItem = CamelizeKeys<OpenApiMemory>;

export type DecisionSignalMemoryFlagUpdateRequest = Override<CamelizeKeys<OpenApiMemoryRequest>, {
  memorable?: boolean;
  ignored?: boolean;
}>;
