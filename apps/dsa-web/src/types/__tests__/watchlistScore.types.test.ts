// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as WatchlistScore from '../watchlistScore';
import type {
  WatchlistScoreDegradationReason,
  WatchlistScoreFactor,
  WatchlistScoreFactorKey,
  WatchlistScoreFactorSource,
  WatchlistScoreFactorStatus,
  WatchlistScoreFreshness,
  WatchlistScoreItem,
  WatchlistScoreResponse,
  WatchlistScoreSortMode,
  WatchlistScoreStatus,
} from '../watchlistScore';

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
type IsOptional<T, K extends keyof T> = Partial<Pick<T, K>> extends Pick<T, K> ? true : false;

type _Post200IsResponse = _Assert<OpenApiScorePost200 extends OpenApiResponse ? true : false>;
type _ResponseIsPost200 = _Assert<OpenApiResponse extends OpenApiScorePost200 ? true : false>;
type _PostBodyIsRequest = _Assert<OpenApiScorePostBody extends WatchlistScoreRequest ? true : false>;
type _RequestIsPostBody = _Assert<WatchlistScoreRequest extends OpenApiScorePostBody ? true : false>;
type _OpIsPath = _Assert<OpenApiOp extends OpenApiPathPost ? true : false>;
type _PathIsOp = _Assert<OpenApiPathPost extends OpenApiOp ? true : false>;
type _Post200HasItems = _Assert<'items' extends keyof OpenApiScorePost200 ? true : false>;
type _PostBodyHasStockCodes = _Assert<'stock_codes' extends keyof OpenApiScorePostBody ? true : false>;
type _Post200LacksStockCodes = _Assert<'stock_codes' extends keyof OpenApiScorePost200 ? false : true>;
type _PostBodyLacksItems = _Assert<'items' extends keyof OpenApiScorePostBody ? false : true>;

type _UiHasStockCode = _Assert<'stockCode' extends keyof WatchlistScoreItem ? true : false>;
type _UiHasFormulaVersion = _Assert<'formulaVersion' extends keyof WatchlistScoreResponse ? true : false>;
type _UiHasQueryCount = _Assert<'queryCount' extends keyof WatchlistScoreResponse ? true : false>;
type _UiHasSourceRows = _Assert<'sourceRows' extends keyof WatchlistScoreResponse ? true : false>;
type _UiHasDegradedReasons = _Assert<'degradedReasons' extends keyof WatchlistScoreItem ? true : false>;
type _UiHasSourceReportId = _Assert<'sourceReportId' extends keyof WatchlistScoreFactorSource ? true : false>;
type _UiHasAgeDays = _Assert<'ageDays' extends keyof WatchlistScoreItem ? true : false>;
type _UiHasAnalysisId = _Assert<'analysisId' extends keyof WatchlistScoreItem ? true : false>;
type _UiHasOperationAdvice = _Assert<'operationAdvice' extends keyof WatchlistScoreItem ? true : false>;
type _UiHasScoringMode = _Assert<'scoringMode' extends keyof WatchlistScoreResponse ? true : false>;
type _UiHasDisclaimerKey = _Assert<'disclaimerKey' extends keyof WatchlistScoreResponse ? true : false>;

type _UiLacksStockCodeSnake = _Assert<'stock_code' extends keyof WatchlistScoreItem ? false : true>;
type _UiLacksFormulaVersionSnake = _Assert<'formula_version' extends keyof WatchlistScoreResponse ? false : true>;
type _UiLacksQueryCountSnake = _Assert<'query_count' extends keyof WatchlistScoreResponse ? false : true>;
type _UiLacksSourceRowsSnake = _Assert<'source_rows' extends keyof WatchlistScoreResponse ? false : true>;
type _UiLacksDegradedReasonsSnake = _Assert<'degraded_reasons' extends keyof WatchlistScoreItem ? false : true>;
type _UiLacksSourceReportIdSnake = _Assert<'source_report_id' extends keyof WatchlistScoreFactorSource ? false : true>;
type _UiLacksAgeDaysSnake = _Assert<'age_days' extends keyof WatchlistScoreItem ? false : true>;
type _UiLacksAnalysisIdSnake = _Assert<'analysis_id' extends keyof WatchlistScoreItem ? false : true>;
type _UiLacksOperationAdviceSnake = _Assert<'operation_advice' extends keyof WatchlistScoreItem ? false : true>;
type _UiLacksScoringModeSnake = _Assert<'scoring_mode' extends keyof WatchlistScoreResponse ? false : true>;
type _UiLacksDisclaimerKeySnake = _Assert<'disclaimer_key' extends keyof WatchlistScoreResponse ? false : true>;

