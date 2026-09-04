// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as Usage from '../usage';
import type {
  UsageAgentModeBreakdown,
  UsageCallRecord,
  UsageCallTypeBreakdown,
  UsageDashboard,
  UsageModelBreakdown,
  UsagePeriod,
  UsageStageBreakdown,
} from '../usage';
import type * as ApiUsage from '../../api/usage';

type OpenApiDashboard = components['schemas']['UsageDashboardResponse'];
type OpenApiCallRecord = components['schemas']['UsageCallRecord'];
type OpenApiCallType = components['schemas']['CallTypeBreakdown'];
type OpenApiModel = components['schemas']['ModelBreakdown'];
type OpenApiStage = components['schemas']['StageBreakdown'];
type OpenApiAgentMode = components['schemas']['AgentModeBreakdown'];
type OpenApiSummary = components['schemas']['UsageSummaryResponse'];
type OpenApiGetOp = operations['get_usage_dashboard_api_v1_usage_dashboard_get'];
type OpenApiGet200 = OpenApiGetOp['responses']['200']['content']['application/json'];
type OpenApiPathGet = paths['/api/v1/usage/dashboard']['get'];
type OpenApiGetQuery = NonNullable<OpenApiGetOp['parameters']['query']>;
type OpenApiSummaryGetOp = operations['get_usage_summary_api_v1_usage_summary_get'];
type OpenApiSummary200 = OpenApiSummaryGetOp['responses']['200']['content']['application/json'];
type UsageApi = typeof import('../../api/usage')['usageApi'];

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

type _SixComponents = _Assert<
  (
    | 'UsageDashboardResponse'
    | 'UsageCallRecord'
    | 'CallTypeBreakdown'
    | 'ModelBreakdown'
    | 'StageBreakdown'
    | 'AgentModeBreakdown'
  ) extends keyof components['schemas'] ? true : false
>;
type _SummaryExists = _Assert<'UsageSummaryResponse' extends keyof components['schemas'] ? true : false>;
type _SummaryNotImported = _Assert<
  'UsageSummaryResponse' extends keyof typeof import('../usage') ? false : true
>;
type _Get200IsDashboard = _Assert<OpenApiGet200 extends OpenApiDashboard ? true : false>;
type _DashboardIsGet200 = _Assert<OpenApiDashboard extends OpenApiGet200 ? true : false>;
type _GetOpIsPath = _Assert<OpenApiGetOp extends OpenApiPathGet ? true : false>;
type _PathIsGetOp = _Assert<OpenApiPathGet extends OpenApiGetOp ? true : false>;
type _GetOpHasNeverRequestBody = _Assert<OpenApiGetOp extends { requestBody?: never } ? true : false>;
type _PathPostNever = _Assert<
  paths['/api/v1/usage/dashboard']['post'] extends never | undefined ? true : false
>;
type _PathPutNever = _Assert<
  paths['/api/v1/usage/dashboard']['put'] extends never | undefined ? true : false
>;
type _PathDeleteNever = _Assert<
  paths['/api/v1/usage/dashboard']['delete'] extends never | undefined ? true : false
>;
type _PathPatchNever = _Assert<
  paths['/api/v1/usage/dashboard']['patch'] extends never | undefined ? true : false
>;
type _SummaryPathExists = _Assert<
  paths['/api/v1/usage/summary']['get'] extends OpenApiSummaryGetOp ? true : false
>;
type _Summary200IsComponent = _Assert<OpenApiSummary200 extends OpenApiSummary ? true : false>;
type _SummaryIs200 = _Assert<OpenApiSummary extends OpenApiSummary200 ? true : false>;

