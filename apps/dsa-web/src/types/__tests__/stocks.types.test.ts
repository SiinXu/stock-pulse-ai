// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as Stocks from '../stocks';
import type {
  FieldTrustAnalysisInput,
  FieldTrustConflict,
  FieldTrustConflictCheck,
  FieldTrustConflictValue,
  FieldTrustEntry,
  FieldTrustGap,
  FieldTrustProviderHealth,
  KLineData,
  StockFieldTrustResponse,
  StockHistoryCandle,
  StockHistoryPeriod,
  StockHistoryResponse,
  StockQuote,
} from '../stocks';

type OpenApiKLineData = components['schemas']['KLineData'];
type OpenApiStockQuote = components['schemas']['StockQuote'];
type OpenApiStockHistoryResponse = components['schemas']['StockHistoryResponse'];
type OpenApiStockFieldTrustResponse = components['schemas']['StockFieldTrustResponse'];
type OpenApiFieldTrustAnalysisInput = components['schemas']['FieldTrustAnalysisInput'];
type OpenApiFieldTrustConflict = components['schemas']['FieldTrustConflict'];
type OpenApiFieldTrustConflictCheck = components['schemas']['FieldTrustConflictCheck'];
type OpenApiFieldTrustConflictValue = components['schemas']['FieldTrustConflictValue'];
type OpenApiFieldTrustEntry = components['schemas']['FieldTrustEntry'];
type OpenApiFieldTrustGap = components['schemas']['FieldTrustGap'];
type OpenApiFieldTrustProviderHealth = components['schemas']['FieldTrustProviderHealth'];
type OpenApiQuoteGet200 =
  operations['get_stock_quote_api_v1_stocks__stock_code__quote_get']['responses']['200']['content']['application/json'];
type OpenApiHistoryGet200 =
  operations['get_stock_history_api_v1_stocks__stock_code__history_get']['responses']['200']['content']['application/json'];
type OpenApiTrustGet200 =
  operations['getStockFieldTrust']['responses']['200']['content']['application/json'];
type OpenApiQuoteOp = operations['get_stock_quote_api_v1_stocks__stock_code__quote_get'];
type OpenApiHistoryOp = operations['get_stock_history_api_v1_stocks__stock_code__history_get'];
type OpenApiTrustOp = operations['getStockFieldTrust'];
type OpenApiQuotePathGet = paths['/api/v1/stocks/{stock_code}/quote']['get'];
type OpenApiHistoryPathGet = paths['/api/v1/stocks/{stock_code}/history']['get'];
type OpenApiTrustPathGet = paths['/api/v1/stocks/{stock_code}/trust']['get'];

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

type _HasKLineData = _Assert<'KLineData' extends keyof components['schemas'] ? true : false>;
type _HasStockQuote = _Assert<'StockQuote' extends keyof components['schemas'] ? true : false>;
type _HasStockHistoryResponse = _Assert<'StockHistoryResponse' extends keyof components['schemas'] ? true : false>;
type _HasStockFieldTrustResponse = _Assert<
  'StockFieldTrustResponse' extends keyof components['schemas'] ? true : false
>;
type _HasFieldTrustAnalysisInput = _Assert<
  'FieldTrustAnalysisInput' extends keyof components['schemas'] ? true : false
>;
type _HasFieldTrustConflict = _Assert<'FieldTrustConflict' extends keyof components['schemas'] ? true : false>;
type _HasFieldTrustConflictCheck = _Assert<
  'FieldTrustConflictCheck' extends keyof components['schemas'] ? true : false
>;
type _HasFieldTrustConflictValue = _Assert<
  'FieldTrustConflictValue' extends keyof components['schemas'] ? true : false
>;
type _HasFieldTrustEntry = _Assert<'FieldTrustEntry' extends keyof components['schemas'] ? true : false>;
type _HasFieldTrustGap = _Assert<'FieldTrustGap' extends keyof components['schemas'] ? true : false>;
type _HasFieldTrustProviderHealth = _Assert<
  'FieldTrustProviderHealth' extends keyof components['schemas'] ? true : false
>;
type _CheckHasStatus = _Assert<'status' extends keyof OpenApiFieldTrustConflictCheck ? true : false>;
type _ValueHasProvider = _Assert<'provider' extends keyof OpenApiFieldTrustConflictValue ? true : false>;
type _EntryHasStaleness = _Assert<'staleness' extends keyof OpenApiFieldTrustEntry ? true : false>;
type _GapHasCode = _Assert<'code' extends keyof OpenApiFieldTrustGap ? true : false>;
type _HealthHasRole = _Assert<'role' extends keyof OpenApiFieldTrustProviderHealth ? true : false>;

