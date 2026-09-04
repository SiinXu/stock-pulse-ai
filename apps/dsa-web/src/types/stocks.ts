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

type _Assert<T extends true> = T;
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
type _QuotePathPostNever = _Assert<
  paths['/api/v1/stocks/{stock_code}/quote']['post'] extends never | undefined ? true : false
>;
type _HistoryPathPostNever = _Assert<
  paths['/api/v1/stocks/{stock_code}/history']['post'] extends never | undefined ? true : false
>;
type _TrustPathPostNever = _Assert<
  paths['/api/v1/stocks/{stock_code}/trust']['post'] extends never | undefined ? true : false
>;

type _OpenApiAnchors = [
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
  _QuotePathPostNever,
  _HistoryPathPostNever,
  _TrustPathPostNever,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type StockHistoryPeriod = 'daily' | 'weekly' | 'monthly';
export type FieldTrustStaleness = OpenApiFieldTrustEntry['staleness'];
export type FieldTrustOrigin = OpenApiFieldTrustEntry['origin'];
export type FieldTrustStatus = OpenApiStockFieldTrustResponse['status'];
export type FieldTrustConfidence = OpenApiFieldTrustAnalysisInput['confidence'];
export type FieldTrustProviderStatus = OpenApiFieldTrustProviderHealth['status'];
export type FieldTrustProviderRole = OpenApiFieldTrustProviderHealth['role'];

export type KLineData = _BindOpenApiAnchors<CamelizeKeys<OpenApiKLineData>>;
export type StockHistoryCandle = KLineData;

/** `updateTime` is the server fetch time of the quote, not a proven market-data timestamp. */
export type StockQuote = CamelizeKeys<OpenApiStockQuote>;

export type StockHistoryResponse = Override<CamelizeKeys<OpenApiStockHistoryResponse>, {
  data: StockHistoryCandle[];
  period: StockHistoryPeriod;
}>;

export type FieldTrustGap = CamelizeKeys<OpenApiFieldTrustGap>;
export type FieldTrustConflictValue = CamelizeKeys<OpenApiFieldTrustConflictValue>;
export type FieldTrustConflictCheck = CamelizeKeys<OpenApiFieldTrustConflictCheck>;
export type FieldTrustEntry = CamelizeKeys<OpenApiFieldTrustEntry>;
export type FieldTrustProviderHealth = CamelizeKeys<OpenApiFieldTrustProviderHealth>;

export type FieldTrustAnalysisInput = Override<CamelizeKeys<OpenApiFieldTrustAnalysisInput>, {
  gaps: FieldTrustGap[];
}>;

export type FieldTrustConflict = Override<CamelizeKeys<OpenApiFieldTrustConflict>, {
  values: FieldTrustConflictValue[];
}>;

export type StockFieldTrustResponse = Override<CamelizeKeys<OpenApiStockFieldTrustResponse>, {
  missingFields: string[];
  fields: FieldTrustEntry[];
  conflicts: FieldTrustConflict[];
  conflictChecks: FieldTrustConflictCheck[];
  providerHealth: FieldTrustProviderHealth[];
}> & {
  analysisInput?: FieldTrustAnalysisInput | null;
};
