// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as Backtest from '../backtest';
import type {
  BacktestAppliedConfig,
  BacktestMethodology,
  BacktestPhaseFilter,
  BacktestResultItem,
  BacktestResultsResponse,
  BacktestRunRequest,
  BacktestRunResponse,
  PerformanceMetrics,
} from '../backtest';
import type { MarketPhaseSummary } from '../analysis';

type OpenApiRunRequest = components['schemas']['BacktestRunRequest'];
type OpenApiApplied = components['schemas']['BacktestAppliedConfig'];
type OpenApiMethodology = components['schemas']['BacktestMethodology'];
type OpenApiRunResponse = components['schemas']['BacktestRunResponse'];
type OpenApiResultItem = components['schemas']['BacktestResultItem'];
type OpenApiResults = components['schemas']['BacktestResultsResponse'];
type OpenApiMetrics = components['schemas']['PerformanceMetrics'];
type OpenApiGeneratedPhase = components['schemas']['MarketPhaseSummary'];

type OpenApiRunOp = operations['run_backtest_api_v1_backtest_run_post'];
type OpenApiResultsOp = operations['get_backtest_results_api_v1_backtest_results_get'];
type OpenApiOverallPerfOp = operations['get_overall_performance_api_v1_backtest_performance_get'];
type OpenApiStockPerfOp = operations['get_stock_performance_api_v1_backtest_performance__code__get'];

type OpenApiRunPathPost = paths['/api/v1/backtest/run']['post'];
type OpenApiResultsPathGet = paths['/api/v1/backtest/results']['get'];
type OpenApiOverallPerfPathGet = paths['/api/v1/backtest/performance']['get'];
type OpenApiStockPerfPathGet = paths['/api/v1/backtest/performance/{code}']['get'];

type OpenApiRunPost200 = OpenApiRunOp['responses']['200']['content']['application/json'];
type OpenApiRunBody = OpenApiRunOp['requestBody']['content']['application/json'];
type OpenApiResultsGet200 = OpenApiResultsOp['responses']['200']['content']['application/json'];
type OpenApiOverallPerfGet200 = OpenApiOverallPerfOp['responses']['200']['content']['application/json'];
type OpenApiStockPerfGet200 = OpenApiStockPerfOp['responses']['200']['content']['application/json'];
type OpenApiOverallQuery = NonNullable<OpenApiOverallPerfOp['parameters']['query']>;
type OpenApiResultsQuery = NonNullable<OpenApiResultsOp['parameters']['query']>;

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

type _SevenComponents = _Assert<
  (
    | 'BacktestRunRequest'
    | 'BacktestAppliedConfig'
    | 'BacktestMethodology'
    | 'BacktestRunResponse'
    | 'BacktestResultItem'
    | 'BacktestResultsResponse'
    | 'PerformanceMetrics'
  ) extends keyof components['schemas'] ? true : false
>;

type _Run200IsResponse = _Assert<OpenApiRunPost200 extends OpenApiRunResponse ? true : false>;
type _ResponseIsRun200 = _Assert<OpenApiRunResponse extends OpenApiRunPost200 ? true : false>;
type _RunOpIsPath = _Assert<OpenApiRunOp extends OpenApiRunPathPost ? true : false>;
type _PathIsRunOp = _Assert<OpenApiRunPathPost extends OpenApiRunOp ? true : false>;
type _RunBodyIsRequest = _Assert<OpenApiRunBody extends OpenApiRunRequest ? true : false>;
type _RequestIsRunBody = _Assert<OpenApiRunRequest extends OpenApiRunBody ? true : false>;
type _RunHas200 = _Assert<200 extends keyof OpenApiRunOp['responses'] ? true : false>;
type _RunLacks201 = _Assert<201 extends keyof OpenApiRunOp['responses'] ? false : true>;
type _Results200IsResults = _Assert<OpenApiResultsGet200 extends OpenApiResults ? true : false>;
type _ResultsIsResults200 = _Assert<OpenApiResults extends OpenApiResultsGet200 ? true : false>;
type _ResultsOpIsPath = _Assert<OpenApiResultsOp extends OpenApiResultsPathGet ? true : false>;
type _PathIsResultsOp = _Assert<OpenApiResultsPathGet extends OpenApiResultsOp ? true : false>;
type _ResultsGetNeverRequestBody = _Assert<OpenApiResultsOp extends { requestBody?: never } ? true : false>;
type _Overall200IsMetrics = _Assert<OpenApiOverallPerfGet200 extends OpenApiMetrics ? true : false>;
type _MetricsIsOverall200 = _Assert<OpenApiMetrics extends OpenApiOverallPerfGet200 ? true : false>;
type _OverallOpIsPath = _Assert<OpenApiOverallPerfOp extends OpenApiOverallPerfPathGet ? true : false>;
type _PathIsOverallOp = _Assert<OpenApiOverallPerfPathGet extends OpenApiOverallPerfOp ? true : false>;
type _OverallGetNeverRequestBody = _Assert<OpenApiOverallPerfOp extends { requestBody?: never } ? true : false>;
type _Stock200IsMetrics = _Assert<OpenApiStockPerfGet200 extends OpenApiMetrics ? true : false>;
type _MetricsIsStock200 = _Assert<OpenApiMetrics extends OpenApiStockPerfGet200 ? true : false>;
type _StockOpIsPath = _Assert<OpenApiStockPerfOp extends OpenApiStockPerfPathGet ? true : false>;
type _PathIsStockOp = _Assert<OpenApiStockPerfPathGet extends OpenApiStockPerfOp ? true : false>;
type _StockGetNeverRequestBody = _Assert<OpenApiStockPerfOp extends { requestBody?: never } ? true : false>;