type _Quote200IsComponent = _Assert<OpenApiQuoteGet200 extends OpenApiStockQuote ? true : false>;
type _QuoteComponentIs200 = _Assert<OpenApiStockQuote extends OpenApiQuoteGet200 ? true : false>;
type _History200IsComponent = _Assert<OpenApiHistoryGet200 extends OpenApiStockHistoryResponse ? true : false>;
type _HistoryComponentIs200 = _Assert<OpenApiStockHistoryResponse extends OpenApiHistoryGet200 ? true : false>;
type _Trust200IsComponent = _Assert<OpenApiTrustGet200 extends OpenApiStockFieldTrustResponse ? true : false>;
type _TrustComponentIs200 = _Assert<OpenApiStockFieldTrustResponse extends OpenApiTrustGet200 ? true : false>;
type _QuoteOpIsPath = _Assert<OpenApiQuoteOp extends OpenApiQuotePathGet ? true : false>;
type _QuotePathIsOp = _Assert<OpenApiQuotePathGet extends OpenApiQuoteOp ? true : false>;
type _HistoryOpIsPath = _Assert<OpenApiHistoryOp extends OpenApiHistoryPathGet ? true : false>;
type _HistoryPathIsOp = _Assert<OpenApiHistoryPathGet extends OpenApiHistoryOp ? true : false>;
type _TrustOpIsPath = _Assert<OpenApiTrustOp extends OpenApiTrustPathGet ? true : false>;
type _TrustPathIsOp = _Assert<OpenApiTrustPathGet extends OpenApiTrustOp ? true : false>;
type _QuoteOpHasNeverRequestBody = _Assert<OpenApiQuoteOp extends { requestBody?: never } ? true : false>;
type _HistoryOpHasNeverRequestBody = _Assert<OpenApiHistoryOp extends { requestBody?: never } ? true : false>;
type _TrustOpHasNeverRequestBody = _Assert<OpenApiTrustOp extends { requestBody?: never } ? true : false>;

type _CandleIsKLine = _Assert<StockHistoryCandle extends KLineData ? true : false>;
type _KLineIsCandle = _Assert<KLineData extends StockHistoryCandle ? true : false>;

type _UiHasStockCode = _Assert<'stockCode' extends keyof StockQuote ? true : false>;
type _UiHasCurrentPrice = _Assert<'currentPrice' extends keyof StockQuote ? true : false>;
type _UiHasChangePercent = _Assert<'changePercent' extends keyof StockQuote ? true : false>;
type _UiHasPrevClose = _Assert<'prevClose' extends keyof StockQuote ? true : false>;
type _UiHasUpdateTime = _Assert<'updateTime' extends keyof StockQuote ? true : false>;
type _UiHasHistoryStockCode = _Assert<'stockCode' extends keyof StockHistoryResponse ? true : false>;
type _UiHasChangePercentCandle = _Assert<'changePercent' extends keyof KLineData ? true : false>;
type _UiHasSchemaVersion = _Assert<'schemaVersion' extends keyof StockFieldTrustResponse ? true : false>;
type _UiHasMetadataPresent = _Assert<'metadataPresent' extends keyof StockFieldTrustResponse ? true : false>;
type _UiHasQuoteSource = _Assert<'quoteSource' extends keyof StockFieldTrustResponse ? true : false>;
type _UiHasFetchedAt = _Assert<'fetchedAt' extends keyof StockFieldTrustResponse ? true : false>;
type _UiHasProviderTimestamp = _Assert<'providerTimestamp' extends keyof StockFieldTrustResponse ? true : false>;
type _UiHasStaleSeconds = _Assert<'staleSeconds' extends keyof StockFieldTrustResponse ? true : false>;
type _UiHasIsStale = _Assert<'isStale' extends keyof StockFieldTrustResponse ? true : false>;
type _UiHasFallbackFrom = _Assert<'fallbackFrom' extends keyof StockFieldTrustResponse ? true : false>;
type _UiHasDataQuality = _Assert<'dataQuality' extends keyof StockFieldTrustResponse ? true : false>;
type _UiHasMissingFields = _Assert<'missingFields' extends keyof StockFieldTrustResponse ? true : false>;
type _UiHasConflictChecks = _Assert<'conflictChecks' extends keyof StockFieldTrustResponse ? true : false>;
type _UiHasProviderHealth = _Assert<'providerHealth' extends keyof StockFieldTrustResponse ? true : false>;
type _UiHasAnalysisInput = _Assert<'analysisInput' extends keyof StockFieldTrustResponse ? true : false>;
type _UiHasRelativeDifference = _Assert<'relativeDifference' extends keyof FieldTrustConflict ? true : false>;
type _UiHasPrimaryProvider = _Assert<'primaryProvider' extends keyof FieldTrustConflictCheck ? true : false>;
type _UiHasHealthScore = _Assert<'healthScore' extends keyof FieldTrustProviderHealth ? true : false>;
type _UiHasCircuitState = _Assert<'circuitState' extends keyof FieldTrustProviderHealth ? true : false>;
type _UiHasConflictCount = _Assert<'conflictCount' extends keyof FieldTrustAnalysisInput ? true : false>;
type _UiHasFailedProviderCount = _Assert<'failedProviderCount' extends keyof FieldTrustAnalysisInput ? true : false>;

