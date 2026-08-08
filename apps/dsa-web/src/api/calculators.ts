// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import apiClient from './index';

const BASE_PATH = '/api/v1/calculators';

const balancePointSchema = z.object({
  period: z.number(),
  balance: z.number(),
  totalContributed: z.number(),
  gain: z.number(),
}).passthrough();

const compoundGrowthResponseSchema = z.object({
  status: z.string(),
  principal: z.number(),
  annualRate: z.number(),
  years: z.number(),
  contributionPerPeriod: z.number(),
  periodsPerYear: z.number(),
  periodCount: z.number(),
  periodRate: z.number(),
  finalValue: z.number(),
  totalContributed: z.number(),
  totalGain: z.number(),
  series: z.array(balancePointSchema),
}).passthrough();

const targetContributionResponseSchema = z.object({
  status: z.string(),
  target: z.number(),
  principal: z.number(),
  annualRate: z.number(),
  years: z.number(),
  periodsPerYear: z.number(),
  periodCount: z.number(),
  periodRate: z.number(),
  contributionPerPeriod: z.number().nullable().optional(),
  message: z.string().nullable().optional(),
}).passthrough();

const targetDurationResponseSchema = z.object({
  status: z.string(),
  target: z.number(),
  principal: z.number(),
  annualRate: z.number(),
  contributionPerPeriod: z.number(),
  periodsPerYear: z.number(),
  periodRate: z.number(),
  periodCount: z.number().nullable().optional(),
  years: z.number().nullable().optional(),
  message: z.string().nullable().optional(),
}).passthrough();

export type CompoundGrowthRequest = {
  principal: number;
  annualRate: number;
  years: number;
  contributionPerPeriod?: number;
  periodsPerYear?: number;
};

export type TargetContributionRequest = {
  target: number;
  principal: number;
  annualRate: number;
  years: number;
  periodsPerYear?: number;
};

export type TargetDurationRequest = {
  target: number;
  principal: number;
  annualRate: number;
  contributionPerPeriod: number;
  periodsPerYear?: number;
};

export type CompoundGrowthResponse = z.infer<typeof compoundGrowthResponseSchema>;
export type TargetContributionResponse = z.infer<typeof targetContributionResponseSchema>;
export type TargetDurationResponse = z.infer<typeof targetDurationResponseSchema>;

function toSnakeBody(body: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(body)) {
    const snake = key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
    out[snake] = value;
  }
  return out;
}

export const calculatorsApi = {
  async compoundGrowth(body: CompoundGrowthRequest): Promise<CompoundGrowthResponse> {
    const response = await apiClient.post(
      `${BASE_PATH}/compound-growth`,
      toSnakeBody(body as unknown as Record<string, unknown>),
    );
    return parseCamelCasePayload<CompoundGrowthResponse>(
      response.data,
      compoundGrowthResponseSchema,
      'CompoundGrowthResponse',
    );
  },

  async targetContribution(body: TargetContributionRequest): Promise<TargetContributionResponse> {
    const response = await apiClient.post(
      `${BASE_PATH}/target-contribution`,
      toSnakeBody(body as unknown as Record<string, unknown>),
    );
    return parseCamelCasePayload<TargetContributionResponse>(
      response.data,
      targetContributionResponseSchema,
      'TargetContributionResponse',
    );
  },

  async targetDuration(body: TargetDurationRequest): Promise<TargetDurationResponse> {
    const response = await apiClient.post(
      `${BASE_PATH}/target-duration`,
      toSnakeBody(body as unknown as Record<string, unknown>),
    );
    return parseCamelCasePayload<TargetDurationResponse>(
      response.data,
      targetDurationResponseSchema,
      'TargetDurationResponse',
    );
  },
};
