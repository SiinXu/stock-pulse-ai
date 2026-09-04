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

type OpenApiCompoundGrowthRequest = components['schemas']['CompoundGrowthRequest'];
type OpenApiTargetContributionRequest = components['schemas']['TargetContributionRequest'];
type OpenApiTargetDurationRequest = components['schemas']['TargetDurationRequest'];
type OpenApiCompoundGrowthResponse = components['schemas']['CompoundGrowthResponse'];
type OpenApiBalancePoint = components['schemas']['BalancePoint'];
type OpenApiTargetContributionOk = components['schemas']['TargetContributionOkResponse'];
type OpenApiTargetContributionAlreadyMet = components['schemas']['TargetContributionAlreadyMetResponse'];
type OpenApiTargetContributionUnreachable = components['schemas']['TargetContributionUnreachableResponse'];
type OpenApiTargetDurationOk = components['schemas']['TargetDurationOkResponse'];
type OpenApiTargetDurationAlreadyMet = components['schemas']['TargetDurationAlreadyMetResponse'];
type OpenApiTargetDurationUnreachable = components['schemas']['TargetDurationUnreachableResponse'];

type OpenApiPostCompoundGrowth = operations['postCompoundGrowth'];
type OpenApiPostTargetContribution = operations['postTargetContribution'];
type OpenApiPostTargetDuration = operations['postTargetDuration'];
type OpenApiPathCompoundGrowthPost = paths['/api/v1/calculators/compound-growth']['post'];
type OpenApiPathTargetContributionPost = paths['/api/v1/calculators/target-contribution']['post'];
type OpenApiPathTargetDurationPost = paths['/api/v1/calculators/target-duration']['post'];
type OpenApiPostCompoundGrowth200 =
  OpenApiPostCompoundGrowth['responses']['200']['content']['application/json'];
type OpenApiPostCompoundGrowthBody =
  OpenApiPostCompoundGrowth['requestBody']['content']['application/json'];
type OpenApiPostTargetContributionBody =
  OpenApiPostTargetContribution['requestBody']['content']['application/json'];
type OpenApiPostTargetDurationBody =
  OpenApiPostTargetDuration['requestBody']['content']['application/json'];

type _Assert<T extends true> = T;
type _PostCompoundGrowth200IsComponent = _Assert<
  OpenApiPostCompoundGrowth200 extends OpenApiCompoundGrowthResponse ? true : false
>;
type _ComponentIsPostCompoundGrowth200 = _Assert<
  OpenApiCompoundGrowthResponse extends OpenApiPostCompoundGrowth200 ? true : false
>;
type _PostCompoundGrowthOpIsPath = _Assert<
  OpenApiPostCompoundGrowth extends OpenApiPathCompoundGrowthPost ? true : false
>;
type _PathIsPostCompoundGrowthOp = _Assert<
  OpenApiPathCompoundGrowthPost extends OpenApiPostCompoundGrowth ? true : false
>;
type _PostTargetContributionOpIsPath = _Assert<
  OpenApiPostTargetContribution extends OpenApiPathTargetContributionPost ? true : false
>;
type _PathIsPostTargetContributionOp = _Assert<
  OpenApiPathTargetContributionPost extends OpenApiPostTargetContribution ? true : false
>;
type _PostTargetDurationOpIsPath = _Assert<
  OpenApiPostTargetDuration extends OpenApiPathTargetDurationPost ? true : false
>;
type _PathIsPostTargetDurationOp = _Assert<
  OpenApiPathTargetDurationPost extends OpenApiPostTargetDuration ? true : false
>;
type _PostCompoundGrowthBodyIsRequest = _Assert<
  OpenApiPostCompoundGrowthBody extends OpenApiCompoundGrowthRequest ? true : false
>;
type _RequestIsPostCompoundGrowthBody = _Assert<
  OpenApiCompoundGrowthRequest extends OpenApiPostCompoundGrowthBody ? true : false
>;
type _PostTargetContributionBodyIsRequest = _Assert<
  OpenApiPostTargetContributionBody extends OpenApiTargetContributionRequest ? true : false
>;
type _RequestIsPostTargetContributionBody = _Assert<
  OpenApiTargetContributionRequest extends OpenApiPostTargetContributionBody ? true : false
>;
type _PostTargetDurationBodyIsRequest = _Assert<
  OpenApiPostTargetDurationBody extends OpenApiTargetDurationRequest ? true : false
>;
type _RequestIsPostTargetDurationBody = _Assert<
  OpenApiTargetDurationRequest extends OpenApiPostTargetDurationBody ? true : false
>;
type _PathCompoundGrowthGetNever = _Assert<
  paths['/api/v1/calculators/compound-growth']['get'] extends never | undefined ? true : false
>;
type _PathCompoundGrowthPutNever = _Assert<
  paths['/api/v1/calculators/compound-growth']['put'] extends never | undefined ? true : false
>;
type _PathCompoundGrowthDeleteNever = _Assert<
  paths['/api/v1/calculators/compound-growth']['delete'] extends never | undefined ? true : false
>;
type _PathCompoundGrowthPatchNever = _Assert<
  paths['/api/v1/calculators/compound-growth']['patch'] extends never | undefined ? true : false
>;
type _PathTargetContributionGetNever = _Assert<
  paths['/api/v1/calculators/target-contribution']['get'] extends never | undefined ? true : false
>;
type _PathTargetContributionPutNever = _Assert<
  paths['/api/v1/calculators/target-contribution']['put'] extends never | undefined ? true : false
