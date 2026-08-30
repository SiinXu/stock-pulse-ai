// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { components, operations } from './api.generated';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type Override<T, U> = Omit<T, keyof U> & U;

type OpenApiScorecard = components['schemas']['SignalScorecardResponse'];
type OpenApiBucket = components['schemas']['ScorecardBucket'];
type OpenApiOverall = components['schemas']['ScorecardOverall'];
type OpenApiBand = components['schemas']['ScorecardReturnBand'];
type OpenApiMiss = components['schemas']['ScorecardMiss'];
type OpenApiScorecardGet200 =
  operations['getPublicSignalScorecard']['responses']['200']['content']['application/json'];

type _Assert<T extends true> = T;
type _ScorecardGetIsComponent = _Assert<OpenApiScorecardGet200 extends OpenApiScorecard ? true : false>;
type _ScorecardComponentIsGet = _Assert<OpenApiScorecard extends OpenApiScorecardGet200 ? true : false>;

type _OpenApiAnchors = [
  _ScorecardGetIsComponent,
  _ScorecardComponentIsGet,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type ScorecardBucketStatus = 'ok' | 'insufficient_data' | string;

export type ScorecardBucket = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiBucket>, {
  signalType: string;
  horizon: string;
  status: ScorecardBucketStatus;
  sampleSize: number;
  completed: number;
  hitRatePct: number | null;
  avgReturnPct: number | null;
}>>;

export type ScorecardOverall = Override<CamelizeKeys<OpenApiOverall>, {
  status: ScorecardBucketStatus;
  sampleSize: number;
  completed: number;
  hitRatePct: number | null;
  avgReturnPct: number | null;
}>;

export type ScorecardReturnBand = Override<CamelizeKeys<OpenApiBand>, {
  band: string;
  count: number;
  sharePct: number | null;
}>;

export type ScorecardMiss = Override<CamelizeKeys<OpenApiMiss>, {
  signalType: string;
  horizon: string;
  returnPct: number | null;
  anchorDate: string | null;
}>;

export type SignalScorecardResponse = Override<CamelizeKeys<OpenApiScorecard>, {
  minSamples: number;
  overall: ScorecardOverall;
  bySignalTypeHorizon: ScorecardBucket[];
  returnDistribution: ScorecardReturnBand[];
  recentMisses: ScorecardMiss[];
}>;
