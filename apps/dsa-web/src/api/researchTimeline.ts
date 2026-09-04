// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { z } from 'zod';
import apiClient from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { components } from '../types/api.generated';
import type {
  ResearchTimelineParams,
  ResearchTimelineResponse,
} from '../types/researchTimeline';

export type {
  ResearchTimelineKind,
  ResearchTimelineLink,
  ResearchTimelineNode,
  ResearchTimelineParams,
  ResearchTimelineResponse,
  ResearchTimelineSources,
} from '../types/researchTimeline';

type OpenApiResearchTimelineResponse = components['schemas']['ResearchTimelineResponse'];
type OpenApiResearchTimelineNode = components['schemas']['ResearchTimelineNode'];

// Compile-time anchor: hand-written camelCase types stay aligned with OpenAPI
// field sets (rename detection is structural; extra optional UI fields are fine).
type _AssertTimelineResponse = keyof OpenApiResearchTimelineResponse;
type _AssertTimelineNode = keyof OpenApiResearchTimelineNode;
const _timelineResponseAnchor: _AssertTimelineResponse = 'stock_code';
const _timelineNodeAnchor: _AssertTimelineNode = 'occurred_at';
void _timelineResponseAnchor;
void _timelineNodeAnchor;

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
  const parsed = parseCamelCasePayload<ResearchTimelineResponse>(
    data,
    researchTimelineResponseSchema,
    'ResearchTimelineResponse',
    'research-timeline',
  );
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
