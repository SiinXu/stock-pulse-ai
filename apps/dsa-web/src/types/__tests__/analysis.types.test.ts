// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as Analysis from '../analysis';
import {
  getSentimentColor,
  getSentimentLabel,
} from '../analysis';
import type {
  AnalysisRequest,
  AnalysisResult,
  MarketPhaseSummary,
  MarketReviewAccepted,
  MarketReviewRequest,
  TaskAccepted,
  TaskListResponse,
} from '../analysis';

type OpenApiAnalyze = components['schemas']['AnalyzeRequest'];
type OpenApiAccepted = components['schemas']['TaskAccepted'];
type OpenApiBatch = components['schemas']['BatchTaskAcceptedResponse'];
type OpenApiPhase = components['schemas']['MarketPhaseSummary'];
type OpenApiReviewRequest = components['schemas']['MarketReviewRequest'];
type OpenApiReviewAccepted = components['schemas']['MarketReviewAccepted'];
type OpenApiResult = components['schemas']['AnalysisResultResponse'];
type OpenApiTaskStatus = components['schemas']['TaskStatus'];
type OpenApiTaskList = components['schemas']['TaskListResponse'];

type OpenApiAnalyzeOp = operations['trigger_analysis_api_v1_analysis_analyze_post'];
type OpenApiReviewOp = operations['trigger_market_review_api_v1_analysis_market_review_post'];
type OpenApiStatusOp = operations['get_analysis_status_api_v1_analysis_status__task_id__get'];
type OpenApiTaskListOp = operations['get_task_list_api_v1_analysis_tasks_get'];
type OpenApiCancelOp = operations['cancelAnalysisTask'];

type OpenApiAnalyzePathPost = paths['/api/v1/analysis/analyze']['post'];
type OpenApiReviewPathPost = paths['/api/v1/analysis/market-review']['post'];
type OpenApiStatusPathGet = paths['/api/v1/analysis/status/{task_id}']['get'];
type OpenApiTaskListPathGet = paths['/api/v1/analysis/tasks']['get'];
type OpenApiCancelPathPost = paths['/api/v1/analysis/tasks/{task_id}/cancel']['post'];

type OpenApiAnalyzePost200 = OpenApiAnalyzeOp['responses']['200']['content']['application/json'];
type OpenApiAnalyzePost202 = OpenApiAnalyzeOp['responses']['202']['content']['application/json'];
type OpenApiAnalyzeBody = OpenApiAnalyzeOp['requestBody']['content']['application/json'];
type OpenApiReviewPost202 = OpenApiReviewOp['responses']['202']['content']['application/json'];
type OpenApiStatusGet200 = OpenApiStatusOp['responses']['200']['content']['application/json'];
type OpenApiTaskListGet200 = OpenApiTaskListOp['responses']['200']['content']['application/json'];
type OpenApiCancelPost200 = OpenApiCancelOp['responses']['200']['content']['application/json'];

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

type _BoundComponents = _Assert<
  (
    | 'AnalyzeRequest'
    | 'TaskAccepted'
    | 'BatchTaskAcceptedItem'
    | 'BatchTaskAcceptedResponse'
    | 'TaskStatus'
    | 'TaskInfo'
    | 'TaskListResponse'
    | 'AnalysisResultResponse'
    | 'AnalysisReport'
    | 'MarketPhaseSummary'
    | 'MarketReviewAccepted'
    | 'MarketReviewRequest'
    | 'AnalysisContextPackOverview'
    | 'ReportStructuredInsights'
  ) extends keyof components['schemas'] ? true : false
>;

type _Analyze200IsResult = _Assert<OpenApiAnalyzePost200 extends OpenApiResult ? true : false>;
type _ResultIsAnalyze200 = _Assert<OpenApiResult extends OpenApiAnalyzePost200 ? true : false>;
type _AnalyzeOpIsPath = _Assert<OpenApiAnalyzeOp extends OpenApiAnalyzePathPost ? true : false>;
type _PathIsAnalyzeOp = _Assert<OpenApiAnalyzePathPost extends OpenApiAnalyzeOp ? true : false>;
type _AnalyzeBodyIsRequest = _Assert<OpenApiAnalyzeBody extends OpenApiAnalyze ? true : false>;
type _RequestIsAnalyzeBody = _Assert<OpenApiAnalyze extends OpenApiAnalyzeBody ? true : false>;
type _AnalyzeHas200 = _Assert<200 extends keyof OpenApiAnalyzeOp['responses'] ? true : false>;
type _AnalyzeHas202 = _Assert<202 extends keyof OpenApiAnalyzeOp['responses'] ? true : false>;
type _AnalyzeLacks201 = _Assert<201 extends keyof OpenApiAnalyzeOp['responses'] ? false : true>;
type _Analyze202IsAcceptedOrBatch = _Assert<
  OpenApiAnalyzePost202 extends OpenApiAccepted | OpenApiBatch ? true : false
