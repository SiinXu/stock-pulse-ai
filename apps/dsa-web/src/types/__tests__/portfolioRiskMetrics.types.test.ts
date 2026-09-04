// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as PortfolioRiskMetrics from '../portfolioRiskMetrics';
import type {
  PortfolioConcentrationBlock,
  PortfolioCorrelationBlock,
  PortfolioHistoricalVaRBlock,
  PortfolioRiskAssumptions,
  PortfolioRiskHistoryMeta,
  PortfolioRiskMetricsQuery,
  PortfolioRiskMetricsResponse,
  PortfolioRiskMetricsStatus,
  PortfolioRiskWeightItem,
} from '../portfolioRiskMetrics';

type OpenApiRiskMetrics = components['schemas']['PortfolioRiskMetricsResponse'];
type OpenApiAssumptions = components['schemas']['PortfolioRiskAssumptions'];
type OpenApiVaR = components['schemas']['PortfolioHistoricalVaRBlock'];
type OpenApiCorrelation = components['schemas']['PortfolioCorrelationBlock'];
type OpenApiConcentration = components['schemas']['PortfolioConcentrationBlock'];
type OpenApiHistory = components['schemas']['PortfolioRiskHistoryMeta'];
type OpenApiWeight = components['schemas']['PortfolioRiskWeightItem'];
type OpenApiGetOp = operations['getPortfolioRiskMetrics'];
type OpenApiGet200 = OpenApiGetOp['responses']['200']['content']['application/json'];
type OpenApiPathGet = paths['/api/v1/portfolio/risk-metrics']['get'];
type OpenApiGetQuery = NonNullable<OpenApiGetOp['parameters']['query']>;

type _Assert<T extends true> = T;
type IsOptional<T, K extends keyof T> = Partial<Pick<T, K>> extends Pick<T, K> ? true : false;

type _SevenComponents = _Assert<
  (
    | 'PortfolioRiskMetricsResponse'
    | 'PortfolioRiskAssumptions'
    | 'PortfolioHistoricalVaRBlock'
    | 'PortfolioCorrelationBlock'
    | 'PortfolioConcentrationBlock'
    | 'PortfolioRiskHistoryMeta'
    | 'PortfolioRiskWeightItem'
  ) extends keyof components['schemas'] ? true : false
>;
type _Get200IsComponent = _Assert<OpenApiGet200 extends OpenApiRiskMetrics ? true : false>;
type _ComponentIsGet200 = _Assert<OpenApiRiskMetrics extends OpenApiGet200 ? true : false>;
type _GetOpIsPath = _Assert<OpenApiGetOp extends OpenApiPathGet ? true : false>;
type _PathIsGetOp = _Assert<OpenApiPathGet extends OpenApiGetOp ? true : false>;
type _GetOpHasNeverRequestBody = _Assert<OpenApiGetOp extends { requestBody?: never } ? true : false>;
type _PathPostNever = _Assert<
  paths['/api/v1/portfolio/risk-metrics']['post'] extends never | undefined ? true : false
>;
type _PathPutNever = _Assert<
  paths['/api/v1/portfolio/risk-metrics']['put'] extends never | undefined ? true : false
>;
type _PathDeleteNever = _Assert<
  paths['/api/v1/portfolio/risk-metrics']['delete'] extends never | undefined ? true : false
>;
type _PathPatchNever = _Assert<
  paths['/api/v1/portfolio/risk-metrics']['patch'] extends never | undefined ? true : false
>;

