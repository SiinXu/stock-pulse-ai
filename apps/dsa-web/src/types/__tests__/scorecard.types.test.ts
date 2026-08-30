// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations } from '../api.generated';
import * as Scorecard from '../scorecard';
import type {
  ScorecardBucket,
  ScorecardMiss,
  ScorecardOverall,
  ScorecardReturnBand,
  SignalScorecardResponse,
} from '../scorecard';

type OpenApiScorecard = components['schemas']['SignalScorecardResponse'];
type OpenApiBucket = components['schemas']['ScorecardBucket'];
type OpenApiOverall = components['schemas']['ScorecardOverall'];
type OpenApiBand = components['schemas']['ScorecardReturnBand'];
type OpenApiMiss = components['schemas']['ScorecardMiss'];
type OpenApiScorecardGet200 =
  operations['getPublicSignalScorecard']['responses']['200']['content']['application/json'];

type _Assert<T extends true> = T;
type IsOptional<T, K extends keyof T> = Partial<Pick<T, K>> extends Pick<T, K> ? true : false;

type _ScorecardGetIsComponent = _Assert<OpenApiScorecardGet200 extends OpenApiScorecard ? true : false>;
type _ScorecardComponentIsGet = _Assert<OpenApiScorecard extends OpenApiScorecardGet200 ? true : false>;

type _UiHasMinSamples = _Assert<'minSamples' extends keyof SignalScorecardResponse ? true : false>;
type _UiHasBySignalTypeHorizon = _Assert<'bySignalTypeHorizon' extends keyof SignalScorecardResponse ? true : false>;
type _UiHasReturnDistribution = _Assert<'returnDistribution' extends keyof SignalScorecardResponse ? true : false>;
type _UiHasRecentMisses = _Assert<'recentMisses' extends keyof SignalScorecardResponse ? true : false>;
type _UiHasSignalType = _Assert<'signalType' extends keyof ScorecardBucket ? true : false>;
type _UiHasSampleSize = _Assert<'sampleSize' extends keyof ScorecardBucket ? true : false>;
type _UiHasHitRatePct = _Assert<'hitRatePct' extends keyof ScorecardBucket ? true : false>;
type _UiHasAvgReturnPct = _Assert<'avgReturnPct' extends keyof ScorecardBucket ? true : false>;
type _UiHasSharePct = _Assert<'sharePct' extends keyof ScorecardReturnBand ? true : false>;
type _UiHasReturnPct = _Assert<'returnPct' extends keyof ScorecardMiss ? true : false>;
type _UiHasAnchorDate = _Assert<'anchorDate' extends keyof ScorecardMiss ? true : false>;

type _UiLacksMinSamplesSnake = _Assert<'min_samples' extends keyof SignalScorecardResponse ? false : true>;
type _UiLacksBySignalSnake = _Assert<'by_signal_type_horizon' extends keyof SignalScorecardResponse ? false : true>;
type _UiLacksReturnDistSnake = _Assert<'return_distribution' extends keyof SignalScorecardResponse ? false : true>;
type _UiLacksRecentMissesSnake = _Assert<'recent_misses' extends keyof SignalScorecardResponse ? false : true>;
type _UiLacksSignalTypeSnake = _Assert<'signal_type' extends keyof ScorecardBucket ? false : true>;
type _UiLacksSampleSizeSnake = _Assert<'sample_size' extends keyof ScorecardBucket ? false : true>;
type _UiLacksHitRateSnake = _Assert<'hit_rate_pct' extends keyof ScorecardBucket ? false : true>;
type _UiLacksAvgReturnSnake = _Assert<'avg_return_pct' extends keyof ScorecardBucket ? false : true>;
type _UiLacksSharePctSnake = _Assert<'share_pct' extends keyof ScorecardReturnBand ? false : true>;
type _UiLacksReturnPctSnake = _Assert<'return_pct' extends keyof ScorecardMiss ? false : true>;
type _UiLacksAnchorDateSnake = _Assert<'anchor_date' extends keyof ScorecardMiss ? false : true>;