type _UiHasEvalWindowDays = _Assert<'evalWindowDays' extends keyof BacktestRunRequest ? true : false>;
type _UiHasAppliedEvalWindowDays = _Assert<'appliedEvalWindowDays' extends keyof BacktestRunResponse ? true : false>;
type _UiHasAnalysisHistoryId = _Assert<'analysisHistoryId' extends keyof BacktestResultItem ? true : false>;
type _UiHasEngineVersion = _Assert<'engineVersion' extends keyof BacktestMethodology ? true : false>;
type _UiHasWinRatePct = _Assert<'winRatePct' extends keyof PerformanceMetrics ? true : false>;
type _UiHasCostModel = _Assert<'costModel' extends keyof BacktestMethodology ? true : false>;
type _UiLacksEvalWindowDaysSnake = _Assert<'eval_window_days' extends keyof BacktestRunRequest ? false : true>;
type _UiLacksAppliedEvalWindowDaysSnake = _Assert<'applied_eval_window_days' extends keyof BacktestRunResponse ? false : true>;
type _UiLacksAnalysisHistoryIdSnake = _Assert<'analysis_history_id' extends keyof BacktestResultItem ? false : true>;
type _UiLacksEngineVersionSnake = _Assert<'engine_version' extends keyof BacktestMethodology ? false : true>;
type _UiLacksWinRatePctSnake = _Assert<'win_rate_pct' extends keyof PerformanceMetrics ? false : true>;
type _UiLacksCostModelSnake = _Assert<'cost_model' extends keyof BacktestMethodology ? false : true>;
type _GeneratedHasEvalWindowDaysSnake = _Assert<'eval_window_days' extends keyof OpenApiRunRequest ? true : false>;
type _GeneratedHasAppliedEvalWindowDaysSnake = _Assert<'applied_eval_window_days' extends keyof OpenApiRunResponse ? true : false>;
type _GeneratedHasAnalysisHistoryIdSnake = _Assert<'analysis_history_id' extends keyof OpenApiResultItem ? true : false>;
type _GeneratedHasEngineVersionSnake = _Assert<'engine_version' extends keyof OpenApiMethodology ? true : false>;
type _GeneratedHasWinRatePctSnake = _Assert<'win_rate_pct' extends keyof OpenApiMetrics ? true : false>;
type _GeneratedHasCostModelSnake = _Assert<'cost_model' extends keyof OpenApiMethodology ? true : false>;
type _GeneratedLacksEvalWindowDaysCamel = _Assert<'evalWindowDays' extends keyof OpenApiRunRequest ? false : true>;
type _GeneratedLacksAppliedEvalWindowDaysCamel = _Assert<'appliedEvalWindowDays' extends keyof OpenApiRunResponse ? false : true>;
type _GeneratedLacksAnalysisHistoryIdCamel = _Assert<'analysisHistoryId' extends keyof OpenApiResultItem ? false : true>;
type _GeneratedLacksEngineVersionCamel = _Assert<'engineVersion' extends keyof OpenApiMethodology ? false : true>;
type _GeneratedLacksWinRatePctCamel = _Assert<'winRatePct' extends keyof OpenApiMetrics ? false : true>;
type _GeneratedLacksCostModelCamel = _Assert<'costModel' extends keyof OpenApiMethodology ? false : true>;

