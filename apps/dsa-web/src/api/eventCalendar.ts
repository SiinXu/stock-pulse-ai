// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import apiClient from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { EventCalendarQuery, EventCalendarResponse } from '../types/eventCalendar';

const impactPreviewSchema = z.object({
  available: z.boolean(),
  whatHappened: z.string().nullable().optional(),
  whyItMatters: z.string().nullable().optional(),
  eventCategory: z.string().nullable().optional(),
  affected: z.record(z.string(), z.unknown()).nullable().optional(),
  relatedAnalysis: z.string().nullable().optional(),
  degraded: z.boolean().nullable().optional(),
  source: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
}).passthrough();

const calendarEventItemSchema = z.object({
  eventId: z.string(),
  eventType: z.string(),
  eventDate: z.string(),
  certainty: z.string(),
  symbol: z.string(),
  title: z.string(),
  market: z.string().optional(),
  source: z.string().optional(),
  fetchedAt: z.string().nullable().optional(),
  description: z.string().optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
  impactPreview: impactPreviewSchema.nullable().optional(),
}).passthrough();

const coverageRowSchema = z.object({
  market: z.string(),
  earnings: z.string(),
  exDividend: z.string(),
  unlock: z.string(),
  indexRebalance: z.string(),
  macro: z.string(),
}).passthrough();

const eventCalendarResponseSchema = z.object({
  enabled: z.boolean(),
  fetchAttempted: z.boolean(),
  asOf: z.string(),
  dateFrom: z.string(),
  dateTo: z.string(),
  eventTypes: z.array(z.string()).optional(),
  symbols: z.array(z.string()).optional(),
  symbolCount: z.number(),
  eventCount: z.number(),
  events: z.array(calendarEventItemSchema).optional(),
  coverage: z.array(coverageRowSchema).optional(),
  sourcesAttempted: z.array(z.string()).optional(),
  errors: z.array(z.string()).optional(),
  coverageNotes: z.array(z.string()).optional(),
  fetchedAt: z.string().nullable().optional(),
  impactPreviewMode: z.string().optional(),
  reusesBuildImpactContext: z.boolean().optional(),
}).passthrough();

function buildParams(query: EventCalendarQuery): Record<string, string | boolean> {
  const params: Record<string, string | boolean> = {};
  if (query.dateFrom) params.date_from = query.dateFrom;
  if (query.dateTo) params.date_to = query.dateTo;
  if (query.symbols) params.symbols = query.symbols;
  if (query.eventTypes) params.event_types = query.eventTypes;
  if (query.includeImpact !== undefined) params.include_impact = query.includeImpact;
  if (query.reportLanguage) params.report_language = query.reportLanguage;
  return params;
}

export const eventCalendarApi = {
  async getCalendar(query: EventCalendarQuery = {}): Promise<EventCalendarResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/event-calendar', {
      params: buildParams(query),
    });
    const parsed = parseCamelCasePayload<EventCalendarResponse>(
      response.data,
      eventCalendarResponseSchema,
      'EventCalendarResponse',
    );
    return {
      ...parsed,
      eventTypes: Array.isArray(parsed.eventTypes) ? parsed.eventTypes : [],
      symbols: Array.isArray(parsed.symbols) ? parsed.symbols : [],
      events: Array.isArray(parsed.events) ? parsed.events : [],
      coverage: Array.isArray(parsed.coverage) ? parsed.coverage : [],
      sourcesAttempted: Array.isArray(parsed.sourcesAttempted) ? parsed.sourcesAttempted : [],
      errors: Array.isArray(parsed.errors) ? parsed.errors : [],
      coverageNotes: Array.isArray(parsed.coverageNotes) ? parsed.coverageNotes : [],
    };
  },
};