type _QueryHasPeriod = _Assert<'period' extends keyof OpenApiGetQuery ? true : false>;
type _QueryHasLimit = _Assert<'limit' extends keyof OpenApiGetQuery ? true : false>;
type _QueryLacksPathKeys = _Assert<'stock_code' extends keyof OpenApiGetQuery ? false : true>;
type _QueryPeriodIsString = _Assert<string extends NonNullable<OpenApiGetQuery['period']> ? true : false>;
type _QueryPeriodNotUnion = _Assert<string extends UsagePeriod ? false : true>;
type _QueryLimitIsNumber = _Assert<number extends NonNullable<OpenApiGetQuery['limit']> ? true : false>;
type _QueryPeriodNotNull = _Assert<null extends OpenApiGetQuery['period'] ? false : true>;
type _QueryLimitNotNull = _Assert<null extends OpenApiGetQuery['limit'] ? false : true>;

type _UiHasFromDate = _Assert<'fromDate' extends keyof UsageDashboard ? true : false>;
type _UiHasCalledAt = _Assert<'calledAt' extends keyof UsageCallRecord ? true : false>;
type _UiHasByCallType = _Assert<'byCallType' extends keyof UsageDashboard ? true : false>;
type _UiHasByStage = _Assert<'byStage' extends keyof UsageDashboard ? true : false>;
type _UiHasByAgentMode = _Assert<'byAgentMode' extends keyof UsageDashboard ? true : false>;
type _UiHasRecentCalls = _Assert<'recentCalls' extends keyof UsageDashboard ? true : false>;
type _UiHasAvgLatencyMs = _Assert<'avgLatencyMs' extends keyof UsageStageBreakdown ? true : false>;
type _UiHasSuccessCalls = _Assert<'successCalls' extends keyof UsageStageBreakdown ? true : false>;
type _UiHasAgentMode = _Assert<'agentMode' extends keyof UsageAgentModeBreakdown ? true : false>;
type _UiLacksFromDateSnake = _Assert<'from_date' extends keyof UsageDashboard ? false : true>;
type _UiLacksCalledAtSnake = _Assert<'called_at' extends keyof UsageCallRecord ? false : true>;
type _UiLacksByCallTypeSnake = _Assert<'by_call_type' extends keyof UsageDashboard ? false : true>;
type _UiLacksByStageSnake = _Assert<'by_stage' extends keyof UsageDashboard ? false : true>;
type _UiLacksByAgentModeSnake = _Assert<'by_agent_mode' extends keyof UsageDashboard ? false : true>;
type _UiLacksRecentCallsSnake = _Assert<'recent_calls' extends keyof UsageDashboard ? false : true>;
type _UiLacksAvgLatencySnake = _Assert<'avg_latency_ms' extends keyof UsageStageBreakdown ? false : true>;
type _UiLacksSuccessCallsSnake = _Assert<'success_calls' extends keyof UsageStageBreakdown ? false : true>;
type _UiLacksAgentModeSnake = _Assert<'agent_mode' extends keyof UsageAgentModeBreakdown ? false : true>;
type _GeneratedHasFromDateSnake = _Assert<'from_date' extends keyof OpenApiDashboard ? true : false>;
type _GeneratedHasCalledAtSnake = _Assert<'called_at' extends keyof OpenApiCallRecord ? true : false>;
type _GeneratedHasByCallTypeSnake = _Assert<'by_call_type' extends keyof OpenApiDashboard ? true : false>;
type _GeneratedHasByStageSnake = _Assert<'by_stage' extends keyof OpenApiDashboard ? true : false>;
type _GeneratedHasByAgentModeSnake = _Assert<'by_agent_mode' extends keyof OpenApiDashboard ? true : false>;
type _GeneratedHasRecentCallsSnake = _Assert<'recent_calls' extends keyof OpenApiDashboard ? true : false>;
type _GeneratedHasAvgLatencySnake = _Assert<'avg_latency_ms' extends keyof OpenApiStage ? true : false>;
type _GeneratedHasSuccessCallsSnake = _Assert<'success_calls' extends keyof OpenApiStage ? true : false>;
type _GeneratedHasAgentModeSnake = _Assert<'agent_mode' extends keyof OpenApiAgentMode ? true : false>;
type _GeneratedLacksFromDateCamel = _Assert<'fromDate' extends keyof OpenApiDashboard ? false : true>;
type _GeneratedLacksCalledAtCamel = _Assert<'calledAt' extends keyof OpenApiCallRecord ? false : true>;