type _UiHasCostMethod = _Assert<'costMethod' extends keyof PortfolioRiskMetricsResponse ? true : false>;
type _UiHasPortfolioValue = _Assert<'portfolioValue' extends keyof PortfolioRiskMetricsResponse ? true : false>;
type _UiHasAccountId = _Assert<'accountId' extends keyof PortfolioRiskMetricsResponse ? true : false>;
type _UiHasAsOf = _Assert<'asOf' extends keyof PortfolioRiskMetricsResponse ? true : false>;
type _UiHasVarMethod = _Assert<'varMethod' extends keyof PortfolioRiskAssumptions ? true : false>;
type _UiHasHorizonDays = _Assert<'horizonDays' extends keyof PortfolioRiskAssumptions ? true : false>;
type _UiHasLookbackTradingDays = _Assert<
  'lookbackTradingDays' extends keyof PortfolioRiskAssumptions ? true : false
>;
type _UiHasPriceSeriesSymbols = _Assert<
  'priceSeriesSymbols' extends keyof PortfolioRiskHistoryMeta ? true : false
>;
type _UiQueryHasAccountId = _Assert<'accountId' extends keyof PortfolioRiskMetricsQuery ? true : false>;
type _UiQueryHasAsOf = _Assert<'asOf' extends keyof PortfolioRiskMetricsQuery ? true : false>;
type _UiQueryHasCostMethod = _Assert<'costMethod' extends keyof PortfolioRiskMetricsQuery ? true : false>;
type _UiQueryHasHorizonDays = _Assert<'horizonDays' extends keyof PortfolioRiskMetricsQuery ? true : false>;
type _UiQueryHasLookbackTradingDays = _Assert<
  'lookbackTradingDays' extends keyof PortfolioRiskMetricsQuery ? true : false
>;

type _UiLacksCostMethodSnake = _Assert<'cost_method' extends keyof PortfolioRiskMetricsResponse ? false : true>;
type _UiLacksPortfolioValueSnake = _Assert<
  'portfolio_value' extends keyof PortfolioRiskMetricsResponse ? false : true
>;
type _UiLacksAccountIdSnake = _Assert<'account_id' extends keyof PortfolioRiskMetricsResponse ? false : true>;
type _UiLacksAsOfSnake = _Assert<'as_of' extends keyof PortfolioRiskMetricsResponse ? false : true>;
type _UiLacksVarMethodSnake = _Assert<'var_method' extends keyof PortfolioRiskAssumptions ? false : true>;
type _UiLacksHorizonDaysSnake = _Assert<'horizon_days' extends keyof PortfolioRiskAssumptions ? false : true>;
type _UiLacksLookbackSnake = _Assert<
  'lookback_trading_days' extends keyof PortfolioRiskAssumptions ? false : true
>;
type _UiLacksPriceSeriesSnake = _Assert<
  'price_series_symbols' extends keyof PortfolioRiskHistoryMeta ? false : true
>;
type _UiQueryLacksAccountIdSnake = _Assert<'account_id' extends keyof PortfolioRiskMetricsQuery ? false : true>;
type _UiQueryLacksAsOfSnake = _Assert<'as_of' extends keyof PortfolioRiskMetricsQuery ? false : true>;
type _UiQueryLacksCostMethodSnake = _Assert<'cost_method' extends keyof PortfolioRiskMetricsQuery ? false : true>;
type _UiQueryLacksHorizonDaysSnake = _Assert<'horizon_days' extends keyof PortfolioRiskMetricsQuery ? false : true>;
type _UiQueryLacksLookbackSnake = _Assert<
  'lookback_trading_days' extends keyof PortfolioRiskMetricsQuery ? false : true
>;

