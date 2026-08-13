// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Composes calendar events from alert trigger list pages (no dedicated calendar schema).
 * Anchors on AlertTriggerListResponse / AlertTriggerItem OpenAPI components.
 */
import { z } from 'zod';
import type { components } from '../types/api.generated';
import apiClient from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type {
  CalendarEventItem,
  CorporateEventCategory,
  EventCalendarQuery,
  EventCalendarResponse,
} from '../types/eventCalendar';
import { CORPORATE_EVENT_CATEGORIES } from '../types/eventAlerts';


type OpenApiTriggerList = components['schemas']['AlertTriggerListResponse'];
type OpenApiTriggerItem = components['schemas']['AlertTriggerItem'];
type _AssertTriggerList = keyof OpenApiTriggerList;
type _AssertTriggerItem = keyof OpenApiTriggerItem;
const _triggerListAnchor: _AssertTriggerList = 'page_size';
const _triggerItemAnchor: _AssertTriggerItem = 'triggered_at';
void _triggerListAnchor;
void _triggerItemAnchor;

const PAGE_SIZE = 100;
const MAX_PAGES = 20;
const CORPORATE_CATEGORIES = new Set<CorporateEventCategory>(CORPORATE_EVENT_CATEGORIES);

const eventContextSchema = z.object({
  eventCategory: z.string().nullable().optional(),
  whatHappened: z.string().nullable().optional(),
  whyItMatters: z.string().nullable().optional(),
}).passthrough();

const impactContextSchema = eventContextSchema.extend({
  degraded: z.boolean().optional(),
  affected: z.object({
    inWatchlist: z.boolean().optional(),
    inPortfolio: z.boolean().optional(),
  }).nullable().optional(),
});

const triggerSchema = z.object({
  id: z.number(),
  target: z.string(),
  status: z.string(),
  reason: z.string().nullable().optional(),
  dataSource: z.string().nullable().optional(),
  dataTimestamp: z.string().nullable().optional(),
  triggeredAt: z.string().nullable().optional(),
  eventContext: eventContextSchema.nullable().optional(),
  impactContext: impactContextSchema.nullable().optional(),
}).passthrough();

const triggerPageSchema = z.object({
  items: z.array(triggerSchema).default([]),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  pageSize: z.number().int().positive(),
  nextCursor: z.string().nullable().optional(),
});

type Trigger = z.infer<typeof triggerSchema>;

function eventDate(trigger: Trigger): string | null {
  const value = trigger.dataTimestamp || trigger.triggeredAt;
  if (!value) return null;
  const match = /^\d{4}-\d{2}-\d{2}/.exec(value);
  return match?.[0] ?? null;
}

function categoryOf(trigger: Trigger): CorporateEventCategory | null {
  const value = trigger.impactContext?.eventCategory
    ?? trigger.eventContext?.eventCategory;
  return value && CORPORATE_CATEGORIES.has(value as CorporateEventCategory)
    ? value as CorporateEventCategory
    : null;
}

function toCalendarEvent(trigger: Trigger): CalendarEventItem | null {
  const date = eventDate(trigger);
  if (!date) return null;
  const context = trigger.impactContext ?? trigger.eventContext;
  return {
    eventId: trigger.id,
    eventDate: date,
    symbol: trigger.target,
    status: trigger.status,
    eventCategory: categoryOf(trigger),
    whatHappened: context?.whatHappened ?? trigger.reason,
    whyItMatters: context?.whyItMatters ?? null,
    degraded: trigger.impactContext?.degraded ?? trigger.status === 'degraded',
    inWatchlist: trigger.impactContext?.affected?.inWatchlist ?? false,
    inPortfolio: trigger.impactContext?.affected?.inPortfolio ?? false,
    source: trigger.dataSource,
  };
}

export const eventCalendarApi = {
  async getCalendar(
    query: EventCalendarQuery,
    options: { signal?: AbortSignal } = {},
  ): Promise<EventCalendarResponse> {
    const triggers: Trigger[] = [];
    const partialErrors: EventCalendarResponse['partialErrors'] = [];
    let total = 0;
    let cursor: string | undefined;

    for (let index = 0; index < MAX_PAGES; index += 1) {
      try {
        const response = await apiClient.get<Record<string, unknown>>('/api/v1/alerts/triggers', {
          params: {
            alert_type: 'corporate_event',
            page: cursor ? undefined : index + 1,
            page_size: PAGE_SIZE,
            cursor,
          },
          signal: options.signal,
        });
        const page = parseCamelCasePayload<z.infer<typeof triggerPageSchema>>(
          response.data,
          triggerPageSchema,
          'CorporateEventTriggerPage',
          'alerts',
        );
        total = page.total;
        triggers.push(...page.items);
        cursor = page.nextCursor ?? undefined;
        if (page.items.length === 0 || triggers.length >= total) break;
      } catch (error) {
        if (options.signal?.aborted || triggers.length === 0) throw error;
        partialErrors.push('event_calendar_page_unavailable');
        break;
      }
    }

    if (triggers.length < total && partialErrors.length === 0) {
      partialErrors.push('event_calendar_result_limit_reached');
    }

    const events = triggers
      .map(toCalendarEvent)
      .filter((event): event is CalendarEventItem => event !== null)
      .filter((event) => event.eventDate >= query.dateFrom && event.eventDate <= query.dateTo)
      .sort((left, right) => left.eventDate.localeCompare(right.eventDate) || left.eventId - right.eventId);

    return {
      events,
      loadedCount: triggers.length,
      total,
      partialErrors,
    };
  },
};