type _GeneratedHasMinSamplesSnake = _Assert<'min_samples' extends keyof OpenApiScorecard ? true : false>;
type _GeneratedHasBySignalSnake = _Assert<'by_signal_type_horizon' extends keyof OpenApiScorecard ? true : false>;
type _GeneratedHasReturnDistSnake = _Assert<'return_distribution' extends keyof OpenApiScorecard ? true : false>;
type _GeneratedHasRecentMissesSnake = _Assert<'recent_misses' extends keyof OpenApiScorecard ? true : false>;
type _GeneratedHasSignalTypeSnake = _Assert<'signal_type' extends keyof OpenApiBucket ? true : false>;
type _GeneratedHasSampleSizeSnake = _Assert<'sample_size' extends keyof OpenApiBucket ? true : false>;
type _GeneratedHasHitRateSnake = _Assert<'hit_rate_pct' extends keyof OpenApiBucket ? true : false>;
type _GeneratedHasAvgReturnSnake = _Assert<'avg_return_pct' extends keyof OpenApiBucket ? true : false>;
type _GeneratedHasSharePctSnake = _Assert<'share_pct' extends keyof OpenApiBand ? true : false>;
type _GeneratedHasReturnPctSnake = _Assert<'return_pct' extends keyof OpenApiMiss ? true : false>;
type _GeneratedHasAnchorDateSnake = _Assert<'anchor_date' extends keyof OpenApiMiss ? true : false>;

type _BucketHitRateRequired = _Assert<IsOptional<ScorecardBucket, 'hitRatePct'> extends false ? true : false>;
type _BucketAvgReturnRequired = _Assert<IsOptional<ScorecardBucket, 'avgReturnPct'> extends false ? true : false>;
type _OverallHitRateRequired = _Assert<IsOptional<ScorecardOverall, 'hitRatePct'> extends false ? true : false>;
type _OverallAvgReturnRequired = _Assert<IsOptional<ScorecardOverall, 'avgReturnPct'> extends false ? true : false>;
type _BandShareRequired = _Assert<IsOptional<ScorecardReturnBand, 'sharePct'> extends false ? true : false>;
type _MissReturnRequired = _Assert<IsOptional<ScorecardMiss, 'returnPct'> extends false ? true : false>;
type _MissAnchorRequired = _Assert<IsOptional<ScorecardMiss, 'anchorDate'> extends false ? true : false>;
type _BySignalRequired = _Assert<IsOptional<SignalScorecardResponse, 'bySignalTypeHorizon'> extends false ? true : false>;
type _ReturnDistRequired = _Assert<IsOptional<SignalScorecardResponse, 'returnDistribution'> extends false ? true : false>;
type _RecentMissesRequired = _Assert<IsOptional<SignalScorecardResponse, 'recentMisses'> extends false ? true : false>;

type _GeneratedBucketHitRateOptional = _Assert<IsOptional<OpenApiBucket, 'hit_rate_pct'>>;
type _GeneratedBucketAvgReturnOptional = _Assert<IsOptional<OpenApiBucket, 'avg_return_pct'>>;
type _GeneratedOverallHitRateOptional = _Assert<IsOptional<OpenApiOverall, 'hit_rate_pct'>>;
type _GeneratedBandShareOptional = _Assert<IsOptional<OpenApiBand, 'share_pct'>>;
type _GeneratedMissReturnOptional = _Assert<IsOptional<OpenApiMiss, 'return_pct'>>;
type _GeneratedMissAnchorOptional = _Assert<IsOptional<OpenApiMiss, 'anchor_date'>>;

type _OmitBucketHitRate = _Assert<Omit<ScorecardBucket, 'hitRatePct'> extends ScorecardBucket ? false : true>;
type _OmitGeneratedBucketHitRate = _Assert<Omit<OpenApiBucket, 'hit_rate_pct'> extends OpenApiBucket ? true : false>;
type _OmitBucketAvgReturn = _Assert<Omit<ScorecardBucket, 'avgReturnPct'> extends ScorecardBucket ? false : true>;
type _OmitGeneratedBucketAvgReturn = _Assert<Omit<OpenApiBucket, 'avg_return_pct'> extends OpenApiBucket ? true : false>;
type _OmitOverallHitRate = _Assert<Omit<ScorecardOverall, 'hitRatePct'> extends ScorecardOverall ? false : true>;
type _OmitGeneratedOverallHitRate = _Assert<Omit<OpenApiOverall, 'hit_rate_pct'> extends OpenApiOverall ? true : false>;
type _OmitBandShare = _Assert<Omit<ScorecardReturnBand, 'sharePct'> extends ScorecardReturnBand ? false : true>;
type _OmitGeneratedBandShare = _Assert<Omit<OpenApiBand, 'share_pct'> extends OpenApiBand ? true : false>;
type _OmitMissReturn = _Assert<Omit<ScorecardMiss, 'returnPct'> extends ScorecardMiss ? false : true>;
type _OmitGeneratedMissReturn = _Assert<Omit<OpenApiMiss, 'return_pct'> extends OpenApiMiss ? true : false>;
type _OmitMissAnchor = _Assert<Omit<ScorecardMiss, 'anchorDate'> extends ScorecardMiss ? false : true>;
type _OmitGeneratedMissAnchor = _Assert<Omit<OpenApiMiss, 'anchor_date'> extends OpenApiMiss ? true : false>;

