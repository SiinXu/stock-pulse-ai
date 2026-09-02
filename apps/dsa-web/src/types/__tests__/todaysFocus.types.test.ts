// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as TodaysFocus from '../todaysFocus';
import type {
  TodaysFocusAlertEvidence,
  TodaysFocusAnalysisEvidence,
  TodaysFocusCorporateEventEvidence,
  TodaysFocusCostContract,
  TodaysFocusEvidence,
  TodaysFocusItem,
  TodaysFocusMarketDayWindow,
  TodaysFocusQuery,
  TodaysFocusReasonCode,
  TodaysFocusResponse,
  TodaysFocusTemporalPolicy,
} from '../todaysFocus';

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

type _TenGeneratedComponents = _Assert<
  'TodaysFocusAlertEvidence' extends keyof components['schemas'] ? true : false
>;
type _HasAnalysisEvidence = _Assert<
  'TodaysFocusAnalysisEvidence' extends keyof components['schemas'] ? true : false
>;
type _HasCorporateEventEvidence = _Assert<
  'TodaysFocusCorporateEventEvidence' extends keyof components['schemas'] ? true : false
>;
type _HasCostContract = _Assert<
  'TodaysFocusCostContract' extends keyof components['schemas'] ? true : false
>;
type _HasItem = _Assert<'TodaysFocusItem' extends keyof components['schemas'] ? true : false>;
type _HasMarketDayWindow = _Assert<
  'TodaysFocusMarketDayWindow' extends keyof components['schemas'] ? true : false
>;
type _HasPresentationBoundary = _Assert<
  'TodaysFocusPresentationBoundary' extends keyof components['schemas'] ? true : false
>;
type _HasResponse = _Assert<'TodaysFocusResponse' extends keyof components['schemas'] ? true : false>;
type _HasTemporalPolicy = _Assert<
  'TodaysFocusTemporalPolicy' extends keyof components['schemas'] ? true : false
>;
type _HasUniverseContract = _Assert<
  'TodaysFocusUniverseContract' extends keyof components['schemas'] ? true : false
>;
type _LacksEleventhSummary = _Assert<
  'TodaysFocusSummary' extends keyof components['schemas'] ? false : true
>;

type _Get200IsResponse = _Assert<OpenApiGet200 extends OpenApiResponse ? true : false>;
type _ResponseIsGet200 = _Assert<OpenApiResponse extends OpenApiGet200 ? true : false>;
type _GetOpIsPath = _Assert<OpenApiGetOp extends OpenApiPathGet ? true : false>;
type _PathIsGetOp = _Assert<OpenApiPathGet extends OpenApiGetOp ? true : false>;
type _GetOpHasNeverRequestBody = _Assert<OpenApiGetOp extends { requestBody?: never } ? true : false>;
type _PathPostNever = _Assert<
  paths['/api/v1/focus/today']['post'] extends never | undefined ? true : false
>;

type _UiHasPackVersion = _Assert<'packVersion' extends keyof TodaysFocusResponse ? true : false>;
type _UiHasGeneratedAt = _Assert<'generatedAt' extends keyof TodaysFocusResponse ? true : false>;
type _UiHasMaxItems = _Assert<'maxItems' extends keyof TodaysFocusResponse ? true : false>;
type _UiHasItemCount = _Assert<'itemCount' extends keyof TodaysFocusResponse ? true : false>;
type _UiHasEmptyReason = _Assert<'emptyReason' extends keyof TodaysFocusResponse ? true : false>;
type _UiHasEmptyMessage = _Assert<'emptyMessage' extends keyof TodaysFocusResponse ? true : false>;
type _UiHasSourcesUsed = _Assert<'sourcesUsed' extends keyof TodaysFocusResponse ? true : false>;
type _UiHasDegradedSources = _Assert<'degradedSources' extends keyof TodaysFocusResponse ? true : false>;
type _UiHasTemporalPolicy = _Assert<'temporalPolicy' extends keyof TodaysFocusResponse ? true : false>;
type _UiHasUniverseContract = _Assert<'universeContract' extends keyof TodaysFocusResponse ? true : false>;
type _UiHasCostContract = _Assert<'costContract' extends keyof TodaysFocusResponse ? true : false>;
type _UiHasPresentationBoundary = _Assert<'presentationBoundary' extends keyof TodaysFocusResponse ? true : false>;
type _UiHasReasonCode = _Assert<'reasonCode' extends keyof TodaysFocusItem ? true : false>;
type _UiHasReasonDisplay = _Assert<'reasonDisplay' extends keyof TodaysFocusItem ? true : false>;
type _UiHasWeightPct = _Assert<'weightPct' extends keyof TodaysFocusItem ? true : false>;
type _UiHasSecondaryReasonCodes = _Assert<'secondaryReasonCodes' extends keyof TodaysFocusItem ? true : false>;
type _UiHasTriggerId = _Assert<'triggerId' extends keyof TodaysFocusAlertEvidence ? true : false>;
type _UiHasRuleId = _Assert<'ruleId' extends keyof TodaysFocusAlertEvidence ? true : false>;
type _UiHasObservedAt = _Assert<'observedAt' extends keyof TodaysFocusAlertEvidence ? true : false>;
type _UiHasRecordId = _Assert<'recordId' extends keyof TodaysFocusAnalysisEvidence ? true : false>;
type _UiHasQueryId = _Assert<'queryId' extends keyof TodaysFocusAnalysisEvidence ? true : false>;
type _UiHasPreviousObservedAt = _Assert<'previousObservedAt' extends keyof TodaysFocusAnalysisEvidence ? true : false>;
type _UiHasPreviousAction = _Assert<'previousAction' extends keyof TodaysFocusAnalysisEvidence ? true : false>;
type _UiHasLatestAction = _Assert<'latestAction' extends keyof TodaysFocusAnalysisEvidence ? true : false>;
type _UiHasEventId = _Assert<'eventId' extends keyof TodaysFocusCorporateEventEvidence ? true : false>;
type _UiHasLocalDate = _Assert<'localDate' extends keyof TodaysFocusMarketDayWindow ? true : false>;
type _UiHasWindowStart = _Assert<'windowStart' extends keyof TodaysFocusMarketDayWindow ? true : false>;
type _UiHasIsTradingDay = _Assert<'isTradingDay' extends keyof TodaysFocusMarketDayWindow ? true : false>;
type _UiHasCrossMarketRule = _Assert<'crossMarketRule' extends keyof TodaysFocusTemporalPolicy ? true : false>;
type _UiHasFallbackTimezone = _Assert<'fallbackTimezone' extends keyof TodaysFocusTemporalPolicy ? true : false>;
type _UiHasNaiveTimestampPolicy = _Assert<'naiveTimestampPolicy' extends keyof TodaysFocusTemporalPolicy ? true : false>;
type _UiHasMissingTimestampPolicy = _Assert<'missingTimestampPolicy' extends keyof TodaysFocusTemporalPolicy ? true : false>;
type _UiHasNonTradingDayPolicy = _Assert<'nonTradingDayPolicy' extends keyof TodaysFocusTemporalPolicy ? true : false>;
type _UiHasAlertRepositoryCalls = _Assert<'alertRepositoryCalls' extends keyof TodaysFocusCostContract ? true : false>;
type _UiHasZeroExtraFetch = _Assert<'zeroExtraFetch' extends keyof TodaysFocusCostContract ? true : false>;
type _UiHasReadOnly = _Assert<'readOnly' extends keyof TodaysFocusCostContract ? true : false>;
type _UiHasAlertsOwnedBy = _Assert<'alertsOwnedBy' extends keyof TodaysFocusResponse['presentationBoundary'] ? true : false>;
type _UiHasFocusShows = _Assert<'focusShows' extends keyof TodaysFocusResponse['presentationBoundary'] ? true : false>;
type _UiHasDuplicateAlertUi = _Assert<'duplicateAlertUi' extends keyof TodaysFocusResponse['presentationBoundary'] ? true : false>;
type _UiHasSymbolCount = _Assert<'symbolCount' extends keyof TodaysFocusResponse['universeContract'] ? true : false>;
type _UiHasHardCap = _Assert<'hardCap' extends keyof TodaysFocusResponse['universeContract'] ? true : false>;
type _UiHasExcludedNonFinite = _Assert<'excludedNonFinitePositions' extends keyof TodaysFocusResponse['universeContract'] ? true : false>;
type _UiHasDataNotes = _Assert<'dataNotes' extends keyof TodaysFocusResponse['universeContract'] ? true : false>;