type _GeneratedHasStockCodeSnake = _Assert<'stock_code' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasFormulaVersionSnake = _Assert<'formula_version' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasQueryCountSnake = _Assert<'query_count' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasSourceRowsSnake = _Assert<'source_rows' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasDegradedReasonsSnake = _Assert<'degraded_reasons' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasSourceReportIdSnake = _Assert<'source_report_id' extends keyof OpenApiFactorSource ? true : false>;
type _GeneratedHasAgeDaysSnake = _Assert<'age_days' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasAnalysisIdSnake = _Assert<'analysis_id' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasOperationAdviceSnake = _Assert<'operation_advice' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasScoringModeSnake = _Assert<'scoring_mode' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasDisclaimerKeySnake = _Assert<'disclaimer_key' extends keyof OpenApiResponse ? true : false>;

type _UiLacksStockCodeCamelOnGenerated = _Assert<'stockCode' extends keyof OpenApiItem ? false : true>;
type _UiLacksFormulaVersionCamelOnGenerated = _Assert<'formulaVersion' extends keyof OpenApiResponse ? false : true>;
type _UiLacksQueryCountCamelOnGenerated = _Assert<'queryCount' extends keyof OpenApiResponse ? false : true>;

type _FactorsRequired = _Assert<IsOptional<WatchlistScoreItem, 'factors'> extends false ? true : false>;
type _DegradedReasonsRequired = _Assert<IsOptional<WatchlistScoreItem, 'degradedReasons'> extends false ? true : false>;
type _ScoreRequired = _Assert<IsOptional<WatchlistScoreItem, 'score'> extends false ? true : false>;
type _AsOfRequired = _Assert<IsOptional<WatchlistScoreItem, 'asOf'> extends false ? true : false>;
type _AgeDaysRequired = _Assert<IsOptional<WatchlistScoreItem, 'ageDays'> extends false ? true : false>;
type _AnalysisIdRequired = _Assert<IsOptional<WatchlistScoreItem, 'analysisId'> extends false ? true : false>;
type _OperationAdviceRequired = _Assert<IsOptional<WatchlistScoreItem, 'operationAdvice'> extends false ? true : false>;
type _ValueRequired = _Assert<IsOptional<WatchlistScoreFactor, 'value'> extends false ? true : false>;
type _ParamsRequired = _Assert<IsOptional<WatchlistScoreFactor, 'params'> extends false ? true : false>;
type _ReasonRequired = _Assert<IsOptional<WatchlistScoreFactor, 'reason'> extends false ? true : false>;
type _SourceIdRequired = _Assert<IsOptional<WatchlistScoreFactorSource, 'id'> extends false ? true : false>;
type _SourceReportIdRequired = _Assert<IsOptional<WatchlistScoreFactorSource, 'sourceReportId'> extends false ? true : false>;
type _SourceProfileRequired = _Assert<IsOptional<WatchlistScoreFactorSource, 'profile'> extends false ? true : false>;
type _SourceAsOfRequired = _Assert<IsOptional<WatchlistScoreFactorSource, 'asOf'> extends false ? true : false>;
type _SourceExpiresAtRequired = _Assert<IsOptional<WatchlistScoreFactorSource, 'expiresAt'> extends false ? true : false>;
type _ItemsRequired = _Assert<IsOptional<WatchlistScoreResponse, 'items'> extends false ? true : false>;
type _QueryCountRequired = _Assert<IsOptional<WatchlistScoreResponse, 'queryCount'> extends false ? true : false>;
type _SourceRowsRequired = _Assert<IsOptional<WatchlistScoreResponse, 'sourceRows'> extends false ? true : false>;

