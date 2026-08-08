// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import apiClient, { locallyRecoverableResourceConfig } from './index';
import { createApiError, createParsedApiError } from './error';
import { toCamelCase } from './utils';
import type { WatchlistScoreResponse, WatchlistScoreSortMode } from '../types/watchlistScore';

const factorSchema = z.object({
  key: z.string(),
  label: z.string(),
  value: z.union([z.string(), z.number()]),
  detail: z.string().nullable().optional(),
}).passthrough();

const itemSchema = z.object({
  stockCode: z.string(),
  status: z.enum(['scored', 'unanalyzed']),
  score: z.number().nullable(),
  asOf: z.string().nullable().optional(),
  ageDays: z.number().nullable().optional(),
  analysisId: z.number().nullable().optional(),
  operationAdvice: z.string().nullable().optional(),
  factors: z.array(factorSchema).default([]),
  freshness: z.string().optional(),
}).passthrough();

const responseSchema = z.object({
  scoringMode: z.string(),
  sort: z.string(),
  items: z.array(itemSchema),
  queryCount: z.object({
    analysis: z.number(),
    signals: z.number(),
  }).passthrough(),
  disclaimer: z.string(),
}).passthrough();

function parseResponse(data: unknown): WatchlistScoreResponse {
  const camel = toCamelCase<unknown>(data);
  const result = responseSchema.safeParse(camel);
  if (!result.success) {
    const issueSummary = result.error.issues
      .slice(0, 5)
      .map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`)
      .join('; ');
    throw createApiError(
      createParsedApiError({
        title: 'Response validation failed',
        message: `Invalid watchlist score response: ${issueSummary}`,
        rawMessage: result.error.message,
        category: 'unknown',
        code: 'api_response_validation_failed',
      }),
    );
  }
  const parsed = result.data;
  return {
    scoringMode: parsed.scoringMode,
    sort: parsed.sort,
    items: parsed.items.map((item) => ({
      stockCode: item.stockCode,
      status: item.status,
      score: item.score,
      asOf: item.asOf ?? null,
      ageDays: item.ageDays ?? null,
      analysisId: item.analysisId ?? null,
      operationAdvice: item.operationAdvice ?? null,
      factors: item.factors.map((factor) => ({
        key: factor.key,
        label: factor.label,
        value: factor.value,
        detail: factor.detail ?? null,
      })),
      freshness: item.freshness ?? 'none',
    })),
    queryCount: {
      analysis: parsed.queryCount.analysis,
      signals: parsed.queryCount.signals,
    },
    disclaimer: parsed.disclaimer,
  };
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
      {
        stock_codes: params.stockCodes,
        sort: params.sort ?? 'manual',
      },
      {
        ...locallyRecoverableResourceConfig(),
        signal: params.signal,
      },
    );
    return parseResponse(response.data);
  },
};