type _GeneratedHasCostMethodSnake = _Assert<'cost_method' extends keyof OpenApiRiskMetrics ? true : false>;
type _GeneratedHasPortfolioValueSnake = _Assert<'portfolio_value' extends keyof OpenApiRiskMetrics ? true : false>;
type _GeneratedHasAccountIdSnake = _Assert<'account_id' extends keyof OpenApiRiskMetrics ? true : false>;
type _GeneratedHasAsOfSnake = _Assert<'as_of' extends keyof OpenApiRiskMetrics ? true : false>;
type _GeneratedHasVarMethodSnake = _Assert<'var_method' extends keyof OpenApiAssumptions ? true : false>;
type _GeneratedHasHorizonDaysSnake = _Assert<'horizon_days' extends keyof OpenApiAssumptions ? true : false>;
type _GeneratedHasLookbackSnake = _Assert<'lookback_trading_days' extends keyof OpenApiAssumptions ? true : false>;
type _GeneratedHasPriceSeriesSnake = _Assert<'price_series_symbols' extends keyof OpenApiHistory ? true : false>;
type _GeneratedQueryHasAccountIdSnake = _Assert<'account_id' extends keyof OpenApiGetQuery ? true : false>;
type _GeneratedQueryHasAsOfSnake = _Assert<'as_of' extends keyof OpenApiGetQuery ? true : false>;
type _GeneratedQueryHasCostMethodSnake = _Assert<'cost_method' extends keyof OpenApiGetQuery ? true : false>;
type _GeneratedQueryHasHorizonDaysSnake = _Assert<'horizon_days' extends keyof OpenApiGetQuery ? true : false>;
type _GeneratedQueryHasLookbackSnake = _Assert<'lookback_trading_days' extends keyof OpenApiGetQuery ? true : false>;
type _GeneratedLacksCostMethodCamel = _Assert<'costMethod' extends keyof OpenApiRiskMetrics ? false : true>;
type _GeneratedLacksPortfolioValueCamel = _Assert<'portfolioValue' extends keyof OpenApiRiskMetrics ? false : true>;

type _UiCostMethodClosed = _Assert<
  PortfolioRiskMetricsResponse['costMethod'] extends 'fifo' | 'avg'
    ? 'fifo' | 'avg' extends PortfolioRiskMetricsResponse['costMethod'] ? true : false
    : false
>;
type _GeneratedCostMethodIsString = _Assert<
  string extends OpenApiRiskMetrics['cost_method'] ? true : false
>;
type _UiQueryCostMethodClosed = _Assert<
  NonNullable<PortfolioRiskMetricsQuery['costMethod']> extends 'fifo' | 'avg' ? true : false
>;
type _GeneratedQueryCostMethodIsString = _Assert<
  string extends NonNullable<OpenApiGetQuery['cost_method']> ? true : false
>;
type _UiStatusClosed = _Assert<
  PortfolioRiskMetricsStatus extends 'ok' | 'empty_portfolio' | 'insufficient_history' | 'partial'
    ? 'ok' | 'empty_portfolio' | 'insufficient_history' | 'partial' extends PortfolioRiskMetricsStatus
      ? true
      : false
    : false
>;
type _PendingRejected = _Assert<'pending' extends PortfolioRiskMetricsStatus ? false : true>;
type _StringStatusRejected = _Assert<string extends PortfolioRiskMetricsStatus ? false : true>;
type _GeneratedStatusIsString = _Assert<string extends OpenApiRiskMetrics['status'] ? true : false>;
type _GeneratedVaRStatusIsString = _Assert<string extends OpenApiVaR['status'] ? true : false>;
type _GeneratedCorrelationStatusIsString = _Assert<string extends OpenApiCorrelation['status'] ? true : false>;
type _GeneratedConcentrationStatusIsString = _Assert<
  string extends OpenApiConcentration['status'] ? true : false
>;

type _HistoryOptional = _Assert<IsOptional<PortfolioRiskMetricsResponse, 'history'>>;
type _HistoryNullable = _Assert<null extends PortfolioRiskMetricsResponse['history'] ? true : false>;
type _OmitHistoryAssignable = _Assert<
  Omit<PortfolioRiskMetricsResponse, 'history'> extends PortfolioRiskMetricsResponse ? true : false
>;
type _UiHistorySymbolsRequired = _Assert<
  IsOptional<PortfolioRiskHistoryMeta, 'priceSeriesSymbols'> extends false ? true : false
>;
type _GeneratedHistorySymbolsOptional = _Assert<IsOptional<OpenApiHistory, 'price_series_symbols'>>;