type _GeneratedFactorsOptional = _Assert<IsOptional<OpenApiItem, 'factors'>>;
type _GeneratedDegradedReasonsOptional = _Assert<IsOptional<OpenApiItem, 'degraded_reasons'>>;
type _GeneratedScoreOptional = _Assert<IsOptional<OpenApiItem, 'score'>>;
type _GeneratedValueOptional = _Assert<IsOptional<OpenApiFactor, 'value'>>;
type _GeneratedParamsOptional = _Assert<IsOptional<OpenApiFactor, 'params'>>;
type _GeneratedReasonOptional = _Assert<IsOptional<OpenApiFactor, 'reason'>>;
type _GeneratedSourceIdOptional = _Assert<IsOptional<OpenApiFactorSource, 'id'>>;

type _OmitFactors = _Assert<Omit<WatchlistScoreItem, 'factors'> extends WatchlistScoreItem ? false : true>;
type _OmitGeneratedFactors = _Assert<Omit<OpenApiItem, 'factors'> extends OpenApiItem ? true : false>;
type _OmitScore = _Assert<Omit<WatchlistScoreItem, 'score'> extends WatchlistScoreItem ? false : true>;
type _OmitGeneratedScore = _Assert<Omit<OpenApiItem, 'score'> extends OpenApiItem ? true : false>;
type _OmitDegradedReasons = _Assert<Omit<WatchlistScoreItem, 'degradedReasons'> extends WatchlistScoreItem ? false : true>;
type _OmitGeneratedDegradedReasons = _Assert<Omit<OpenApiItem, 'degraded_reasons'> extends OpenApiItem ? true : false>;
type _OmitValue = _Assert<Omit<WatchlistScoreFactor, 'value'> extends WatchlistScoreFactor ? false : true>;
type _OmitGeneratedValue = _Assert<Omit<OpenApiFactor, 'value'> extends OpenApiFactor ? true : false>;

type NarrowSource = {
  id: null;
  sourceReportId: null;
  profile: null;
  asOf: null;
  expiresAt: null;
  formulaVersion: 'watchlist_score_v1';
};
type NarrowFactor = {
  key: 'analysis_sentiment';
  status: 'applied';
  value: null;
  params: Record<string, string | number | boolean | null>;
  reason: null;
  source: NarrowSource;
};
type NarrowUnanalyzedItem = {
  stockCode: string;
  status: 'unanalyzed';
  score: null;
  asOf: null;
  ageDays: null;
  analysisId: null;
  operationAdvice: null;
  factors: [];
  freshness: 'none';
  degradedReasons: [];
};
type NarrowScoredItem = {
  stockCode: string;
  status: 'scored';
  score: number;
  asOf: string;
  ageDays: number;
  analysisId: number;
  operationAdvice: string;
  factors: NarrowFactor[];
  freshness: 'recent';
  degradedReasons: [];
};
type NarrowResponse = {
  formulaVersion: 'watchlist_score_v1';
  scoringMode: 'aggregate_existing';
  sort: 'manual';
  items: NarrowUnanalyzedItem[];
  queryCount: { analysis: number; signals: number };
  sourceRows: { analysis: number; signals: number };
  disclaimerKey: 'watchlist_score.disclaimer';
};

type _NarrowSourceAssignable = _Assert<NarrowSource extends WatchlistScoreFactorSource ? true : false>;
type _NarrowFactorAssignable = _Assert<NarrowFactor extends WatchlistScoreFactor ? true : false>;
type _NarrowUnanalyzedAssignable = _Assert<NarrowUnanalyzedItem extends WatchlistScoreItem ? true : false>;
type _NarrowScoredAssignable = _Assert<NarrowScoredItem extends WatchlistScoreItem ? true : false>;
type _NarrowResponseAssignable = _Assert<NarrowResponse extends WatchlistScoreResponse ? true : false>;