type _UiLacksPackVersionSnake = _Assert<'pack_version' extends keyof TodaysFocusResponse ? false : true>;
type _UiLacksGeneratedAtSnake = _Assert<'generated_at' extends keyof TodaysFocusResponse ? false : true>;
type _UiLacksMaxItemsSnake = _Assert<'max_items' extends keyof TodaysFocusResponse ? false : true>;
type _UiLacksItemCountSnake = _Assert<'item_count' extends keyof TodaysFocusResponse ? false : true>;
type _UiLacksEmptyReasonSnake = _Assert<'empty_reason' extends keyof TodaysFocusResponse ? false : true>;
type _UiLacksEmptyMessageSnake = _Assert<'empty_message' extends keyof TodaysFocusResponse ? false : true>;
type _UiLacksSourcesUsedSnake = _Assert<'sources_used' extends keyof TodaysFocusResponse ? false : true>;
type _UiLacksDegradedSourcesSnake = _Assert<'degraded_sources' extends keyof TodaysFocusResponse ? false : true>;
type _UiLacksTemporalPolicySnake = _Assert<'temporal_policy' extends keyof TodaysFocusResponse ? false : true>;
type _UiLacksUniverseContractSnake = _Assert<'universe_contract' extends keyof TodaysFocusResponse ? false : true>;
type _UiLacksCostContractSnake = _Assert<'cost_contract' extends keyof TodaysFocusResponse ? false : true>;
type _UiLacksPresentationBoundarySnake = _Assert<'presentation_boundary' extends keyof TodaysFocusResponse ? false : true>;
type _UiLacksReasonCodeSnake = _Assert<'reason_code' extends keyof TodaysFocusItem ? false : true>;
type _UiLacksWeightPctSnake = _Assert<'weight_pct' extends keyof TodaysFocusItem ? false : true>;
type _UiLacksTriggerIdSnake = _Assert<'trigger_id' extends keyof TodaysFocusAlertEvidence ? false : true>;
type _UiLacksRuleIdSnake = _Assert<'rule_id' extends keyof TodaysFocusAlertEvidence ? false : true>;
type _UiLacksObservedAtSnake = _Assert<'observed_at' extends keyof TodaysFocusAlertEvidence ? false : true>;
type _UiLacksRecordIdSnake = _Assert<'record_id' extends keyof TodaysFocusAnalysisEvidence ? false : true>;
type _UiLacksQueryIdSnake = _Assert<'query_id' extends keyof TodaysFocusAnalysisEvidence ? false : true>;
type _UiLacksEventIdSnake = _Assert<'event_id' extends keyof TodaysFocusCorporateEventEvidence ? false : true>;
type _UiLacksIsTradingDaySnake = _Assert<'is_trading_day' extends keyof TodaysFocusMarketDayWindow ? false : true>;
type _UiLacksDataNotesSnake = _Assert<'data_notes' extends keyof TodaysFocusResponse['universeContract'] ? false : true>;

type _GeneratedHasPackVersionSnake = _Assert<'pack_version' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasGeneratedAtSnake = _Assert<'generated_at' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasEmptyReasonSnake = _Assert<'empty_reason' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasEmptyMessageSnake = _Assert<'empty_message' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasSourcesUsedSnake = _Assert<'sources_used' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasDegradedSourcesSnake = _Assert<'degraded_sources' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasTemporalPolicySnake = _Assert<'temporal_policy' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasUniverseContractSnake = _Assert<'universe_contract' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasCostContractSnake = _Assert<'cost_contract' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasPresentationBoundarySnake = _Assert<'presentation_boundary' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasReasonCodeSnake = _Assert<'reason_code' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasWeightPctSnake = _Assert<'weight_pct' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasTriggerIdSnake = _Assert<'trigger_id' extends keyof OpenApiAlertEvidence ? true : false>;
type _GeneratedHasRuleIdSnake = _Assert<'rule_id' extends keyof OpenApiAlertEvidence ? true : false>;
type _GeneratedHasQueryIdSnake = _Assert<'query_id' extends keyof OpenApiAnalysisEvidence ? true : false>;
type _GeneratedHasEventIdSnake = _Assert<'event_id' extends keyof OpenApiCorporateEventEvidence ? true : false>;
type _GeneratedHasIsTradingDaySnake = _Assert<'is_trading_day' extends keyof OpenApiMarketDayWindow ? true : false>;
type _GeneratedHasDataNotesSnake = _Assert<'data_notes' extends keyof OpenApiUniverseContract ? true : false>;
type _GeneratedLacksPackVersionCamel = _Assert<'packVersion' extends keyof OpenApiResponse ? false : true>;
type _GeneratedLacksReasonCodeCamel = _Assert<'reasonCode' extends keyof OpenApiItem ? false : true>;
type _GeneratedLacksEmptyReasonCamel = _Assert<'emptyReason' extends keyof OpenApiResponse ? false : true>;

