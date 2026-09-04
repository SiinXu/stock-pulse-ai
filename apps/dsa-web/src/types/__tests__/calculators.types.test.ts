// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as Calculators from '../calculators';
import type {
  CalculatorBalancePoint,
  CompoundGrowthRequest,
  CompoundGrowthResponse,
  TargetContributionRequest,
  TargetContributionResponse,
  TargetDurationRequest,
  TargetDurationResponse,
} from '../calculators';
import type * as ApiCalculators from '../../api/calculators';
import type { CalculatorBalancePoint as ApiCalculatorBalancePoint } from '../../api/calculators';

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
type OpenApiPostCompoundGrowth200 =
  OpenApiPostCompoundGrowth['responses']['200']['content']['application/json'];
type OpenApiPathCompoundGrowthPost = paths['/api/v1/calculators/compound-growth']['post'];
type OpenApiPathTargetContributionPost = paths['/api/v1/calculators/target-contribution']['post'];
type OpenApiPathTargetDurationPost = paths['/api/v1/calculators/target-duration']['post'];
type OpenApiPostCompoundGrowthBody =
  OpenApiPostCompoundGrowth['requestBody']['content']['application/json'];
type OpenApiPostTargetContributionBody =
  OpenApiPostTargetContribution['requestBody']['content']['application/json'];
type OpenApiPostTargetDurationBody =
  OpenApiPostTargetDuration['requestBody']['content']['application/json'];
type CalculatorsApi = typeof import('../../api/calculators')['calculatorsApi'];

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

type _ElevenComponents = _Assert<
  (
    | 'CompoundGrowthRequest'
    | 'TargetContributionRequest'
    | 'TargetDurationRequest'
    | 'CompoundGrowthResponse'
    | 'BalancePoint'
    | 'TargetContributionOkResponse'
    | 'TargetContributionAlreadyMetResponse'
    | 'TargetContributionUnreachableResponse'
    | 'TargetDurationOkResponse'
    | 'TargetDurationAlreadyMetResponse'
    | 'TargetDurationUnreachableResponse'
  ) extends keyof components['schemas'] ? true : false
>;
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

type _UiHasAnnualRate = _Assert<'annualRate' extends keyof CompoundGrowthRequest ? true : false>;
type _UiHasContributionPerPeriod = _Assert<
  'contributionPerPeriod' extends keyof CompoundGrowthRequest ? true : false
>;
type _UiHasPeriodsPerYear = _Assert<'periodsPerYear' extends keyof CompoundGrowthRequest ? true : false>;
type _UiHasSeriesTotalPoints = _Assert<
  'seriesTotalPoints' extends keyof CompoundGrowthResponse ? true : false
>;
type _UiHasTotalContributed = _Assert<
  'totalContributed' extends keyof CompoundGrowthResponse ? true : false
>;
type _UiHasReasonCode = _Assert<'reasonCode' extends keyof TargetContributionResponse ? true : false>;
type _UiLacksAnnualRateSnake = _Assert<'annual_rate' extends keyof CompoundGrowthRequest ? false : true>;
type _UiLacksContributionSnake = _Assert<
  'contribution_per_period' extends keyof CompoundGrowthRequest ? false : true
>;
type _UiLacksPeriodsSnake = _Assert<'periods_per_year' extends keyof CompoundGrowthRequest ? false : true>;
type _UiLacksSeriesTotalPointsSnake = _Assert<
  'series_total_points' extends keyof CompoundGrowthResponse ? false : true
>;
type _UiLacksTotalContributedSnake = _Assert<
  'total_contributed' extends keyof CompoundGrowthResponse ? false : true
>;
type _UiLacksReasonCodeSnake = _Assert<'reason_code' extends keyof TargetContributionResponse ? false : true>;
type _GeneratedHasAnnualRateSnake = _Assert<
  'annual_rate' extends keyof OpenApiCompoundGrowthRequest ? true : false
>;
type _GeneratedHasContributionSnake = _Assert<
  'contribution_per_period' extends keyof OpenApiCompoundGrowthRequest ? true : false
>;
type _GeneratedHasPeriodsSnake = _Assert<
  'periods_per_year' extends keyof OpenApiCompoundGrowthRequest ? true : false
>;
type _GeneratedHasSeriesTotalPointsSnake = _Assert<
  'series_total_points' extends keyof OpenApiCompoundGrowthResponse ? true : false