type _UiLacksStockCodeSnake = _Assert<'stock_code' extends keyof StockQuote ? false : true>;
type _UiLacksCurrentPriceSnake = _Assert<'current_price' extends keyof StockQuote ? false : true>;
type _UiLacksChangePercentSnake = _Assert<'change_percent' extends keyof StockQuote ? false : true>;
type _UiLacksPrevCloseSnake = _Assert<'prev_close' extends keyof StockQuote ? false : true>;
type _UiLacksUpdateTimeSnake = _Assert<'update_time' extends keyof StockQuote ? false : true>;
type _UiLacksChangePercentCandleSnake = _Assert<'change_percent' extends keyof KLineData ? false : true>;
type _UiLacksSchemaVersionSnake = _Assert<'schema_version' extends keyof StockFieldTrustResponse ? false : true>;
type _UiLacksMetadataPresentSnake = _Assert<'metadata_present' extends keyof StockFieldTrustResponse ? false : true>;
type _UiLacksMissingFieldsSnake = _Assert<'missing_fields' extends keyof StockFieldTrustResponse ? false : true>;
type _UiLacksConflictChecksSnake = _Assert<'conflict_checks' extends keyof StockFieldTrustResponse ? false : true>;
type _UiLacksProviderHealthSnake = _Assert<'provider_health' extends keyof StockFieldTrustResponse ? false : true>;
type _UiLacksAnalysisInputSnake = _Assert<'analysis_input' extends keyof StockFieldTrustResponse ? false : true>;
type _UiLacksRelativeDifferenceSnake = _Assert<'relative_difference' extends keyof FieldTrustConflict ? false : true>;
type _UiLacksPrimaryProviderSnake = _Assert<'primary_provider' extends keyof FieldTrustConflictCheck ? false : true>;
type _UiLacksHealthScoreSnake = _Assert<'health_score' extends keyof FieldTrustProviderHealth ? false : true>;
type _UiLacksConflictCountSnake = _Assert<'conflict_count' extends keyof FieldTrustAnalysisInput ? false : true>;

type _GeneratedHasStockCodeSnake = _Assert<'stock_code' extends keyof OpenApiStockQuote ? true : false>;
type _GeneratedHasCurrentPriceSnake = _Assert<'current_price' extends keyof OpenApiStockQuote ? true : false>;
type _GeneratedHasChangePercentSnake = _Assert<'change_percent' extends keyof OpenApiStockQuote ? true : false>;
type _GeneratedHasSchemaVersionSnake = _Assert<
  'schema_version' extends keyof OpenApiStockFieldTrustResponse ? true : false
>;
type _GeneratedHasMissingFieldsSnake = _Assert<
  'missing_fields' extends keyof OpenApiStockFieldTrustResponse ? true : false
>;
type _GeneratedHasConflictChecksSnake = _Assert<
  'conflict_checks' extends keyof OpenApiStockFieldTrustResponse ? true : false
>;
type _GeneratedHasProviderHealthSnake = _Assert<
  'provider_health' extends keyof OpenApiStockFieldTrustResponse ? true : false
>;
type _GeneratedHasAnalysisInputSnake = _Assert<
  'analysis_input' extends keyof OpenApiStockFieldTrustResponse ? true : false
>;
type _GeneratedLacksStockCodeCamel = _Assert<'stockCode' extends keyof OpenApiStockQuote ? false : true>;
type _GeneratedLacksMissingFieldsCamel = _Assert<
  'missingFields' extends keyof OpenApiStockFieldTrustResponse ? false : true
>;

type _UiDataRequired = _Assert<IsOptional<StockHistoryResponse, 'data'> extends false ? true : false>;
type _UiPeriodRequired = _Assert<IsOptional<StockHistoryResponse, 'period'> extends false ? true : false>;
type _UiGapsRequired = _Assert<IsOptional<FieldTrustAnalysisInput, 'gaps'> extends false ? true : false>;
type _UiValuesRequired = _Assert<IsOptional<FieldTrustConflict, 'values'> extends false ? true : false>;
type _UiMissingFieldsRequired = _Assert<
  IsOptional<StockFieldTrustResponse, 'missingFields'> extends false ? true : false
>;
type _UiFieldsRequired = _Assert<IsOptional<StockFieldTrustResponse, 'fields'> extends false ? true : false>;
type _UiConflictsRequired = _Assert<IsOptional<StockFieldTrustResponse, 'conflicts'> extends false ? true : false>;
type _UiConflictChecksRequired = _Assert<
  IsOptional<StockFieldTrustResponse, 'conflictChecks'> extends false ? true : false
>;
type _UiProviderHealthRequired = _Assert<
  IsOptional<StockFieldTrustResponse, 'providerHealth'> extends false ? true : false
>;
type _UiSeverityRequired = _Assert<IsOptional<FieldTrustConflict, 'severity'> extends false ? true : false>;
type _UiAnalysisInputOptional = _Assert<IsOptional<StockFieldTrustResponse, 'analysisInput'>>;
type _NestedAnalysisIsNamed = _Assert<
  NonNullable<StockFieldTrustResponse['analysisInput']> extends FieldTrustAnalysisInput ? true : false
>;
type _NamedAnalysisIsNested = _Assert<
  FieldTrustAnalysisInput extends NonNullable<StockFieldTrustResponse['analysisInput']> ? true : false
>;

type _GeneratedDataOptional = _Assert<IsOptional<OpenApiStockHistoryResponse, 'data'>>;
type _GeneratedGapsOptional = _Assert<IsOptional<OpenApiFieldTrustAnalysisInput, 'gaps'>>;
type _GeneratedValuesOptional = _Assert<IsOptional<OpenApiFieldTrustConflict, 'values'>>;
type _GeneratedMissingFieldsOptional = _Assert<IsOptional<OpenApiStockFieldTrustResponse, 'missing_fields'>>;
type _GeneratedFieldsOptional = _Assert<IsOptional<OpenApiStockFieldTrustResponse, 'fields'>>;
type _GeneratedConflictsOptional = _Assert<IsOptional<OpenApiStockFieldTrustResponse, 'conflicts'>>;
type _GeneratedConflictChecksOptional = _Assert<IsOptional<OpenApiStockFieldTrustResponse, 'conflict_checks'>>;
type _GeneratedProviderHealthOptional = _Assert<IsOptional<OpenApiStockFieldTrustResponse, 'provider_health'>>;
type _GeneratedSeverityRequired = _Assert<
  IsOptional<OpenApiFieldTrustConflict, 'severity'> extends false ? true : false