type _UiRuleIdRequired = _Assert<IsOptional<TodaysFocusAlertEvidence, 'ruleId'> extends false ? true : false>;
type _UiQueryIdRequired = _Assert<IsOptional<TodaysFocusAnalysisEvidence, 'queryId'> extends false ? true : false>;
type _UiWeightPctRequired = _Assert<IsOptional<TodaysFocusItem, 'weightPct'> extends false ? true : false>;
type _UiIsTradingDayRequired = _Assert<
  IsOptional<TodaysFocusMarketDayWindow, 'isTradingDay'> extends false ? true : false
>;
type _UiEmptyReasonRequired = _Assert<IsOptional<TodaysFocusResponse, 'emptyReason'> extends false ? true : false>;
type _UiEmptyMessageRequired = _Assert<IsOptional<TodaysFocusResponse, 'emptyMessage'> extends false ? true : false>;
type _UiDataNotesRequired = _Assert<
  IsOptional<TodaysFocusResponse['universeContract'], 'dataNotes'> extends false ? true : false
>;
type _GeneratedRuleIdOptional = _Assert<IsOptional<OpenApiAlertEvidence, 'rule_id'>>;
type _GeneratedQueryIdOptional = _Assert<IsOptional<OpenApiAnalysisEvidence, 'query_id'>>;
type _GeneratedWeightPctOptional = _Assert<IsOptional<OpenApiItem, 'weight_pct'>>;
type _GeneratedIsTradingDayOptional = _Assert<IsOptional<OpenApiMarketDayWindow, 'is_trading_day'>>;
type _GeneratedEmptyReasonOptional = _Assert<IsOptional<OpenApiResponse, 'empty_reason'>>;
type _GeneratedEmptyMessageOptional = _Assert<IsOptional<OpenApiResponse, 'empty_message'>>;
type _GeneratedDataNotesOptional = _Assert<IsOptional<OpenApiUniverseContract, 'data_notes'>>;
type _NaiveCamelEmptyReasonOptional = _Assert<IsOptional<CamelizeKeys<OpenApiResponse>, 'emptyReason'>>;
type _NaiveCamelWeightPctOptional = _Assert<IsOptional<CamelizeKeys<OpenApiItem>, 'weightPct'>>;
type _NaiveCamelDataNotesOptional = _Assert<IsOptional<CamelizeKeys<OpenApiUniverseContract>, 'dataNotes'>>;
type _UiSourceOptional = _Assert<IsOptional<TodaysFocusAlertEvidence, 'source'>>;
type _GeneratedSourceOptional = _Assert<IsOptional<OpenApiAlertEvidence, 'source'>>;

type _OmitUiRuleId = _Assert<Omit<TodaysFocusAlertEvidence, 'ruleId'> extends TodaysFocusAlertEvidence ? false : true>;
type _OmitGeneratedRuleId = _Assert<Omit<OpenApiAlertEvidence, 'rule_id'> extends OpenApiAlertEvidence ? true : false>;
type _OmitUiQueryId = _Assert<
  Omit<TodaysFocusAnalysisEvidence, 'queryId'> extends TodaysFocusAnalysisEvidence ? false : true
>;
type _OmitGeneratedQueryId = _Assert<
  Omit<OpenApiAnalysisEvidence, 'query_id'> extends OpenApiAnalysisEvidence ? true : false
>;
type _OmitUiWeightPct = _Assert<Omit<TodaysFocusItem, 'weightPct'> extends TodaysFocusItem ? false : true>;
type _OmitGeneratedWeightPct = _Assert<Omit<OpenApiItem, 'weight_pct'> extends OpenApiItem ? true : false>;
type _OmitUiIsTradingDay = _Assert<
  Omit<TodaysFocusMarketDayWindow, 'isTradingDay'> extends TodaysFocusMarketDayWindow ? false : true
>;
type _OmitGeneratedIsTradingDay = _Assert<
  Omit<OpenApiMarketDayWindow, 'is_trading_day'> extends OpenApiMarketDayWindow ? true : false
>;
type _OmitUiEmptyReason = _Assert<Omit<TodaysFocusResponse, 'emptyReason'> extends TodaysFocusResponse ? false : true>;
type _OmitGeneratedEmptyReason = _Assert<Omit<OpenApiResponse, 'empty_reason'> extends OpenApiResponse ? true : false>;
type _OmitUiEmptyMessage = _Assert<Omit<TodaysFocusResponse, 'emptyMessage'> extends TodaysFocusResponse ? false : true>;
type _OmitGeneratedEmptyMessage = _Assert<Omit<OpenApiResponse, 'empty_message'> extends OpenApiResponse ? true : false>;
type _OmitUiDataNotes = _Assert<
  Omit<TodaysFocusResponse['universeContract'], 'dataNotes'> extends TodaysFocusResponse['universeContract']
    ? false
    : true
>;
type _OmitGeneratedDataNotes = _Assert<
  Omit<OpenApiUniverseContract, 'data_notes'> extends OpenApiUniverseContract ? true : false
>;
type _OmitUiSource = _Assert<Omit<TodaysFocusAlertEvidence, 'source'> extends TodaysFocusAlertEvidence ? true : false>;

type _AlertTriggeredAssignable = _Assert<'alert_triggered' extends TodaysFocusReasonCode ? true : false>;
type _CorporateEventAssignable = _Assert<'corporate_event' extends TodaysFocusReasonCode ? true : false>;
type _AnalysisReversalAssignable = _Assert<'analysis_reversal' extends TodaysFocusReasonCode ? true : false>;
type _AlertTriggeredCamelRejected = _Assert<'alertTriggered' extends TodaysFocusReasonCode ? false : true>;
type _CorporateEventCamelRejected = _Assert<'corporateEvent' extends TodaysFocusReasonCode ? false : true>;
type _StringReasonRejected = _Assert<string extends TodaysFocusReasonCode ? false : true>;
type _AlertTypeAssignable = _Assert<'alert' extends TodaysFocusAlertEvidence['type'] ? true : false>;
type _AnalysisTypeAssignable = _Assert<'analysis' extends TodaysFocusAnalysisEvidence['type'] ? true : false>;
type _CorporateEventTypeAssignable = _Assert<
  'corporate_event' extends TodaysFocusCorporateEventEvidence['type'] ? true : false
>;
type _CorporateEventTypeCamelRejected = _Assert<
  'corporateEvent' extends TodaysFocusCorporateEventEvidence['type'] ? false : true
>;
type _StringEvidenceTypeRejected = _Assert<string extends TodaysFocusEvidence['type'] ? false : true>;
type _AnalysisHistorySourceAssignable = _Assert<
  'analysis_history' extends TodaysFocusResponse['sourcesUsed'][number] ? true : false
>;
type _AnalysisHistoryCamelRejected = _Assert<
  'analysisHistory' extends TodaysFocusResponse['sourcesUsed'][number] ? false : true
