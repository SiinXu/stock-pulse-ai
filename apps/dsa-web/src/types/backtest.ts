// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { components, operations, paths } from './api.generated';
import type { DecisionAction, MarketPhaseSummary } from './analysis';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type Override<T, U> = Omit<T, keyof U> & U;

type OpenApiRunRequest = components['schemas']['BacktestRunRequest'];
type OpenApiApplied = components['schemas']['BacktestAppliedConfig'];
type OpenApiMethodology = components['schemas']['BacktestMethodology'];
type OpenApiRunResponse = components['schemas']['BacktestRunResponse'];
type OpenApiResultItem = components['schemas']['BacktestResultItem'];
type OpenApiResults = components['schemas']['BacktestResultsResponse'];
type OpenApiMetrics = components['schemas']['PerformanceMetrics'];

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

type _Assert<T extends true> = T;
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

type _OpenApiAnchors = [
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
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type BacktestAnalysisPhase = 'premarket' | 'intraday' | 'postmarket' | 'unknown';
export type BacktestPhaseFilter = BacktestAnalysisPhase | 'all';

export type BacktestAppliedConfig = Override<CamelizeKeys<OpenApiApplied>, {
  commissionBps?: number;
  slippageBps?: number;
  roundTripCostPct?: number;
}>;

export type BacktestMethodology = Override<CamelizeKeys<OpenApiMethodology>, {
  version?: string;
  metricSource?: string;
  disclaimerCodes?: string[];
  lookAheadPolicy?: string;
  survivorshipPolicy?: string;
  costModel?: Record<string, unknown>;
  sampleSplit?: Record<string, unknown>;
  returnUnits?: string;
  currencyPolicy?: string;
  limitations?: string[];
}>;

export type BacktestRunRequest = Override<CamelizeKeys<OpenApiRunRequest>, {
  code?: string;
  force?: boolean;
  evalWindowDays?: number;
  minAgeDays?: number;
  analysisDateFrom?: string;
  analysisDateTo?: string;
  limit?: number;
}>;

export type BacktestResultItem = Override<CamelizeKeys<OpenApiResultItem>, {
  stockName?: string;
  analysisDate?: string;
  evaluatedAt?: string;
  operationAdvice?: string;
  action?: DecisionAction | null;
  trendPrediction?: string;
  marketPhaseSummary?: MarketPhaseSummary | null;
  positionRecommendation?: string;
  startPrice?: number;
  endClose?: number;
  maxHigh?: number;
  minLow?: number;
  stockReturnPct?: number;
  actualReturnPct?: number;
  actualMovement?: string;
  directionExpected?: string;
  directionCorrect?: boolean;
  outcome?: string;
  stopLoss?: number;
  takeProfit?: number;
  hitStopLoss?: boolean;
  hitTakeProfit?: boolean;
  firstHit?: string;
  firstHitDate?: string;
  firstHitTradingDays?: number;
  simulatedEntryPrice?: number;
  simulatedExitPrice?: number;
  simulatedExitReason?: string;
  simulatedReturnPct?: number;
}>;

export type BacktestRunResponse = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiRunResponse>, {
  appliedConfig?: BacktestAppliedConfig | null;
  methodology?: BacktestMethodology | null;
  diagnostics?: Record<string, unknown>;
}>>;

export type BacktestResultsResponse = Override<CamelizeKeys<OpenApiResults>, {
  items: BacktestResultItem[];
}>;

export type PerformanceMetrics = Override<CamelizeKeys<OpenApiMetrics>, {
  code?: string;
  computedAt?: string;
  adviceBreakdown?: Record<string, unknown>;
  diagnostics?: Record<string, unknown>;
  methodology?: BacktestMethodology | null;
}>;