>;
type _GeneratedHasTotalContributedSnake = _Assert<
  'total_contributed' extends keyof OpenApiCompoundGrowthResponse ? true : false
>;
type _GeneratedHasReasonCodeSnake = _Assert<
  'reason_code' extends keyof OpenApiTargetContributionOk ? true : false
>;
type _GeneratedLacksAnnualRateCamel = _Assert<
  'annualRate' extends keyof OpenApiCompoundGrowthRequest ? false : true
>;
type _GeneratedLacksContributionCamel = _Assert<
  'contributionPerPeriod' extends keyof OpenApiCompoundGrowthRequest ? false : true
>;

type _StatusIsOk = _Assert<
  CompoundGrowthResponse['status'] extends 'ok'
    ? 'ok' extends CompoundGrowthResponse['status'] ? true : false
    : false
>;
type _StringDoesNotExtendStatus = _Assert<
  string extends CompoundGrowthResponse['status'] ? false : true
>;

type _ContributionUnion = _Assert<
  TargetContributionResponse extends CamelizeKeys<
    OpenApiTargetContributionOk | OpenApiTargetContributionAlreadyMet | OpenApiTargetContributionUnreachable
  >
    ? CamelizeKeys<
      OpenApiTargetContributionOk | OpenApiTargetContributionAlreadyMet | OpenApiTargetContributionUnreachable
    > extends TargetContributionResponse ? true : false
    : false
>;
type _DurationUnion = _Assert<
  TargetDurationResponse extends CamelizeKeys<
    OpenApiTargetDurationOk | OpenApiTargetDurationAlreadyMet | OpenApiTargetDurationUnreachable
  >
    ? CamelizeKeys<
      OpenApiTargetDurationOk | OpenApiTargetDurationAlreadyMet | OpenApiTargetDurationUnreachable
    > extends TargetDurationResponse ? true : false
    : false
>;
type PendingContribution = {
  status: 'pending';
  target: number;
  principal: number;
  annualRate: number;
  years: number;
  periodsPerYear: number;
  periodCount: number;
  periodRate: number;
  currencyPrecisionDigits: 2;
  contributionRounding: 'ceiling';
  reasonCode: 'contribution_required';
  contributionPerPeriod: number;
};
type _PendingRejected = _Assert<PendingContribution extends TargetContributionResponse ? false : true>;

type UnreachableDuration = Extract<TargetDurationResponse, { status: 'unreachable' }>;
type GeneratedUnreachableCodes =
  | 'non_positive_trajectory'
  | 'max_years_exceeded'
  | 'target_unreachable';
type _UnreachableReasonCode = _Assert<
  UnreachableDuration['reasonCode'] extends GeneratedUnreachableCodes
    ? GeneratedUnreachableCodes extends UnreachableDuration['reasonCode'] ? true : false
    : false
>;
type _UnreachableRejectsExtraCode = _Assert<
  'something_else' extends UnreachableDuration['reasonCode'] ? false : true
>;

type _BalancePointNamed = _Assert<
  CalculatorBalancePoint extends CamelizeKeys<OpenApiBalancePoint>
    ? CamelizeKeys<OpenApiBalancePoint> extends CalculatorBalancePoint ? true : false
    : false
>;
type _BalancePointIsSeriesItem = _Assert<
  CalculatorBalancePoint extends CompoundGrowthResponse['series'][number]
    ? CompoundGrowthResponse['series'][number] extends CalculatorBalancePoint ? true : false
    : false
>;

type _NaiveEqualsPublicRequest = _Assert<
  CompoundGrowthRequest extends CamelizeKeys<OpenApiCompoundGrowthRequest>
    ? CamelizeKeys<OpenApiCompoundGrowthRequest> extends CompoundGrowthRequest ? true : false
    : false
>;
type _ContributionRequired = _Assert<
  IsOptional<CompoundGrowthRequest, 'contributionPerPeriod'> extends false ? true : false
>;
type _PeriodsRequired = _Assert<
  IsOptional<CompoundGrowthRequest, 'periodsPerYear'> extends false ? true : false
>;
type MissingContribution = Omit<CompoundGrowthRequest, 'contributionPerPeriod'>;
type _MissingContributionRejected = _Assert<
  MissingContribution extends CompoundGrowthRequest ? false : true
>;
type MissingPeriods = Omit<CompoundGrowthRequest, 'periodsPerYear'>;
type _MissingPeriodsRejected = _Assert<MissingPeriods extends CompoundGrowthRequest ? false : true>;