>;
type _AcceptedOrBatchIsAnalyze202 = _Assert<
  OpenApiAccepted | OpenApiBatch extends OpenApiAnalyzePost202 ? true : false
>;
type _Review202IsAccepted = _Assert<OpenApiReviewPost202 extends OpenApiReviewAccepted ? true : false>;
type _AcceptedIsReview202 = _Assert<OpenApiReviewAccepted extends OpenApiReviewPost202 ? true : false>;
type _ReviewOpIsPath = _Assert<OpenApiReviewOp extends OpenApiReviewPathPost ? true : false>;
type _PathIsReviewOp = _Assert<OpenApiReviewPathPost extends OpenApiReviewOp ? true : false>;
type _ReviewHas202 = _Assert<202 extends keyof OpenApiReviewOp['responses'] ? true : false>;
type _ReviewLacks200 = _Assert<200 extends keyof OpenApiReviewOp['responses'] ? false : true>;
type _ReviewLacks201 = _Assert<201 extends keyof OpenApiReviewOp['responses'] ? false : true>;
type _Status200IsStatus = _Assert<OpenApiStatusGet200 extends OpenApiTaskStatus ? true : false>;
type _StatusIsStatus200 = _Assert<OpenApiTaskStatus extends OpenApiStatusGet200 ? true : false>;
type _StatusOpIsPath = _Assert<OpenApiStatusOp extends OpenApiStatusPathGet ? true : false>;
type _PathIsStatusOp = _Assert<OpenApiStatusPathGet extends OpenApiStatusOp ? true : false>;
type _StatusGetNeverRequestBody = _Assert<OpenApiStatusOp extends { requestBody?: never } ? true : false>;
type _TaskList200IsTaskList = _Assert<OpenApiTaskListGet200 extends OpenApiTaskList ? true : false>;
type _TaskListIsTaskList200 = _Assert<OpenApiTaskList extends OpenApiTaskListGet200 ? true : false>;
type _TaskListGetNeverRequestBody = _Assert<
  OpenApiTaskListOp extends { requestBody?: never } ? true : false
>;
type _Cancel200IsStatus = _Assert<OpenApiCancelPost200 extends OpenApiTaskStatus ? true : false>;
type _CancelNeverRequestBody = _Assert<OpenApiCancelOp extends { requestBody?: never } ? true : false>;

type _PublicResultNotPath200 = _Assert<AnalysisResult extends OpenApiAnalyzePost200 ? false : true>;
type _Path200NotPublicResult = _Assert<OpenApiAnalyzePost200 extends AnalysisResult ? false : true>;
type _PublicAcceptedNotPath202 = _Assert<TaskAccepted extends OpenApiAnalyzePost202 ? false : true>;
type _PublicListNotPath200 = _Assert<TaskListResponse extends OpenApiTaskListGet200 ? false : true>;
type _Path200NotPublicList = _Assert<OpenApiTaskListGet200 extends TaskListResponse ? false : true>;

type _UiHasTaskId = _Assert<'taskId' extends keyof TaskAccepted ? true : false>;
type _UiHasMessageCode = _Assert<'messageCode' extends keyof TaskAccepted ? true : false>;
type _UiHasAnalysisPhase = _Assert<'analysisPhase' extends keyof TaskAccepted ? true : false>;
type _UiLacksTaskIdSnake = _Assert<'task_id' extends keyof TaskAccepted ? false : true>;
type _UiLacksMessageCodeSnake = _Assert<'message_code' extends keyof TaskAccepted ? false : true>;
type _UiLacksAnalysisPhaseSnake = _Assert<'analysis_phase' extends keyof TaskAccepted ? false : true>;
type _GeneratedHasTaskIdSnake = _Assert<'task_id' extends keyof OpenApiAccepted ? true : false>;
type _GeneratedHasMessageCodeSnake = _Assert<'message_code' extends keyof OpenApiAccepted ? true : false>;
type _GeneratedHasAnalysisPhaseSnake = _Assert<'analysis_phase' extends keyof OpenApiAccepted ? true : false>;
type _GeneratedLacksTaskIdCamel = _Assert<'taskId' extends keyof OpenApiAccepted ? false : true>;
type _GeneratedLacksMessageCodeCamel = _Assert<'messageCode' extends keyof OpenApiAccepted ? false : true>;
type _GeneratedLacksAnalysisPhaseCamel = _Assert<
  'analysisPhase' extends keyof OpenApiAccepted ? false : true
