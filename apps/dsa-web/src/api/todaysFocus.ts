// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import apiClient from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { TodaysFocusQuery, TodaysFocusResponse } from '../types/todaysFocus';

const awareDatetime = z.string().datetime({ offset: true });
const directionalAction = z.enum(['buy', 'sell', 'hold']);
const reasonCode = z.enum([
  'alert_triggered',
  'corporate_event',
  'analysis_reversal',
]);
const alertEvidenceSchema = z.object({
  type: z.literal('alert'),
  triggerId: z.number().int().positive(),
  ruleId: z.number().int().positive().nullable(),
  observedAt: awareDatetime,
  status: z.literal('triggered'),
  source: z.string().min(1).max(64).nullable().optional(),
}).strict();
const analysisEvidenceSchema = z.object({
  type: z.literal('analysis'),
  recordId: z.number().int().positive(),
  queryId: z.string().min(1).max(128).nullable(),
  observedAt: awareDatetime,
  previousObservedAt: awareDatetime,
  previousAction: directionalAction,
  latestAction: directionalAction,
}).strict().refine(
  (value) => value.previousAction !== value.latestAction,
  { message: 'Analysis reversal actions must differ' },
);
const corporateEventEvidenceSchema = z.object({
  type: z.literal('corporate_event'),
  eventId: z.string().min(1).max(128),
  observedAt: awareDatetime,
  href: z.string().min(2).max(512).refine(
    (value) => value.startsWith('/') && !value.startsWith('//'),
    { message: 'Corporate event href must be a safe relative path' },
  ),
}).strict();
const evidenceSchema = z.discriminatedUnion('type', [
  alertEvidenceSchema,
  analysisEvidenceSchema,
  corporateEventEvidenceSchema,
]);
const todaysFocusItemSchema = z.object({
  code: z.string().min(1).max(32),
  name: z.string().min(1).max(80),
  reasonCode,
  reasonDisplay: z.string().min(1).max(240),
  priority: z.number().int().min(0).max(100),
  weightPct: z.number().finite().min(0).max(100).nullable(),
  secondaryReasonCodes: z.array(reasonCode).max(2),
  evidence: evidenceSchema,
}).strict().refine((item) => {
  const expectedEvidenceType = {
    alert_triggered: 'alert',
    corporate_event: 'corporate_event',
    analysis_reversal: 'analysis',
  } as const;
  return item.evidence.type === expectedEvidenceType[item.reasonCode];
}, { message: 'Reason code must match evidence type' });

const todaysFocusResponseSchema = z.object({
  packVersion: z.literal('todays_focus/2.0'),
  generatedAt: awareDatetime,
  status: z.enum(['ok', 'empty', 'degraded']),
  maxItems: z.number().int().min(0).max(10),
  itemCount: z.number().int().min(0).max(10),
  items: z.array(todaysFocusItemSchema).max(10),
  emptyReason: z.enum([
    'source_unavailable',
    'no_fresh_deterministic_signals',
  ]).nullable(),
  emptyMessage: z.string().max(240).nullable(),
  sourcesUsed: z.array(z.enum([
    'alert',
    'analysis',
    'corporate_event',
    'alerts',
    'analysis_history',
    'corporate_events',
  ])).max(6),
  degradedSources: z.array(z.enum([
    'alerts',
    'analysis_history',
    'corporate_events',
    'portfolio_position_cache',
  ])).max(4),
  temporalPolicy: z.object({
    semantics: z.literal('local_calendar_day'),
    timezone: z.string().min(1).max(64),
    localDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    windowStart: awareDatetime,
    windowEnd: awareDatetime,
    naiveTimestampPolicy: z.literal('assume_utc'),
    missingTimestampPolicy: z.literal('exclude'),
    nonTradingDayPolicy: z.literal('same_local_day_only'),
  }).strict(),
  universeContract: z.object({
    symbolCount: z.number().int().min(0).max(1000),
    hardCap: z.literal(1000),
    truncated: z.boolean(),
    sources: z.array(z.enum([
      'injected_evidences',
      'portfolio_position_cache',
      'request',
      'watchlist_config',
    ])).max(4),
  }).strict(),
  costContract: z.object({
    alertRepositoryCalls: z.number().int().min(0).max(1),
    portfolioRepositoryCalls: z.number().int().min(0).max(1),
    analysisHistoryRepositoryCalls: z.number().int().min(0).max(1),
    eventRepositoryCalls: z.number().int().min(0).max(1),
    databaseWrites: z.literal(0),
    providerCalls: z.literal(0),
    analysisRunsTriggered: z.literal(0),
    zeroExtraFetch: z.literal(true),
    readOnly: z.literal(true),
  }).strict(),
  presentationBoundary: z.object({
    alertsOwnedBy: z.literal('signal_center'),
    focusShows: z.literal('prioritized_symbols_with_evidence_links'),
    duplicateAlertUi: z.literal(false),
  }).strict(),
}).strict().refine(
  (value) => value.itemCount === value.items.length && value.itemCount <= value.maxItems,
  { message: 'Item count must match the bounded item list' },
);

export async function getTodaysFocus(
  query: TodaysFocusQuery = {},
): Promise<TodaysFocusResponse> {
  const response = await apiClient.get('/focus/today', {
    params: {
      max_items: query.maxItems,
      account_id: query.accountId,
      language: query.language,
    },
  });
  return parseCamelCasePayload<TodaysFocusResponse>(
    response.data,
    todaysFocusResponseSchema,
    'TodaysFocusResponse',
  );
}