type _UiItemsRequired = _Assert<IsOptional<BacktestResultsResponse, 'items'> extends false ? true : false>;
type _GeneratedItemsOptional = _Assert<IsOptional<OpenApiResults, 'items'>>;
type _NaiveItemsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiResults>, 'items'>>;

type _UiForceOptional = _Assert<IsOptional<BacktestRunRequest, 'force'>>;
type _UiLimitOptional = _Assert<IsOptional<BacktestRunRequest, 'limit'>>;
type _NaiveForceRequired = _Assert<IsOptional<CamelizeKeys<OpenApiRunRequest>, 'force'> extends false ? true : false>;
type _NaiveLimitRequired = _Assert<IsOptional<CamelizeKeys<OpenApiRunRequest>, 'limit'> extends false ? true : false>;

type _UiCommissionOptional = _Assert<IsOptional<BacktestAppliedConfig, 'commissionBps'>>;
type _UiSlippageOptional = _Assert<IsOptional<BacktestAppliedConfig, 'slippageBps'>>;
type _UiRoundTripOptional = _Assert<IsOptional<BacktestAppliedConfig, 'roundTripCostPct'>>;
type _NaiveCommissionRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiApplied>, 'commissionBps'> extends false ? true : false
>;
type _NaiveSlippageRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiApplied>, 'slippageBps'> extends false ? true : false
>;
type _NaiveRoundTripRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiApplied>, 'roundTripCostPct'> extends false ? true : false
>;

type _UiVersionOptional = _Assert<IsOptional<BacktestMethodology, 'version'>>;
type _UiMetricSourceOptional = _Assert<IsOptional<BacktestMethodology, 'metricSource'>>;
type _UiLookAheadOptional = _Assert<IsOptional<BacktestMethodology, 'lookAheadPolicy'>>;
type _UiSurvivorshipOptional = _Assert<IsOptional<BacktestMethodology, 'survivorshipPolicy'>>;
type _UiReturnUnitsOptional = _Assert<IsOptional<BacktestMethodology, 'returnUnits'>>;
type _UiCurrencyOptional = _Assert<IsOptional<BacktestMethodology, 'currencyPolicy'>>;
type _NaiveVersionRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiMethodology>, 'version'> extends false ? true : false
>;
type _NaiveMetricSourceRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiMethodology>, 'metricSource'> extends false ? true : false
>;
type _NaiveLookAheadRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiMethodology>, 'lookAheadPolicy'> extends false ? true : false
>;
type _NaiveSurvivorshipRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiMethodology>, 'survivorshipPolicy'> extends false ? true : false
>;
type _NaiveReturnUnitsRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiMethodology>, 'returnUnits'> extends false ? true : false
>;
type _NaiveCurrencyRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiMethodology>, 'currencyPolicy'> extends false ? true : false
>;

type _UiPhaseFilterHasAll = _Assert<'all' extends BacktestPhaseFilter ? true : false>;
type _GeneratedOverallPhaseLacksAll = _Assert<
  'all' extends NonNullable<OpenApiOverallQuery['analysis_phase']> ? false : true
>;
type _GeneratedResultsPhaseLacksAll = _Assert<
  'all' extends NonNullable<OpenApiResultsQuery['analysis_phase']> ? false : true
>;

type _UiWarningsRequired = _Assert<IsOptional<MarketPhaseSummary, 'warnings'> extends false ? true : false>;
type _GeneratedWarningsOptional = _Assert<IsOptional<OpenApiGeneratedPhase, 'warnings'>>;

type PartialRun = { code: '600519'; force: true };
type _PartialRunAssignable = _Assert<PartialRun extends BacktestRunRequest ? true : false>;
type _NaivePartialRejected = _Assert<PartialRun extends CamelizeKeys<OpenApiRunRequest> ? false : true>;

type PageApplied = {
  code: null;
  force: false;
  evalWindowDays: 10;
  minAgeDays: 14;
  limit: 200;
  engineVersion: string;
  neutralBandPct: 2;
  analysisDateFrom: null;
  analysisDateTo: null;
};
type _PageAppliedAssignable = _Assert<PageApplied extends BacktestAppliedConfig ? true : false>;
type _NaiveAppliedRejected = _Assert<PageApplied extends CamelizeKeys<OpenApiApplied> ? false : true>;