>;
type _WatchlistConfigAssignable = _Assert<
  'watchlist_config' extends TodaysFocusResponse['universeContract']['sources'][number] ? true : false
>;
type _WatchlistConfigCamelRejected = _Assert<
  'watchlistConfig' extends TodaysFocusResponse['universeContract']['sources'][number] ? false : true
>;
type _PortfolioCacheAssignable = _Assert<
  'portfolio_position_cache' extends TodaysFocusResponse['degradedSources'][number] ? true : false
>;
type _PortfolioCacheCamelRejected = _Assert<
  'portfolioPositionCache' extends TodaysFocusResponse['degradedSources'][number] ? false : true
>;
type _OkStatusAssignable = _Assert<'ok' extends TodaysFocusResponse['status'] ? true : false>;
type _EmptyStatusAssignable = _Assert<'empty' extends TodaysFocusResponse['status'] ? true : false>;
type _DegradedStatusAssignable = _Assert<'degraded' extends TodaysFocusResponse['status'] ? true : false>;
type _MysteryStatusRejected = _Assert<'mystery' extends TodaysFocusResponse['status'] ? false : true>;
type _StringStatusRejected = _Assert<string extends TodaysFocusResponse['status'] ? false : true>;
type _BuyActionAssignable = _Assert<'buy' extends TodaysFocusAnalysisEvidence['latestAction'] ? true : false>;
type _HoldActionAssignable = _Assert<'hold' extends TodaysFocusAnalysisEvidence['previousAction'] ? true : false>;
type _StringActionRejected = _Assert<string extends TodaysFocusAnalysisEvidence['latestAction'] ? false : true>;

type _UiPackVersionLiteral = _Assert<
  TodaysFocusResponse['packVersion'] extends 'todays_focus/2.1' ? true : false
>;
type _UiPackVersionNotString = _Assert<string extends TodaysFocusResponse['packVersion'] ? false : true>;
type _UiHardCapLiteral = _Assert<TodaysFocusResponse['universeContract']['hardCap'] extends 1000 ? true : false>;
type _UiHardCapNotNumber = _Assert<number extends TodaysFocusResponse['universeContract']['hardCap'] ? false : true>;
type _UiDatabaseWritesZero = _Assert<TodaysFocusCostContract['databaseWrites'] extends 0 ? true : false>;
type _UiProviderCallsZero = _Assert<TodaysFocusCostContract['providerCalls'] extends 0 ? true : false>;
type _UiAnalysisRunsZero = _Assert<TodaysFocusCostContract['analysisRunsTriggered'] extends 0 ? true : false>;
type _UiZeroExtraFetchTrue = _Assert<TodaysFocusCostContract['zeroExtraFetch'] extends true ? true : false>;
type _UiReadOnlyTrue = _Assert<TodaysFocusCostContract['readOnly'] extends true ? true : false>;
type _UiDuplicateAlertFalse = _Assert<
  TodaysFocusResponse['presentationBoundary']['duplicateAlertUi'] extends false ? true : false
>;
type _UiAlertsOwnedByLiteral = _Assert<
  TodaysFocusResponse['presentationBoundary']['alertsOwnedBy'] extends 'signal_center' ? true : false
>;
type _UiFocusShowsLiteral = _Assert<
  TodaysFocusResponse['presentationBoundary']['focusShows'] extends 'prioritized_symbols_with_evidence_links'
    ? true
    : false
>;
type _GeneratedPackVersionLiteral = _Assert<
  OpenApiResponse['pack_version'] extends 'todays_focus/2.1' ? true : false
>;
type _GeneratedHardCapLiteral = _Assert<OpenApiUniverseContract['hard_cap'] extends 1000 ? true : false>;
type _GeneratedReadOnlyTrue = _Assert<OpenApiCostContract['read_only'] extends true ? true : false>;
type _GeneratedPresentationHasAlertsOwnedBy = _Assert<
  'alerts_owned_by' extends keyof OpenApiPresentationBoundary ? true : false
>;
type _GeneratedTemporalHasCrossMarket = _Assert<
  'cross_market_rule' extends keyof OpenApiTemporalPolicy ? true : false
>;

type _PublicQueryHasMaxItems = _Assert<'maxItems' extends keyof TodaysFocusQuery ? true : false>;
type _PublicQueryHasAccountId = _Assert<'accountId' extends keyof TodaysFocusQuery ? true : false>;
type _PublicQueryHasLanguage = _Assert<'language' extends keyof TodaysFocusQuery ? true : false>;
type _PublicQueryLacksSnake = _Assert<'account_id' extends keyof TodaysFocusQuery ? false : true>;
type _PublicQueryLacksMaxItemsSnake = _Assert<'max_items' extends keyof TodaysFocusQuery ? false : true>;
type _PublicQueryRejectsNullAccount = _Assert<{ accountId: null } extends TodaysFocusQuery ? false : true>;
type _PublicQueryRejectsNullLanguage = _Assert<{ language: null } extends TodaysFocusQuery ? false : true>;
type _GeneratedQueryAcceptsNullAccount = _Assert<{ account_id: null } extends OpenApiGetQuery ? true : false>;
type _GeneratedQueryAcceptsNullLanguage = _Assert<{ language: null } extends OpenApiGetQuery ? true : false>;
type _CamelizedQueryAcceptsNull = _Assert<{ accountId: null } extends CamelizeKeys<OpenApiGetQuery> ? true : false>;
type _CamelizedQueryIsNotPublic = _Assert<CamelizeKeys<OpenApiGetQuery> extends TodaysFocusQuery ? false : true>;
type _UiQueryMaxItemsOptional = _Assert<IsOptional<TodaysFocusQuery, 'maxItems'>>;
type _UiQueryAccountIdOptional = _Assert<IsOptional<TodaysFocusQuery, 'accountId'>>;
type _UiQueryLanguageOptional = _Assert<IsOptional<TodaysFocusQuery, 'language'>>;