>;
type _UiLacksUseMemory = _Assert<'useMemory' extends keyof AnalysisRequest ? false : true>;
type _NaiveHasUseMemory = _Assert<'useMemory' extends keyof CamelizeKeys<OpenApiAnalyze> ? true : false>;

type _UiAnalyzePhaseOptional = _Assert<IsOptional<AnalysisRequest, 'analysisPhase'>>;
type _UiAsyncModeOptional = _Assert<IsOptional<AnalysisRequest, 'asyncMode'>>;
type _UiForceRefreshOptional = _Assert<IsOptional<AnalysisRequest, 'forceRefresh'>>;
type _UiNotifyOptional = _Assert<IsOptional<AnalysisRequest, 'notify'>>;
type _UiReportTypeOptional = _Assert<IsOptional<AnalysisRequest, 'reportType'>>;
type _NaiveAnalyzePhaseRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiAnalyze>, 'analysisPhase'> extends false ? true : false
>;
type _NaiveAsyncModeRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiAnalyze>, 'asyncMode'> extends false ? true : false
>;
type _UiAcceptedPhaseOptional = _Assert<IsOptional<TaskAccepted, 'analysisPhase'>>;
type _UiAcceptedCodeOptional = _Assert<IsOptional<TaskAccepted, 'messageCode'>>;
type _NaiveAcceptedPhaseRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiAccepted>, 'analysisPhase'> extends false ? true : false
>;
type _NaiveAcceptedCodeRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiAccepted>, 'messageCode'> extends false ? true : false
>;
type _UiWarningsRequired = _Assert<
  IsOptional<MarketPhaseSummary, 'warnings'> extends false ? true : false
>;
type _NaiveWarningsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiPhase>, 'warnings'>>;
type _UiReviewSendOptional = _Assert<IsOptional<MarketReviewRequest, 'sendNotification'>>;
type _NaiveReviewSendRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiReviewRequest>, 'sendNotification'> extends false ? true : false
>;

type _CompileTimePins = [
  _BoundComponents,
  _Analyze200IsResult,
  _ResultIsAnalyze200,
  _AnalyzeOpIsPath,
  _PathIsAnalyzeOp,
  _AnalyzeBodyIsRequest,
  _RequestIsAnalyzeBody,
  _AnalyzeHas200,
  _AnalyzeHas202,
  _AnalyzeLacks201,
  _Analyze202IsAcceptedOrBatch,
  _AcceptedOrBatchIsAnalyze202,
  _Review202IsAccepted,
  _AcceptedIsReview202,
  _ReviewOpIsPath,
  _PathIsReviewOp,
  _ReviewHas202,
  _ReviewLacks200,
  _ReviewLacks201,
  _Status200IsStatus,
  _StatusIsStatus200,
  _StatusOpIsPath,
  _PathIsStatusOp,
  _StatusGetNeverRequestBody,
  _TaskList200IsTaskList,
  _TaskListIsTaskList200,
  _TaskListGetNeverRequestBody,
  _Cancel200IsStatus,
  _CancelNeverRequestBody,
  _PublicResultNotPath200,
  _Path200NotPublicResult,
  _PublicAcceptedNotPath202,
  _PublicListNotPath200,
  _Path200NotPublicList,
  _UiHasTaskId,
  _UiHasMessageCode,
  _UiHasAnalysisPhase,
  _UiLacksTaskIdSnake,
  _UiLacksMessageCodeSnake,
  _UiLacksAnalysisPhaseSnake,
  _GeneratedHasTaskIdSnake,
  _GeneratedHasMessageCodeSnake,
  _GeneratedHasAnalysisPhaseSnake,
  _GeneratedLacksTaskIdCamel,
  _GeneratedLacksMessageCodeCamel,
  _GeneratedLacksAnalysisPhaseCamel,
  _UiLacksUseMemory,
  _NaiveHasUseMemory,
  _UiAnalyzePhaseOptional,
  _UiAsyncModeOptional,
  _UiForceRefreshOptional,
  _UiNotifyOptional,
  _UiReportTypeOptional,
  _NaiveAnalyzePhaseRequired,
  _NaiveAsyncModeRequired,
  _UiAcceptedPhaseOptional,
  _UiAcceptedCodeOptional,
  _NaiveAcceptedPhaseRequired,
  _NaiveAcceptedCodeRequired,
  _UiWarningsRequired,
  _NaiveWarningsOptional,
  _UiReviewSendOptional,
  _NaiveReviewSendRequired,
];