type MatrixCell = PortfolioCorrelationBlock['matrix'][number][number];
type _MatrixCell = _Assert<
  MatrixCell extends number | null ? number | null extends MatrixCell ? true : false : false
>;
type GeneratedMatrixCell = NonNullable<OpenApiCorrelation['matrix']>[number][number];
type _GeneratedMatrixCell = _Assert<
  GeneratedMatrixCell extends number | null
    ? number | null extends GeneratedMatrixCell ? true : false
    : false
>;
type _WeightsItem = _Assert<
  PortfolioConcentrationBlock['weights'][number] extends PortfolioRiskWeightItem
    ? PortfolioRiskWeightItem extends PortfolioConcentrationBlock['weights'][number] ? true : false
    : false
>;
type _UiWeightHasWeightPct = _Assert<'weightPct' extends keyof PortfolioRiskWeightItem ? true : false>;
type _UiWeightLacksSnake = _Assert<'weight_pct' extends keyof PortfolioRiskWeightItem ? false : true>;
type _GeneratedWeightHasSnake = _Assert<'weight_pct' extends keyof OpenApiWeight ? true : false>;

type _UiQueryAccountNotNull = _Assert<null extends PortfolioRiskMetricsQuery['accountId'] ? false : true>;
type _GeneratedQueryAccountNull = _Assert<null extends OpenApiGetQuery['account_id'] ? true : false>;
type _UiQueryAsOfNotNull = _Assert<null extends PortfolioRiskMetricsQuery['asOf'] ? false : true>;
type _GeneratedQueryAsOfNull = _Assert<null extends OpenApiGetQuery['as_of'] ? true : false>;
type _QueryKeySetsDiffer = _Assert<
  keyof PortfolioRiskMetricsQuery extends keyof OpenApiGetQuery ? false : true
>;

type NarrowAssumptions = {
  varMethod: string;
  confidence: number;
  horizonDays: number;
  lookbackTradingDays: number;
  minReturnObservations: number;
  minCorrelationObservations: number;
  returnDefinition: string;
  portfolioAggregation: string;
  cashExcluded: boolean;
  weightBasis: string;
  fxPolicy: string;
  horizonScaling: string;
  distributionAssumption: string;
  correlationMethod: string;
  concentrationMetrics: string;
  dataSource: string;
  providerCallsOnHotPath: boolean;
};
type NarrowVaR = {
  status: 'ok';
  observationCount: number;
};
type NarrowCorrelation = {
  status: 'ok';
  observationCount: number;
  symbols: string[];
  matrix: Array<Array<number | null>>;
};
type NarrowConcentration = {
  status: 'ok';
  positionCount: number;
  weights: PortfolioRiskWeightItem[];
};
type NarrowResponse = {
  asOf: string;
  assumptions: NarrowAssumptions;
  concentration: NarrowConcentration;
  correlation: NarrowCorrelation;
  costMethod: 'fifo';
  currency: string;
  fxStale: boolean;
  portfolioValue: number;
  positionsUsed: number;
  status: 'ok';
  var: NarrowVaR;
};
type _NarrowAssumptionsAssignable = _Assert<NarrowAssumptions extends PortfolioRiskAssumptions ? true : false>;
type _NarrowVaRAssignable = _Assert<NarrowVaR extends PortfolioHistoricalVaRBlock ? true : false>;
type _NarrowCorrelationAssignable = _Assert<NarrowCorrelation extends PortfolioCorrelationBlock ? true : false>;
type _NarrowConcentrationAssignable = _Assert<
  NarrowConcentration extends PortfolioConcentrationBlock ? true : false
>;
type _NarrowResponseAssignable = _Assert<NarrowResponse extends PortfolioRiskMetricsResponse ? true : false>;
type PendingResponse = Omit<NarrowResponse, 'status'> & { status: 'pending' };
type _PendingResponseRejected = _Assert<PendingResponse extends PortfolioRiskMetricsResponse ? false : true>;
type StringCostMethod = Omit<NarrowResponse, 'costMethod'> & { costMethod: string };
type _StringCostMethodRejected = _Assert<
  StringCostMethod extends PortfolioRiskMetricsResponse ? false : true