type NarrowAlert = {
  type: 'alert';
  triggerId: 1;
  ruleId: null;
  observedAt: '2026-08-09T07:30:00Z';
  status: 'triggered';
};
type NarrowItem = {
  code: string;
  name: string;
  reasonCode: 'alert_triggered';
  reasonDisplay: string;
  priority: number;
  weightPct: number | null;
  secondaryReasonCodes: TodaysFocusReasonCode[];
  evidence: NarrowAlert;
};
type NarrowWindow = {
  market: 'cn';
  timezone: string;
  localDate: string;
  windowStart: string;
  windowEnd: string;
  isTradingDay: boolean | null;
};
type NarrowResponse = {
  packVersion: 'todays_focus/2.1';
  generatedAt: string;
  status: 'empty';
  maxItems: number;
  itemCount: number;
  items: NarrowItem[];
  emptyReason: 'no_fresh_deterministic_signals';
  emptyMessage: string | null;
  sourcesUsed: Array<'alerts'>;
  degradedSources: Array<'portfolio_position_cache'>;
  temporalPolicy: {
    semantics: 'per_market_local_calendar_day';
    crossMarketRule: 'evidence_uses_target_symbol_market_timezone';
    fallbackTimezone: string;
    windowEnd: string;
    naiveTimestampPolicy: 'assume_utc';
    missingTimestampPolicy: 'exclude';
    nonTradingDayPolicy: 'same_local_day_only';
    markets: NarrowWindow[];
  };
  universeContract: {
    symbolCount: number;
    hardCap: 1000;
    truncated: boolean;
    sources: Array<'watchlist_config'>;
    excludedNonFinitePositions: number;
    dataNotes: string[];
  };
  costContract: {
    alertRepositoryCalls: number;
    portfolioRepositoryCalls: number;
    analysisHistoryRepositoryCalls: number;
    eventRepositoryCalls: number;
    databaseWrites: 0;
    providerCalls: 0;
    analysisRunsTriggered: 0;
    zeroExtraFetch: true;
    readOnly: true;
  };
  presentationBoundary: {
    alertsOwnedBy: 'signal_center';
    focusShows: 'prioritized_symbols_with_evidence_links';
    duplicateAlertUi: false;
  };
};
type _NarrowResponseAssignable = _Assert<NarrowResponse extends TodaysFocusResponse ? true : false>;
type _NarrowItemAssignable = _Assert<NarrowItem extends TodaysFocusItem ? true : false>;
type _NarrowAlertAssignable = _Assert<NarrowAlert extends TodaysFocusAlertEvidence ? true : false>;
type _NarrowAlertAssignableToEvidence = _Assert<NarrowAlert extends TodaysFocusEvidence ? true : false>;

type SnakeResponse = {
  pack_version: 'todays_focus/2.1';
  generated_at: string;
  status: 'empty';
  max_items: number;
  item_count: number;
  items: OpenApiItem[];
  sources_used: OpenApiResponse['sources_used'];
  degraded_sources: OpenApiResponse['degraded_sources'];
  temporal_policy: OpenApiTemporalPolicy;
  universe_contract: OpenApiUniverseContract;
  cost_contract: OpenApiCostContract;
  presentation_boundary: OpenApiPresentationBoundary;
};
type _SnakeMatchesGenerated = _Assert<SnakeResponse extends OpenApiResponse ? true : false>;
type _SnakeDoesNotMatchUi = _Assert<SnakeResponse extends TodaysFocusResponse ? false : true>;

type CamelReasonItem = Omit<NarrowItem, 'reasonCode'> & { reasonCode: 'alertTriggered' };
type _CamelReasonRejected = _Assert<CamelReasonItem extends TodaysFocusItem ? false : true>;
type CamelEvidenceType = Omit<NarrowAlert, 'type'> & { type: 'corporateEvent' };
type _CamelEvidenceTypeRejected = _Assert<CamelEvidenceType extends TodaysFocusAlertEvidence ? false : true>;
type CamelUniverseSources = Omit<NarrowResponse, 'universeContract'> & {
  universeContract: Omit<NarrowResponse['universeContract'], 'sources'> & {
    sources: Array<'watchlistConfig'>;
  };
};
type _CamelUniverseSourcesRejected = _Assert<CamelUniverseSources extends TodaysFocusResponse ? false : true>;
type MissingEmptyReason = Omit<NarrowResponse, 'emptyReason'>;
type _MissingEmptyReasonRejected = _Assert<MissingEmptyReason extends TodaysFocusResponse ? false : true>;
type MissingDataNotes = Omit<NarrowResponse, 'universeContract'> & {
  universeContract: Omit<NarrowResponse['universeContract'], 'dataNotes'>;
};
type _MissingDataNotesRejected = _Assert<MissingDataNotes extends TodaysFocusResponse ? false : true>;
type MissingRuleId = Omit<NarrowAlert, 'ruleId'>;
type _MissingRuleIdRejected = _Assert<MissingRuleId extends TodaysFocusAlertEvidence ? false : true>;