type NarrowBucket = {
  signalType: string;
  horizon: string;
  status: 'ok';
  sampleSize: number;
  completed: number;
  hitRatePct: null;
  avgReturnPct: null;
};
type NarrowOverall = {
  status: 'ok';
  sampleSize: number;
  completed: number;
  hitRatePct: null;
  avgReturnPct: null;
};
type NarrowBand = {
  band: string;
  count: number;
  sharePct: null;
};
type NarrowMiss = {
  signalType: string;
  horizon: string;
  returnPct: null;
  anchorDate: null;
};
type NarrowResponse = {
  minSamples: number;
  overall: NarrowOverall;
  bySignalTypeHorizon: NarrowBucket[];
  returnDistribution: NarrowBand[];
  recentMisses: NarrowMiss[];
};

type _NarrowBucketAssignable = _Assert<NarrowBucket extends ScorecardBucket ? true : false>;
type _NarrowOverallAssignable = _Assert<NarrowOverall extends ScorecardOverall ? true : false>;
type _NarrowBandAssignable = _Assert<NarrowBand extends ScorecardReturnBand ? true : false>;
type _NarrowMissAssignable = _Assert<NarrowMiss extends ScorecardMiss ? true : false>;
type _NarrowResponseAssignable = _Assert<NarrowResponse extends SignalScorecardResponse ? true : false>;

type SnakeScorecard = {
  min_samples: number;
  overall: { status: string; sample_size: number; completed: number };
  by_signal_type_horizon: OpenApiBucket[];
  return_distribution: OpenApiBand[];
  recent_misses: OpenApiMiss[];
};
type _SnakeMatchesGenerated = _Assert<SnakeScorecard extends OpenApiScorecard ? true : false>;
type _SnakeDoesNotMatchUi = _Assert<SnakeScorecard extends SignalScorecardResponse ? false : true>;

type OtherStatusBucket = {
  signalType: string;
  horizon: string;
  status: 'other';
  sampleSize: number;
  completed: number;
  hitRatePct: null;
  avgReturnPct: null;
};
type InsufficientStatusBucket = {
  signalType: string;
  horizon: string;
  status: 'insufficient_data';
  sampleSize: number;
  completed: number;
  hitRatePct: null;
  avgReturnPct: null;
};
type _OkStatusAssignable = _Assert<NarrowBucket extends ScorecardBucket ? true : false>;
type _InsufficientStatusAssignable = _Assert<InsufficientStatusBucket extends ScorecardBucket ? true : false>;
type _OtherStatusAssignable = _Assert<OtherStatusBucket extends ScorecardBucket ? true : false>;

