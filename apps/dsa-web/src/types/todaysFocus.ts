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

type OpenApiAlertEvidence = components['schemas']['TodaysFocusAlertEvidence'];
type OpenApiAnalysisEvidence = components['schemas']['TodaysFocusAnalysisEvidence'];
type OpenApiCorporateEventEvidence = components['schemas']['TodaysFocusCorporateEventEvidence'];
type OpenApiCostContract = components['schemas']['TodaysFocusCostContract'];
type OpenApiItem = components['schemas']['TodaysFocusItem'];
type OpenApiMarketDayWindow = components['schemas']['TodaysFocusMarketDayWindow'];
type OpenApiPresentationBoundary = components['schemas']['TodaysFocusPresentationBoundary'];
type OpenApiResponse = components['schemas']['TodaysFocusResponse'];
type OpenApiTemporalPolicy = components['schemas']['TodaysFocusTemporalPolicy'];
type OpenApiUniverseContract = components['schemas']['TodaysFocusUniverseContract'];
type OpenApiGet200 =
  operations['getTodaysFocus']['responses']['200']['content']['application/json'];
type OpenApiGetOp = operations['getTodaysFocus'];
type OpenApiPathGet = paths['/api/v1/focus/today']['get'];
type OpenApiGetQuery = NonNullable<operations['getTodaysFocus']['parameters']['query']>;

type _Assert<T extends true> = T;
type _Get200IsResponse = _Assert<OpenApiGet200 extends OpenApiResponse ? true : false>;
type _ResponseIsGet200 = _Assert<OpenApiResponse extends OpenApiGet200 ? true : false>;
type _GetOpIsPath = _Assert<OpenApiGetOp extends OpenApiPathGet ? true : false>;
type _PathIsGetOp = _Assert<OpenApiPathGet extends OpenApiGetOp ? true : false>;
type _GetOpHasNeverRequestBody = _Assert<OpenApiGetOp extends { requestBody?: never } ? true : false>;
type _PathPostNever = _Assert<
  paths['/api/v1/focus/today']['post'] extends never | undefined ? true : false
>;
type _GetQueryHasMaxItemsSnake = _Assert<'max_items' extends keyof OpenApiGetQuery ? true : false>;
type _GetQueryHasAccountIdSnake = _Assert<'account_id' extends keyof OpenApiGetQuery ? true : false>;
type _GetQueryHasLanguageSnake = _Assert<'language' extends keyof OpenApiGetQuery ? true : false>;
type _GetQueryAllowsNullAccount = _Assert<null extends OpenApiGetQuery['account_id'] ? true : false>;
type _GetQueryAllowsNullLanguage = _Assert<null extends OpenApiGetQuery['language'] ? true : false>;
type _GetQueryLacksMaxItemsCamel = _Assert<'maxItems' extends keyof OpenApiGetQuery ? false : true>;

