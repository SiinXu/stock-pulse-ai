// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as MoneyFlow from '../moneyFlow';
import type {
  MoneyFlowSnapshot,
  MoneyFlowSourceAttempt,
  MoneyFlowView,
  MoneyFlowViewParams,
} from '../moneyFlow';

type OpenApiView = components['schemas']['MoneyFlowViewResponse'];
type OpenApiSnapshot = components['schemas']['MoneyFlowSnapshotResponse'];
type OpenApiGetOp = operations['getStockMoneyFlow'];
type OpenApiGet200 = OpenApiGetOp['responses']['200']['content']['application/json'];
type OpenApiPathGet = paths['/api/v1/stocks/{stock_code}/money-flow']['get'];
type OpenApiGetQuery = NonNullable<OpenApiGetOp['parameters']['query']>;

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

type _ThreeComponents = _Assert<
  ('MoneyFlowViewResponse' | 'MoneyFlowSnapshotResponse' | 'MoneyFlowSourceAttempt') extends keyof components['schemas'] ? true : false
>;
type _Get200IsComponent = _Assert<OpenApiGet200 extends OpenApiView ? true : false>;
type _ComponentIsGet200 = _Assert<OpenApiView extends OpenApiGet200 ? true : false>;
type _GetOpIsPath = _Assert<OpenApiGetOp extends OpenApiPathGet ? true : false>;
type _PathIsGetOp = _Assert<OpenApiPathGet extends OpenApiGetOp ? true : false>;
type _GetOpHasNeverRequestBody = _Assert<OpenApiGetOp extends { requestBody?: never } ? true : false>;
type _PathPostNever = _Assert<
  paths['/api/v1/stocks/{stock_code}/money-flow']['post'] extends never | undefined ? true : false
>;

type _UiHasStockCode = _Assert<'stockCode' extends keyof MoneyFlowView ? true : false>;
type _UiHasSchemaVersion = _Assert<'schemaVersion' extends keyof MoneyFlowView ? true : false>;
type _UiHasAmountScale = _Assert<'amountScale' extends keyof MoneyFlowSnapshot ? true : false>;
type _UiHasLatencyMs = _Assert<'latencyMs' extends keyof MoneyFlowSourceAttempt ? true : false>;
type _UiHasMainNetInflow5d = _Assert<'mainNetInflow5d' extends keyof MoneyFlowSnapshot ? true : false>;
type _UiLacksStockCodeSnake = _Assert<'stock_code' extends keyof MoneyFlowView ? false : true>;
type _UiLacksSchemaVersionSnake = _Assert<'schema_version' extends keyof MoneyFlowView ? false : true>;
type _UiLacksAmountScaleSnake = _Assert<'amount_scale' extends keyof MoneyFlowSnapshot ? false : true>;
type _UiLacksMainNetInflow5dSnake = _Assert<'main_net_inflow_5d' extends keyof MoneyFlowSnapshot ? false : true>;
type _GeneratedHasStockCodeSnake = _Assert<'stock_code' extends keyof OpenApiView ? true : false>;
type _GeneratedHasAmountScaleSnake = _Assert<'amount_scale' extends keyof OpenApiSnapshot ? true : false>;
type _GeneratedLacksStockCodeCamel = _Assert<'stockCode' extends keyof OpenApiView ? false : true>;