>;

type SnakeResponse = {
  as_of: string;
  assumptions: OpenApiAssumptions;
  concentration: OpenApiConcentration;
  correlation: OpenApiCorrelation;
  cost_method: string;
  currency: string;
  fx_stale: boolean;
  portfolio_value: number;
  positions_used: number;
  status: string;
  var: OpenApiVaR;
};
type _SnakeMatchesGenerated = _Assert<SnakeResponse extends OpenApiRiskMetrics ? true : false>;
type _SnakeDoesNotMatchUi = _Assert<SnakeResponse extends PortfolioRiskMetricsResponse ? false : true>;

type _CompileTimePins = [
  _SevenComponents,
  _Get200IsComponent,
  _ComponentIsGet200,
  _GetOpIsPath,
  _PathIsGetOp,
  _GetOpHasNeverRequestBody,
  _PathPostNever,
  _PathPutNever,
  _PathDeleteNever,
  _PathPatchNever,
  _UiHasCostMethod,
  _UiHasPortfolioValue,
  _UiHasAccountId,
  _UiHasAsOf,
  _UiHasVarMethod,
  _UiHasHorizonDays,
  _UiHasLookbackTradingDays,
  _UiHasPriceSeriesSymbols,
  _UiQueryHasAccountId,
  _UiQueryHasAsOf,
  _UiQueryHasCostMethod,
  _UiQueryHasHorizonDays,
  _UiQueryHasLookbackTradingDays,
  _UiLacksCostMethodSnake,
  _UiLacksPortfolioValueSnake,
  _UiLacksAccountIdSnake,
  _UiLacksAsOfSnake,
  _UiLacksVarMethodSnake,
  _UiLacksHorizonDaysSnake,
  _UiLacksLookbackSnake,
  _UiLacksPriceSeriesSnake,
  _UiQueryLacksAccountIdSnake,
  _UiQueryLacksAsOfSnake,
  _UiQueryLacksCostMethodSnake,
  _UiQueryLacksHorizonDaysSnake,
  _UiQueryLacksLookbackSnake,
  _GeneratedHasCostMethodSnake,
  _GeneratedHasPortfolioValueSnake,
  _GeneratedHasAccountIdSnake,
  _GeneratedHasAsOfSnake,
  _GeneratedHasVarMethodSnake,
  _GeneratedHasHorizonDaysSnake,
  _GeneratedHasLookbackSnake,
  _GeneratedHasPriceSeriesSnake,
  _GeneratedQueryHasAccountIdSnake,
  _GeneratedQueryHasAsOfSnake,
  _GeneratedQueryHasCostMethodSnake,
  _GeneratedQueryHasHorizonDaysSnake,
  _GeneratedQueryHasLookbackSnake,
  _GeneratedLacksCostMethodCamel,
  _GeneratedLacksPortfolioValueCamel,
  _UiCostMethodClosed,
  _GeneratedCostMethodIsString,
  _UiQueryCostMethodClosed,
  _GeneratedQueryCostMethodIsString,
  _UiStatusClosed,
  _PendingRejected,
  _StringStatusRejected,
  _GeneratedStatusIsString,
  _GeneratedVaRStatusIsString,
  _GeneratedCorrelationStatusIsString,
  _GeneratedConcentrationStatusIsString,
  _HistoryOptional,
  _HistoryNullable,
  _OmitHistoryAssignable,
  _UiHistorySymbolsRequired,
  _GeneratedHistorySymbolsOptional,
  _MatrixCell,
  _GeneratedMatrixCell,
  _WeightsItem,
  _UiWeightHasWeightPct,
  _UiWeightLacksSnake,
  _GeneratedWeightHasSnake,
  _UiQueryAccountNotNull,
  _GeneratedQueryAccountNull,
  _UiQueryAsOfNotNull,
  _GeneratedQueryAsOfNull,
  _QueryKeySetsDiffer,
  _NarrowAssumptionsAssignable,
  _NarrowVaRAssignable,
  _NarrowCorrelationAssignable,
  _NarrowConcentrationAssignable,
  _NarrowResponseAssignable,
  _PendingResponseRejected,
  _StringCostMethodRejected,
  _SnakeMatchesGenerated,
  _SnakeDoesNotMatchUi,
];