type _CompileTimePins = [
  _ScorecardGetIsComponent,
  _ScorecardComponentIsGet,
  _UiHasMinSamples,
  _UiHasBySignalTypeHorizon,
  _UiHasReturnDistribution,
  _UiHasRecentMisses,
  _UiHasSignalType,
  _UiHasSampleSize,
  _UiHasHitRatePct,
  _UiHasAvgReturnPct,
  _UiHasSharePct,
  _UiHasReturnPct,
  _UiHasAnchorDate,
  _UiLacksMinSamplesSnake,
  _UiLacksBySignalSnake,
  _UiLacksReturnDistSnake,
  _UiLacksRecentMissesSnake,
  _UiLacksSignalTypeSnake,
  _UiLacksSampleSizeSnake,
  _UiLacksHitRateSnake,
  _UiLacksAvgReturnSnake,
  _UiLacksSharePctSnake,
  _UiLacksReturnPctSnake,
  _UiLacksAnchorDateSnake,
  _GeneratedHasMinSamplesSnake,
  _GeneratedHasBySignalSnake,
  _GeneratedHasReturnDistSnake,
  _GeneratedHasRecentMissesSnake,
  _GeneratedHasSignalTypeSnake,
  _GeneratedHasSampleSizeSnake,
  _GeneratedHasHitRateSnake,
  _GeneratedHasAvgReturnSnake,
  _GeneratedHasSharePctSnake,
  _GeneratedHasReturnPctSnake,
  _GeneratedHasAnchorDateSnake,
  _BucketHitRateRequired,
  _BucketAvgReturnRequired,
  _OverallHitRateRequired,
  _OverallAvgReturnRequired,
  _BandShareRequired,
  _MissReturnRequired,
  _MissAnchorRequired,
  _BySignalRequired,
  _ReturnDistRequired,
  _RecentMissesRequired,
  _GeneratedBucketHitRateOptional,
  _GeneratedBucketAvgReturnOptional,
  _GeneratedOverallHitRateOptional,
  _GeneratedBandShareOptional,
  _GeneratedMissReturnOptional,
  _GeneratedMissAnchorOptional,
  _OmitBucketHitRate,
  _OmitGeneratedBucketHitRate,
  _OmitBucketAvgReturn,
  _OmitGeneratedBucketAvgReturn,
  _OmitOverallHitRate,
  _OmitGeneratedOverallHitRate,
  _OmitBandShare,
  _OmitGeneratedBandShare,
  _OmitMissReturn,
  _OmitGeneratedMissReturn,
  _OmitMissAnchor,
  _OmitGeneratedMissAnchor,
  _NarrowBucketAssignable,
  _NarrowOverallAssignable,
  _NarrowBandAssignable,
  _NarrowMissAssignable,
  _NarrowResponseAssignable,
  _SnakeMatchesGenerated,
  _SnakeDoesNotMatchUi,
  _OkStatusAssignable,
  _InsufficientStatusAssignable,
  _OtherStatusAssignable,
];

const BUCKET_REST = {
  signalType: 'buy',
  horizon: '5d',
  sampleSize: 8,
  completed: 8,
  hitRatePct: null as number | null,
  avgReturnPct: null as number | null,
};