const acceptedBase = {
  taskId: 't-1',
  status: 'pending' as const,
};

const reviewAcceptedBase = {
  status: 'accepted' as const,
  message: 'queued',
  sendNotification: true,
  region: 'cn',
};

const phaseMissingWarnings = { phase: 'intraday' as const };

const uiAnalyze: AnalysisRequest = {};
void uiAnalyze;
const uiAccepted: TaskAccepted = acceptedBase;
void uiAccepted;
const uiReviewRequest: MarketReviewRequest = {};
void uiReviewRequest;
const uiReview: MarketReviewAccepted = reviewAcceptedBase;
void uiReview;
const uiPhase: MarketPhaseSummary = { phase: 'intraday', warnings: [] };
void uiPhase;
const uiTaskList: TaskListResponse = { total: 0, pending: 0, processing: 0, tasks: [] };
void uiTaskList;

// @ts-expect-error naive analyze requires generated-default analysisPhase/asyncMode/forceRefresh/notify/reportType
const naiveAnalyze: CamelizeKeys<OpenApiAnalyze> = {};
void naiveAnalyze;

// @ts-expect-error naive TaskAccepted requires generated-default analysisPhase and messageCode
const naiveAccepted: CamelizeKeys<OpenApiAccepted> = acceptedBase;
void naiveAccepted;

const naivePhaseMissing: CamelizeKeys<OpenApiPhase> = phaseMissingWarnings;
void naivePhaseMissing;
// @ts-expect-error public MarketPhaseSummary.warnings is required
const publicPhaseMissing: MarketPhaseSummary = phaseMissingWarnings;
void publicPhaseMissing;

// @ts-expect-error naive market-review request requires generated-default sendNotification
const naiveReviewRequest: CamelizeKeys<OpenApiReviewRequest> = {};
void naiveReviewRequest;

const naiveReviewQueued: CamelizeKeys<OpenApiReviewAccepted> = {
  ...reviewAcceptedBase,
  status: 'queued',
  messageCode: 'task.market_review.queued',
};
void naiveReviewQueued;
// @ts-expect-error public market-review status is the 'accepted' literal
const publicReviewQueued: MarketReviewAccepted = { ...reviewAcceptedBase, status: 'queued' };
void publicReviewQueued;

// @ts-expect-error useMemory is not a public AnalysisRequest field
const publicUseMemory: AnalysisRequest = { useMemory: true };
void publicUseMemory;
const naiveUseMemory: CamelizeKeys<OpenApiAnalyze> = {
  analysisPhase: 'auto',
  asyncMode: false,
  forceRefresh: false,
  notify: true,
  reportType: 'detailed',
  useMemory: true,
};
void naiveUseMemory;

// @ts-expect-error futureTaskFlag is not a public TaskAccepted field
const extraAccepted: TaskAccepted = { ...acceptedBase, futureTaskFlag: true };

const publicParams: TaskAccepted = {
  ...acceptedBase,
  messageParams: { count: 1, futureParam: true },
};
void publicParams;

// @ts-expect-error task_id is not a public camelCase field
const publicSnake: TaskAccepted = { ...acceptedBase, task_id: 't-1' };

void extraAccepted;
void publicSnake;

