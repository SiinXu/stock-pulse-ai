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

type OpenApiMoneyFlowViewResponse = components['schemas']['MoneyFlowViewResponse'];
type OpenApiMoneyFlowSnapshotResponse = components['schemas']['MoneyFlowSnapshotResponse'];
type OpenApiMoneyFlowSourceAttempt = components['schemas']['MoneyFlowSourceAttempt'];
type OpenApiGet200 =
  operations['getStockMoneyFlow']['responses']['200']['content']['application/json'];
type OpenApiGetOp = operations['getStockMoneyFlow'];
type OpenApiPathGet = paths['/api/v1/stocks/{stock_code}/money-flow']['get'];
type OpenApiGetQuery = NonNullable<OpenApiGetOp['parameters']['query']>;

type _Assert<T extends true> = T;
type _Get200IsComponent = _Assert<OpenApiGet200 extends OpenApiMoneyFlowViewResponse ? true : false>;
type _ComponentIsGet200 = _Assert<OpenApiMoneyFlowViewResponse extends OpenApiGet200 ? true : false>;
type _GetOpIsPath = _Assert<OpenApiGetOp extends OpenApiPathGet ? true : false>;
type _PathIsGetOp = _Assert<OpenApiPathGet extends OpenApiGetOp ? true : false>;
type _GetOpHasNeverRequestBody = _Assert<OpenApiGetOp extends { requestBody?: never } ? true : false>;
type _PathPostNever = _Assert<
  paths['/api/v1/stocks/{stock_code}/money-flow']['post'] extends never | undefined ? true : false
>;
type _PathPutNever = _Assert<
  paths['/api/v1/stocks/{stock_code}/money-flow']['put'] extends never | undefined ? true : false
>;
type _PathDeleteNever = _Assert<
  paths['/api/v1/stocks/{stock_code}/money-flow']['delete'] extends never | undefined ? true : false
>;
type _GetQueryHasDays = _Assert<'days' extends keyof OpenApiGetQuery ? true : false>;
type _GetQueryDaysIsNumber = _Assert<number extends NonNullable<OpenApiGetQuery['days']> ? true : false>;
type _GetQueryDaysNotNull = _Assert<null extends OpenApiGetQuery['days'] ? false : true>;
type _GetQueryLacksStockCode = _Assert<'stock_code' extends keyof OpenApiGetQuery ? false : true>;

type _OpenApiAnchors = [
  _Get200IsComponent,
  _ComponentIsGet200,
  _GetOpIsPath,
  _PathIsGetOp,
  _GetOpHasNeverRequestBody,
  _PathPostNever,
  _PathPutNever,
  _PathDeleteNever,
  _GetQueryHasDays,
  _GetQueryDaysIsNumber,
  _GetQueryDaysNotNull,
  _GetQueryLacksStockCode,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type MoneyFlowSourceAttempt = CamelizeKeys<OpenApiMoneyFlowSourceAttempt>;

export type MoneyFlowSnapshot = CamelizeKeys<OpenApiMoneyFlowSnapshotResponse>;

export type MoneyFlowView = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiMoneyFlowViewResponse>, {
  snapshot?: MoneyFlowSnapshot | null;
  sourceChain?: MoneyFlowSourceAttempt[];
}>>;

export type MoneyFlowViewParams = {
  stockCode: string;
  days?: number;
};
