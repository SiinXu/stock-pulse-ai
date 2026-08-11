// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import type { components } from '../types/api.generated';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import apiClient from './index';

const BASE_PATH = '/api/v1/calculators';

type Schemas = components['schemas'];
type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;
type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? Array<CamelizeKeys<U>>
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type OpenApiTargetContributionResponse =
  | Schemas['TargetContributionOkResponse']
  | Schemas['TargetContributionAlreadyMetResponse']
  | Schemas['TargetContributionUnreachableResponse'];
type OpenApiTargetDurationResponse =
  | Schemas['TargetDurationOkResponse']
  | Schemas['TargetDurationAlreadyMetResponse']
  | Schemas['TargetDurationUnreachableResponse'];

export type CompoundGrowthRequest = CamelizeKeys<Schemas['CompoundGrowthRequest']>;
export type TargetContributionRequest = CamelizeKeys<Schemas['TargetContributionRequest']>;
export type TargetDurationRequest = CamelizeKeys<Schemas['TargetDurationRequest']>;
export type CompoundGrowthResponse = CamelizeKeys<Schemas['CompoundGrowthResponse']>;
export type TargetContributionResponse = CamelizeKeys<OpenApiTargetContributionResponse>;
export type TargetDurationResponse = CamelizeKeys<OpenApiTargetDurationResponse>;

const balancePointSchema = z.object({
  period: z.number().int().nonnegative(),
  balance: z.number().finite(),
  totalContributed: z.number().finite(),
  gain: z.number().finite(),
}).strict();

const compoundGrowthResponseSchema: z.ZodType<CompoundGrowthResponse> = z.object({
  status: z.literal('ok'),
  principal: z.number().finite(),
  annualRate: z.number().finite(),
  years: z.number().finite(),
  contributionPerPeriod: z.number().finite(),
  periodsPerYear: z.number().int(),
  periodCount: z.number().int(),
  periodRate: z.number().finite(),
  finalValue: z.number().finite(),
  totalContributed: z.number().finite(),
  totalGain: z.number().finite(),
  seriesTotalPoints: z.number().int().min(2),
  seriesReturnedPoints: z.number().int().min(2).max(241),
  seriesSampled: z.boolean(),
  seriesStride: z.number().int().min(1),
  series: z.array(balancePointSchema).max(241),
}).strict();

const targetContributionBase = {
  target: z.number().finite(),
  principal: z.number().finite(),
  annualRate: z.number().finite(),
  years: z.number().finite(),
  periodsPerYear: z.number().int(),
  periodCount: z.number().int(),
  periodRate: z.number().finite(),
  currencyPrecisionDigits: z.literal(2),
  contributionRounding: z.literal('ceiling'),
};

const targetContributionResponseSchema: z.ZodType<TargetContributionResponse> = z.discriminatedUnion('status', [
  z.object({
    ...targetContributionBase,
    status: z.literal('ok'),
    reasonCode: z.literal('contribution_required'),
    contributionPerPeriod: z.number().finite(),
  }).strict(),
  z.object({
    ...targetContributionBase,
    status: z.literal('already_met'),
    reasonCode: z.literal('principal_growth_meets_target'),
    contributionPerPeriod: z.number().finite(),
  }).strict(),
  z.object({
    ...targetContributionBase,
    status: z.literal('unreachable'),
    reasonCode: z.literal('target_unreachable'),
    contributionPerPeriod: z.null(),
  }).strict(),
]);

const targetDurationBase = {
  target: z.number().finite(),
  principal: z.number().finite(),
  annualRate: z.number().finite(),
  contributionPerPeriod: z.number().finite(),
  periodsPerYear: z.number().int(),
  periodRate: z.number().finite(),
};

const targetDurationResponseSchema: z.ZodType<TargetDurationResponse> = z.discriminatedUnion('status', [
  z.object({
    ...targetDurationBase,
    status: z.literal('ok'),
    reasonCode: z.literal('duration_solved'),
    periodCount: z.number().int().positive(),
    years: z.number().positive().max(100),
  }).strict(),
  z.object({
    ...targetDurationBase,
    status: z.literal('already_met'),
    reasonCode: z.literal('principal_already_meets_target'),
    periodCount: z.literal(0),
    years: z.literal(0),
  }).strict(),
  z.object({
    ...targetDurationBase,
    status: z.literal('unreachable'),
    reasonCode: z.enum(['non_positive_trajectory', 'max_years_exceeded', 'target_unreachable']),
    periodCount: z.null(),
    years: z.null(),
  }).strict(),
]);

function toSnakeBody(body: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(body).map(([key, value]) => [
    key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`),
    value,
  ]));
}

type RequestOptions = { signal?: AbortSignal };

export const calculatorsApi = {
  async compoundGrowth(
    body: CompoundGrowthRequest,
    options: RequestOptions = {},
  ): Promise<CompoundGrowthResponse> {
    const response = await apiClient.post(
      `${BASE_PATH}/compound-growth`,
      toSnakeBody(body as unknown as Record<string, unknown>),
      { signal: options.signal },
    );
    return parseCamelCasePayload<CompoundGrowthResponse>(
      response.data,
      compoundGrowthResponseSchema,
      'CompoundGrowthResponse',
    );
  },

  async targetContribution(
    body: TargetContributionRequest,
    options: RequestOptions = {},
  ): Promise<TargetContributionResponse> {
    const response = await apiClient.post(
      `${BASE_PATH}/target-contribution`,
      toSnakeBody(body as unknown as Record<string, unknown>),
      { signal: options.signal },
    );
    return parseCamelCasePayload<TargetContributionResponse>(
      response.data,
      targetContributionResponseSchema,
      'TargetContributionResponse',
    );
  },

  async targetDuration(
    body: TargetDurationRequest,
    options: RequestOptions = {},
  ): Promise<TargetDurationResponse> {
    const response = await apiClient.post(
      `${BASE_PATH}/target-duration`,
      toSnakeBody(body as unknown as Record<string, unknown>),
      { signal: options.signal },
    );
    return parseCamelCasePayload<TargetDurationResponse>(
      response.data,
      targetDurationResponseSchema,
      'TargetDurationResponse',
    );
  },
};