type _CompileTimePins = [
  _TenGeneratedComponents,
  _HasAnalysisEvidence,
  _HasCorporateEventEvidence,
  _HasCostContract,
  _HasItem,
  _HasMarketDayWindow,
  _HasPresentationBoundary,
  _HasResponse,
  _HasTemporalPolicy,
  _HasUniverseContract,
  _LacksEleventhSummary,
  _Get200IsResponse,
  _ResponseIsGet200,
  _GetOpIsPath,
  _PathIsGetOp,
  _GetOpHasNeverRequestBody,
  _PathPostNever,
  _UiHasPackVersion,
  _UiHasGeneratedAt,
  _UiHasMaxItems,
  _UiHasItemCount,
  _UiHasEmptyReason,
  _UiHasEmptyMessage,
  _UiHasSourcesUsed,
  _UiHasDegradedSources,
  _UiHasTemporalPolicy,
  _UiHasUniverseContract,
  _UiHasCostContract,
  _UiHasPresentationBoundary,
  _UiHasReasonCode,
  _UiHasReasonDisplay,
  _UiHasWeightPct,
  _UiHasSecondaryReasonCodes,
  _UiHasTriggerId,
  _UiHasRuleId,
  _UiHasObservedAt,
  _UiHasRecordId,
  _UiHasQueryId,
  _UiHasPreviousObservedAt,
  _UiHasPreviousAction,
  _UiHasLatestAction,
  _UiHasEventId,
  _UiHasLocalDate,
  _UiHasWindowStart,
  _UiHasIsTradingDay,
  _UiHasCrossMarketRule,
  _UiHasFallbackTimezone,
  _UiHasNaiveTimestampPolicy,
  _UiHasMissingTimestampPolicy,
  _UiHasNonTradingDayPolicy,
  _UiHasAlertRepositoryCalls,
  _UiHasZeroExtraFetch,
  _UiHasReadOnly,
  _UiHasAlertsOwnedBy,
  _UiHasFocusShows,
  _UiHasDuplicateAlertUi,
  _UiHasSymbolCount,
  _UiHasHardCap,
  _UiHasExcludedNonFinite,
  _UiHasDataNotes,
  _UiLacksPackVersionSnake,
  _UiLacksGeneratedAtSnake,
  _UiLacksMaxItemsSnake,
  _UiLacksItemCountSnake,
  _UiLacksEmptyReasonSnake,
  _UiLacksEmptyMessageSnake,
  _UiLacksSourcesUsedSnake,
  _UiLacksDegradedSourcesSnake,
  _UiLacksTemporalPolicySnake,
  _UiLacksUniverseContractSnake,
  _UiLacksCostContractSnake,
  _UiLacksPresentationBoundarySnake,
  _UiLacksReasonCodeSnake,
  _UiLacksWeightPctSnake,
  _UiLacksTriggerIdSnake,
  _UiLacksRuleIdSnake,
  _UiLacksObservedAtSnake,
  _UiLacksRecordIdSnake,
  _UiLacksQueryIdSnake,
  _UiLacksEventIdSnake,
  _UiLacksIsTradingDaySnake,
  _UiLacksDataNotesSnake,
  _GeneratedHasPackVersionSnake,
  _GeneratedHasGeneratedAtSnake,
  _GeneratedHasEmptyReasonSnake,
  _GeneratedHasEmptyMessageSnake,
  _GeneratedHasSourcesUsedSnake,
  _GeneratedHasDegradedSourcesSnake,
  _GeneratedHasTemporalPolicySnake,
  _GeneratedHasUniverseContractSnake,
  _GeneratedHasCostContractSnake,
  _GeneratedHasPresentationBoundarySnake,
  _GeneratedHasReasonCodeSnake,
  _GeneratedHasWeightPctSnake,
  _GeneratedHasTriggerIdSnake,
  _GeneratedHasRuleIdSnake,
  _GeneratedHasQueryIdSnake,
  _GeneratedHasEventIdSnake,
  _GeneratedHasIsTradingDaySnake,
  _GeneratedHasDataNotesSnake,
  _GeneratedLacksPackVersionCamel,
  _GeneratedLacksReasonCodeCamel,
  _GeneratedLacksEmptyReasonCamel,
  _UiRuleIdRequired,
  _UiQueryIdRequired,
  _UiWeightPctRequired,
  _UiIsTradingDayRequired,
  _UiEmptyReasonRequired,
  _UiEmptyMessageRequired,
  _UiDataNotesRequired,
  _GeneratedRuleIdOptional,
  _GeneratedQueryIdOptional,
  _GeneratedWeightPctOptional,
  _GeneratedIsTradingDayOptional,
  _GeneratedEmptyReasonOptional,
  _GeneratedEmptyMessageOptional,
  _GeneratedDataNotesOptional,
  _NaiveCamelEmptyReasonOptional,
  _NaiveCamelWeightPctOptional,
  _NaiveCamelDataNotesOptional,
  _UiSourceOptional,
  _GeneratedSourceOptional,
  _OmitUiRuleId,
  _OmitGeneratedRuleId,
  _OmitUiQueryId,
  _OmitGeneratedQueryId,
  _OmitUiWeightPct,
  _OmitGeneratedWeightPct,
  _OmitUiIsTradingDay,
  _OmitGeneratedIsTradingDay,
  _OmitUiEmptyReason,
  _OmitGeneratedEmptyReason,
  _OmitUiEmptyMessage,
  _OmitGeneratedEmptyMessage,
  _OmitUiDataNotes,
  _OmitGeneratedDataNotes,
  _OmitUiSource,
  _AlertTriggeredAssignable,
  _CorporateEventAssignable,
  _AnalysisReversalAssignable,
  _AlertTriggeredCamelRejected,
  _CorporateEventCamelRejected,
  _StringReasonRejected,
  _AlertTypeAssignable,
  _AnalysisTypeAssignable,
  _CorporateEventTypeAssignable,
  _CorporateEventTypeCamelRejected,
  _StringEvidenceTypeRejected,
  _AnalysisHistorySourceAssignable,
  _AnalysisHistoryCamelRejected,
  _WatchlistConfigAssignable,
  _WatchlistConfigCamelRejected,
  _PortfolioCacheAssignable,
  _PortfolioCacheCamelRejected,
  _OkStatusAssignable,
  _EmptyStatusAssignable,
  _DegradedStatusAssignable,
  _MysteryStatusRejected,
  _StringStatusRejected,
  _BuyActionAssignable,
  _HoldActionAssignable,
  _StringActionRejected,
  _UiPackVersionLiteral,
  _UiPackVersionNotString,
  _UiHardCapLiteral,
  _UiHardCapNotNumber,
  _UiDatabaseWritesZero,
  _UiProviderCallsZero,
  _UiAnalysisRunsZero,
  _UiZeroExtraFetchTrue,
  _UiReadOnlyTrue,
  _UiDuplicateAlertFalse,
  _UiAlertsOwnedByLiteral,
  _UiFocusShowsLiteral,
  _GeneratedPackVersionLiteral,
  _GeneratedHardCapLiteral,
  _GeneratedReadOnlyTrue,
  _GeneratedPresentationHasAlertsOwnedBy,
  _GeneratedTemporalHasCrossMarket,
  _PublicQueryHasMaxItems,
  _PublicQueryHasAccountId,
  _PublicQueryHasLanguage,
  _PublicQueryLacksSnake,
  _PublicQueryLacksMaxItemsSnake,
  _PublicQueryRejectsNullAccount,
  _PublicQueryRejectsNullLanguage,
  _GeneratedQueryAcceptsNullAccount,
  _GeneratedQueryAcceptsNullLanguage,
  _CamelizedQueryAcceptsNull,
  _CamelizedQueryIsNotPublic,
  _UiQueryMaxItemsOptional,
  _UiQueryAccountIdOptional,
  _UiQueryLanguageOptional,
  _NarrowResponseAssignable,
  _NarrowItemAssignable,
  _NarrowAlertAssignable,
  _NarrowAlertAssignableToEvidence,
  _SnakeMatchesGenerated,
  _SnakeDoesNotMatchUi,
  _CamelReasonRejected,
  _CamelEvidenceTypeRejected,
  _CamelUniverseSourcesRejected,
  _MissingEmptyReasonRejected,
  _MissingDataNotesRejected,
  _MissingRuleIdRejected,
];