type SnakeItem = {
  stock_code: string;
  status: 'unanalyzed';
  freshness: 'none';
};
type SnakeResponse = {
  formula_version: 'watchlist_score_v1';
  scoring_mode: 'aggregate_existing';
  sort: 'manual';
  items: OpenApiItem[];
  query_count: OpenApiQueryCount;
  source_rows: OpenApiSourceRows;
  disclaimer_key: 'watchlist_score.disclaimer';
};
type _SnakeItemMatchesGenerated = _Assert<SnakeItem extends OpenApiItem ? true : false>;
type _SnakeItemDoesNotMatchUi = _Assert<SnakeItem extends WatchlistScoreItem ? false : true>;
type _SnakeResponseMatchesGenerated = _Assert<SnakeResponse extends OpenApiResponse ? true : false>;
type _SnakeResponseDoesNotMatchUi = _Assert<SnakeResponse extends WatchlistScoreResponse ? false : true>;
type _UiResponseIsNotGeneratedAlias = _Assert<WatchlistScoreResponse extends OpenApiResponse ? false : true>;
type _GeneratedResponseIsNotUi = _Assert<OpenApiResponse extends WatchlistScoreResponse ? false : true>;

type MysteryFreshnessItem = {
  stockCode: string;
  status: 'unanalyzed';
  score: null;
  asOf: null;
  ageDays: null;
  analysisId: null;
  operationAdvice: null;
  factors: [];
  freshness: string;
  degradedReasons: [];
};
type MysteryStatusItem = {
  stockCode: string;
  status: string;
  score: null;
  asOf: null;
  ageDays: null;
  analysisId: null;
  operationAdvice: null;
  factors: [];
  freshness: 'none';
  degradedReasons: [];
};
type MysterySortResponse = {
  formulaVersion: 'watchlist_score_v1';
  scoringMode: 'aggregate_existing';
  sort: string;
  items: NarrowUnanalyzedItem[];
  queryCount: { analysis: number; signals: number };
  sourceRows: { analysis: number; signals: number };
  disclaimerKey: 'watchlist_score.disclaimer';
};

type _MysteryFreshnessRejected = _Assert<MysteryFreshnessItem extends WatchlistScoreItem ? false : true>;
type _MysteryStatusRejected = _Assert<MysteryStatusItem extends WatchlistScoreItem ? false : true>;
type _MysterySortRejected = _Assert<MysterySortResponse extends WatchlistScoreResponse ? false : true>;
type _StringFreshnessRejected = _Assert<string extends WatchlistScoreFreshness ? false : true>;
type _StringStatusRejected = _Assert<string extends WatchlistScoreStatus ? false : true>;
type _StringSortRejected = _Assert<string extends WatchlistScoreSortMode ? false : true>;
type _StringKeyRejected = _Assert<string extends WatchlistScoreFactorKey ? false : true>;
type _StringFactorStatusRejected = _Assert<string extends WatchlistScoreFactorStatus ? false : true>;
type _StringReasonRejected = _Assert<string extends WatchlistScoreDegradationReason ? false : true>;
type _NoneFreshnessAssignable = _Assert<'none' extends WatchlistScoreFreshness ? true : false>;
type _UnanalyzedStatusAssignable = _Assert<'unanalyzed' extends WatchlistScoreStatus ? true : false>;
type _ManualSortAssignable = _Assert<'manual' extends WatchlistScoreSortMode ? true : false>;
type _AnalysisSentimentAssignable = _Assert<'analysis_sentiment' extends WatchlistScoreFactorKey ? true : false>;
type _AppliedStatusAssignable = _Assert<'applied' extends WatchlistScoreFactorStatus ? true : false>;
type _InvalidSentimentAssignable = _Assert<'invalid_sentiment' extends WatchlistScoreDegradationReason ? true : false>;