type ConsumerFixture = {
  principal: number;
  annualRate: number;
  years: number;
  contributionPerPeriod: number;
  periodsPerYear: number;
};
type _ConsumerAssignable = _Assert<ConsumerFixture extends CompoundGrowthRequest ? true : false>;

type SnakeRequest = {
  principal: number;
  annual_rate: number;
  years: number;
  contribution_per_period: number;
  periods_per_year: number;
};
type _SnakeMatchesGenerated = _Assert<SnakeRequest extends OpenApiCompoundGrowthRequest ? true : false>;
type _SnakeDoesNotMatchUi = _Assert<SnakeRequest extends CompoundGrowthRequest ? false : true>;

type _ParamsEqual = _Assert<
  Parameters<CalculatorsApi['compoundGrowth']>[0] extends CompoundGrowthRequest
    ? CompoundGrowthRequest extends Parameters<CalculatorsApi['compoundGrowth']>[0] ? true : false
    : false
>;
type _PublicNotGeneratedSnake = _Assert<
  CompoundGrowthResponse extends OpenApiCompoundGrowthResponse ? false : true
>;

type _CompileTimePins = [
  _ElevenComponents, _PostCompoundGrowth200IsComponent, _ComponentIsPostCompoundGrowth200,
  _PostCompoundGrowthOpIsPath, _PathIsPostCompoundGrowthOp, _PostTargetContributionOpIsPath,
  _PathIsPostTargetContributionOp, _PostTargetDurationOpIsPath, _PathIsPostTargetDurationOp,
  _PostCompoundGrowthBodyIsRequest, _RequestIsPostCompoundGrowthBody,
  _PostTargetContributionBodyIsRequest, _RequestIsPostTargetContributionBody,
  _PostTargetDurationBodyIsRequest, _RequestIsPostTargetDurationBody,
  _PathCompoundGrowthGetNever, _PathCompoundGrowthPutNever, _PathCompoundGrowthDeleteNever,
  _PathCompoundGrowthPatchNever, _PathTargetContributionGetNever, _PathTargetContributionPutNever,
  _PathTargetContributionDeleteNever, _PathTargetContributionPatchNever,
  _PathTargetDurationGetNever, _PathTargetDurationPutNever, _PathTargetDurationDeleteNever,
  _PathTargetDurationPatchNever, _PostCompoundGrowthQueryNever, _PostCompoundGrowthHeaderNever,
  _PostCompoundGrowthPathNever, _PostCompoundGrowthCookieNever, _PostTargetContributionQueryNever,
  _PostTargetContributionHeaderNever, _PostTargetContributionPathNever,
  _PostTargetContributionCookieNever, _PostTargetDurationQueryNever, _PostTargetDurationHeaderNever,
  _PostTargetDurationPathNever, _PostTargetDurationCookieNever, _UiHasAnnualRate,
  _UiHasContributionPerPeriod, _UiHasPeriodsPerYear, _UiHasSeriesTotalPoints, _UiHasTotalContributed,
  _UiHasReasonCode, _UiLacksAnnualRateSnake, _UiLacksContributionSnake, _UiLacksPeriodsSnake,
  _UiLacksSeriesTotalPointsSnake, _UiLacksTotalContributedSnake, _UiLacksReasonCodeSnake,
  _GeneratedHasAnnualRateSnake, _GeneratedHasContributionSnake, _GeneratedHasPeriodsSnake,
  _GeneratedHasSeriesTotalPointsSnake, _GeneratedHasTotalContributedSnake,
  _GeneratedHasReasonCodeSnake, _GeneratedLacksAnnualRateCamel, _GeneratedLacksContributionCamel,
  _StatusIsOk, _StringDoesNotExtendStatus, _ContributionUnion, _DurationUnion, _PendingRejected,
  _UnreachableReasonCode, _UnreachableRejectsExtraCode, _BalancePointNamed,
  _BalancePointIsSeriesItem, _NaiveEqualsPublicRequest, _ContributionRequired, _PeriodsRequired,
  _MissingContributionRejected, _MissingPeriodsRejected, _ConsumerAssignable,
  _SnakeMatchesGenerated, _SnakeDoesNotMatchUi, _ParamsEqual, _PublicNotGeneratedSnake,
];