const emptyFocus: TodaysFocusResponse = {
  packVersion: 'todays_focus/2.1',
  generatedAt: '2026-08-09T00:00:00Z',
  status: 'empty',
  maxItems: 5,
  itemCount: 0,
  items: [],
  emptyReason: 'no_fresh_deterministic_signals',
  emptyMessage: 'No symbols need special attention today.',
  sourcesUsed: [],
  degradedSources: [],
  temporalPolicy: {
    semantics: 'per_market_local_calendar_day',
    crossMarketRule: 'evidence_uses_target_symbol_market_timezone',
    fallbackTimezone: 'Asia/Shanghai',
    windowEnd: '2026-08-09T00:00:00Z',
    naiveTimestampPolicy: 'assume_utc',
    missingTimestampPolicy: 'exclude',
    nonTradingDayPolicy: 'same_local_day_only',
    markets: [
      {
        market: 'cn',
        timezone: 'Asia/Shanghai',
        localDate: '2026-08-09',
        windowStart: '2026-08-08T16:00:00Z',
        windowEnd: '2026-08-09T00:00:00Z',
        isTradingDay: false,
      },
      {
        market: 'unknown',
        timezone: 'Asia/Shanghai',
        localDate: '2026-08-09',
        windowStart: '2026-08-08T16:00:00Z',
        windowEnd: '2026-08-09T00:00:00Z',
        isTradingDay: null,
      },
    ],
  },
  universeContract: {
    symbolCount: 0,
    hardCap: 1000,
    truncated: false,
    sources: ['watchlist_config'],
    excludedNonFinitePositions: 0,
    dataNotes: [],
  },
  costContract: {
    alertRepositoryCalls: 1,
    portfolioRepositoryCalls: 1,
    analysisHistoryRepositoryCalls: 1,
    eventRepositoryCalls: 0,
    databaseWrites: 0,
    providerCalls: 0,
    analysisRunsTriggered: 0,
    zeroExtraFetch: true,
    readOnly: true,
  },
  presentationBoundary: {
    alertsOwnedBy: 'signal_center',
    focusShows: 'prioritized_symbols_with_evidence_links',
    duplicateAlertUi: false,
  },
};

const alertItem: TodaysFocusItem = {
  code: '600519',
  name: 'Kweichow Moutai',
  reasonCode: 'alert_triggered',
  reasonDisplay: 'Alert triggered: price above MA',
  priority: 100,
  weightPct: null,
  secondaryReasonCodes: [],
  evidence: {
    type: 'alert',
    triggerId: 7,
    ruleId: 9,
    observedAt: '2026-08-09T07:30:00Z',
    status: 'triggered',
  },
};