type _CompileTimePins = [
  _Post200IsResponse,
  _ResponseIsPost200,
  _PostBodyIsRequest,
  _RequestIsPostBody,
  _OpIsPath,
  _PathIsOp,
  _Post200HasItems,
  _PostBodyHasStockCodes,
  _Post200LacksStockCodes,
  _PostBodyLacksItems,
  _UiHasStockCode,
  _UiHasFormulaVersion,
  _UiHasQueryCount,
  _UiHasSourceRows,
  _UiHasDegradedReasons,
  _UiHasSourceReportId,
  _UiHasAgeDays,
  _UiHasAnalysisId,
  _UiHasOperationAdvice,
  _UiHasScoringMode,
  _UiHasDisclaimerKey,
  _UiLacksStockCodeSnake,
  _UiLacksFormulaVersionSnake,
  _UiLacksQueryCountSnake,
  _UiLacksSourceRowsSnake,
  _UiLacksDegradedReasonsSnake,
  _UiLacksSourceReportIdSnake,
  _UiLacksAgeDaysSnake,
  _UiLacksAnalysisIdSnake,
  _UiLacksOperationAdviceSnake,
  _UiLacksScoringModeSnake,
  _UiLacksDisclaimerKeySnake,
  _GeneratedHasStockCodeSnake,
  _GeneratedHasFormulaVersionSnake,
  _GeneratedHasQueryCountSnake,
  _GeneratedHasSourceRowsSnake,
  _GeneratedHasDegradedReasonsSnake,
  _GeneratedHasSourceReportIdSnake,
  _GeneratedHasAgeDaysSnake,
  _GeneratedHasAnalysisIdSnake,
  _GeneratedHasOperationAdviceSnake,
  _GeneratedHasScoringModeSnake,
  _GeneratedHasDisclaimerKeySnake,
  _UiLacksStockCodeCamelOnGenerated,
  _UiLacksFormulaVersionCamelOnGenerated,
  _UiLacksQueryCountCamelOnGenerated,
  _FactorsRequired,
  _DegradedReasonsRequired,
  _ScoreRequired,
  _AsOfRequired,
  _AgeDaysRequired,
  _AnalysisIdRequired,
  _OperationAdviceRequired,
  _ValueRequired,
  _ParamsRequired,
  _ReasonRequired,
  _SourceIdRequired,
  _SourceReportIdRequired,
  _SourceProfileRequired,
  _SourceAsOfRequired,
  _SourceExpiresAtRequired,
  _ItemsRequired,
  _QueryCountRequired,
  _SourceRowsRequired,
  _GeneratedFactorsOptional,
  _GeneratedDegradedReasonsOptional,
  _GeneratedScoreOptional,
  _GeneratedValueOptional,
  _GeneratedParamsOptional,
  _GeneratedReasonOptional,
  _GeneratedSourceIdOptional,
  _OmitFactors,
  _OmitGeneratedFactors,
  _OmitScore,
  _OmitGeneratedScore,
  _OmitDegradedReasons,
  _OmitGeneratedDegradedReasons,
  _OmitValue,
  _OmitGeneratedValue,
  _NarrowSourceAssignable,
  _NarrowFactorAssignable,
  _NarrowUnanalyzedAssignable,
  _NarrowScoredAssignable,
  _NarrowResponseAssignable,
  _SnakeItemMatchesGenerated,
  _SnakeItemDoesNotMatchUi,
  _SnakeResponseMatchesGenerated,
  _SnakeResponseDoesNotMatchUi,
  _UiResponseIsNotGeneratedAlias,
  _GeneratedResponseIsNotUi,
  _MysteryFreshnessRejected,
  _MysteryStatusRejected,
  _MysterySortRejected,
  _StringFreshnessRejected,
  _StringStatusRejected,
  _StringSortRejected,
  _StringKeyRejected,
  _StringFactorStatusRejected,
  _StringReasonRejected,
  _NoneFreshnessAssignable,
  _UnanalyzedStatusAssignable,
  _ManualSortAssignable,
  _AnalysisSentimentAssignable,
  _AppliedStatusAssignable,
  _InvalidSentimentAssignable,
];

const SOURCE_REST: WatchlistScoreFactorSource = {
  id: null,
  sourceReportId: null,
  profile: null,
  asOf: null,
  expiresAt: null,
  formulaVersion: 'watchlist_score_v1',
};