type _OpenApiAnchors = [
  _Get200IsResponse,
  _ResponseIsGet200,
  _GetOpIsPath,
  _PathIsGetOp,
  _GetOpHasNeverRequestBody,
  _PathPostNever,
  _GetQueryHasMaxItemsSnake,
  _GetQueryHasAccountIdSnake,
  _GetQueryHasLanguageSnake,
  _GetQueryAllowsNullAccount,
  _GetQueryAllowsNullLanguage,
  _GetQueryLacksMaxItemsCamel,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type TodaysFocusReasonCode = OpenApiItem['reason_code'];

export type TodaysFocusAlertEvidence = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiAlertEvidence>, {
  type: OpenApiAlertEvidence['type'];
  triggerId: number;
  ruleId: number | null;
  observedAt: string;
  status: OpenApiAlertEvidence['status'];
  source?: string | null;
}>>;

export type TodaysFocusAnalysisEvidence = Override<CamelizeKeys<OpenApiAnalysisEvidence>, {
  type: OpenApiAnalysisEvidence['type'];
  recordId: number;
  queryId: string | null;
  observedAt: string;
  previousObservedAt: string;
  previousAction: OpenApiAnalysisEvidence['previous_action'];
  latestAction: OpenApiAnalysisEvidence['latest_action'];
}>;

export type TodaysFocusCorporateEventEvidence = Override<CamelizeKeys<OpenApiCorporateEventEvidence>, {
  type: OpenApiCorporateEventEvidence['type'];
  eventId: string;
  observedAt: string;
  href: string;
}>;

export type TodaysFocusEvidence =
  | TodaysFocusAlertEvidence
  | TodaysFocusAnalysisEvidence
  | TodaysFocusCorporateEventEvidence;

export type TodaysFocusItem = Override<CamelizeKeys<OpenApiItem>, {
  code: string;
  name: string;
  reasonCode: TodaysFocusReasonCode;
  reasonDisplay: string;
  priority: number;
  weightPct: number | null;
  secondaryReasonCodes: TodaysFocusReasonCode[];
  evidence: TodaysFocusEvidence;
}>;

export type TodaysFocusCostContract = Override<CamelizeKeys<OpenApiCostContract>, {
  alertRepositoryCalls: number;
  portfolioRepositoryCalls: number;
  analysisHistoryRepositoryCalls: number;
  eventRepositoryCalls: number;
  databaseWrites: 0;
  providerCalls: 0;
  analysisRunsTriggered: 0;
  zeroExtraFetch: true;
  readOnly: true;
}>;

export type TodaysFocusMarketDayWindow = Override<CamelizeKeys<OpenApiMarketDayWindow>, {
  market: OpenApiMarketDayWindow['market'];
  timezone: string;
  localDate: string;
  windowStart: string;
  windowEnd: string;
  isTradingDay: boolean | null;
}>;

type TodaysFocusPresentationBoundary = Override<CamelizeKeys<OpenApiPresentationBoundary>, {
  alertsOwnedBy: OpenApiPresentationBoundary['alerts_owned_by'];
  focusShows: OpenApiPresentationBoundary['focus_shows'];
  duplicateAlertUi: false;
}>;

type TodaysFocusUniverseContract = Override<CamelizeKeys<OpenApiUniverseContract>, {
  symbolCount: number;
  hardCap: 1000;
  truncated: boolean;
  sources: OpenApiUniverseContract['sources'];
  excludedNonFinitePositions: number;
  dataNotes: string[];
}>;

export type TodaysFocusTemporalPolicy = Override<CamelizeKeys<OpenApiTemporalPolicy>, {
  semantics: OpenApiTemporalPolicy['semantics'];
  crossMarketRule: OpenApiTemporalPolicy['cross_market_rule'];
  fallbackTimezone: string;
  windowEnd: string;
  naiveTimestampPolicy: OpenApiTemporalPolicy['naive_timestamp_policy'];
  missingTimestampPolicy: OpenApiTemporalPolicy['missing_timestamp_policy'];
  nonTradingDayPolicy: OpenApiTemporalPolicy['non_trading_day_policy'];
  markets: TodaysFocusMarketDayWindow[];
}>;

export type TodaysFocusResponse = Override<CamelizeKeys<OpenApiResponse>, {
  packVersion: 'todays_focus/2.1';
  generatedAt: string;
  status: OpenApiResponse['status'];
  maxItems: number;
  itemCount: number;
  items: TodaysFocusItem[];
  emptyReason: NonNullable<OpenApiResponse['empty_reason']> | null;
  emptyMessage: string | null;
  sourcesUsed: OpenApiResponse['sources_used'];
  degradedSources: OpenApiResponse['degraded_sources'];
  temporalPolicy: TodaysFocusTemporalPolicy;
  universeContract: TodaysFocusUniverseContract;
  costContract: TodaysFocusCostContract;
  presentationBoundary: TodaysFocusPresentationBoundary;
}>;

export type TodaysFocusQuery = {
  maxItems?: number;
  accountId?: number;
  language?: string;
};
