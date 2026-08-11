// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

export type EventCalendarEventType =
  | 'earnings'
  | 'ex_dividend'
  | 'unlock'
  | 'index_rebalance'
  | 'macro';

export type EventCalendarCertainty = 'confirmed' | 'scheduled' | 'estimated';

export type EventImpactPreview = {
  available: boolean;
  whatHappened?: string | null;
  whyItMatters?: string | null;
  eventCategory?: string | null;
  affected?: Record<string, unknown> | null;
  relatedAnalysis?: string | null;
  degraded?: boolean | null;
  source?: string | null;
  error?: string | null;
};

export type CalendarEventItem = {
  eventId: string;
  eventType: EventCalendarEventType | string;
  eventDate: string;
  certainty: EventCalendarCertainty | string;
  symbol: string;
  title: string;
  market?: string;
  source?: string;
  fetchedAt?: string | null;
  description?: string;
  metadata?: Record<string, unknown>;
  impactPreview?: EventImpactPreview | null;
};

export type EventCalendarCoverageRow = {
  market: string;
  earnings: string;
  exDividend: string;
  unlock: string;
  indexRebalance: string;
  macro: string;
};

export type EventCalendarResponse = {
  enabled: boolean;
  fetchAttempted: boolean;
  asOf: string;
  dateFrom: string;
  dateTo: string;
  eventTypes: string[];
  symbols: string[];
  symbolCount: number;
  eventCount: number;
  events: CalendarEventItem[];
  coverage: EventCalendarCoverageRow[];
  sourcesAttempted: string[];
  errors: string[];
  coverageNotes: string[];
  fetchedAt?: string | null;
  impactPreviewMode?: string;
  reusesBuildImpactContext?: boolean;
};

export type EventCalendarQuery = {
  dateFrom?: string;
  dateTo?: string;
  symbols?: string;
  eventTypes?: string;
  includeImpact?: boolean;
  reportLanguage?: string;
};