describe('watchlistScore OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    // ESM namespace objects carry Symbol.toStringTag='Module'; enumerable exports must stay empty.
    expect({ ...WatchlistScore }).toEqual({});
    expect(Object.keys(WatchlistScore)).toEqual([]);
    expect(Object.getOwnPropertyNames(WatchlistScore)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates path 200 JSON and request bodies to the generated components', () => {
    expectTypeOf<OpenApiScorePost200>().toEqualTypeOf<OpenApiResponse>();
    expectTypeOf<OpenApiScorePostBody>().toEqualTypeOf<WatchlistScoreRequest>();
    expectTypeOf<OpenApiOp>().toEqualTypeOf<OpenApiPathPost>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof WatchlistScoreItem>().not.toMatchTypeOf<
      'stock_code' | 'age_days' | 'analysis_id' | 'operation_advice' | 'degraded_reasons'
    >();
    expectTypeOf<keyof WatchlistScoreResponse>().not.toMatchTypeOf<
      'formula_version' | 'query_count' | 'source_rows' | 'scoring_mode' | 'disclaimer_key'
    >();
    expectTypeOf<keyof WatchlistScoreFactorSource>().not.toMatchTypeOf<
      'source_report_id' | 'as_of' | 'expires_at' | 'formula_version'
    >();

    type UiHasStockCode = 'stockCode' extends keyof WatchlistScoreItem ? true : false;
    type UiHasStockCodeSnake = 'stock_code' extends keyof WatchlistScoreItem ? true : false;
    type GeneratedHasStockCodeSnake = 'stock_code' extends keyof OpenApiItem ? true : false;
    type UiHasFormulaVersion = 'formulaVersion' extends keyof WatchlistScoreResponse ? true : false;
    type UiHasFormulaVersionSnake = 'formula_version' extends keyof WatchlistScoreResponse ? true : false;
    type GeneratedHasFormulaVersionSnake = 'formula_version' extends keyof OpenApiResponse ? true : false;
    type UiHasQueryCount = 'queryCount' extends keyof WatchlistScoreResponse ? true : false;
    type UiHasQueryCountSnake = 'query_count' extends keyof WatchlistScoreResponse ? true : false;
    type GeneratedHasQueryCountSnake = 'query_count' extends keyof OpenApiResponse ? true : false;

    expectTypeOf<UiHasStockCode>().toEqualTypeOf<true>();
    expectTypeOf<UiHasStockCodeSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasStockCodeSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasFormulaVersion>().toEqualTypeOf<true>();
    expectTypeOf<UiHasFormulaVersionSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasFormulaVersionSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasQueryCount>().toEqualTypeOf<true>();
    expectTypeOf<UiHasQueryCountSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasQueryCountSnake>().toEqualTypeOf<true>();
  });

  it('keeps UI arrays and nullables required while generated counterparts stay optional', () => {
    expectTypeOf<Omit<WatchlistScoreItem, 'factors'>>().not.toMatchTypeOf<WatchlistScoreItem>();
    expectTypeOf<Omit<OpenApiItem, 'factors'>>().toMatchTypeOf<OpenApiItem>();
    expectTypeOf<Omit<WatchlistScoreItem, 'score'>>().not.toMatchTypeOf<WatchlistScoreItem>();
    expectTypeOf<Omit<OpenApiItem, 'score'>>().toMatchTypeOf<OpenApiItem>();
    expectTypeOf<Omit<WatchlistScoreItem, 'degradedReasons'>>().not.toMatchTypeOf<WatchlistScoreItem>();
    expectTypeOf<Omit<OpenApiItem, 'degraded_reasons'>>().toMatchTypeOf<OpenApiItem>();
    expectTypeOf<Omit<WatchlistScoreFactor, 'value'>>().not.toMatchTypeOf<WatchlistScoreFactor>();
    expectTypeOf<Omit<OpenApiFactor, 'value'>>().toMatchTypeOf<OpenApiFactor>();
  });

  it('rejects illegal enum widening on freshness, status, and sort', () => {
    expectTypeOf({
      stockCode: 'AAPL',
      status: 'unanalyzed' as const,
      score: null,
      asOf: null,
      ageDays: null,
      analysisId: null,
      operationAdvice: null,
      factors: [],
      freshness: 'mystery' as string,
      degradedReasons: [],
    }).not.toMatchTypeOf<WatchlistScoreItem>();
    expectTypeOf({
      stockCode: 'AAPL',
      status: 'mystery' as string,
      score: null,
      asOf: null,
      ageDays: null,
      analysisId: null,
      operationAdvice: null,
      factors: [],
      freshness: 'none' as const,
      degradedReasons: [],
    }).not.toMatchTypeOf<WatchlistScoreItem>();
    expectTypeOf<string>().not.toMatchTypeOf<WatchlistScoreFreshness>();
    expectTypeOf<string>().not.toMatchTypeOf<WatchlistScoreStatus>();
    expectTypeOf<string>().not.toMatchTypeOf<WatchlistScoreSortMode>();
    expectTypeOf<'none'>().toMatchTypeOf<WatchlistScoreFreshness>();
    expectTypeOf<'unanalyzed'>().toMatchTypeOf<WatchlistScoreStatus>();
    expectTypeOf<'manual'>().toMatchTypeOf<WatchlistScoreSortMode>();
  });

  it('still accepts the narrow existing scored, unanalyzed, and response fixtures', () => {
    const unanalyzed: WatchlistScoreItem = {
      stockCode: 'AAPL',
      status: 'unanalyzed',
      score: null,
      asOf: null,
      ageDays: null,
      analysisId: null,
      operationAdvice: null,
      factors: [],
      freshness: 'none',
      degradedReasons: [],
    };
    const scored: WatchlistScoreItem = {
      stockCode: '600519',
      status: 'scored',
      score: 72,
      asOf: '2026-08-08T09:00:00+00:00',
      ageDays: 1,
      analysisId: 5,
      operationAdvice: 'Buy',
      freshness: 'recent',
      degradedReasons: [],
      factors: [
        {
          key: 'analysis_sentiment',
          status: 'applied',
          value: 72,
          params: { operationAdvice: 'Buy', reportType: 'detailed' },
          reason: null,
          source: {
            id: 5,
            sourceReportId: 5,
            profile: null,
            asOf: '2026-08-08T09:00:00+00:00',
            expiresAt: null,
            formulaVersion: 'watchlist_score_v1',
          },
        },
      ],
    };
    const response: WatchlistScoreResponse = {
      formulaVersion: 'watchlist_score_v1',
      scoringMode: 'aggregate_existing',
      sort: 'manual',
      items: [unanalyzed, scored],
      queryCount: { analysis: 1, signals: 1 },
      sourceRows: { analysis: 2, signals: 0 },
      disclaimerKey: 'watchlist_score.disclaimer',
    };
    expectTypeOf(unanalyzed).toMatchTypeOf<WatchlistScoreItem>();
    expectTypeOf(scored).toMatchTypeOf<WatchlistScoreItem>();
    expectTypeOf(response).toMatchTypeOf<WatchlistScoreResponse>();
    expectTypeOf(SOURCE_REST).toMatchTypeOf<WatchlistScoreFactorSource>();
  });

  it('does not re-export generated snake_case as the UI type', () => {
    const snakeItem = {
      stock_code: 'AAPL',
      status: 'unanalyzed' as const,
      freshness: 'none' as const,
    };
    const snakeResponse = {
      formula_version: 'watchlist_score_v1' as const,
      scoring_mode: 'aggregate_existing' as const,
      sort: 'manual' as const,
      items: [],
      query_count: { analysis: 0, signals: 0 },
      source_rows: { analysis: 0, signals: 0 },
      disclaimer_key: 'watchlist_score.disclaimer' as const,
    };
    expectTypeOf(snakeItem).toMatchTypeOf<OpenApiItem>();
    expectTypeOf(snakeItem).not.toMatchTypeOf<WatchlistScoreItem>();
    expectTypeOf(snakeResponse).toMatchTypeOf<OpenApiResponse>();
    expectTypeOf(snakeResponse).not.toMatchTypeOf<WatchlistScoreResponse>();
  });
});
