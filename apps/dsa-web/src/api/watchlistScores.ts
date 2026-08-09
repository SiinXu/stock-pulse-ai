// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import apiClient, { locallyRecoverableResourceConfig } from './index';
import { createApiError, createParsedApiError } from './error';
import { toCamelCase } from './utils';
import type { WatchlistScoreResponse, WatchlistScoreSortMode } from '../types/watchlistScore';

const degradationReasonSchema = z.enum([
  'invalid_sentiment',
  'inactive_signal',
  'expired_signal',
  'incoherent_signal_source',
  'unknown_signal_action',
  'invalid_signal_confidence',
]);
const finiteNumber = z.number().finite();
const factorSourceSchema = z.object({
  id: z.number().int().positive().nullable(),
  sourceReportId: z.number().int().positive().nullable(),
  profile: z.string().max(24).nullable(),
  asOf: z.string().datetime({ offset: true }).nullable(),
  expiresAt: z.string().datetime({ offset: true }).nullable(),
  formulaVersion: z.literal('watchlist_score_v1'),
}).strict();
const factorSchema = z.object({
  key: z.enum(['analysis_sentiment', 'decision_signal']),
  status: z.enum(['applied', 'ignored']),
  value: z.union([z.string(), finiteNumber]).nullable(),
  params: z.record(z.string(), z.union([z.string(), finiteNumber, z.boolean(), z.null()])),
  reason: degradationReasonSchema.nullable(),
  source: factorSourceSchema,
}).strict();
const itemSchema = z.object({
  stockCode: z.string().min(1).max(16),
  status: z.enum(['scored', 'unanalyzed']),
  score: z.number().int().min(0).max(100).nullable(),
  asOf: z.string().datetime({ offset: true }).nullable(),
  ageDays: z.number().int().nonnegative().nullable(),
  analysisId: z.number().int().positive().nullable(),
  operationAdvice: z.string().max(64).nullable(),
  factors: z.array(factorSchema).max(2),
  freshness: z.enum(['none', 'unknown', 'today', 'recent', 'stale_week', 'stale']),
  degradedReasons: z.array(degradationReasonSchema).max(2),
}).strict();
const boundedRows = z.object({
  analysis: z.number().int().min(0).max(200),
  signals: z.number().int().min(0).max(200),
}).strict();
const responseSchema = z.object({
  formulaVersion: z.literal('watchlist_score_v1'),
  scoringMode: z.literal('aggregate_existing'),
  sort: z.enum(['manual', 'score_desc', 'score_asc']),
  items: z.array(itemSchema).max(200),
  queryCount: z.object({
    analysis: z.number().int().min(0).max(1),
    signals: z.number().int().min(0).max(1),
  }).strict(),
  sourceRows: boundedRows,
  disclaimerKey: z.literal('watchlist_score.disclaimer'),
}).strict();

function parseResponse(data: unknown): WatchlistScoreResponse {
  const result = responseSchema.safeParse(toCamelCase<unknown>(data));
  if (!result.success) {
    const issueSummary = result.error.issues
      .slice(0, 5)
      .map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`)
      .join('; ');
    throw createApiError(createParsedApiError({
      title: 'Response validation failed',
      message: `Invalid watchlist score response: ${issueSummary}`,
      rawMessage: result.error.message,
      category: 'unknown',
      code: 'api_response_validation_failed',
    }));
  }
  return result.data;
}

export interface ScoreWatchlistParams {
  stockCodes: string[];
  sort?: WatchlistScoreSortMode;
  signal?: AbortSignal;
}

export const watchlistScoresApi = {
  score: async (params: ScoreWatchlistParams): Promise<WatchlistScoreResponse> => {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/watchlist/scores',
      { stock_codes: params.stockCodes, sort: params.sort ?? 'manual' },
      { ...locallyRecoverableResourceConfig(), signal: params.signal },
    );
    return parseResponse(response.data);
  },
};