>;
type _NaiveCamelDataOptional = _Assert<IsOptional<CamelizeKeys<OpenApiStockHistoryResponse>, 'data'>>;
type _NaiveCamelGapsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiFieldTrustAnalysisInput>, 'gaps'>>;
type _NaiveCamelValuesOptional = _Assert<IsOptional<CamelizeKeys<OpenApiFieldTrustConflict>, 'values'>>;
type _NaiveCamelMissingFieldsOptional = _Assert<
  IsOptional<CamelizeKeys<OpenApiStockFieldTrustResponse>, 'missingFields'>
>;
type _NaiveCamelPeriodIsString = _Assert<
  string extends CamelizeKeys<OpenApiStockHistoryResponse>['period'] ? true : false
>;
type _GeneratedPeriodIsString = _Assert<string extends OpenApiStockHistoryResponse['period'] ? true : false>;

type _OmitUiData = _Assert<Omit<StockHistoryResponse, 'data'> extends StockHistoryResponse ? false : true>;
type _OmitGeneratedData = _Assert<
  Omit<OpenApiStockHistoryResponse, 'data'> extends OpenApiStockHistoryResponse ? true : false
>;
type _OmitUiGaps = _Assert<Omit<FieldTrustAnalysisInput, 'gaps'> extends FieldTrustAnalysisInput ? false : true>;
type _OmitGeneratedGaps = _Assert<
  Omit<OpenApiFieldTrustAnalysisInput, 'gaps'> extends OpenApiFieldTrustAnalysisInput ? true : false
>;
type _OmitUiValues = _Assert<Omit<FieldTrustConflict, 'values'> extends FieldTrustConflict ? false : true>;
type _OmitGeneratedValues = _Assert<
  Omit<OpenApiFieldTrustConflict, 'values'> extends OpenApiFieldTrustConflict ? true : false
>;
type _OmitUiMissingFields = _Assert<
  Omit<StockFieldTrustResponse, 'missingFields'> extends StockFieldTrustResponse ? false : true
>;
type _OmitGeneratedMissingFields = _Assert<
  Omit<OpenApiStockFieldTrustResponse, 'missing_fields'> extends OpenApiStockFieldTrustResponse ? true : false
>;
type _OmitUiFields = _Assert<Omit<StockFieldTrustResponse, 'fields'> extends StockFieldTrustResponse ? false : true>;
type _OmitGeneratedFields = _Assert<
  Omit<OpenApiStockFieldTrustResponse, 'fields'> extends OpenApiStockFieldTrustResponse ? true : false
>;
type _OmitUiConflicts = _Assert<
  Omit<StockFieldTrustResponse, 'conflicts'> extends StockFieldTrustResponse ? false : true
>;
type _OmitGeneratedConflicts = _Assert<
  Omit<OpenApiStockFieldTrustResponse, 'conflicts'> extends OpenApiStockFieldTrustResponse ? true : false
>;
type _OmitUiConflictChecks = _Assert<
  Omit<StockFieldTrustResponse, 'conflictChecks'> extends StockFieldTrustResponse ? false : true
>;
type _OmitGeneratedConflictChecks = _Assert<
  Omit<OpenApiStockFieldTrustResponse, 'conflict_checks'> extends OpenApiStockFieldTrustResponse ? true : false
>;
type _OmitUiProviderHealth = _Assert<
  Omit<StockFieldTrustResponse, 'providerHealth'> extends StockFieldTrustResponse ? false : true
>;
type _OmitGeneratedProviderHealth = _Assert<
  Omit<OpenApiStockFieldTrustResponse, 'provider_health'> extends OpenApiStockFieldTrustResponse ? true : false
>;
type _OmitUiSeverity = _Assert<Omit<FieldTrustConflict, 'severity'> extends FieldTrustConflict ? false : true>;
type _OmitGeneratedSeverity = _Assert<
  Omit<OpenApiFieldTrustConflict, 'severity'> extends OpenApiFieldTrustConflict ? false : true
>;

type _DailyAssignable = _Assert<'daily' extends StockHistoryPeriod ? true : false>;
type _WeeklyAssignable = _Assert<'weekly' extends StockHistoryPeriod ? true : false>;
type _MonthlyAssignable = _Assert<'monthly' extends StockHistoryPeriod ? true : false>;
type _YearlyRejected = _Assert<'yearly' extends StockHistoryPeriod ? false : true>;
type _StringPeriodRejected = _Assert<string extends StockHistoryPeriod ? false : true>;
type _GeneratedYearlyAssignable = _Assert<'yearly' extends OpenApiStockHistoryResponse['period'] ? true : false>;
type _UiPeriodClosed = _Assert<StockHistoryResponse['period'] extends StockHistoryPeriod ? true : false>;
type _FreshAssignable = _Assert<'fresh' extends FieldTrustEntry['staleness'] ? true : false>;
type _StaleAssignable = _Assert<'stale' extends FieldTrustEntry['staleness'] ? true : false>;
type _UnknownStalenessAssignable = _Assert<'unknown' extends FieldTrustEntry['staleness'] ? true : false>;
type _StringStalenessRejected = _Assert<string extends FieldTrustEntry['staleness'] ? false : true>;
type _HighConfidenceAssignable = _Assert<'high' extends FieldTrustAnalysisInput['confidence'] ? true : false>;
type _StringConfidenceRejected = _Assert<string extends FieldTrustAnalysisInput['confidence'] ? false : true>;
type _EvaluatedAssignable = _Assert<'evaluated' extends FieldTrustConflictCheck['status'] ? true : false>;
type _SkippedAssignable = _Assert<'skipped' extends FieldTrustConflictCheck['status'] ? true : false>;
type _StringCheckStatusRejected = _Assert<string extends FieldTrustConflictCheck['status'] ? false : true>;
type _SeverityIsString = _Assert<string extends FieldTrustConflict['severity'] ? true : false>;
type _GeneratedSeverityIsString = _Assert<string extends OpenApiFieldTrustConflict['severity'] ? true : false>;