describe('scorecard OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    // ESM namespace objects carry Symbol.toStringTag='Module'; enumerable exports must stay empty.
    expect({ ...Scorecard }).toEqual({});
    expect(Object.keys(Scorecard)).toEqual([]);
    expect(Object.getOwnPropertyNames(Scorecard)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates path 200 JSON to the generated response component', () => {
    expectTypeOf<OpenApiScorecardGet200>().toEqualTypeOf<OpenApiScorecard>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof SignalScorecardResponse>().not.toMatchTypeOf<
      'min_samples' | 'by_signal_type_horizon' | 'return_distribution' | 'recent_misses'
    >();
    expectTypeOf<keyof ScorecardBucket>().not.toMatchTypeOf<
      'signal_type' | 'sample_size' | 'hit_rate_pct' | 'avg_return_pct'
    >();
    expectTypeOf<keyof ScorecardReturnBand>().not.toMatchTypeOf<'share_pct'>();
    expectTypeOf<keyof ScorecardMiss>().not.toMatchTypeOf<'return_pct' | 'anchor_date'>();

    type UiHasMinSamples = 'minSamples' extends keyof SignalScorecardResponse ? true : false;
    type UiHasMinSamplesSnake = 'min_samples' extends keyof SignalScorecardResponse ? true : false;
    type GeneratedHasMinSamplesSnake = 'min_samples' extends keyof OpenApiScorecard ? true : false;
    type UiHasBySignal = 'bySignalTypeHorizon' extends keyof SignalScorecardResponse ? true : false;
    type UiHasBySignalSnake = 'by_signal_type_horizon' extends keyof SignalScorecardResponse ? true : false;
    type GeneratedHasBySignalSnake = 'by_signal_type_horizon' extends keyof OpenApiScorecard ? true : false;
    type UiHasReturnDist = 'returnDistribution' extends keyof SignalScorecardResponse ? true : false;
    type UiHasReturnDistSnake = 'return_distribution' extends keyof SignalScorecardResponse ? true : false;
    type GeneratedHasReturnDistSnake = 'return_distribution' extends keyof OpenApiScorecard ? true : false;
    type UiHasRecentMisses = 'recentMisses' extends keyof SignalScorecardResponse ? true : false;
    type UiHasRecentMissesSnake = 'recent_misses' extends keyof SignalScorecardResponse ? true : false;
    type GeneratedHasRecentMissesSnake = 'recent_misses' extends keyof OpenApiScorecard ? true : false;
    type UiHasSignalType = 'signalType' extends keyof ScorecardBucket ? true : false;
    type UiHasSignalTypeSnake = 'signal_type' extends keyof ScorecardBucket ? true : false;
    type GeneratedHasSignalTypeSnake = 'signal_type' extends keyof OpenApiBucket ? true : false;
    type UiHasSampleSize = 'sampleSize' extends keyof ScorecardBucket ? true : false;
    type UiHasSampleSizeSnake = 'sample_size' extends keyof ScorecardBucket ? true : false;
    type GeneratedHasSampleSizeSnake = 'sample_size' extends keyof OpenApiBucket ? true : false;
    type UiHasHitRate = 'hitRatePct' extends keyof ScorecardBucket ? true : false;
    type UiHasHitRateSnake = 'hit_rate_pct' extends keyof ScorecardBucket ? true : false;
    type GeneratedHasHitRateSnake = 'hit_rate_pct' extends keyof OpenApiBucket ? true : false;
    type UiHasAvgReturn = 'avgReturnPct' extends keyof ScorecardBucket ? true : false;
    type UiHasAvgReturnSnake = 'avg_return_pct' extends keyof ScorecardBucket ? true : false;
    type GeneratedHasAvgReturnSnake = 'avg_return_pct' extends keyof OpenApiBucket ? true : false;
    type UiHasSharePct = 'sharePct' extends keyof ScorecardReturnBand ? true : false;
    type UiHasSharePctSnake = 'share_pct' extends keyof ScorecardReturnBand ? true : false;
    type GeneratedHasSharePctSnake = 'share_pct' extends keyof OpenApiBand ? true : false;
    type UiHasReturnPct = 'returnPct' extends keyof ScorecardMiss ? true : false;
    type UiHasReturnPctSnake = 'return_pct' extends keyof ScorecardMiss ? true : false;
    type GeneratedHasReturnPctSnake = 'return_pct' extends keyof OpenApiMiss ? true : false;
    type UiHasAnchorDate = 'anchorDate' extends keyof ScorecardMiss ? true : false;
    type UiHasAnchorDateSnake = 'anchor_date' extends keyof ScorecardMiss ? true : false;
    type GeneratedHasAnchorDateSnake = 'anchor_date' extends keyof OpenApiMiss ? true : false;

    expectTypeOf<UiHasMinSamples>().toEqualTypeOf<true>();
    expectTypeOf<UiHasMinSamplesSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasMinSamplesSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasBySignal>().toEqualTypeOf<true>();
    expectTypeOf<UiHasBySignalSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasBySignalSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasReturnDist>().toEqualTypeOf<true>();
    expectTypeOf<UiHasReturnDistSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasReturnDistSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasRecentMisses>().toEqualTypeOf<true>();
    expectTypeOf<UiHasRecentMissesSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasRecentMissesSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasSignalType>().toEqualTypeOf<true>();
    expectTypeOf<UiHasSignalTypeSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasSignalTypeSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasSampleSize>().toEqualTypeOf<true>();
    expectTypeOf<UiHasSampleSizeSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasSampleSizeSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasHitRate>().toEqualTypeOf<true>();
    expectTypeOf<UiHasHitRateSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasHitRateSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasAvgReturn>().toEqualTypeOf<true>();
    expectTypeOf<UiHasAvgReturnSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasAvgReturnSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasSharePct>().toEqualTypeOf<true>();
    expectTypeOf<UiHasSharePctSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasSharePctSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasReturnPct>().toEqualTypeOf<true>();
    expectTypeOf<UiHasReturnPctSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasReturnPctSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasAnchorDate>().toEqualTypeOf<true>();
    expectTypeOf<UiHasAnchorDateSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasAnchorDateSnake>().toEqualTypeOf<true>();
  });

  it('keeps UI nested metrics required-nullable while generated counterparts stay optional', () => {
    expectTypeOf<Omit<ScorecardBucket, 'hitRatePct'>>().not.toMatchTypeOf<ScorecardBucket>();
    expectTypeOf<Omit<OpenApiBucket, 'hit_rate_pct'>>().toMatchTypeOf<OpenApiBucket>();
    expectTypeOf<Omit<ScorecardBucket, 'avgReturnPct'>>().not.toMatchTypeOf<ScorecardBucket>();
    expectTypeOf<Omit<OpenApiBucket, 'avg_return_pct'>>().toMatchTypeOf<OpenApiBucket>();
    expectTypeOf<Omit<ScorecardOverall, 'hitRatePct'>>().not.toMatchTypeOf<ScorecardOverall>();
    expectTypeOf<Omit<OpenApiOverall, 'hit_rate_pct'>>().toMatchTypeOf<OpenApiOverall>();
    expectTypeOf<Omit<ScorecardOverall, 'avgReturnPct'>>().not.toMatchTypeOf<ScorecardOverall>();
    expectTypeOf<Omit<OpenApiOverall, 'avg_return_pct'>>().toMatchTypeOf<OpenApiOverall>();
    expectTypeOf<Omit<ScorecardReturnBand, 'sharePct'>>().not.toMatchTypeOf<ScorecardReturnBand>();
    expectTypeOf<Omit<OpenApiBand, 'share_pct'>>().toMatchTypeOf<OpenApiBand>();
    expectTypeOf<Omit<ScorecardMiss, 'returnPct'>>().not.toMatchTypeOf<ScorecardMiss>();
    expectTypeOf<Omit<OpenApiMiss, 'return_pct'>>().toMatchTypeOf<OpenApiMiss>();
    expectTypeOf<Omit<ScorecardMiss, 'anchorDate'>>().not.toMatchTypeOf<ScorecardMiss>();
    expectTypeOf<Omit<OpenApiMiss, 'anchor_date'>>().toMatchTypeOf<OpenApiMiss>();
  });

  it('still accepts the narrow existing bucket, overall, band, miss, and response fixtures', () => {
    const bucket = {
      signalType: 'buy',
      horizon: '5d',
      status: 'ok' as const,
      sampleSize: 8,
      completed: 8,
      hitRatePct: null,
      avgReturnPct: null,
    };
    const overall = {
      status: 'ok' as const,
      sampleSize: 12,
      completed: 14,
      hitRatePct: null,
      avgReturnPct: null,
    };
    const band = {
      band: '+2% ~ +5%',
      count: 3,
      sharePct: null,
    };
    const miss = {
      signalType: 'buy',
      horizon: '5d',
      returnPct: null,
      anchorDate: null,
    };
    const response = {
      minSamples: 10,
      overall,
      bySignalTypeHorizon: [bucket],
      returnDistribution: [band],
      recentMisses: [miss],
    };
    expectTypeOf(bucket).toMatchTypeOf<ScorecardBucket>();
    expectTypeOf(overall).toMatchTypeOf<ScorecardOverall>();
    expectTypeOf(band).toMatchTypeOf<ScorecardReturnBand>();
    expectTypeOf(miss).toMatchTypeOf<ScorecardMiss>();
    expectTypeOf(response).toMatchTypeOf<SignalScorecardResponse>();
  });

  it('does not re-export generated snake_case as the UI type', () => {
    const snakeScorecard = {
      min_samples: 10,
      overall: { status: 'ok', sample_size: 12, completed: 14 },
      by_signal_type_horizon: [],
      return_distribution: [],
      recent_misses: [],
    };
    expectTypeOf(snakeScorecard).toMatchTypeOf<OpenApiScorecard>();
    expectTypeOf(snakeScorecard).not.toMatchTypeOf<SignalScorecardResponse>();
  });

  it('keeps bucket status documentation-widened including arbitrary strings', () => {
    expectTypeOf({ status: 'ok' as const, ...BUCKET_REST }).toMatchTypeOf<ScorecardBucket>();
    expectTypeOf({ status: 'insufficient_data' as const, ...BUCKET_REST }).toMatchTypeOf<ScorecardBucket>();
    expectTypeOf({ status: 'other' as const, ...BUCKET_REST }).toMatchTypeOf<ScorecardBucket>();
  });
});