describe('todaysFocus OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    // ESM namespace objects carry Symbol.toStringTag='Module'; enumerable exports must stay empty.
    expect({ ...TodaysFocus }).toEqual({});
    expect(Object.keys(TodaysFocus)).toEqual([]);
    expect(Object.getOwnPropertyNames(TodaysFocus)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates GET /api/v1/focus/today 200 JSON to the generated response component', () => {
    expectTypeOf<OpenApiGet200>().toEqualTypeOf<OpenApiResponse>();
    expectTypeOf<OpenApiGetOp>().toEqualTypeOf<OpenApiPathGet>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof TodaysFocusResponse>().not.toMatchTypeOf<
      'pack_version' | 'generated_at' | 'empty_reason' | 'empty_message' | 'sources_used' | 'cost_contract'
    >();
    expectTypeOf<keyof TodaysFocusItem>().not.toMatchTypeOf<
      'reason_code' | 'reason_display' | 'weight_pct' | 'secondary_reason_codes'
    >();
    expectTypeOf<keyof OpenApiResponse>().not.toMatchTypeOf<'packVersion' | 'emptyReason' | 'costContract'>();

    type UiHasPackVersion = 'packVersion' extends keyof TodaysFocusResponse ? true : false;
    type UiHasPackVersionSnake = 'pack_version' extends keyof TodaysFocusResponse ? true : false;
    type GeneratedHasPackVersionSnake = 'pack_version' extends keyof OpenApiResponse ? true : false;
    type GeneratedHasPackVersionCamel = 'packVersion' extends keyof OpenApiResponse ? true : false;
    type UiHasReasonCode = 'reasonCode' extends keyof TodaysFocusItem ? true : false;
    type UiHasReasonCodeSnake = 'reason_code' extends keyof TodaysFocusItem ? true : false;
    type GeneratedHasReasonCodeSnake = 'reason_code' extends keyof OpenApiItem ? true : false;
    type UiHasRuleId = 'ruleId' extends keyof TodaysFocusAlertEvidence ? true : false;
    type UiHasRuleIdSnake = 'rule_id' extends keyof TodaysFocusAlertEvidence ? true : false;
    type GeneratedHasRuleIdSnake = 'rule_id' extends keyof OpenApiAlertEvidence ? true : false;

    expectTypeOf<UiHasPackVersion>().toEqualTypeOf<true>();
    expectTypeOf<UiHasPackVersionSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasPackVersionSnake>().toEqualTypeOf<true>();
    expectTypeOf<GeneratedHasPackVersionCamel>().toEqualTypeOf<false>();
    expectTypeOf<UiHasReasonCode>().toEqualTypeOf<true>();
    expectTypeOf<UiHasReasonCodeSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasReasonCodeSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasRuleId>().toEqualTypeOf<true>();
    expectTypeOf<UiHasRuleIdSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasRuleIdSnake>().toEqualTypeOf<true>();
  });

  it('keeps seven UI fields required while generated counterparts stay optional', () => {
    expectTypeOf<Omit<TodaysFocusAlertEvidence, 'ruleId'>>().not.toMatchTypeOf<TodaysFocusAlertEvidence>();
    expectTypeOf<Omit<OpenApiAlertEvidence, 'rule_id'>>().toMatchTypeOf<OpenApiAlertEvidence>();
    expectTypeOf<Omit<TodaysFocusAnalysisEvidence, 'queryId'>>().not.toMatchTypeOf<TodaysFocusAnalysisEvidence>();
    expectTypeOf<Omit<OpenApiAnalysisEvidence, 'query_id'>>().toMatchTypeOf<OpenApiAnalysisEvidence>();
    expectTypeOf<Omit<TodaysFocusItem, 'weightPct'>>().not.toMatchTypeOf<TodaysFocusItem>();
    expectTypeOf<Omit<OpenApiItem, 'weight_pct'>>().toMatchTypeOf<OpenApiItem>();
    expectTypeOf<Omit<TodaysFocusMarketDayWindow, 'isTradingDay'>>().not.toMatchTypeOf<TodaysFocusMarketDayWindow>();
    expectTypeOf<Omit<OpenApiMarketDayWindow, 'is_trading_day'>>().toMatchTypeOf<OpenApiMarketDayWindow>();
    expectTypeOf<Omit<TodaysFocusResponse, 'emptyReason'>>().not.toMatchTypeOf<TodaysFocusResponse>();
    expectTypeOf<Omit<OpenApiResponse, 'empty_reason'>>().toMatchTypeOf<OpenApiResponse>();
    expectTypeOf<Omit<TodaysFocusResponse, 'emptyMessage'>>().not.toMatchTypeOf<TodaysFocusResponse>();
    expectTypeOf<Omit<OpenApiResponse, 'empty_message'>>().toMatchTypeOf<OpenApiResponse>();
    expectTypeOf<Omit<TodaysFocusResponse['universeContract'], 'dataNotes'>>().not.toMatchTypeOf<
      TodaysFocusResponse['universeContract']
    >();
    expectTypeOf<Omit<OpenApiUniverseContract, 'data_notes'>>().toMatchTypeOf<OpenApiUniverseContract>();
    expectTypeOf<Omit<TodaysFocusAlertEvidence, 'source'>>().toMatchTypeOf<TodaysFocusAlertEvidence>();
  });

  it('keeps enum and discriminator values snake while object keys camel', () => {
    expectTypeOf<'alert_triggered'>().toMatchTypeOf<TodaysFocusReasonCode>();
    expectTypeOf<'corporate_event'>().toMatchTypeOf<TodaysFocusReasonCode>();
    expectTypeOf<'analysis_reversal'>().toMatchTypeOf<TodaysFocusReasonCode>();
    expectTypeOf<'alertTriggered'>().not.toMatchTypeOf<TodaysFocusReasonCode>();
    expectTypeOf<'corporateEvent'>().not.toMatchTypeOf<TodaysFocusReasonCode>();
    expectTypeOf<string>().not.toMatchTypeOf<TodaysFocusReasonCode>();
    expectTypeOf<'corporate_event'>().toMatchTypeOf<TodaysFocusCorporateEventEvidence['type']>();
    expectTypeOf<'corporateEvent'>().not.toMatchTypeOf<TodaysFocusCorporateEventEvidence['type']>();
    expectTypeOf<'analysis_history'>().toMatchTypeOf<TodaysFocusResponse['sourcesUsed'][number]>();
    expectTypeOf<'analysisHistory'>().not.toMatchTypeOf<TodaysFocusResponse['sourcesUsed'][number]>();
    expectTypeOf<'watchlist_config'>().toMatchTypeOf<TodaysFocusResponse['universeContract']['sources'][number]>();
    expectTypeOf<'watchlistConfig'>().not.toMatchTypeOf<TodaysFocusResponse['universeContract']['sources'][number]>();
    expectTypeOf<'portfolio_position_cache'>().toMatchTypeOf<TodaysFocusResponse['degradedSources'][number]>();
    expectTypeOf<'portfolioPositionCache'>().not.toMatchTypeOf<TodaysFocusResponse['degradedSources'][number]>();
  });

  it('keeps generated constants closed on the UI type', () => {
    expectTypeOf<'todays_focus/2.1'>().toEqualTypeOf<TodaysFocusResponse['packVersion']>();
    expectTypeOf<1000>().toEqualTypeOf<TodaysFocusResponse['universeContract']['hardCap']>();
    expectTypeOf<0>().toEqualTypeOf<TodaysFocusCostContract['databaseWrites']>();
    expectTypeOf<true>().toEqualTypeOf<TodaysFocusCostContract['zeroExtraFetch']>();
    expectTypeOf<true>().toEqualTypeOf<TodaysFocusCostContract['readOnly']>();
    expectTypeOf<false>().toEqualTypeOf<TodaysFocusResponse['presentationBoundary']['duplicateAlertUi']>();
    expectTypeOf<'signal_center'>().toEqualTypeOf<TodaysFocusResponse['presentationBoundary']['alertsOwnedBy']>();
    expectTypeOf<string>().not.toMatchTypeOf<TodaysFocusResponse['packVersion']>();
    expectTypeOf<number>().not.toMatchTypeOf<TodaysFocusResponse['universeContract']['hardCap']>();
    expectTypeOf<true>().not.toMatchTypeOf<TodaysFocusResponse['presentationBoundary']['duplicateAlertUi']>();
  });

  it('accepts the Home empty fixture and a required-null alert item', () => {
    expectTypeOf(emptyFocus).toMatchTypeOf<TodaysFocusResponse>();
    expectTypeOf(alertItem).toMatchTypeOf<TodaysFocusItem>();
    expectTypeOf(alertItem.evidence).toMatchTypeOf<TodaysFocusEvidence>();
  });

  it('does not re-export generated snake_case as the UI type', () => {
    const snakeResponse = {
      pack_version: 'todays_focus/2.1' as const,
      generated_at: '2026-08-09T00:00:00Z',
      status: 'empty' as const,
      max_items: 5,
      item_count: 0,
      items: [] as OpenApiItem[],
      sources_used: [] as OpenApiResponse['sources_used'],
      degraded_sources: [] as OpenApiResponse['degraded_sources'],
      temporal_policy: {
        semantics: 'per_market_local_calendar_day' as const,
        cross_market_rule: 'evidence_uses_target_symbol_market_timezone' as const,
        fallback_timezone: 'Asia/Shanghai',
        window_end: '2026-08-09T00:00:00Z',
        naive_timestamp_policy: 'assume_utc' as const,
        missing_timestamp_policy: 'exclude' as const,
        non_trading_day_policy: 'same_local_day_only' as const,
        markets: [] as OpenApiMarketDayWindow[],
      },
      universe_contract: {
        excluded_non_finite_positions: 0,
        hard_cap: 1000 as const,
        sources: ['watchlist_config'] as OpenApiUniverseContract['sources'],
        symbol_count: 0,
        truncated: false,
      },
      cost_contract: {
        alert_repository_calls: 1,
        analysis_history_repository_calls: 1,
        analysis_runs_triggered: 0 as const,
        database_writes: 0 as const,
        event_repository_calls: 0,
        portfolio_repository_calls: 1,
        provider_calls: 0 as const,
        read_only: true as const,
        zero_extra_fetch: true as const,
      },
      presentation_boundary: {
        alerts_owned_by: 'signal_center' as const,
        duplicate_alert_ui: false as const,
        focus_shows: 'prioritized_symbols_with_evidence_links' as const,
      },
    };
    expectTypeOf(snakeResponse).toMatchTypeOf<OpenApiResponse>();
    expectTypeOf(snakeResponse).not.toMatchTypeOf<TodaysFocusResponse>();
  });

  it('keeps handwritten queries optional-without-null', () => {
    const query = { maxItems: 5, accountId: 1, language: 'en' };
    expectTypeOf(query).toMatchTypeOf<TodaysFocusQuery>();
    expectTypeOf({}).toMatchTypeOf<TodaysFocusQuery>();
    expectTypeOf<'account_id'>().not.toMatchTypeOf<keyof TodaysFocusQuery>();
    expectTypeOf<'max_items'>().not.toMatchTypeOf<keyof TodaysFocusQuery>();
    expectTypeOf({ accountId: null }).not.toMatchTypeOf<TodaysFocusQuery>();
    expectTypeOf({ language: null }).not.toMatchTypeOf<TodaysFocusQuery>();
    expectTypeOf({ account_id: null }).toMatchTypeOf<OpenApiGetQuery>();
    expectTypeOf({ language: null }).toMatchTypeOf<OpenApiGetQuery>();
    expectTypeOf({ accountId: null }).toMatchTypeOf<CamelizeKeys<OpenApiGetQuery>>();
  });
});
