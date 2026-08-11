// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

export type CorporateEventCategory =
  | 'earnings'
  | 'shareholder'
  | 'mna'
  | 'regulatory'
  | 'analyst';

export type EventCalendarErrorCode =
  | 'event_calendar_page_unavailable'
  | 'event_calendar_result_limit_reached';

export interface CalendarEventItem {
  eventId: number;
  eventDate: string;
  symbol: string;
  status: string;
  eventCategory?: CorporateEventCategory | null;
  whatHappened?: string | null;
  whyItMatters?: string | null;
  degraded: boolean;
  inWatchlist: boolean;
  inPortfolio: boolean;
  source?: string | null;
}

export interface EventCalendarResponse {
  events: CalendarEventItem[];
  loadedCount: number;
  total: number;
  partialErrors: EventCalendarErrorCode[];
}

export interface EventCalendarQuery {
  dateFrom: string;
  dateTo: string;
}