type _UiPricedOptional = _Assert<IsOptional<UsageDashboard, 'pricedCalls'>>;
type _GeneratedPricedRequired = _Assert<
  IsOptional<OpenApiDashboard, 'priced_calls'> extends false ? true : false
>;
type _UiUnpricedOptional = _Assert<IsOptional<UsageDashboard, 'unpricedCalls'>>;
type _GeneratedUnpricedRequired = _Assert<
  IsOptional<OpenApiDashboard, 'unpriced_calls'> extends false ? true : false
>;
type _UiRoutingPrimaryOptional = _Assert<IsOptional<UsageDashboard, 'routingPrimarySuccess'>>;
type _GeneratedRoutingPrimaryRequired = _Assert<
  IsOptional<OpenApiDashboard, 'routing_primary_success'> extends false ? true : false
>;
type _UiRoutingFallbackOptional = _Assert<IsOptional<UsageDashboard, 'routingFallbackSuccess'>>;
type _GeneratedRoutingFallbackRequired = _Assert<
  IsOptional<OpenApiDashboard, 'routing_fallback_success'> extends false ? true : false
>;
type _UiRoutingFailedOptional = _Assert<IsOptional<UsageDashboard, 'routingFailed'>>;
type _GeneratedRoutingFailedRequired = _Assert<
  IsOptional<OpenApiDashboard, 'routing_failed'> extends false ? true : false
>;
type _UiTotalPromptOptional = _Assert<IsOptional<UsageDashboard, 'totalPromptTokens'>>;
type _GeneratedTotalPromptRequired = _Assert<
  IsOptional<OpenApiDashboard, 'total_prompt_tokens'> extends false ? true : false
>;
type _UiTotalCompletionOptional = _Assert<IsOptional<UsageDashboard, 'totalCompletionTokens'>>;
type _GeneratedTotalCompletionRequired = _Assert<
  IsOptional<OpenApiDashboard, 'total_completion_tokens'> extends false ? true : false
>;

type _PublicDoesNotExtendNaiveDashboard = _Assert<
  UsageDashboard extends CamelizeKeys<OpenApiDashboard> ? false : true
>;
type _PublicDoesNotExtendNaiveStage = _Assert<
  UsageStageBreakdown extends CamelizeKeys<OpenApiStage> ? false : true
>;
type _PublicDoesNotExtendNaiveAgentMode = _Assert<
  UsageAgentModeBreakdown extends CamelizeKeys<OpenApiAgentMode> ? false : true
>;

type _UiStageAvgOptional = _Assert<IsOptional<UsageStageBreakdown, 'avgLatencyMs'>>;
type _GeneratedStageAvgRequired = _Assert<
  IsOptional<OpenApiStage, 'avg_latency_ms'> extends false ? true : false
>;
type _UiStageSuccessOptional = _Assert<IsOptional<UsageStageBreakdown, 'successCalls'>>;
type _GeneratedStageSuccessRequired = _Assert<
  IsOptional<OpenApiStage, 'success_calls'> extends false ? true : false
>;
type _UiStagePromptOptional = _Assert<IsOptional<UsageStageBreakdown, 'promptTokens'>>;
type _GeneratedStagePromptRequired = _Assert<
  IsOptional<OpenApiStage, 'prompt_tokens'> extends false ? true : false
>;