type NarrowCandle = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
};
type NarrowHistory = {
  stockCode: string;
  period: 'daily';
  data: NarrowCandle[];
};
type NarrowQuote = {
  stockCode: string;
  currentPrice: number;
};
type NarrowGap = { code: string };
type NarrowAnalysisInput = {
  schemaVersion: 'field_trust_analysis_input/1.0';
  confidence: 'medium';
  gaps: NarrowGap[];
  conflictCount: number;
  failedProviderCount: number;
};
type NarrowConflictValue = { provider: string; value: number };
type NarrowConflict = {
  field: string;
  severity: string;
  values: NarrowConflictValue[];
};
type NarrowTrust = {
  schemaVersion: 'field_trust_view/1.0';
  stockCode: string;
  status: 'ok';
  metadataPresent: boolean;
  missingFields: string[];
  fields: [];
  conflicts: NarrowConflict[];
  conflictChecks: [];
  providerHealth: [];
};

type _NarrowCandleAssignable = _Assert<NarrowCandle extends KLineData ? true : false>;
type _NarrowCandleAssignableToPublic = _Assert<NarrowCandle extends StockHistoryCandle ? true : false>;
type _NarrowHistoryAssignable = _Assert<NarrowHistory extends StockHistoryResponse ? true : false>;
type _NarrowQuoteAssignable = _Assert<NarrowQuote extends StockQuote ? true : false>;
type _NarrowGapAssignable = _Assert<NarrowGap extends FieldTrustGap ? true : false>;
type _NarrowAnalysisAssignable = _Assert<NarrowAnalysisInput extends FieldTrustAnalysisInput ? true : false>;
type _NarrowConflictAssignable = _Assert<NarrowConflict extends FieldTrustConflict ? true : false>;
type _NarrowValueAssignable = _Assert<NarrowConflictValue extends FieldTrustConflictValue ? true : false>;
type _NarrowTrustAssignable = _Assert<NarrowTrust extends StockFieldTrustResponse ? true : false>;

type MissingHistoryData = {
  stockCode: string;
  period: 'daily';
};
type _MissingHistoryDataRejected = _Assert<MissingHistoryData extends StockHistoryResponse ? false : true>;
type YearlyHistory = {
  stockCode: string;
  period: 'yearly';
  data: NarrowCandle[];
};
type _YearlyHistoryRejected = _Assert<YearlyHistory extends StockHistoryResponse ? false : true>;
type MissingGaps = {
  schemaVersion: 'field_trust_analysis_input/1.0';
  confidence: 'medium';
  conflictCount: number;
  failedProviderCount: number;
};
type _MissingGapsRejected = _Assert<MissingGaps extends FieldTrustAnalysisInput ? false : true>;
type MissingValues = {
  field: string;
  severity: string;
};
type _MissingValuesRejected = _Assert<MissingValues extends FieldTrustConflict ? false : true>;
type MissingTrustArrays = {
  schemaVersion: 'field_trust_view/1.0';
  stockCode: string;
  status: 'ok';
  metadataPresent: boolean;
};
type _MissingTrustArraysRejected = _Assert<MissingTrustArrays extends StockFieldTrustResponse ? false : true>;

type SnakeQuote = {
  stock_code: string;
  current_price: number;
};
type _SnakeQuoteMatchesGenerated = _Assert<SnakeQuote extends OpenApiStockQuote ? true : false>;
type _SnakeQuoteDoesNotMatchUi = _Assert<SnakeQuote extends StockQuote ? false : true>;
type SnakeHistory = {
  stock_code: string;
  period: string;
};
type _SnakeHistoryMatchesGenerated = _Assert<SnakeHistory extends OpenApiStockHistoryResponse ? true : false>;
type _SnakeHistoryDoesNotMatchUi = _Assert<SnakeHistory extends StockHistoryResponse ? false : true>;
type SnakeTrust = {
  schema_version: 'field_trust_view/1.0';
  stock_code: string;
  status: 'ok';
  metadata_present: boolean;
};
type _SnakeTrustMatchesGenerated = _Assert<SnakeTrust extends OpenApiStockFieldTrustResponse ? true : false>;
type _SnakeTrustDoesNotMatchUi = _Assert<SnakeTrust extends StockFieldTrustResponse ? false : true>;
type SnakeKLine = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  change_percent: number;
};
type _SnakeKLineMatchesGenerated = _Assert<SnakeKLine extends OpenApiKLineData ? true : false>;
type _SnakeKLineChangePercentNotUiKey = _Assert<'change_percent' extends keyof KLineData ? false : true>;
type SnakeConflict = {
  field: string;
  severity: string;
};
type _SnakeConflictMatchesGenerated = _Assert<SnakeConflict extends OpenApiFieldTrustConflict ? true : false>;
type _SnakeConflictDoesNotMatchUi = _Assert<SnakeConflict extends FieldTrustConflict ? false : true>;