type _UiSnapshotOptional = _Assert<IsOptional<MoneyFlowView, 'snapshot'>>;
type _UiSnapshotNullable = _Assert<null extends MoneyFlowView['snapshot'] ? true : false>;
type _GeneratedSnapshotOptional = _Assert<IsOptional<OpenApiView, 'snapshot'>>;
type _GeneratedSnapshotNullable = _Assert<null extends OpenApiView['snapshot'] ? true : false>;
type _NaiveCamelSnapshotOptional = _Assert<IsOptional<CamelizeKeys<OpenApiView>, 'snapshot'>>;
type _UiSourceChainOptional = _Assert<IsOptional<MoneyFlowView, 'sourceChain'>>;
type _UiWarningsOptional = _Assert<IsOptional<MoneyFlowView, 'warnings'>>;
type _GeneratedSourceChainOptional = _Assert<IsOptional<OpenApiView, 'source_chain'>>;
type _GeneratedWarningsOptional = _Assert<IsOptional<OpenApiView, 'warnings'>>;
type _OmitUiDisclaimer = _Assert<Omit<MoneyFlowView, 'disclaimer'> extends MoneyFlowView ? false : true>;
type _OmitGeneratedDisclaimer = _Assert<Omit<OpenApiView, 'disclaimer'> extends OpenApiView ? false : true>;
type _OmitUiSnapshot = _Assert<Omit<MoneyFlowView, 'snapshot'> extends MoneyFlowView ? true : false>;

type _UiUnitIsString = _Assert<string extends MoneyFlowSnapshot['unit'] ? true : false>;
type _GeneratedUnitIsString = _Assert<string extends OpenApiSnapshot['unit'] ? true : false>;
type _NaiveCamelUnitIsString = _Assert<string extends CamelizeKeys<OpenApiSnapshot>['unit'] ? true : false>;
type _UiSchemaVersionClosed = _Assert<MoneyFlowView['schemaVersion'] extends 'money_flow_view/1.0' ? true : false>;
type _StringSchemaRejected = _Assert<string extends MoneyFlowView['schemaVersion'] ? false : true>;
type _GeneratedSchemaVersionClosed = _Assert<
  OpenApiView['schema_version'] extends 'money_flow_view/1.0' ? true : false
>;
type _StatusClosed = _Assert<MoneyFlowView['status'] extends
  'disabled' | 'available' | 'partial' | 'not_supported' | 'fetch_failed' | 'empty' | 'stale' | 'fallback'
  ? true : false>;
type _StringStatusRejected = _Assert<string extends MoneyFlowView['status'] ? false : true>;
type _PassedStatusRejected = _Assert<'passed' extends MoneyFlowView['status'] ? false : true>;
type _AmountScaleClosed = _Assert<MoneyFlowSnapshot['amountScale'] extends
  'unknown' | 'yuan' | 'thousand_yuan' | 'ten_thousand_yuan' | 'million_yuan' ? true : false>;
type _NestedSnapshotNamed = _Assert<
  NonNullable<MoneyFlowView['snapshot']> extends MoneyFlowSnapshot ? true : false
>;
type _NestedAttemptNamed = _Assert<
  NonNullable<MoneyFlowView['sourceChain']>[number] extends MoneyFlowSourceAttempt ? true : false
>;

type _QueryDaysIsNumber = _Assert<number extends NonNullable<OpenApiGetQuery['days']> ? true : false>;
type _QueryDaysNotNull = _Assert<null extends OpenApiGetQuery['days'] ? false : true>;
type _ParamsHasStockCode = _Assert<'stockCode' extends keyof MoneyFlowViewParams ? true : false>;
type _ParamsDaysOptional = _Assert<IsOptional<MoneyFlowViewParams, 'days'>>;
type _ParamsDaysIsNumber = _Assert<number extends NonNullable<MoneyFlowViewParams['days']> ? true : false>;
type _ParamsNotQuery = _Assert<'stockCode' extends keyof OpenApiGetQuery ? false : true>;