type PartialMethodology = {
  engineVersion: string;
  isReturnPromise: false;
  disclaimer: string;
};
type _PartialMethodologyAssignable = _Assert<PartialMethodology extends BacktestMethodology ? true : false>;
type _NaiveMethodologyRejected = _Assert<
  PartialMethodology extends CamelizeKeys<OpenApiMethodology> ? false : true
>;

type OmittedItems = { total: number; page: number; limit: number };
type _OmittedItemsRejected = _Assert<OmittedItems extends BacktestResultsResponse ? false : true>;
type _NaiveOmittedItemsAssignable = _Assert<OmittedItems extends CamelizeKeys<OpenApiResults> ? true : false>;

type _CompileTimePins = [
  _SevenComponents,
  _Run200IsResponse,
  _ResponseIsRun200,
  _RunOpIsPath,
  _PathIsRunOp,
  _RunBodyIsRequest,
  _RequestIsRunBody,
  _RunHas200,
  _RunLacks201,
  _Results200IsResults,
  _ResultsIsResults200,
  _ResultsOpIsPath,
  _PathIsResultsOp,
  _ResultsGetNeverRequestBody,
  _Overall200IsMetrics,
  _MetricsIsOverall200,
  _OverallOpIsPath,
  _PathIsOverallOp,
  _OverallGetNeverRequestBody,
  _Stock200IsMetrics,
  _MetricsIsStock200,
  _StockOpIsPath,
  _PathIsStockOp,
  _StockGetNeverRequestBody,
  _UiHasEvalWindowDays,
  _UiHasAppliedEvalWindowDays,
  _UiHasAnalysisHistoryId,
  _UiHasEngineVersion,
  _UiHasWinRatePct,
  _UiHasCostModel,
  _UiLacksEvalWindowDaysSnake,
  _UiLacksAppliedEvalWindowDaysSnake,
  _UiLacksAnalysisHistoryIdSnake,
  _UiLacksEngineVersionSnake,
  _UiLacksWinRatePctSnake,
  _UiLacksCostModelSnake,
  _GeneratedHasEvalWindowDaysSnake,
  _GeneratedHasAppliedEvalWindowDaysSnake,
  _GeneratedHasAnalysisHistoryIdSnake,
  _GeneratedHasEngineVersionSnake,
  _GeneratedHasWinRatePctSnake,
  _GeneratedHasCostModelSnake,
  _GeneratedLacksEvalWindowDaysCamel,
  _GeneratedLacksAppliedEvalWindowDaysCamel,
  _GeneratedLacksAnalysisHistoryIdCamel,
  _GeneratedLacksEngineVersionCamel,
  _GeneratedLacksWinRatePctCamel,
  _GeneratedLacksCostModelCamel,
  _UiItemsRequired,
  _GeneratedItemsOptional,
  _NaiveItemsOptional,
  _UiForceOptional,
  _UiLimitOptional,
  _NaiveForceRequired,
  _NaiveLimitRequired,
  _UiCommissionOptional,
  _UiSlippageOptional,
  _UiRoundTripOptional,
  _NaiveCommissionRequired,
  _NaiveSlippageRequired,
  _NaiveRoundTripRequired,
  _UiVersionOptional,
  _UiMetricSourceOptional,
  _UiLookAheadOptional,
  _UiSurvivorshipOptional,
  _UiReturnUnitsOptional,
  _UiCurrencyOptional,
  _NaiveVersionRequired,
  _NaiveMetricSourceRequired,
  _NaiveLookAheadRequired,
  _NaiveSurvivorshipRequired,
  _NaiveReturnUnitsRequired,
  _NaiveCurrencyRequired,
  _UiPhaseFilterHasAll,
  _GeneratedOverallPhaseLacksAll,
  _GeneratedResultsPhaseLacksAll,
  _UiWarningsRequired,
  _GeneratedWarningsOptional,
  _PartialRunAssignable,
  _NaivePartialRejected,
  _PageAppliedAssignable,
  _NaiveAppliedRejected,
  _PartialMethodologyAssignable,
  _NaiveMethodologyRejected,
  _OmittedItemsRejected,
  _NaiveOmittedItemsAssignable,
];

const runBase = { code: '600519', force: true };

// @ts-expect-error futurePolicy is not a public run field
const extraRun: BacktestRunRequest = { ...runBase, futurePolicy: true };

const appliedBase = {
  code: null,
  force: false,
  evalWindowDays: 10,
  minAgeDays: 14,
  limit: 200,
  engineVersion: 'test-engine',
  neutralBandPct: 2,
  analysisDateFrom: null,
  analysisDateTo: null,
};