type _CompileTimePins = [
  _HasKLineData,
  _HasStockQuote,
  _HasStockHistoryResponse,
  _HasStockFieldTrustResponse,
  _HasFieldTrustAnalysisInput,
  _HasFieldTrustConflict,
  _HasFieldTrustConflictCheck,
  _HasFieldTrustConflictValue,
  _HasFieldTrustEntry,
  _HasFieldTrustGap,
  _HasFieldTrustProviderHealth,
  _CheckHasStatus,
  _ValueHasProvider,
  _EntryHasStaleness,
  _GapHasCode,
  _HealthHasRole,
  _Quote200IsComponent,
  _QuoteComponentIs200,
  _History200IsComponent,
  _HistoryComponentIs200,
  _Trust200IsComponent,
  _TrustComponentIs200,
  _QuoteOpIsPath,
  _QuotePathIsOp,
  _HistoryOpIsPath,
  _HistoryPathIsOp,
  _TrustOpIsPath,
  _TrustPathIsOp,
  _QuoteOpHasNeverRequestBody,
  _HistoryOpHasNeverRequestBody,
  _TrustOpHasNeverRequestBody,
  _CandleIsKLine,
  _KLineIsCandle,
  _UiHasStockCode,
  _UiHasCurrentPrice,
  _UiHasChangePercent,
  _UiHasPrevClose,
  _UiHasUpdateTime,
  _UiHasHistoryStockCode,
  _UiHasChangePercentCandle,
  _UiHasSchemaVersion,
  _UiHasMetadataPresent,
  _UiHasQuoteSource,
  _UiHasFetchedAt,
  _UiHasProviderTimestamp,
  _UiHasStaleSeconds,
  _UiHasIsStale,
  _UiHasFallbackFrom,
  _UiHasDataQuality,
  _UiHasMissingFields,
  _UiHasConflictChecks,
  _UiHasProviderHealth,
  _UiHasAnalysisInput,
  _UiHasRelativeDifference,
  _UiHasPrimaryProvider,
  _UiHasHealthScore,
  _UiHasCircuitState,
  _UiHasConflictCount,
  _UiHasFailedProviderCount,
  _UiLacksStockCodeSnake,
  _UiLacksCurrentPriceSnake,
  _UiLacksChangePercentSnake,
  _UiLacksPrevCloseSnake,
  _UiLacksUpdateTimeSnake,
  _UiLacksChangePercentCandleSnake,
  _UiLacksSchemaVersionSnake,
  _UiLacksMetadataPresentSnake,
  _UiLacksMissingFieldsSnake,
  _UiLacksConflictChecksSnake,
  _UiLacksProviderHealthSnake,
  _UiLacksAnalysisInputSnake,
  _UiLacksRelativeDifferenceSnake,
  _UiLacksPrimaryProviderSnake,
  _UiLacksHealthScoreSnake,
  _UiLacksConflictCountSnake,
  _GeneratedHasStockCodeSnake,
  _GeneratedHasCurrentPriceSnake,
  _GeneratedHasChangePercentSnake,
  _GeneratedHasSchemaVersionSnake,
  _GeneratedHasMissingFieldsSnake,
  _GeneratedHasConflictChecksSnake,
  _GeneratedHasProviderHealthSnake,
  _GeneratedHasAnalysisInputSnake,
  _GeneratedLacksStockCodeCamel,
  _GeneratedLacksMissingFieldsCamel,
  _UiDataRequired,
  _UiPeriodRequired,
  _UiGapsRequired,
  _UiValuesRequired,
  _UiMissingFieldsRequired,
  _UiFieldsRequired,
  _UiConflictsRequired,
  _UiConflictChecksRequired,
  _UiProviderHealthRequired,
  _UiSeverityRequired,
  _UiAnalysisInputOptional,
  _NestedAnalysisIsNamed,
  _NamedAnalysisIsNested,
  _GeneratedDataOptional,
  _GeneratedGapsOptional,
  _GeneratedValuesOptional,
  _GeneratedMissingFieldsOptional,
  _GeneratedFieldsOptional,
  _GeneratedConflictsOptional,
  _GeneratedConflictChecksOptional,
  _GeneratedProviderHealthOptional,
  _GeneratedSeverityRequired,
  _NaiveCamelDataOptional,
  _NaiveCamelGapsOptional,
  _NaiveCamelValuesOptional,
  _NaiveCamelMissingFieldsOptional,
  _NaiveCamelPeriodIsString,
  _GeneratedPeriodIsString,
  _OmitUiData,
  _OmitGeneratedData,
  _OmitUiGaps,
  _OmitGeneratedGaps,
  _OmitUiValues,
  _OmitGeneratedValues,
  _OmitUiMissingFields,
  _OmitGeneratedMissingFields,
  _OmitUiFields,
  _OmitGeneratedFields,
  _OmitUiConflicts,
  _OmitGeneratedConflicts,
  _OmitUiConflictChecks,
  _OmitGeneratedConflictChecks,
  _OmitUiProviderHealth,
  _OmitGeneratedProviderHealth,
  _OmitUiSeverity,
  _OmitGeneratedSeverity,
  _DailyAssignable,
  _WeeklyAssignable,
  _MonthlyAssignable,
  _YearlyRejected,
  _StringPeriodRejected,
  _GeneratedYearlyAssignable,
  _UiPeriodClosed,
  _FreshAssignable,
  _StaleAssignable,
  _UnknownStalenessAssignable,
  _StringStalenessRejected,
  _HighConfidenceAssignable,
  _StringConfidenceRejected,
  _EvaluatedAssignable,
  _SkippedAssignable,
  _StringCheckStatusRejected,
  _SeverityIsString,
  _GeneratedSeverityIsString,
  _NarrowCandleAssignable,
  _NarrowCandleAssignableToPublic,
  _NarrowHistoryAssignable,
  _NarrowQuoteAssignable,
  _NarrowGapAssignable,
  _NarrowAnalysisAssignable,
  _NarrowConflictAssignable,
  _NarrowValueAssignable,
  _NarrowTrustAssignable,
  _MissingHistoryDataRejected,
  _YearlyHistoryRejected,
  _MissingGapsRejected,
  _MissingValuesRejected,
  _MissingTrustArraysRejected,
  _SnakeQuoteMatchesGenerated,
  _SnakeQuoteDoesNotMatchUi,
  _SnakeHistoryMatchesGenerated,
  _SnakeHistoryDoesNotMatchUi,
  _SnakeTrustMatchesGenerated,
  _SnakeTrustDoesNotMatchUi,
  _SnakeKLineMatchesGenerated,
  _SnakeKLineChangePercentNotUiKey,
  _SnakeConflictMatchesGenerated,
  _SnakeConflictDoesNotMatchUi,
];