type ConsumerFixture = {
  schemaVersion: 'money_flow_view/1.0';
  stockCode: string;
  enabled: true;
  status: 'partial';
  requestedDays: number;
  disclaimer: string;
  snapshot: {
    code: string; date: string; source: string; market: 'cn';
    unit: string; amountScale: 'unknown'; bucketDefinition: string; asOf: string;
    requestedDays: number; observedDays: number; completeness: 'complete';
    attitude: 'inflow'; calibrationNote: string;
  };
};
type _ConsumerAssignable = _Assert<ConsumerFixture extends MoneyFlowView ? true : false>;
type MissingDisclaimer = Omit<ConsumerFixture, 'disclaimer'>;
type _MissingDisclaimerRejected = _Assert<MissingDisclaimer extends MoneyFlowView ? false : true>;
type OpenStatus = Omit<ConsumerFixture, 'status'> & { status: 'passed' };
type _OpenStatusRejected = _Assert<OpenStatus extends MoneyFlowView ? false : true>;
type WidenedSchema = Omit<ConsumerFixture, 'schemaVersion'> & { schemaVersion: string };
type _WidenedSchemaRejected = _Assert<WidenedSchema extends MoneyFlowView ? false : true>;

type SnakeView = {
  schema_version: 'money_flow_view/1.0'; stock_code: string; enabled: boolean;
  status: 'partial'; requested_days: number; disclaimer: string;
};
type _SnakeMatchesGenerated = _Assert<SnakeView extends OpenApiView ? true : false>;
type _SnakeDoesNotMatchUi = _Assert<SnakeView extends MoneyFlowView ? false : true>;

type _CompileTimePins = [
  _ThreeComponents, _Get200IsComponent, _ComponentIsGet200, _GetOpIsPath, _PathIsGetOp,
  _GetOpHasNeverRequestBody, _PathPostNever, _UiHasStockCode, _UiHasSchemaVersion,
  _UiHasAmountScale, _UiHasLatencyMs, _UiHasMainNetInflow5d, _UiLacksStockCodeSnake,
  _UiLacksSchemaVersionSnake, _UiLacksAmountScaleSnake, _UiLacksMainNetInflow5dSnake,
  _GeneratedHasStockCodeSnake, _GeneratedHasAmountScaleSnake, _GeneratedLacksStockCodeCamel,
  _UiSnapshotOptional, _UiSnapshotNullable, _GeneratedSnapshotOptional, _GeneratedSnapshotNullable,
  _NaiveCamelSnapshotOptional, _UiSourceChainOptional, _UiWarningsOptional,
  _GeneratedSourceChainOptional, _GeneratedWarningsOptional, _OmitUiDisclaimer,
  _OmitGeneratedDisclaimer, _OmitUiSnapshot, _UiUnitIsString, _GeneratedUnitIsString,
  _NaiveCamelUnitIsString, _UiSchemaVersionClosed, _StringSchemaRejected,
  _GeneratedSchemaVersionClosed, _StatusClosed, _StringStatusRejected, _PassedStatusRejected,
  _AmountScaleClosed, _NestedSnapshotNamed, _NestedAttemptNamed, _QueryDaysIsNumber,
  _QueryDaysNotNull, _ParamsHasStockCode, _ParamsDaysOptional, _ParamsDaysIsNumber,
  _ParamsNotQuery, _ConsumerAssignable, _MissingDisclaimerRejected, _OpenStatusRejected,
  _WidenedSchemaRejected, _SnakeMatchesGenerated, _SnakeDoesNotMatchUi,
];

