// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { AlertTriggerItem } from '../types/alerts';
import {
  CORPORATE_EVENT_CATEGORIES, MAJOR_EVENT_CATEGORIES,
  type CorporateEventCategory, type EventAlertAffected, type EventAlertDisplayItem,
  type EventAlertEventContext, type EventAlertImpactContext, type EventAlertImpactGrade,
} from '../types/eventAlerts';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function asOptionalString(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text ? text : null;
}
function asOptionalNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const num = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(num) ? num : null;
}
function asOptionalBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}
function parseJsonObject(value: unknown): Record<string, unknown> | null {
  if (isRecord(value)) return value;
  if (typeof value !== 'string') return null;
  const text = value.trim();
  if (!text.startsWith('{')) return null;
  try {
    const parsed: unknown = JSON.parse(text);
    return isRecord(parsed) ? parsed : null;
  } catch { return null; }
}
function normalizeAffected(raw: unknown): EventAlertAffected | null {
  if (!isRecord(raw)) return null;
  return {
    symbol: asOptionalString(raw.symbol),
    inWatchlist: asOptionalBoolean(raw.inWatchlist ?? raw.in_watchlist),
    inPortfolio: asOptionalBoolean(raw.inPortfolio ?? raw.in_portfolio),
    portfolioAccounts: Array.isArray(raw.portfolioAccounts ?? raw.portfolio_accounts) ? ((raw.portfolioAccounts ?? raw.portfolio_accounts) as unknown[]) : null,
    quantity: asOptionalNumber(raw.quantity),
    weightPct: asOptionalNumber(raw.weightPct ?? raw.weight_pct),
    marketValueBase: asOptionalNumber(raw.marketValueBase ?? raw.market_value_base),
    watchlistError: asOptionalString(raw.watchlistError ?? raw.watchlist_error),
    portfolioError: asOptionalString(raw.portfolioError ?? raw.portfolio_error),
  };
}
function normalizeImpactContext(raw: unknown): EventAlertImpactContext | null {
  if (!isRecord(raw)) return null;
  const eventCategories = raw.eventCategories ?? raw.event_categories;
  return {
    degraded: asOptionalBoolean(raw.degraded) ?? false,
    whatHappened: asOptionalString(raw.whatHappened ?? raw.what_happened),
    whyItMatters: asOptionalString(raw.whyItMatters ?? raw.why_it_matters),
    eventCategory: asOptionalString(raw.eventCategory ?? raw.event_category),
    eventCategories: Array.isArray(eventCategories) ? eventCategories.map(String) : null,
    affected: normalizeAffected(raw.affected),
    relatedAnalysis: asOptionalString(raw.relatedAnalysis ?? raw.related_analysis),
    matchedCount: asOptionalNumber(raw.matchedCount ?? raw.matched_count),
    sourceItemId: (raw.sourceItemId ?? raw.source_item_id) as number | string | null | undefined,
    sourceName: asOptionalString(raw.sourceName ?? raw.source_name),
    sourceUrl: asOptionalString(raw.sourceUrl ?? raw.source_url),
  };
}
function normalizeEventContext(raw: unknown): EventAlertEventContext | null {
  if (!isRecord(raw)) return null;
  const eventCategories = raw.eventCategories ?? raw.event_categories;
  return {
    whatHappened: asOptionalString(raw.whatHappened ?? raw.what_happened),
    whyItMatters: asOptionalString(raw.whyItMatters ?? raw.why_it_matters),
    eventCategory: asOptionalString(raw.eventCategory ?? raw.event_category),
    eventCategories: Array.isArray(eventCategories) ? eventCategories.map(String) : null,
    matchedCount: asOptionalNumber(raw.matchedCount ?? raw.matched_count),
    sourceItemId: (raw.sourceItemId ?? raw.source_item_id) as number | string | null | undefined,
    sourceName: asOptionalString(raw.sourceName ?? raw.source_name),
    sourceUrl: asOptionalString(raw.sourceUrl ?? raw.source_url),
    matchedItems: Array.isArray(raw.matchedItems ?? raw.matched_items) ? ((raw.matchedItems ?? raw.matched_items) as unknown[]) : null,
  };
}
export function resolveEventContextsFromTrigger(trigger: AlertTriggerItem) {
  const fromFieldsImpact = normalizeImpactContext(trigger.impactContext);
  const fromFieldsEvent = normalizeEventContext(trigger.eventContext);
  if (fromFieldsImpact || fromFieldsEvent) return { impactContext: fromFieldsImpact, eventContext: fromFieldsEvent };
  const parsed = parseJsonObject(trigger.diagnostics);
  if (!parsed) return { impactContext: null, eventContext: null };
  return {
    impactContext: normalizeImpactContext(parsed.impactContext ?? parsed.impact_context),
    eventContext: normalizeEventContext(parsed.eventContext ?? parsed.event_context),
  };
}
export function isCorporateEventCategory(value: string | null | undefined): value is CorporateEventCategory {
  return Boolean(value && (CORPORATE_EVENT_CATEGORIES as readonly string[]).includes(value));
}
export function gradeEventCategory(category: string | null | undefined): EventAlertImpactGrade {
  return isCorporateEventCategory(category) && MAJOR_EVENT_CATEGORIES.has(category) ? 'major' : 'routine';
}
export function isCorporateEventTrigger(trigger: AlertTriggerItem): boolean {
  if (trigger.dataSource === 'intelligence_items') return true;
  const { impactContext, eventContext } = resolveEventContextsFromTrigger(trigger);
  return Boolean(impactContext || eventContext);
}
export function toEventAlertDisplayItem(trigger: AlertTriggerItem): EventAlertDisplayItem {
  const { impactContext, eventContext } = resolveEventContextsFromTrigger(trigger);
  const category = impactContext?.eventCategory ?? eventContext?.eventCategory ?? null;
  const affected = impactContext?.affected ?? null;
  return {
    id: trigger.id, ruleId: trigger.ruleId, target: trigger.target, status: trigger.status,
    reason: trigger.reason, dataSource: trigger.dataSource, dataTimestamp: trigger.dataTimestamp,
    triggeredAt: trigger.triggeredAt, observedValue: trigger.observedValue, threshold: trigger.threshold,
    whatHappened: impactContext?.whatHappened ?? eventContext?.whatHappened ?? trigger.reason ?? null,
    whyItMatters: impactContext?.whyItMatters ?? eventContext?.whyItMatters ?? null,
    eventCategory: category, impactGrade: gradeEventCategory(category),
    degraded: Boolean(impactContext?.degraded), inWatchlist: Boolean(affected?.inWatchlist),
    inPortfolio: Boolean(affected?.inPortfolio), weightPct: affected?.weightPct ?? null,
    relatedAnalysis: impactContext?.relatedAnalysis ?? null,
    matchedCount: impactContext?.matchedCount ?? eventContext?.matchedCount ?? null,
    impactContext, eventContext,
  };
}
export function projectCorporateEventAlerts(triggers: AlertTriggerItem[]): EventAlertDisplayItem[] {
  return triggers.filter(isCorporateEventTrigger).map(toEventAlertDisplayItem).sort((a, b) => {
    if (a.impactGrade !== b.impactGrade) return a.impactGrade === 'major' ? -1 : 1;
    return (b.triggeredAt ? Date.parse(b.triggeredAt) : 0) - (a.triggeredAt ? Date.parse(a.triggeredAt) : 0);
  });
}