describe('analysis OpenAPI type bind', () => {
  it('keeps runtime sentiment helpers exported', () => {
    expect(getSentimentLabel(50, 'en')).toBe('Neutral');
    expect(getSentimentLabel(20, 'zh')).toBe('极度悲观');
    expect(getSentimentLabel(90, 'ko')).toBe('매우 낙관');
    expect(getSentimentColor(50)).toBe('#eab308');
    expect(getSentimentColor(10)).toBe('#ef4444');
    expect(Analysis.getSentimentLabel(80, 'en')).toBe('Bullish');
    expect(Analysis.getSentimentColor(90)).toBe('#10b981');
    expect(Object.keys(Analysis)).toEqual(
      expect.arrayContaining(['getSentimentLabel', 'getSentimentColor']),
    );
    expect({ ...Analysis }).not.toEqual({});
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates path JSON to named generated components, keeps GET requestBody never, and uses 200/202 not 201', () => {
    expectTypeOf<OpenApiAnalyzePost200>().toEqualTypeOf<OpenApiResult>();
    expectTypeOf<OpenApiAnalyzePost202>().toEqualTypeOf<OpenApiAccepted | OpenApiBatch>();
    expectTypeOf<OpenApiAnalyzeBody>().toEqualTypeOf<OpenApiAnalyze>();
    expectTypeOf<OpenApiReviewPost202>().toEqualTypeOf<OpenApiReviewAccepted>();
    expectTypeOf<OpenApiStatusGet200>().toEqualTypeOf<OpenApiTaskStatus>();
    expectTypeOf<OpenApiTaskListGet200>().toEqualTypeOf<OpenApiTaskList>();
    expectTypeOf<OpenApiCancelPost200>().toEqualTypeOf<OpenApiTaskStatus>();
    expectTypeOf<OpenApiAnalyzeOp>().toEqualTypeOf<OpenApiAnalyzePathPost>();
    expectTypeOf<OpenApiReviewOp>().toEqualTypeOf<OpenApiReviewPathPost>();
    expectTypeOf<OpenApiStatusOp>().toEqualTypeOf<OpenApiStatusPathGet>();
    expectTypeOf<OpenApiTaskListOp>().toEqualTypeOf<OpenApiTaskListPathGet>();
    expectTypeOf<OpenApiCancelOp>().toEqualTypeOf<OpenApiCancelPathPost>();
    type StatusNeverBody = OpenApiStatusOp extends { requestBody?: never } ? true : false;
    type TaskListNeverBody = OpenApiTaskListOp extends { requestBody?: never } ? true : false;
    type CancelNeverBody = OpenApiCancelOp extends { requestBody?: never } ? true : false;
    type AnalyzeHas200 = 200 extends keyof OpenApiAnalyzeOp['responses'] ? true : false;
    type AnalyzeHas202 = 202 extends keyof OpenApiAnalyzeOp['responses'] ? true : false;
    type AnalyzeHas201 = 201 extends keyof OpenApiAnalyzeOp['responses'] ? true : false;
    type ReviewHas202 = 202 extends keyof OpenApiReviewOp['responses'] ? true : false;
    type ReviewHas200 = 200 extends keyof OpenApiReviewOp['responses'] ? true : false;
    type ReviewHas201 = 201 extends keyof OpenApiReviewOp['responses'] ? true : false;
    type StatusHas201 = 201 extends keyof OpenApiStatusOp['responses'] ? true : false;
    type TaskListHas201 = 201 extends keyof OpenApiTaskListOp['responses'] ? true : false;
    expectTypeOf<StatusNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<TaskListNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<CancelNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<AnalyzeHas200>().toEqualTypeOf<true>();
    expectTypeOf<AnalyzeHas202>().toEqualTypeOf<true>();
    expectTypeOf<AnalyzeHas201>().toEqualTypeOf<false>();
    expectTypeOf<ReviewHas202>().toEqualTypeOf<true>();
    expectTypeOf<ReviewHas200>().toEqualTypeOf<false>();
    expectTypeOf<ReviewHas201>().toEqualTypeOf<false>();
    expectTypeOf<StatusHas201>().toEqualTypeOf<false>();
    expectTypeOf<TaskListHas201>().toEqualTypeOf<false>();
  });

  it('does not claim public Override types equal path 200/202 JSON', () => {
    type PublicResultExtendsPath = AnalysisResult extends OpenApiAnalyzePost200 ? true : false;
    type PathExtendsPublicResult = OpenApiAnalyzePost200 extends AnalysisResult ? true : false;
    type PublicAcceptedExtendsPath = TaskAccepted extends OpenApiAnalyzePost202 ? true : false;
    type PublicListExtendsPath = TaskListResponse extends OpenApiTaskListGet200 ? true : false;
    type PathExtendsPublicList = OpenApiTaskListGet200 extends TaskListResponse ? true : false;
    expectTypeOf<PublicResultExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicResult>().toEqualTypeOf<false>();
    expectTypeOf<PublicAcceptedExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PublicListExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicList>().toEqualTypeOf<false>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof TaskAccepted>().not.toMatchTypeOf<'task_id' | 'message_code' | 'analysis_phase'>();
    expectTypeOf<keyof OpenApiAccepted>().not.toMatchTypeOf<'taskId' | 'messageCode' | 'analysisPhase'>();
    expectTypeOf<keyof AnalysisRequest>().not.toMatchTypeOf<'useMemory' | 'enableDebate' | 'debateMaxRounds'>();
  });

  it('keeps UI AnalyzeRequest empty fixtures assignable and omits generated-only useMemory', () => {
    const empty = {};
    expectTypeOf(empty).toMatchTypeOf<AnalysisRequest>();
    expectTypeOf(empty).not.toMatchTypeOf<CamelizeKeys<OpenApiAnalyze>>();
    type UiPhaseOptional = IsOptional<AnalysisRequest, 'analysisPhase'>;
    type NaivePhaseOptional = IsOptional<CamelizeKeys<OpenApiAnalyze>, 'analysisPhase'>;
    type UiHasUseMemory = 'useMemory' extends keyof AnalysisRequest ? true : false;
    type NaiveHasUseMemory = 'useMemory' extends keyof CamelizeKeys<OpenApiAnalyze> ? true : false;
    expectTypeOf<UiPhaseOptional>().toEqualTypeOf<true>();
    expectTypeOf<NaivePhaseOptional>().toEqualTypeOf<false>();
    expectTypeOf<UiHasUseMemory>().toEqualTypeOf<false>();
    expectTypeOf<NaiveHasUseMemory>().toEqualTypeOf<true>();
    expectTypeOf(naiveUseMemory).toMatchTypeOf<CamelizeKeys<OpenApiAnalyze>>();
  });

  it('keeps UI TaskAccepted analysisPhase and messageCode optional so short fixtures assign', () => {
    expectTypeOf(acceptedBase).toMatchTypeOf<TaskAccepted>();
    expectTypeOf(acceptedBase).not.toMatchTypeOf<CamelizeKeys<OpenApiAccepted>>();
    type UiPhaseOptional = IsOptional<TaskAccepted, 'analysisPhase'>;
    type UiCodeOptional = IsOptional<TaskAccepted, 'messageCode'>;
    type NaivePhaseOptional = IsOptional<CamelizeKeys<OpenApiAccepted>, 'analysisPhase'>;
    type NaiveCodeOptional = IsOptional<CamelizeKeys<OpenApiAccepted>, 'messageCode'>;
    expectTypeOf<UiPhaseOptional>().toEqualTypeOf<true>();
    expectTypeOf<UiCodeOptional>().toEqualTypeOf<true>();
    expectTypeOf<NaivePhaseOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveCodeOptional>().toEqualTypeOf<false>();
  });

  it('keeps UI MarketPhaseSummary warnings required while naive CamelizeKeys leaves them optional', () => {
    expectTypeOf(phaseMissingWarnings).not.toMatchTypeOf<MarketPhaseSummary>();
    expectTypeOf(phaseMissingWarnings).toMatchTypeOf<CamelizeKeys<OpenApiPhase>>();
    expectTypeOf({ phase: 'intraday' as const, warnings: [] }).toMatchTypeOf<MarketPhaseSummary>();
    type UiWarningsOptional = IsOptional<MarketPhaseSummary, 'warnings'>;
    type NaiveWarningsOptional = IsOptional<CamelizeKeys<OpenApiPhase>, 'warnings'>;
    expectTypeOf<UiWarningsOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveWarningsOptional>().toEqualTypeOf<true>();
  });

  it('keeps UI MarketReviewAccepted status as accepted while naive status stays string', () => {
    expectTypeOf(reviewAcceptedBase).toMatchTypeOf<MarketReviewAccepted>();
    expectTypeOf({ ...reviewAcceptedBase, status: 'queued' as const }).not.toMatchTypeOf<MarketReviewAccepted>();
    expectTypeOf(naiveReviewQueued).toMatchTypeOf<CamelizeKeys<OpenApiReviewAccepted>>();
    type PublicStatus = MarketReviewAccepted['status'];
    expectTypeOf<PublicStatus>().toEqualTypeOf<'accepted'>();
    expectTypeOf<CamelizeKeys<OpenApiReviewAccepted>['status']>().toEqualTypeOf<string>();
  });

  it('keeps parent extra keys rejected and named messageParams bag extras assignable', () => {
    type PublicRejectsExtra = { futureTaskFlag: true } extends TaskAccepted ? true : false;
    expectTypeOf<PublicRejectsExtra>().toEqualTypeOf<false>();
    expectTypeOf(publicParams).toMatchTypeOf<TaskAccepted>();
    expectTypeOf({ count: 1, futureParam: true }).toMatchTypeOf<NonNullable<TaskAccepted['messageParams']>>();
  });
});