describe('moneyFlow OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    expect({ ...MoneyFlow }).toEqual({});
    expect(Object.keys(MoneyFlow)).toEqual([]);
    expect(Object.getOwnPropertyNames(MoneyFlow)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates GET 200 JSON to the generated view component', () => {
    expectTypeOf<OpenApiGet200>().toEqualTypeOf<OpenApiView>();
    expectTypeOf<OpenApiGetOp>().toEqualTypeOf<OpenApiPathGet>();
    type HasNeverBody = OpenApiGetOp extends { requestBody?: never } ? true : false;
    expectTypeOf<HasNeverBody>().toEqualTypeOf<true>();
  });

  it('keeps generated unit as string and schemaVersion plus enums closed', () => {
    expectTypeOf<MoneyFlowSnapshot['unit']>().toEqualTypeOf<string>();
    expectTypeOf<OpenApiSnapshot['unit']>().toEqualTypeOf<string>();
    expectTypeOf<MoneyFlowView['schemaVersion']>().toEqualTypeOf<'money_flow_view/1.0'>();
    expectTypeOf<string>().not.toMatchTypeOf<MoneyFlowView['schemaVersion']>();
    expectTypeOf<MoneyFlowView['status']>().toEqualTypeOf<
      'disabled' | 'available' | 'partial' | 'not_supported' | 'fetch_failed' | 'empty' | 'stale' | 'fallback'
    >();
    expectTypeOf<string>().not.toMatchTypeOf<MoneyFlowView['status']>();
    expectTypeOf<'passed'>().not.toMatchTypeOf<MoneyFlowView['status']>();
    expectTypeOf<MoneyFlowSnapshot['amountScale']>().toEqualTypeOf<
      'unknown' | 'yuan' | 'thousand_yuan' | 'ten_thousand_yuan' | 'million_yuan'
    >();
  });

  it('keeps snapshot optional nullable and sourceChain/warnings optional', () => {
    expectTypeOf<Omit<MoneyFlowView, 'snapshot'>>().toMatchTypeOf<MoneyFlowView>();
    expectTypeOf<null>().toMatchTypeOf<MoneyFlowView['snapshot']>();
    expectTypeOf<Omit<MoneyFlowView, 'sourceChain' | 'warnings'>>().toMatchTypeOf<MoneyFlowView>();
    expectTypeOf<Omit<MoneyFlowView, 'disclaimer'>>().not.toMatchTypeOf<MoneyFlowView>();
    expectTypeOf<NonNullable<MoneyFlowView['snapshot']>>().toEqualTypeOf<MoneyFlowSnapshot>();
    expectTypeOf<NonNullable<MoneyFlowView['sourceChain']>[number]>().toEqualTypeOf<MoneyFlowSourceAttempt>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof MoneyFlowView>().not.toMatchTypeOf<'stock_code' | 'schema_version' | 'source_chain'>();
    expectTypeOf<keyof MoneyFlowSnapshot>().not.toMatchTypeOf<'amount_scale' | 'main_net_inflow_5d'>();
    expectTypeOf<keyof OpenApiView>().not.toMatchTypeOf<'stockCode' | 'schemaVersion'>();
    const snake = {
      schema_version: 'money_flow_view/1.0' as const,
      stock_code: '600519', enabled: true, status: 'partial' as const,
      requested_days: 5, disclaimer: 'Research evidence only.',
    };
    expectTypeOf(snake).toMatchTypeOf<OpenApiView>();
    expectTypeOf(snake).not.toMatchTypeOf<MoneyFlowView>();
  });

  it('keeps handwritten view params distinct from the generated days query', () => {
    expectTypeOf<NonNullable<OpenApiGetQuery['days']>>().toEqualTypeOf<number>();
    expectTypeOf<MoneyFlowViewParams>().toEqualTypeOf<{ stockCode: string; days?: number }>();
    expectTypeOf<{ days: number }>().not.toMatchTypeOf<MoneyFlowViewParams>();
  });

  it('accepts one consumer-shaped fixture and rejects missing disclaimer or open status', () => {
    const fixture: MoneyFlowView = {
      schemaVersion: 'money_flow_view/1.0',
      stockCode: '600519',
      enabled: true,
      status: 'partial',
      requestedDays: 5,
      disclaimer: 'Research evidence only.',
      snapshot: {
        code: '600519', date: '2026-08-08', source: 'akshare:test', market: 'cn',
        unit: 'unknown', amountScale: 'unknown',
        bucketDefinition: 'eastmoney_em_order_size_buckets_v1',
        asOf: '2026-08-08T08:00:00+00:00', requestedDays: 5, observedDays: 5,
        completeness: 'complete', attitude: 'inflow', calibrationNote: 'Ratios only.',
      },
    };
    expectTypeOf(fixture).toMatchTypeOf<MoneyFlowView>();
    expectTypeOf(fixture.snapshot).toMatchTypeOf<MoneyFlowSnapshot | null | undefined>();
  });
});