describe('calculators OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    expect({ ...Calculators }).toEqual({});
    expect(Object.keys(Calculators)).toEqual([]);
    expect(Object.getOwnPropertyNames(Calculators)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('re-exports the seven public names from api/calculators', () => {
    expectTypeOf<ApiCalculators.CompoundGrowthRequest>().toEqualTypeOf<CompoundGrowthRequest>();
    expectTypeOf<ApiCalculators.TargetContributionRequest>().toEqualTypeOf<TargetContributionRequest>();
    expectTypeOf<ApiCalculators.TargetDurationRequest>().toEqualTypeOf<TargetDurationRequest>();
    expectTypeOf<ApiCalculators.CompoundGrowthResponse>().toEqualTypeOf<CompoundGrowthResponse>();
    expectTypeOf<ApiCalculators.TargetContributionResponse>().toEqualTypeOf<TargetContributionResponse>();
    expectTypeOf<ApiCalculators.TargetDurationResponse>().toEqualTypeOf<TargetDurationResponse>();
    expectTypeOf<ApiCalculators.CalculatorBalancePoint>().toEqualTypeOf<CalculatorBalancePoint>();
    expectTypeOf<ApiCalculatorBalancePoint>().toEqualTypeOf<CalculatorBalancePoint>();
  });

  it('equates POST 200 JSON to CompoundGrowthResponse and POST ops to their paths', () => {
    expectTypeOf<OpenApiPostCompoundGrowth200>().toEqualTypeOf<OpenApiCompoundGrowthResponse>();
    expectTypeOf<OpenApiPostCompoundGrowth>().toEqualTypeOf<OpenApiPathCompoundGrowthPost>();
    expectTypeOf<OpenApiPostTargetContribution>().toEqualTypeOf<OpenApiPathTargetContributionPost>();
    expectTypeOf<OpenApiPostTargetDuration>().toEqualTypeOf<OpenApiPathTargetDurationPost>();
    expectTypeOf<OpenApiPostCompoundGrowthBody>().toEqualTypeOf<OpenApiCompoundGrowthRequest>();
    expectTypeOf<OpenApiPostTargetContributionBody>().toEqualTypeOf<OpenApiTargetContributionRequest>();
    expectTypeOf<OpenApiPostTargetDurationBody>().toEqualTypeOf<OpenApiTargetDurationRequest>();
  });

  it('keeps GET/PUT/DELETE/PATCH never and POST query/header/path/cookie never', () => {
    type GrowthGetNever = paths['/api/v1/calculators/compound-growth']['get'] extends never | undefined
      ? true : false;
    type GrowthPutNever = paths['/api/v1/calculators/compound-growth']['put'] extends never | undefined
      ? true : false;
    type GrowthDeleteNever = paths['/api/v1/calculators/compound-growth']['delete'] extends never | undefined
      ? true : false;
    type GrowthPatchNever = paths['/api/v1/calculators/compound-growth']['patch'] extends never | undefined
      ? true : false;
    type ContributionGetNever = paths['/api/v1/calculators/target-contribution']['get'] extends
      never | undefined ? true : false;
    type DurationGetNever = paths['/api/v1/calculators/target-duration']['get'] extends never | undefined
      ? true : false;
    type QueryNever = OpenApiPostCompoundGrowth['parameters']['query'] extends never | undefined
      ? true : false;
    type HeaderNever = OpenApiPostCompoundGrowth['parameters']['header'] extends never | undefined
      ? true : false;
    type PathNever = OpenApiPostCompoundGrowth['parameters']['path'] extends never | undefined
      ? true : false;
    type CookieNever = OpenApiPostCompoundGrowth['parameters']['cookie'] extends never | undefined
      ? true : false;
    expectTypeOf<GrowthGetNever>().toEqualTypeOf<true>();
    expectTypeOf<GrowthPutNever>().toEqualTypeOf<true>();
    expectTypeOf<GrowthDeleteNever>().toEqualTypeOf<true>();
    expectTypeOf<GrowthPatchNever>().toEqualTypeOf<true>();
    expectTypeOf<ContributionGetNever>().toEqualTypeOf<true>();
    expectTypeOf<DurationGetNever>().toEqualTypeOf<true>();
    expectTypeOf<QueryNever>().toEqualTypeOf<true>();
    expectTypeOf<HeaderNever>().toEqualTypeOf<true>();
    expectTypeOf<PathNever>().toEqualTypeOf<true>();
    expectTypeOf<CookieNever>().toEqualTypeOf<true>();
  });

  it('keeps UI keys camelCase and generated keys snake_case', () => {
    expectTypeOf<keyof CompoundGrowthRequest>().not.toMatchTypeOf<
      'annual_rate' | 'contribution_per_period' | 'periods_per_year'
    >();
    expectTypeOf<keyof CompoundGrowthResponse>().not.toMatchTypeOf<
      'series_total_points' | 'total_contributed'
    >();
    expectTypeOf<keyof TargetContributionResponse>().not.toMatchTypeOf<'reason_code'>();
    expectTypeOf<keyof OpenApiCompoundGrowthRequest>().not.toMatchTypeOf<
      'annualRate' | 'contributionPerPeriod' | 'periodsPerYear'
    >();
    expectTypeOf<'annualRate'>().toMatchTypeOf<keyof CompoundGrowthRequest>();
    expectTypeOf<'contributionPerPeriod'>().toMatchTypeOf<keyof CompoundGrowthRequest>();
    expectTypeOf<'periodsPerYear'>().toMatchTypeOf<keyof CompoundGrowthRequest>();
    expectTypeOf<'seriesTotalPoints'>().toMatchTypeOf<keyof CompoundGrowthResponse>();
    expectTypeOf<'totalContributed'>().toMatchTypeOf<keyof CompoundGrowthResponse>();
    expectTypeOf<'reasonCode'>().toMatchTypeOf<keyof TargetContributionResponse>();
  });

  it('keeps compound-growth status as the ok literal and contribution unions closed', () => {
    expectTypeOf<CompoundGrowthResponse['status']>().toEqualTypeOf<'ok'>();
    expectTypeOf<string>().not.toMatchTypeOf<CompoundGrowthResponse['status']>();
    expectTypeOf<TargetContributionResponse>().toEqualTypeOf<CamelizeKeys<
      OpenApiTargetContributionOk | OpenApiTargetContributionAlreadyMet | OpenApiTargetContributionUnreachable
    >>();
    const pending: PendingContribution = {
      status: 'pending',
      target: 1,
      principal: 1,
      annualRate: 0.01,
      years: 1,
      periodsPerYear: 12,
      periodCount: 12,
      periodRate: 0.001,
      currencyPrecisionDigits: 2,
      contributionRounding: 'ceiling',
      reasonCode: 'contribution_required',
      contributionPerPeriod: 0,
    };
    expectTypeOf(pending).not.toMatchTypeOf<TargetContributionResponse>();
    expectTypeOf<UnreachableDuration['reasonCode']>().toEqualTypeOf<GeneratedUnreachableCodes>();
    expectTypeOf<'something_else'>().not.toMatchTypeOf<UnreachableDuration['reasonCode']>();
  });

  it('names nested series points CalculatorBalancePoint without an Override', () => {
    expectTypeOf<CalculatorBalancePoint>().toEqualTypeOf<CamelizeKeys<OpenApiBalancePoint>>();
    expectTypeOf<CalculatorBalancePoint>().toEqualTypeOf<CompoundGrowthResponse['series'][number]>();
    expectTypeOf<CompoundGrowthRequest>().toEqualTypeOf<CamelizeKeys<OpenApiCompoundGrowthRequest>>();
    expectTypeOf<Omit<CompoundGrowthRequest, 'contributionPerPeriod'>>().not.toMatchTypeOf<
      CompoundGrowthRequest
    >();
    expectTypeOf<Omit<CompoundGrowthRequest, 'periodsPerYear'>>().not.toMatchTypeOf<
      CompoundGrowthRequest
    >();
    expectTypeOf<CompoundGrowthResponse>().not.toEqualTypeOf<
      components['schemas']['CompoundGrowthResponse']
    >();
  });

  it('accepts the FinancialCalculatorsPage compound payload and rejects snake_case', () => {
    const consumer = {
      principal: 10000,
      annualRate: 0.08,
      years: 10,
      contributionPerPeriod: 500,
      periodsPerYear: 12,
    };
    expectTypeOf(consumer).toMatchTypeOf<CompoundGrowthRequest>();
    const snake = {
      principal: 10000,
      annual_rate: 0.08,
      years: 10,
      contribution_per_period: 500,
      periods_per_year: 12,
    };
    expectTypeOf(snake).toMatchTypeOf<OpenApiCompoundGrowthRequest>();
    expectTypeOf(snake).not.toMatchTypeOf<CompoundGrowthRequest>();
    expectTypeOf<Parameters<CalculatorsApi['compoundGrowth']>[0]>().toEqualTypeOf<CompoundGrowthRequest>();
  });
});