// @ts-expect-error futureCostFlag is not a public appliedConfig field
const extraApplied: BacktestAppliedConfig = { ...appliedBase, futureCostFlag: true };

void extraRun;
void extraApplied;

describe('backtest OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    expect({ ...Backtest }).toEqual({});
    expect(Object.keys(Backtest)).toEqual([]);
    expect(Object.getOwnPropertyNames(Backtest)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates path 200 JSON to the named components, keeps GET requestBody never, and uses run 200 not 201', () => {
    expectTypeOf<OpenApiRunPost200>().toEqualTypeOf<OpenApiRunResponse>();
    expectTypeOf<OpenApiRunBody>().toEqualTypeOf<OpenApiRunRequest>();
    expectTypeOf<OpenApiResultsGet200>().toEqualTypeOf<OpenApiResults>();
    expectTypeOf<OpenApiOverallPerfGet200>().toEqualTypeOf<OpenApiMetrics>();
    expectTypeOf<OpenApiStockPerfGet200>().toEqualTypeOf<OpenApiMetrics>();
    expectTypeOf<OpenApiRunOp>().toEqualTypeOf<OpenApiRunPathPost>();
    expectTypeOf<OpenApiResultsOp>().toEqualTypeOf<OpenApiResultsPathGet>();
    expectTypeOf<OpenApiOverallPerfOp>().toEqualTypeOf<OpenApiOverallPerfPathGet>();
    expectTypeOf<OpenApiStockPerfOp>().toEqualTypeOf<OpenApiStockPerfPathGet>();
    type ResultsNeverBody = OpenApiResultsOp extends { requestBody?: never } ? true : false;
    type OverallNeverBody = OpenApiOverallPerfOp extends { requestBody?: never } ? true : false;
    type StockNeverBody = OpenApiStockPerfOp extends { requestBody?: never } ? true : false;
    type RunHas201 = 201 extends keyof OpenApiRunOp['responses'] ? true : false;
    expectTypeOf<ResultsNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<OverallNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<StockNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<RunHas201>().toEqualTypeOf<false>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof BacktestRunRequest>().not.toMatchTypeOf<'eval_window_days'>();
    expectTypeOf<keyof BacktestRunResponse>().not.toMatchTypeOf<'applied_eval_window_days'>();
    expectTypeOf<keyof BacktestResultItem>().not.toMatchTypeOf<'analysis_history_id'>();
    expectTypeOf<keyof BacktestMethodology>().not.toMatchTypeOf<'engine_version' | 'cost_model'>();
    expectTypeOf<keyof PerformanceMetrics>().not.toMatchTypeOf<'win_rate_pct'>();
    expectTypeOf<keyof OpenApiRunRequest>().not.toMatchTypeOf<'evalWindowDays'>();
    expectTypeOf<keyof OpenApiRunResponse>().not.toMatchTypeOf<'appliedEvalWindowDays'>();
    expectTypeOf<keyof OpenApiResultItem>().not.toMatchTypeOf<'analysisHistoryId'>();
    expectTypeOf<keyof OpenApiMethodology>().not.toMatchTypeOf<'engineVersion' | 'costModel'>();
    expectTypeOf<keyof OpenApiMetrics>().not.toMatchTypeOf<'winRatePct'>();
  });

  it('keeps UI results items required while naive CamelizeKeys leaves them optional', () => {
    const omittedItems = { total: 0, page: 1, limit: 20 };
    expectTypeOf(omittedItems).not.toMatchTypeOf<BacktestResultsResponse>();
    expectTypeOf(omittedItems).toMatchTypeOf<CamelizeKeys<OpenApiResults>>();
    type UiItemsOptional = IsOptional<BacktestResultsResponse, 'items'>;
    type NaiveItemsOptional = IsOptional<CamelizeKeys<OpenApiResults>, 'items'>;
    expectTypeOf<UiItemsOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveItemsOptional>().toEqualTypeOf<true>();
  });

  it('keeps UI run force and limit optional so empty and partial run fixtures assign', () => {
    type UiForceOptional = IsOptional<BacktestRunRequest, 'force'>;
    type UiLimitOptional = IsOptional<BacktestRunRequest, 'limit'>;
    type NaiveForceOptional = IsOptional<CamelizeKeys<OpenApiRunRequest>, 'force'>;
    type NaiveLimitOptional = IsOptional<CamelizeKeys<OpenApiRunRequest>, 'limit'>;
    expectTypeOf<UiForceOptional>().toEqualTypeOf<true>();
    expectTypeOf<UiLimitOptional>().toEqualTypeOf<true>();
    expectTypeOf<NaiveForceOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveLimitOptional>().toEqualTypeOf<false>();
    expectTypeOf({}).toMatchTypeOf<BacktestRunRequest>();
    expectTypeOf({ code: '600519', force: true }).toMatchTypeOf<BacktestRunRequest>();
    expectTypeOf({}).not.toMatchTypeOf<CamelizeKeys<OpenApiRunRequest>>();
    expectTypeOf({ code: '600519', force: true }).not.toMatchTypeOf<CamelizeKeys<OpenApiRunRequest>>();
  });

  it('keeps UI appliedConfig cost fields optional so the page fixture assigns', () => {
    type UiCommissionOptional = IsOptional<BacktestAppliedConfig, 'commissionBps'>;
    type NaiveCommissionOptional = IsOptional<CamelizeKeys<OpenApiApplied>, 'commissionBps'>;
    expectTypeOf<UiCommissionOptional>().toEqualTypeOf<true>();
    expectTypeOf<NaiveCommissionOptional>().toEqualTypeOf<false>();
    expectTypeOf(appliedBase).toMatchTypeOf<BacktestAppliedConfig>();
    expectTypeOf(appliedBase).not.toMatchTypeOf<CamelizeKeys<OpenApiApplied>>();
  });

  it('keeps UI methodology defaulted fields optional while naive CamelizeKeys requires them', () => {
    const partialMethodology = {
      engineVersion: 'v1',
      isReturnPromise: false,
      disclaimer: 'historical simulation only',
    };
    expectTypeOf(partialMethodology).toMatchTypeOf<BacktestMethodology>();
    expectTypeOf(partialMethodology).not.toMatchTypeOf<CamelizeKeys<OpenApiMethodology>>();
    type UiCurrencyOptional = IsOptional<BacktestMethodology, 'currencyPolicy'>;
    type NaiveCurrencyOptional = IsOptional<CamelizeKeys<OpenApiMethodology>, 'currencyPolicy'>;
    expectTypeOf<UiCurrencyOptional>().toEqualTypeOf<true>();
    expectTypeOf<NaiveCurrencyOptional>().toEqualTypeOf<false>();
  });

  it('accepts diagnostics bag extras on UI PerformanceMetrics', () => {
    const metricsBase = {
      scope: 'overall',
      evalWindowDays: 10,
      engineVersion: 'test-engine',
      totalEvaluations: 3,
      completedCount: 2,
      insufficientCount: 1,
      longCount: 2,
      cashCount: 1,
      winCount: 1,
      lossCount: 1,
      neutralCount: 0,
    };
    const withDiagnostics = {
      ...metricsBase,
      diagnostics: { phaseBreakdown: {}, futureDiag: true },
    };
    expectTypeOf(withDiagnostics).toMatchTypeOf<PerformanceMetrics>();
  });

  it("keeps handwritten BacktestPhaseFilter including 'all' while generated query analysis_phase does not", () => {
    expectTypeOf<'all'>().toMatchTypeOf<BacktestPhaseFilter>();
    type GeneratedOverallHasAll = 'all' extends NonNullable<OpenApiOverallQuery['analysis_phase']> ? true : false;
    type GeneratedResultsHasAll = 'all' extends NonNullable<OpenApiResultsQuery['analysis_phase']> ? true : false;
    expectTypeOf<GeneratedOverallHasAll>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedResultsHasAll>().toEqualTypeOf<false>();
  });

  it('keeps analysis MarketPhaseSummary warnings required on UI result items', () => {
    const summaryWithWarnings: MarketPhaseSummary = { phase: 'premarket', warnings: [] };
    const item: BacktestResultItem = {
      analysisHistoryId: 101,
      code: '600519',
      evalWindowDays: 10,
      engineVersion: 'test-engine',
      evalStatus: 'completed',
      marketPhaseSummary: summaryWithWarnings,
    };
    expectTypeOf(item).toMatchTypeOf<BacktestResultItem>();
    type UiWarningsOptional = IsOptional<MarketPhaseSummary, 'warnings'>;
    type GeneratedWarningsOptional = IsOptional<OpenApiGeneratedPhase, 'warnings'>;
    expectTypeOf<UiWarningsOptional>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedWarningsOptional>().toEqualTypeOf<true>();
  });
});