type _StageKeepsAvgLatency = _Assert<'avgLatencyMs' extends keyof UsageStageBreakdown ? true : false>;
type _StageKeepsSuccessCalls = _Assert<'successCalls' extends keyof UsageStageBreakdown ? true : false>;
type _StageKeepsEstimatedCost = _Assert<'estimatedCostUsd' extends keyof UsageStageBreakdown ? true : false>;
type _AgentModeKeepsPrompt = _Assert<'promptTokens' extends keyof UsageAgentModeBreakdown ? true : false>;
type _CallTypeKeepsEstimatedCost = _Assert<'estimatedCostUsd' extends keyof UsageCallTypeBreakdown ? true : false>;
type _GeneratedCallTypeHasCost = _Assert<'estimated_cost_usd' extends keyof OpenApiCallType ? true : false>;
type _GeneratedModelHasCost = _Assert<'estimated_cost_usd' extends keyof OpenApiModel ? true : false>;
type _UiModelKeepsEstimatedCost = _Assert<'estimatedCostUsd' extends keyof UsageModelBreakdown ? true : false>;
type _RecordKeepsRunId = _Assert<'runId' extends keyof UsageCallRecord ? true : false>;
type _RecordKeepsCallSuccess = _Assert<'callSuccess' extends keyof UsageCallRecord ? true : false>;

type NarrowStage = { stage: string; calls: number; totalTokens: number };
type _NarrowStageAssignable = _Assert<NarrowStage extends UsageStageBreakdown ? true : false>;
type _NarrowStageAssignableInDashboard = _Assert<
  NarrowStage extends NonNullable<UsageDashboard['byStage']>[number] ? true : false
>;
type NarrowAgentMode = { agentMode: string; calls: number; totalTokens: number };
type _NarrowAgentModeAssignable = _Assert<NarrowAgentMode extends UsageAgentModeBreakdown ? true : false>;

type ConsumerFixture = {
  period: UsagePeriod;
  fromDate: string;
  toDate: string;
  totalCalls: number;
  totalPromptTokens: number;
  totalCompletionTokens: number;
  totalTokens: number;
  byCallType: [];
  byModel: [];
  recentCalls: [];
};
type _ConsumerAssignable = _Assert<ConsumerFixture extends UsageDashboard ? true : false>;
type MissingFromDate = Omit<ConsumerFixture, 'fromDate'>;
type _MissingFromDateRejected = _Assert<MissingFromDate extends UsageDashboard ? false : true>;
type _OmitPricedNotNaive = _Assert<
  Omit<CamelizeKeys<OpenApiDashboard>, 'pricedCalls'> extends CamelizeKeys<OpenApiDashboard>
    ? false
    : true
>;
type _ConsumerNotNaive = _Assert<
  ConsumerFixture extends CamelizeKeys<OpenApiDashboard> ? false : true
>;

type SnakeDashboard = {
  period: string;
  from_date: string;
  to_date: string;
  total_calls: number;
  total_tokens: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  priced_calls: number;
  unpriced_calls: number;
  routing_primary_success: number;
  routing_fallback_success: number;
  routing_failed: number;
  by_call_type: [];
  by_model: [];
  recent_calls: [];
};
type _SnakeMatchesGenerated = _Assert<SnakeDashboard extends OpenApiDashboard ? true : false>;
type _SnakeDoesNotMatchUi = _Assert<SnakeDashboard extends UsageDashboard ? false : true>;

type _PeriodUnion = _Assert<UsagePeriod extends 'today' | 'month' | 'all'
  ? 'today' | 'month' | 'all' extends UsagePeriod ? true : false
  : false>;
type _StringDoesNotExtendPeriod = _Assert<string extends UsagePeriod ? false : true>;
type _DashboardPeriodAcceptsString = _Assert<string extends UsageDashboard['period'] ? true : false>;
type _WeeklyRejected = _Assert<'weekly' extends UsagePeriod ? false : true>;

