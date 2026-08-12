// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { z } from 'zod';
import apiClient from './index';
import { createApiError, createParsedApiError } from './error';
import { toCamelCase } from './utils';

const researchTimelineLinkSchema = z.object({
  type: z.string(),
  stockCode: z.string().nullable().optional(),
  recordId: z.number().int().finite().nullable().optional(),
  queryId: z.string().nullable().optional(),
  sessionId: z.string().nullable().optional(),
  messageId: z.number().int().finite().nullable().optional(),
  turnId: z.string().nullable().optional(),
  signalId: z.number().int().finite().nullable().optional(),
  sourceReportId: z.number().int().finite().nullable().optional(),
}).passthrough();

const researchTimelineNodeSchema = z.object({
  id: z.string(),
  kind: z.enum(['analysis_run', 'chat', 'signal', 'hypothesis']),
  occurredAt: z.string(),
  title: z.string(),
  summary: z.string().nullable().optional(),
  direction: z.string().nullable().optional(),
  confidence: z.number().finite().nullable().optional(),
  status: z.string().nullable().optional(),
  link: researchTimelineLinkSchema,
  meta: z.record(z.string(), z.unknown()).optional(),
}).passthrough();

const researchTimelineSourcesSchema = z.object({
  analysisRun: z.string(),
  chat: z.string(),
  signal: z.string(),
  hypothesis: z.string(),
}).passthrough();

const researchTimelineResponseSchema = z.object({
  stockCode: z.string(),
  items: z.array(researchTimelineNodeSchema).optional(),
  nextCursor: z.string().nullable().optional(),
  hasMore: z.boolean(),
  limit: z.number().int().finite(),
  sources: researchTimelineSourcesSchema,
}).passthrough();

export type ResearchTimelineKind = 'analysis_run' | 'chat' | 'signal' | 'hypothesis';

export type ResearchTimelineLink = {
  type: string;
  stockCode?: string | null;
  recordId?: number | null;
  queryId?: string | null;
  sessionId?: string | null;
  messageId?: number | null;
  turnId?: string | null;
  signalId?: number | null;
  sourceReportId?: number | null;
};

export type ResearchTimelineNode = {
  id: string;
  kind: ResearchTimelineKind;
  occurredAt: string;
  title: string;
  summary?: string | null;
  direction?: string | null;
  confidence?: number | null;
  status?: string | null;
  link: ResearchTimelineLink;
  meta?: Record<string, unknown>;
};

export type ResearchTimelineSources = {
  analysisRun: string;
  chat: string;
  signal: string;
  hypothesis: string;
};

export type ResearchTimelineResponse = {
  stockCode: string;
  items: ResearchTimelineNode[];
  nextCursor?: string | null;
  hasMore: boolean;
  limit: number;
  sources: ResearchTimelineSources;
};

export type ResearchTimelineParams = {
  cursor?: string | null;
  limit?: number;
  kinds?: ResearchTimelineKind[];
};

function toStockCodePath(stockCode: string): string {
  const trimmed = stockCode.trim();
  if (!trimmed) throw new Error('Stock code is required');
  if (trimmed.includes('/')) {
    throw new Error(
      'Stock code cannot contain "/" because the backend route accepts a single path segment; use 600519, HK00700, or AAPL.',
    );
  }
  return encodeURIComponent(trimmed);
}

function parseResponse(data: unknown): ResearchTimelineResponse {
  const camel = toCamelCase<unknown>(data);
  const result = researchTimelineResponseSchema.safeParse(camel);
  if (!result.success) {
    throw createApiError(createParsedApiError({
      title: 'Invalid research timeline response',
      message: `ResearchTimelineResponse validation failed: ${result.error.message}`,
      code: 'api_response_validation_failed',
      category: 'unknown',
    }));
  }
  const parsed = camel as ResearchTimelineResponse;
  return {
    ...parsed,
    items: Array.isArray(parsed.items) ? parsed.items : [],
  };
}

export const researchTimelineApi = {
  async list(
    stockCode: string,
    params: ResearchTimelineParams = {},
  ): Promise<ResearchTimelineResponse> {
    const query: Record<string, string | number> = {};
    if (params.cursor) query.cursor = params.cursor;
    if (params.limit != null) query.limit = params.limit;
    if (params.kinds && params.kinds.length > 0) {
      query.kinds = params.kinds.join(',');
    }
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/stocks/${toStockCodePath(stockCode)}/research-timeline`,
      { params: query },
    );
    return parseResponse(response.data);
  },
};