describe('stocks OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    // ESM namespace objects carry Symbol.toStringTag='Module'; enumerable exports must stay empty.
    expect({ ...Stocks }).toEqual({});
    expect(Object.keys(Stocks)).toEqual([]);
    expect(Object.getOwnPropertyNames(Stocks)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates three GET 200 JSON bodies to the generated components', () => {
    expectTypeOf<OpenApiQuoteGet200>().toEqualTypeOf<OpenApiStockQuote>();
    expectTypeOf<OpenApiHistoryGet200>().toEqualTypeOf<OpenApiStockHistoryResponse>();
    expectTypeOf<OpenApiTrustGet200>().toEqualTypeOf<OpenApiStockFieldTrustResponse>();
    expectTypeOf<OpenApiQuoteOp>().toEqualTypeOf<OpenApiQuotePathGet>();
    expectTypeOf<OpenApiHistoryOp>().toEqualTypeOf<OpenApiHistoryPathGet>();
    expectTypeOf<OpenApiTrustOp>().toEqualTypeOf<OpenApiTrustPathGet>();
  });

  it('keeps GET requestBody never on quote, history, and field-trust', () => {
    type QuoteHasNever = OpenApiQuoteOp extends { requestBody?: never } ? true : false;
    type HistoryHasNever = OpenApiHistoryOp extends { requestBody?: never } ? true : false;
    type TrustHasNever = OpenApiTrustOp extends { requestBody?: never } ? true : false;
    expectTypeOf<QuoteHasNever>().toEqualTypeOf<true>();
    expectTypeOf<HistoryHasNever>().toEqualTypeOf<true>();
    expectTypeOf<TrustHasNever>().toEqualTypeOf<true>();
  });

  it('keeps the nine UI overrides required or closed versus generated optionality', () => {
    expectTypeOf<Omit<StockHistoryResponse, 'data'>>().not.toMatchTypeOf<StockHistoryResponse>();
    expectTypeOf<Omit<OpenApiStockHistoryResponse, 'data'>>().toMatchTypeOf<OpenApiStockHistoryResponse>();
    expectTypeOf<StockHistoryResponse['period']>().toEqualTypeOf<StockHistoryPeriod>();
    expectTypeOf<OpenApiStockHistoryResponse['period']>().toEqualTypeOf<string>();
    expectTypeOf<'daily' | 'weekly' | 'monthly'>().toEqualTypeOf<StockHistoryPeriod>();
    expectTypeOf<string>().not.toMatchTypeOf<StockHistoryPeriod>();
    expectTypeOf<Omit<FieldTrustAnalysisInput, 'gaps'>>().not.toMatchTypeOf<FieldTrustAnalysisInput>();
    expectTypeOf<Omit<OpenApiFieldTrustAnalysisInput, 'gaps'>>().toMatchTypeOf<OpenApiFieldTrustAnalysisInput>();
    expectTypeOf<Omit<FieldTrustConflict, 'values'>>().not.toMatchTypeOf<FieldTrustConflict>();
    expectTypeOf<Omit<OpenApiFieldTrustConflict, 'values'>>().toMatchTypeOf<OpenApiFieldTrustConflict>();
    expectTypeOf<Omit<StockFieldTrustResponse, 'missingFields'>>().not.toMatchTypeOf<StockFieldTrustResponse>();
    expectTypeOf<Omit<OpenApiStockFieldTrustResponse, 'missing_fields'>>().toMatchTypeOf<
      OpenApiStockFieldTrustResponse
    >();
    expectTypeOf<Omit<StockFieldTrustResponse, 'fields'>>().not.toMatchTypeOf<StockFieldTrustResponse>();
    expectTypeOf<Omit<OpenApiStockFieldTrustResponse, 'fields'>>().toMatchTypeOf<OpenApiStockFieldTrustResponse>();
    expectTypeOf<Omit<StockFieldTrustResponse, 'conflicts'>>().not.toMatchTypeOf<StockFieldTrustResponse>();
    expectTypeOf<Omit<OpenApiStockFieldTrustResponse, 'conflicts'>>().toMatchTypeOf<OpenApiStockFieldTrustResponse>();
    expectTypeOf<Omit<StockFieldTrustResponse, 'conflictChecks'>>().not.toMatchTypeOf<StockFieldTrustResponse>();
    expectTypeOf<Omit<OpenApiStockFieldTrustResponse, 'conflict_checks'>>().toMatchTypeOf<
      OpenApiStockFieldTrustResponse
    >();
    expectTypeOf<Omit<StockFieldTrustResponse, 'providerHealth'>>().not.toMatchTypeOf<StockFieldTrustResponse>();
    expectTypeOf<Omit<OpenApiStockFieldTrustResponse, 'provider_health'>>().toMatchTypeOf<
      OpenApiStockFieldTrustResponse
    >();
    expectTypeOf<Omit<FieldTrustConflict, 'severity'>>().not.toMatchTypeOf<FieldTrustConflict>();
    expectTypeOf<Omit<OpenApiFieldTrustConflict, 'severity'>>().not.toMatchTypeOf<OpenApiFieldTrustConflict>();
    expectTypeOf<FieldTrustConflict['severity']>().toEqualTypeOf<string>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof StockQuote>().not.toMatchTypeOf<
      'stock_code' | 'current_price' | 'change_percent' | 'prev_close' | 'update_time'
    >();
    expectTypeOf<keyof StockHistoryResponse>().not.toMatchTypeOf<'stock_code' | 'stock_name'>();
    expectTypeOf<keyof KLineData>().not.toMatchTypeOf<'change_percent'>();
    expectTypeOf<keyof StockFieldTrustResponse>().not.toMatchTypeOf<
      'schema_version' | 'missing_fields' | 'conflict_checks' | 'provider_health' | 'analysis_input'
    >();
    expectTypeOf<keyof OpenApiStockQuote>().not.toMatchTypeOf<'stockCode' | 'currentPrice'>();
    expectTypeOf<keyof OpenApiStockFieldTrustResponse>().not.toMatchTypeOf<'missingFields' | 'providerHealth'>();

    type UiHasStockCode = 'stockCode' extends keyof StockQuote ? true : false;
    type UiHasStockCodeSnake = 'stock_code' extends keyof StockQuote ? true : false;
    type GeneratedHasStockCodeSnake = 'stock_code' extends keyof OpenApiStockQuote ? true : false;
    type GeneratedHasStockCodeCamel = 'stockCode' extends keyof OpenApiStockQuote ? true : false;
    type UiHasMissingFields = 'missingFields' extends keyof StockFieldTrustResponse ? true : false;
    type UiHasMissingFieldsSnake = 'missing_fields' extends keyof StockFieldTrustResponse ? true : false;
    type GeneratedHasMissingFieldsSnake = 'missing_fields' extends keyof OpenApiStockFieldTrustResponse ? true : false;

    expectTypeOf<UiHasStockCode>().toEqualTypeOf<true>();
    expectTypeOf<UiHasStockCodeSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasStockCodeSnake>().toEqualTypeOf<true>();
    expectTypeOf<GeneratedHasStockCodeCamel>().toEqualTypeOf<false>();
    expectTypeOf<UiHasMissingFields>().toEqualTypeOf<true>();
    expectTypeOf<UiHasMissingFieldsSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasMissingFieldsSnake>().toEqualTypeOf<true>();
  });

  it('does not re-export generated snake_case as the UI type', () => {
    const snakeQuote = {
      stock_code: '600519',
      current_price: 1800,
    };
    const snakeHistory = {
      stock_code: '600519',
      period: 'daily',
    };
    const snakeTrust = {
      schema_version: 'field_trust_view/1.0' as const,
      stock_code: '600519',
      status: 'ok' as const,
      metadata_present: true,
    };
    const snakeCandle = {
      date: '2024-01-01',
      open: 1,
      high: 2,
      low: 0.5,
      close: 1.5,
      change_percent: 0.84,
    };
    expectTypeOf(snakeQuote).toMatchTypeOf<OpenApiStockQuote>();
    expectTypeOf(snakeQuote).not.toMatchTypeOf<StockQuote>();
    expectTypeOf(snakeHistory).toMatchTypeOf<OpenApiStockHistoryResponse>();
    expectTypeOf(snakeHistory).not.toMatchTypeOf<StockHistoryResponse>();
    expectTypeOf(snakeTrust).toMatchTypeOf<OpenApiStockFieldTrustResponse>();
    expectTypeOf(snakeTrust).not.toMatchTypeOf<StockFieldTrustResponse>();
    expectTypeOf(snakeCandle).toMatchTypeOf<OpenApiKLineData>();
    expectTypeOf<'change_percent'>().not.toMatchTypeOf<keyof KLineData>();
    expectTypeOf<'changePercent'>().toMatchTypeOf<keyof KLineData>();
  });

  it('binds public StockHistoryCandle to KLineData and accepts a required-array history fixture', () => {
    const candle: StockHistoryCandle = {
      date: '2024-01-01',
      open: 1785,
      high: 1810,
      low: 1780,
      close: 1800,
    };
    const history: StockHistoryResponse = {
      stockCode: '600519',
      period: 'daily',
      data: [candle],
    };
    expectTypeOf(candle).toMatchTypeOf<KLineData>();
    expectTypeOf(candle).toMatchTypeOf<StockHistoryCandle>();
    expectTypeOf(history).toMatchTypeOf<StockHistoryResponse>();
    expectTypeOf(history.data[0]).toMatchTypeOf<KLineData>();
  });
});