>;
type _PathTargetContributionDeleteNever = _Assert<
  paths['/api/v1/calculators/target-contribution']['delete'] extends never | undefined ? true : false
>;
type _PathTargetContributionPatchNever = _Assert<
  paths['/api/v1/calculators/target-contribution']['patch'] extends never | undefined ? true : false
>;
type _PathTargetDurationGetNever = _Assert<
  paths['/api/v1/calculators/target-duration']['get'] extends never | undefined ? true : false
>;
type _PathTargetDurationPutNever = _Assert<
  paths['/api/v1/calculators/target-duration']['put'] extends never | undefined ? true : false
>;
type _PathTargetDurationDeleteNever = _Assert<
  paths['/api/v1/calculators/target-duration']['delete'] extends never | undefined ? true : false
>;
type _PathTargetDurationPatchNever = _Assert<
  paths['/api/v1/calculators/target-duration']['patch'] extends never | undefined ? true : false
>;
type _PostCompoundGrowthQueryNever = _Assert<
  OpenApiPostCompoundGrowth['parameters']['query'] extends never | undefined ? true : false
>;
type _PostCompoundGrowthHeaderNever = _Assert<
  OpenApiPostCompoundGrowth['parameters']['header'] extends never | undefined ? true : false
>;
type _PostCompoundGrowthPathNever = _Assert<
  OpenApiPostCompoundGrowth['parameters']['path'] extends never | undefined ? true : false
>;
type _PostCompoundGrowthCookieNever = _Assert<
  OpenApiPostCompoundGrowth['parameters']['cookie'] extends never | undefined ? true : false
>;
type _PostTargetContributionQueryNever = _Assert<
  OpenApiPostTargetContribution['parameters']['query'] extends never | undefined ? true : false
>;
type _PostTargetContributionHeaderNever = _Assert<
  OpenApiPostTargetContribution['parameters']['header'] extends never | undefined ? true : false
>;
type _PostTargetContributionPathNever = _Assert<
  OpenApiPostTargetContribution['parameters']['path'] extends never | undefined ? true : false
>;
type _PostTargetContributionCookieNever = _Assert<
  OpenApiPostTargetContribution['parameters']['cookie'] extends never | undefined ? true : false
>;
type _PostTargetDurationQueryNever = _Assert<
  OpenApiPostTargetDuration['parameters']['query'] extends never | undefined ? true : false
>;
type _PostTargetDurationHeaderNever = _Assert<
  OpenApiPostTargetDuration['parameters']['header'] extends never | undefined ? true : false
>;
type _PostTargetDurationPathNever = _Assert<
  OpenApiPostTargetDuration['parameters']['path'] extends never | undefined ? true : false
>;
type _PostTargetDurationCookieNever = _Assert<
  OpenApiPostTargetDuration['parameters']['cookie'] extends never | undefined ? true : false
>;

type _OpenApiAnchors = [
  _PostCompoundGrowth200IsComponent,
  _ComponentIsPostCompoundGrowth200,
  _PostCompoundGrowthOpIsPath,
  _PathIsPostCompoundGrowthOp,
  _PostTargetContributionOpIsPath,
  _PathIsPostTargetContributionOp,
  _PostTargetDurationOpIsPath,
  _PathIsPostTargetDurationOp,
  _PostCompoundGrowthBodyIsRequest,
  _RequestIsPostCompoundGrowthBody,
  _PostTargetContributionBodyIsRequest,
  _RequestIsPostTargetContributionBody,
  _PostTargetDurationBodyIsRequest,
  _RequestIsPostTargetDurationBody,
  _PathCompoundGrowthGetNever,
  _PathCompoundGrowthPutNever,
  _PathCompoundGrowthDeleteNever,
  _PathCompoundGrowthPatchNever,
  _PathTargetContributionGetNever,
  _PathTargetContributionPutNever,
  _PathTargetContributionDeleteNever,
  _PathTargetContributionPatchNever,
  _PathTargetDurationGetNever,
  _PathTargetDurationPutNever,
  _PathTargetDurationDeleteNever,
  _PathTargetDurationPatchNever,
  _PostCompoundGrowthQueryNever,
  _PostCompoundGrowthHeaderNever,
  _PostCompoundGrowthPathNever,
  _PostCompoundGrowthCookieNever,
  _PostTargetContributionQueryNever,
  _PostTargetContributionHeaderNever,
  _PostTargetContributionPathNever,
  _PostTargetContributionCookieNever,
  _PostTargetDurationQueryNever,
  _PostTargetDurationHeaderNever,
  _PostTargetDurationPathNever,
  _PostTargetDurationCookieNever,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type CompoundGrowthRequest = CamelizeKeys<OpenApiCompoundGrowthRequest>;
export type TargetContributionRequest = CamelizeKeys<OpenApiTargetContributionRequest>;
export type TargetDurationRequest = CamelizeKeys<OpenApiTargetDurationRequest>;
export type CompoundGrowthResponse = _BindOpenApiAnchors<CamelizeKeys<OpenApiCompoundGrowthResponse>>;
export type TargetContributionResponse = CamelizeKeys<
  OpenApiTargetContributionOk | OpenApiTargetContributionAlreadyMet | OpenApiTargetContributionUnreachable
>;
export type TargetDurationResponse = CamelizeKeys<
  OpenApiTargetDurationOk | OpenApiTargetDurationAlreadyMet | OpenApiTargetDurationUnreachable
>;
export type CalculatorBalancePoint = CamelizeKeys<OpenApiBalancePoint>;
