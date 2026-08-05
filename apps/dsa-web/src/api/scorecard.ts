// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import apiClient, { locallyRecoverableResourceConfig } from './index';
import { createApiError, createParsedApiError } from './error';
import { toCamelCase } from './utils';
import type { SignalScorecardResponse } from '../types/scorecard';
import type { components } from '../types/api.generated';

type OpenApiSignalScorecard = components['schemas']['SignalScorecardResponse'];
type _AssertScorecardFields = keyof OpenApiSignalScorecard;
const _scorecardFieldAnchor: _AssertScorecardFields = 'min_samples';
void _scorecardFieldAnchor;

const scorecardOverallSchema = z.object({
  status: z.string(),
  sampleSize: z.number(),
  completed: z.number(),
  hitRatePct: z.number().nullable().optional(),
  avgReturnPct: z.number().nullable().optional(),
}).passthrough();

const scorecardBucketSchema = z.object({
  signalType: z.string(),
  horizon: z.string(),
  status: z.string(),
  sampleSize: z.number(),
  completed: z.number(),
  hitRatePct: z.number().nullable().optional(),
  avgReturnPct: z.number().nullable().optional(),
}).passthrough();

const scorecardReturnBandSchema = z.object({
  band: z.string(),
  count: z.number(),
  sharePct: z.number().nullable().optional(),
}).passthrough();

const scorecardMissSchema = z.object({
  signalType: z.string(),
  horizon: z.string(),
  returnPct: z.number().nullable().optional(),
  anchorDate: z.string().nullable().optional(),
}).passthrough();

const signalScorecardResponseSchema = z.object({
  minSamples: z.number(),
  overall: scorecardOverallSchema,
  bySignalTypeHorizon: z.array(scorecardBucketSchema),
  returnDistribution: z.array(scorecardReturnBandSchema),
  recentMisses: z.array(scorecardMissSchema),
}).passthrough();

function parseCamelCasePayload<T>(data: unknown, schema: z.ZodTypeAny, label: string): T {
  const camel = toCamelCase<unknown>(data);
  const result = schema.safeParse(camel);
  if (!result.success) {
    const issueSummary = result.error.issues
      .slice(0, 5)
      .map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`)
      .join('; ');
    if (import.meta.env.DEV) {
      console.error(`[scorecard] response validation failed (${label})`, result.error.issues);
    }
    throw createApiError(
      createParsedApiError({
        title: '响应校验失败',
        message: `接口响应未通过校验（${label}）。${issueSummary}`,
        rawMessage: result.error.message,
        category: 'unknown',
        code: 'api_response_validation_failed',
        params: { label, issues: issueSummary },
        details: result.error.issues,
      }),
    );
  }
  return camel as T;
}

export const scorecardApi = {
  async getPublic(): Promise<SignalScorecardResponse> {
    const response = await apiClient.get(
      '/api/v1/scorecard',
      locallyRecoverableResourceConfig(),
    );
    return parseCamelCasePayload<SignalScorecardResponse>(
      response.data,
      signalScorecardResponseSchema,
      'SignalScorecardResponse',
    );
  },
};