const NARROW_ASSUMPTIONS: NarrowAssumptions = {
  varMethod: 'historical',
  confidence: 0.95,
  horizonDays: 1,
  lookbackTradingDays: 60,
  minReturnObservations: 20,
  minCorrelationObservations: 20,
  returnDefinition: 'log',
  portfolioAggregation: 'value_weighted',
  cashExcluded: true,
  weightBasis: 'market_value',
  fxPolicy: 'convert_to_base',
  horizonScaling: 'sqrt_time',
  distributionAssumption: 'empirical',
  correlationMethod: 'pearson',
  concentrationMetrics: 'hhi',
  dataSource: 'stored_closes',
  providerCallsOnHotPath: false,
};

describe('portfolioRiskMetrics OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    // ESM namespace objects carry Symbol.toStringTag='Module'; enumerable exports must stay empty.
    expect({ ...PortfolioRiskMetrics }).toEqual({});
    expect(Object.keys(PortfolioRiskMetrics)).toEqual([]);
    expect(Object.getOwnPropertyNames(PortfolioRiskMetrics)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates GET 200 JSON to PortfolioRiskMetricsResponse and GET op to the path', () => {
    expectTypeOf<OpenApiGet200>().toEqualTypeOf<OpenApiRiskMetrics>();
    expectTypeOf<OpenApiGetOp>().toEqualTypeOf<OpenApiPathGet>();
    type HasNeverBody = OpenApiGetOp extends { requestBody?: never } ? true : false;
    expectTypeOf<HasNeverBody>().toEqualTypeOf<true>();
  });

  it('keeps GET requestBody never and non-GET risk-metrics methods never', () => {
    type PostNever = paths['/api/v1/portfolio/risk-metrics']['post'] extends never | undefined ? true : false;
    type PutNever = paths['/api/v1/portfolio/risk-metrics']['put'] extends never | undefined ? true : false;
    type DeleteNever = paths['/api/v1/portfolio/risk-metrics']['delete'] extends never | undefined
      ? true
      : false;
    type PatchNever = paths['/api/v1/portfolio/risk-metrics']['patch'] extends never | undefined ? true : false;
    expectTypeOf<PostNever>().toEqualTypeOf<true>();
    expectTypeOf<PutNever>().toEqualTypeOf<true>();
    expectTypeOf<DeleteNever>().toEqualTypeOf<true>();
    expectTypeOf<PatchNever>().toEqualTypeOf<true>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof PortfolioRiskMetricsResponse>().not.toMatchTypeOf<
      'cost_method' | 'portfolio_value' | 'account_id' | 'as_of'
    >();
    expectTypeOf<keyof PortfolioRiskAssumptions>().not.toMatchTypeOf<
      'var_method' | 'horizon_days' | 'lookback_trading_days'
    >();
    expectTypeOf<keyof PortfolioRiskHistoryMeta>().not.toMatchTypeOf<'price_series_symbols'>();
    expectTypeOf<keyof PortfolioRiskMetricsQuery>().not.toMatchTypeOf<
      'account_id' | 'as_of' | 'cost_method' | 'horizon_days' | 'lookback_trading_days'
    >();
    expectTypeOf<keyof OpenApiRiskMetrics>().not.toMatchTypeOf<'costMethod' | 'portfolioValue'>();

    type UiHasCostMethod = 'costMethod' extends keyof PortfolioRiskMetricsResponse ? true : false;
    type UiHasCostMethodSnake = 'cost_method' extends keyof PortfolioRiskMetricsResponse ? true : false;
    type GeneratedHasCostMethodSnake = 'cost_method' extends keyof OpenApiRiskMetrics ? true : false;
    type UiHasPortfolioValue = 'portfolioValue' extends keyof PortfolioRiskMetricsResponse ? true : false;
    type UiHasPortfolioValueSnake = 'portfolio_value' extends keyof PortfolioRiskMetricsResponse ? true : false;
    type GeneratedHasPortfolioValueSnake = 'portfolio_value' extends keyof OpenApiRiskMetrics ? true : false;
    type UiHasVarMethod = 'varMethod' extends keyof PortfolioRiskAssumptions ? true : false;
    type UiHasVarMethodSnake = 'var_method' extends keyof PortfolioRiskAssumptions ? true : false;
    type GeneratedHasVarMethodSnake = 'var_method' extends keyof OpenApiAssumptions ? true : false;
    type UiHasPriceSeries = 'priceSeriesSymbols' extends keyof PortfolioRiskHistoryMeta ? true : false;
    type UiHasPriceSeriesSnake = 'price_series_symbols' extends keyof PortfolioRiskHistoryMeta ? true : false;
    type GeneratedHasPriceSeriesSnake = 'price_series_symbols' extends keyof OpenApiHistory ? true : false;
    type UiQueryHasAccountId = 'accountId' extends keyof PortfolioRiskMetricsQuery ? true : false;
    type UiQueryHasAccountIdSnake = 'account_id' extends keyof PortfolioRiskMetricsQuery ? true : false;
    type GeneratedQueryHasAccountIdSnake = 'account_id' extends keyof OpenApiGetQuery ? true : false;

    expectTypeOf<UiHasCostMethod>().toEqualTypeOf<true>();
    expectTypeOf<UiHasCostMethodSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasCostMethodSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasPortfolioValue>().toEqualTypeOf<true>();
    expectTypeOf<UiHasPortfolioValueSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasPortfolioValueSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasVarMethod>().toEqualTypeOf<true>();
    expectTypeOf<UiHasVarMethodSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasVarMethodSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasPriceSeries>().toEqualTypeOf<true>();
    expectTypeOf<UiHasPriceSeriesSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasPriceSeriesSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiQueryHasAccountId>().toEqualTypeOf<true>();
    expectTypeOf<UiQueryHasAccountIdSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedQueryHasAccountIdSnake>().toEqualTypeOf<true>();
  });

  it('does not re-export generated snake_case as the UI response type', () => {
    expectTypeOf<PortfolioRiskMetricsResponse>().not.toEqualTypeOf<
      components['schemas']['PortfolioRiskMetricsResponse']
    >();
    const snake: SnakeResponse = {
      as_of: '2026-09-04',
      assumptions: {
        cash_excluded: true,
        concentration_metrics: 'hhi',
        confidence: 0.95,
        correlation_method: 'pearson',
        data_source: 'stored_closes',
        distribution_assumption: 'empirical',
        fx_policy: 'convert_to_base',
        horizon_days: 1,
        horizon_scaling: 'sqrt_time',
        lookback_trading_days: 60,
        min_correlation_observations: 20,
        min_return_observations: 20,
        portfolio_aggregation: 'value_weighted',
        provider_calls_on_hot_path: false,
        return_definition: 'log',
        var_method: 'historical',
        weight_basis: 'market_value',
      },
      concentration: { position_count: 0, status: 'empty_portfolio' },
      correlation: { observation_count: 0, status: 'unavailable' },
      cost_method: 'fifo',
      currency: 'USD',
      fx_stale: false,
      portfolio_value: 0,
      positions_used: 0,
      status: 'empty_portfolio',
      var: { observation_count: 0, status: 'unavailable' },
    };
    expectTypeOf(snake).toMatchTypeOf<OpenApiRiskMetrics>();
    expectTypeOf(snake).not.toMatchTypeOf<PortfolioRiskMetricsResponse>();
  });

  it('keeps handwritten status unions closed and generated status as string', () => {
    expectTypeOf<PortfolioRiskMetricsResponse['status']>().toEqualTypeOf<PortfolioRiskMetricsStatus>();
    expectTypeOf<PortfolioRiskMetricsStatus>().toEqualTypeOf<
      'ok' | 'empty_portfolio' | 'insufficient_history' | 'partial'
    >();
    expectTypeOf<'pending'>().not.toMatchTypeOf<PortfolioRiskMetricsStatus>();
    expectTypeOf<string>().not.toMatchTypeOf<PortfolioRiskMetricsStatus>();
    expectTypeOf<OpenApiRiskMetrics['status']>().toEqualTypeOf<string>();
    expectTypeOf<OpenApiVaR['status']>().toEqualTypeOf<string>();
    expectTypeOf<OpenApiCorrelation['status']>().toEqualTypeOf<string>();
    expectTypeOf<OpenApiConcentration['status']>().toEqualTypeOf<string>();
  });

  it('keeps UI costMethod as PortfolioCostMethod, not generated string', () => {
    expectTypeOf<PortfolioRiskMetricsResponse['costMethod']>().toEqualTypeOf<'fifo' | 'avg'>();
    expectTypeOf<PortfolioRiskMetricsResponse['costMethod']>().not.toEqualTypeOf<string>();
    expectTypeOf<OpenApiRiskMetrics['cost_method']>().toEqualTypeOf<string>();
    expectTypeOf<NonNullable<PortfolioRiskMetricsQuery['costMethod']>>().toEqualTypeOf<'fifo' | 'avg'>();
    expectTypeOf<NonNullable<OpenApiGetQuery['cost_method']>>().toEqualTypeOf<string>();
  });

  it('accepts number | null correlation cells and PortfolioRiskWeightItem concentration weights', () => {
    expectTypeOf<PortfolioCorrelationBlock['matrix'][number][number]>().toEqualTypeOf<number | null>();
    expectTypeOf<PortfolioConcentrationBlock['weights'][number]>().toEqualTypeOf<PortfolioRiskWeightItem>();
    const matrix: PortfolioCorrelationBlock['matrix'] = [[1, null], [null, 1]];
    const weights: PortfolioConcentrationBlock['weights'] = [{ symbol: 'AAPL', weightPct: 40 }];
    expectTypeOf(matrix).toMatchTypeOf<PortfolioCorrelationBlock['matrix']>();
    expectTypeOf(weights).toMatchTypeOf<PortfolioConcentrationBlock['weights']>();
    expectTypeOf(weights[0]).toMatchTypeOf<PortfolioRiskWeightItem>();
    expectTypeOf<{ symbol: string; weight_pct: number }>().not.toMatchTypeOf<PortfolioRiskWeightItem>();
  });

  it('still accepts a narrow response that omits history', () => {
    const response: NarrowResponse = {
      asOf: '2026-09-04',
      assumptions: NARROW_ASSUMPTIONS,
      concentration: { status: 'ok', positionCount: 1, weights: [{ symbol: 'AAPL', weightPct: 100 }] },
      correlation: { status: 'ok', observationCount: 40, symbols: ['AAPL'], matrix: [[1]] },
      costMethod: 'fifo',
      currency: 'USD',
      fxStale: false,
      portfolioValue: 1000,
      positionsUsed: 1,
      status: 'ok',
      var: { status: 'ok', observationCount: 40 },
    };
    expectTypeOf(response).toMatchTypeOf<PortfolioRiskMetricsResponse>();
    expectTypeOf<Omit<PortfolioRiskMetricsResponse, 'history'>>().toMatchTypeOf<
      PortfolioRiskMetricsResponse
    >();
  });
});
