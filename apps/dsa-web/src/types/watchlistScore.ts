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

type OpenApiFactorSource = components['schemas']['WatchlistScoreFactorSource'];
type OpenApiFactor = components['schemas']['WatchlistScoreFactor'];
type OpenApiItem = components['schemas']['WatchlistScoreItem'];
type OpenApiQueryCount = components['schemas']['WatchlistScoreQueryCount'];
type OpenApiSourceRows = components['schemas']['WatchlistScoreSourceRows'];
type OpenApiResponse = components['schemas']['WatchlistScoreResponse'];
type WatchlistScoreRequest = components['schemas']['WatchlistScoreRequest'];
type OpenApiScorePost200 =
  operations['scoreWatchlistSymbols']['responses']['200']['content']['application/json'];
type OpenApiScorePostBody =
  operations['scoreWatchlistSymbols']['requestBody']['content']['application/json'];
type OpenApiPathPost = paths['/api/v1/watchlist/scores']['post'];
type OpenApiOp = operations['scoreWatchlistSymbols'];

type _Assert<T extends true> = T;
type _Post200IsResponse = _Assert<OpenApiScorePost200 extends OpenApiResponse ? true : false>;
type _ResponseIsPost200 = _Assert<OpenApiResponse extends OpenApiScorePost200 ? true : false>;
type _PostBodyIsRequest = _Assert<OpenApiScorePostBody extends WatchlistScoreRequest ? true : false>;
type _RequestIsPostBody = _Assert<WatchlistScoreRequest extends OpenApiScorePostBody ? true : false>;
type _OpIsPath = _Assert<OpenApiOp extends OpenApiPathPost ? true : false>;
type _PathIsOp = _Assert<OpenApiPathPost extends OpenApiOp ? true : false>;
type _QueryCountIsNested = _Assert<OpenApiQueryCount extends { analysis: number; signals: number } ? true : false>;
type _NestedIsQueryCount = _Assert<{ analysis: number; signals: number } extends OpenApiQueryCount ? true : false>;
type _SourceRowsIsNested = _Assert<OpenApiSourceRows extends { analysis: number; signals: number } ? true : false>;
type _NestedIsSourceRows = _Assert<{ analysis: number; signals: number } extends OpenApiSourceRows ? true : false>;

type _OpenApiAnchors = [
  _Post200IsResponse,
  _ResponseIsPost200,
  _PostBodyIsRequest,
  _RequestIsPostBody,
  _OpIsPath,
  _PathIsOp,
  _QueryCountIsNested,
  _NestedIsQueryCount,
  _SourceRowsIsNested,
  _NestedIsSourceRows,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type WatchlistScoreFactorKey = OpenApiFactor['key'];
export type WatchlistScoreFactorStatus = OpenApiFactor['status'];
export type WatchlistScoreDegradationReason = NonNullable<OpenApiFactor['reason']>;

export type WatchlistScoreFactorSource = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiFactorSource>, {
  id: number | null;
  sourceReportId: number | null;
  profile: string | null;
  asOf: string | null;
  expiresAt: string | null;
  formulaVersion: 'watchlist_score_v1';
}>>;

export type WatchlistScoreFactor = Override<CamelizeKeys<OpenApiFactor>, {
  key: WatchlistScoreFactorKey;
  status: WatchlistScoreFactorStatus;
  value: string | number | null;
  params: Record<string, string | number | boolean | null>;
  reason: WatchlistScoreDegradationReason | null;
  source: WatchlistScoreFactorSource;
}>;

export type WatchlistScoreStatus = OpenApiItem['status'];
export type WatchlistScoreSortMode = OpenApiResponse['sort'];
export type WatchlistScoreFreshness = OpenApiItem['freshness'];

export type WatchlistScoreItem = Override<CamelizeKeys<OpenApiItem>, {
  stockCode: string;
  status: WatchlistScoreStatus;
  score: number | null;
  asOf: string | null;
  ageDays: number | null;
  analysisId: number | null;
  operationAdvice: string | null;
  factors: WatchlistScoreFactor[];
  freshness: WatchlistScoreFreshness;
  degradedReasons: WatchlistScoreDegradationReason[];
}>;

export type WatchlistScoreResponse = Override<CamelizeKeys<OpenApiResponse>, {
  formulaVersion: 'watchlist_score_v1';
  scoringMode: 'aggregate_existing';
  sort: WatchlistScoreSortMode;
  items: WatchlistScoreItem[];
  queryCount: { analysis: number; signals: number };
  sourceRows: { analysis: number; signals: number };
  disclaimerKey: 'watchlist_score.disclaimer';
}>;