type DashboardParams = Parameters<UsageApi['getDashboard']>[0];
type ExpectedParams = { period?: UsagePeriod; limit?: number };
type _ParamsEqual = _Assert<
  NonNullable<DashboardParams> extends ExpectedParams
    ? ExpectedParams extends NonNullable<DashboardParams> ? true : false
    : false
>;

type _CompileTimePins = [
  _SixComponents, _SummaryExists, _SummaryNotImported, _Get200IsDashboard, _DashboardIsGet200,
  _GetOpIsPath, _PathIsGetOp, _GetOpHasNeverRequestBody, _PathPostNever, _PathPutNever,
  _PathDeleteNever, _PathPatchNever, _SummaryPathExists, _Summary200IsComponent, _SummaryIs200,
  _QueryHasPeriod, _QueryHasLimit, _QueryLacksPathKeys, _QueryPeriodIsString, _QueryPeriodNotUnion,
  _QueryLimitIsNumber, _QueryPeriodNotNull, _QueryLimitNotNull, _UiHasFromDate, _UiHasCalledAt,
  _UiHasByCallType, _UiHasByStage, _UiHasByAgentMode, _UiHasRecentCalls, _UiHasAvgLatencyMs,
  _UiHasSuccessCalls, _UiHasAgentMode, _UiLacksFromDateSnake, _UiLacksCalledAtSnake,
  _UiLacksByCallTypeSnake, _UiLacksByStageSnake, _UiLacksByAgentModeSnake, _UiLacksRecentCallsSnake,
  _UiLacksAvgLatencySnake, _UiLacksSuccessCallsSnake, _UiLacksAgentModeSnake,
  _GeneratedHasFromDateSnake, _GeneratedHasCalledAtSnake, _GeneratedHasByCallTypeSnake,
  _GeneratedHasByStageSnake, _GeneratedHasByAgentModeSnake, _GeneratedHasRecentCallsSnake,
  _GeneratedHasAvgLatencySnake, _GeneratedHasSuccessCallsSnake, _GeneratedHasAgentModeSnake,
  _GeneratedLacksFromDateCamel, _GeneratedLacksCalledAtCamel, _UiPricedOptional,
  _GeneratedPricedRequired, _UiUnpricedOptional, _GeneratedUnpricedRequired,
  _UiRoutingPrimaryOptional, _GeneratedRoutingPrimaryRequired, _UiRoutingFallbackOptional,
  _GeneratedRoutingFallbackRequired, _UiRoutingFailedOptional, _GeneratedRoutingFailedRequired,
  _UiTotalPromptOptional, _GeneratedTotalPromptRequired, _UiTotalCompletionOptional,
  _GeneratedTotalCompletionRequired, _PublicDoesNotExtendNaiveDashboard,
  _PublicDoesNotExtendNaiveStage, _PublicDoesNotExtendNaiveAgentMode, _UiStageAvgOptional,
  _GeneratedStageAvgRequired, _UiStageSuccessOptional, _GeneratedStageSuccessRequired,
  _UiStagePromptOptional, _GeneratedStagePromptRequired, _StageKeepsAvgLatency,
  _StageKeepsSuccessCalls, _StageKeepsEstimatedCost, _AgentModeKeepsPrompt,
  _CallTypeKeepsEstimatedCost, _GeneratedCallTypeHasCost, _GeneratedModelHasCost,
  _UiModelKeepsEstimatedCost, _RecordKeepsRunId, _RecordKeepsCallSuccess, _NarrowStageAssignable,
  _NarrowStageAssignableInDashboard, _NarrowAgentModeAssignable, _ConsumerAssignable,
  _MissingFromDateRejected, _OmitPricedNotNaive, _ConsumerNotNaive, _SnakeMatchesGenerated,
  _SnakeDoesNotMatchUi, _PeriodUnion, _StringDoesNotExtendPeriod, _DashboardPeriodAcceptsString,
  _WeeklyRejected, _ParamsEqual,
];

