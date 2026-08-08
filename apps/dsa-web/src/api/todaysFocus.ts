// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import apiClient from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { TodaysFocusQuery, TodaysFocusResponse } from '../types/todaysFocus';

const todaysFocusItemSchema = z.object({
  code: z.string(),
  name: z.string(),
  reasonCode: z.string(),
  reasonDisplay: z.string(),
  priority: z.number(),
  weightPct: z.number().nullable().optional(),
  secondaryReasonCodes: z.array(z.string()).optional(),
  evidence: z.record(z.string(), z.unknown()).optional(),
}).passthrough();

const todaysFocusResponseSchema = z.object({
  packVersion: z.string(),
  generatedAt: z.string(),
  status: z.string(),
  maxItems: z.number(),
  itemCount: z.number(),
  items: z.array(todaysFocusItemSchema).optional(),
  emptyReason: z.string().nullable().optional(),
  emptyMessage: z.string().nullable().optional(),
  sourcesUsed: z.array(z.string()).optional(),
  costContract: z.object({
    providerCalls: z.number().optional(),
    analysisRunsTriggered: z.number().optional(),
    zeroExtraFetch: z.boolean().optional(),
  }).passthrough().optional(),
  presentationBoundary: z.record(z.string(), z.unknown()).optional(),
}).passthrough();

export async function getTodaysFocus(query: TodaysFocusQuery = {}): Promise<TodaysFocusResponse> {
  const response = await apiClient.get('/focus/today', {
    params: {
      max_items: query.maxItems,
      account_id: query.accountId,
      language: query.language,
    },
  });
  return parseCamelCasePayload(todaysFocusResponseSchema, response.data) as TodaysFocusResponse;
}
