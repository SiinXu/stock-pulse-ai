// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import apiClient, { locallyRecoverableResourceConfig } from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';
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
      'scorecard',
    );
  },
};