describe('usage OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    expect({ ...Usage }).toEqual({});
    expect(Object.keys(Usage)).toEqual([]);
    expect(Object.getOwnPropertyNames(Usage)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('re-exports the public stage and agent-mode names from api/usage', () => {
    expectTypeOf<ApiUsage.UsageStageBreakdown>().toEqualTypeOf<UsageStageBreakdown>();
    expectTypeOf<ApiUsage.UsageAgentModeBreakdown>().toEqualTypeOf<UsageAgentModeBreakdown>();
    expectTypeOf<ApiUsage.UsageDashboard>().toEqualTypeOf<UsageDashboard>();
    expectTypeOf<ApiUsage.UsageCallRecord>().toEqualTypeOf<UsageCallRecord>();
    expectTypeOf<ApiUsage.UsageCallTypeBreakdown>().toEqualTypeOf<UsageCallTypeBreakdown>();
    expectTypeOf<ApiUsage.UsageModelBreakdown>().toEqualTypeOf<UsageModelBreakdown>();
    expectTypeOf<ApiUsage.UsagePeriod>().toEqualTypeOf<UsagePeriod>();
  });

  it('equates GET 200 JSON to UsageDashboardResponse and GET op to the path', () => {
    expectTypeOf<OpenApiGet200>().toEqualTypeOf<OpenApiDashboard>();
    expectTypeOf<OpenApiGetOp>().toEqualTypeOf<OpenApiPathGet>();
    type HasNeverBody = OpenApiGetOp extends { requestBody?: never } ? true : false;
    expectTypeOf<HasNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<OpenApiSummary200>().toEqualTypeOf<OpenApiSummary>();
  });

  it('keeps GET requestBody never and non-GET dashboard methods never', () => {
    type PostNever = paths['/api/v1/usage/dashboard']['post'] extends never | undefined ? true : false;
    type PutNever = paths['/api/v1/usage/dashboard']['put'] extends never | undefined ? true : false;
    type DeleteNever = paths['/api/v1/usage/dashboard']['delete'] extends never | undefined ? true : false;
    type PatchNever = paths['/api/v1/usage/dashboard']['patch'] extends never | undefined ? true : false;
    expectTypeOf<PostNever>().toEqualTypeOf<true>();
    expectTypeOf<PutNever>().toEqualTypeOf<true>();
    expectTypeOf<DeleteNever>().toEqualTypeOf<true>();
    expectTypeOf<PatchNever>().toEqualTypeOf<true>();
  });

  it('keeps generated query period/limit as non-null string/number, not UsagePeriod', () => {
    expectTypeOf<NonNullable<OpenApiGetQuery['period']>>().toEqualTypeOf<string>();
    expectTypeOf<NonNullable<OpenApiGetQuery['limit']>>().toEqualTypeOf<number>();
    expectTypeOf<string>().not.toMatchTypeOf<UsagePeriod>();
    expectTypeOf<null>().not.toMatchTypeOf<OpenApiGetQuery['period']>();
    expectTypeOf<null>().not.toMatchTypeOf<OpenApiGetQuery['limit']>();
    expectTypeOf<UsagePeriod>().toEqualTypeOf<'today' | 'month' | 'all'>();
    expectTypeOf<'weekly'>().not.toMatchTypeOf<UsagePeriod>();
    expectTypeOf<string>().toMatchTypeOf<UsageDashboard['period']>();
  });

  it('keeps defaulted generated counters optional on the public types', () => {
    expectTypeOf<Omit<UsageDashboard, 'pricedCalls'>>().toMatchTypeOf<UsageDashboard>();
    expectTypeOf<Omit<CamelizeKeys<OpenApiDashboard>, 'pricedCalls'>>().not.toMatchTypeOf<
      CamelizeKeys<OpenApiDashboard>
    >();
    expectTypeOf<UsageDashboard>().not.toMatchTypeOf<CamelizeKeys<OpenApiDashboard>>();
    expectTypeOf<UsageStageBreakdown>().not.toMatchTypeOf<CamelizeKeys<OpenApiStage>>();
    expectTypeOf<UsageAgentModeBreakdown>().not.toMatchTypeOf<CamelizeKeys<OpenApiAgentMode>>();
    expectTypeOf<UsageDashboard>().not.toEqualTypeOf<components['schemas']['UsageDashboardResponse']>();
    expectTypeOf<UsageCallRecord>().not.toEqualTypeOf<components['schemas']['UsageCallRecord']>();
  });

  it('keeps extra generated keys on stage, agent-mode, call-type, and record types', () => {
    expectTypeOf<'avgLatencyMs' | 'successCalls' | 'estimatedCostUsd'>().toMatchTypeOf<
      keyof UsageStageBreakdown
    >();
    const narrowStage: UsageStageBreakdown = { stage: 'analysis', calls: 1, totalTokens: 10 };
    const narrowAgent: UsageAgentModeBreakdown = { agentMode: 'ask', calls: 1, totalTokens: 10 };
    expectTypeOf(narrowStage).toMatchTypeOf<UsageStageBreakdown>();
    expectTypeOf(narrowStage).toMatchTypeOf<NonNullable<UsageDashboard['byStage']>[number]>();
    expectTypeOf(narrowAgent).toMatchTypeOf<UsageAgentModeBreakdown>();
    expectTypeOf<'runId'>().toMatchTypeOf<keyof UsageCallRecord>();
    expectTypeOf<'callSuccess'>().toMatchTypeOf<keyof UsageCallRecord>();
    expectTypeOf<'estimatedCostUsd'>().toMatchTypeOf<keyof UsageCallTypeBreakdown>();
    expectTypeOf<'promptTokens'>().toMatchTypeOf<keyof UsageAgentModeBreakdown>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof UsageDashboard>().not.toMatchTypeOf<
      'from_date' | 'by_call_type' | 'by_stage' | 'by_agent_mode' | 'recent_calls'
    >();
    expectTypeOf<keyof UsageCallRecord>().not.toMatchTypeOf<'called_at'>();
    expectTypeOf<keyof OpenApiDashboard>().not.toMatchTypeOf<'fromDate' | 'byCallType' | 'recentCalls'>();
    const snake = {
      period: 'month',
      from_date: '2026-06-01',
      to_date: '2026-06-11',
      total_calls: 0,
      total_tokens: 0,
      total_prompt_tokens: 0,
      total_completion_tokens: 0,
      priced_calls: 0,
      unpriced_calls: 0,
      routing_primary_success: 0,
      routing_fallback_success: 0,
      routing_failed: 0,
      by_call_type: [] as [],
      by_model: [] as [],
      recent_calls: [] as [],
    };
    expectTypeOf(snake).toMatchTypeOf<OpenApiDashboard>();
    expectTypeOf(snake).not.toMatchTypeOf<UsageDashboard>();
  });

  it('accepts the useTokenUsageQuery payload fixture and rejects a missing fromDate', () => {
    const fixture: UsageDashboard = {
      period: 'month',
      fromDate: '2026-06-01',
      toDate: '2026-06-11',
      totalCalls: 3,
      totalPromptTokens: 120,
      totalCompletionTokens: 280,
      totalTokens: 400,
      byCallType: [],
      byModel: [],
      recentCalls: [],
    };
    expectTypeOf(fixture).toMatchTypeOf<UsageDashboard>();
    expectTypeOf(fixture).not.toMatchTypeOf<CamelizeKeys<OpenApiDashboard>>();
  });

  it('keeps getDashboard params handwritten and un-camelized', () => {
    expectTypeOf<NonNullable<Parameters<UsageApi['getDashboard']>[0]>>().toEqualTypeOf<{
      period?: UsagePeriod;
      limit?: number;
    }>();
  });
});
