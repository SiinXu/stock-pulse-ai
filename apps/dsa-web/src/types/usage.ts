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

type Override<T, U> = Omit<T, keyof U> & U;

type OpenApiUsageDashboard = components['schemas']['UsageDashboardResponse'];
type OpenApiUsageCallRecord = components['schemas']['UsageCallRecord'];
type OpenApiCallTypeBreakdown = components['schemas']['CallTypeBreakdown'];
type OpenApiModelBreakdown = components['schemas']['ModelBreakdown'];
type OpenApiStageBreakdown = components['schemas']['StageBreakdown'];
type OpenApiAgentModeBreakdown = components['schemas']['AgentModeBreakdown'];
type OpenApiGetOp = operations['get_usage_dashboard_api_v1_usage_dashboard_get'];
type OpenApiPathGet = paths['/api/v1/usage/dashboard']['get'];
type OpenApiGet200 = OpenApiGetOp['responses']['200']['content']['application/json'];
type OpenApiGetQuery = NonNullable<OpenApiGetOp['parameters']['query']>;

type _Assert<T extends true> = T;
type _Get200IsComponent = _Assert<OpenApiGet200 extends OpenApiUsageDashboard ? true : false>;
type _ComponentIsGet200 = _Assert<OpenApiUsageDashboard extends OpenApiGet200 ? true : false>;
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
type _GetQueryHasPeriod = _Assert<'period' extends keyof OpenApiGetQuery ? true : false>;
type _GetQueryHasLimit = _Assert<'limit' extends keyof OpenApiGetQuery ? true : false>;
type _GetQueryPeriodIsString = _Assert<
  string extends NonNullable<OpenApiGetQuery['period']> ? true : false
>;
type _GetQueryLimitIsNumber = _Assert<
  number extends NonNullable<OpenApiGetQuery['limit']> ? true : false
>;
type _GetQueryPeriodNotNull = _Assert<null extends OpenApiGetQuery['period'] ? false : true>;
type _GetQueryLimitNotNull = _Assert<null extends OpenApiGetQuery['limit'] ? false : true>;
type _GetQueryLacksPathKeys = _Assert<'stock_code' extends keyof OpenApiGetQuery ? false : true>;

type _OpenApiAnchors = [
  _Get200IsComponent,
  _ComponentIsGet200,
  _GetOpIsPath,
  _PathIsGetOp,
  _GetOpHasNeverRequestBody,
  _PathPostNever,
  _PathPutNever,
  _PathDeleteNever,
  _PathPatchNever,
  _GetQueryHasPeriod,
  _GetQueryHasLimit,
  _GetQueryPeriodIsString,
  _GetQueryLimitIsNumber,
  _GetQueryPeriodNotNull,
  _GetQueryLimitNotNull,
  _GetQueryLacksPathKeys,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type UsagePeriod = 'today' | 'month' | 'all';

export type UsageCallTypeBreakdown = Override<CamelizeKeys<OpenApiCallTypeBreakdown>, {
  promptTokens?: number;
  completionTokens?: number;
}>;

export type UsageModelBreakdown = Override<CamelizeKeys<OpenApiModelBreakdown>, {
  promptTokens?: number;
  completionTokens?: number;
  maxTotalTokens?: number;
}>;

export type UsageStageBreakdown = Override<CamelizeKeys<OpenApiStageBreakdown>, {
  promptTokens?: number;
  completionTokens?: number;
  successCalls?: number;
  avgLatencyMs?: number;
}>;

export type UsageAgentModeBreakdown = Override<CamelizeKeys<OpenApiAgentModeBreakdown>, {
  promptTokens?: number;
  completionTokens?: number;
}>;

export type UsageCallRecord = CamelizeKeys<OpenApiUsageCallRecord>;

export type UsageDashboard = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiUsageDashboard>, {
  period: UsagePeriod | string;
  totalPromptTokens?: number;
  totalCompletionTokens?: number;
  pricedCalls?: number;
  unpricedCalls?: number;
  routingPrimarySuccess?: number;
  routingFallbackSuccess?: number;
  routingFailed?: number;
  byCallType: UsageCallTypeBreakdown[];
  byModel: UsageModelBreakdown[];
  byStage?: UsageStageBreakdown[];
  byAgentMode?: UsageAgentModeBreakdown[];
  recentCalls: UsageCallRecord[];
}>>;
