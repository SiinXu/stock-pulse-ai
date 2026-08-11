// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
export const CORPORATE_EVENT_CATEGORIES = ['earnings','shareholder','mna','regulatory','analyst'] as const;
export type CorporateEventCategory = (typeof CORPORATE_EVENT_CATEGORIES)[number];
export const MAJOR_EVENT_CATEGORIES: ReadonlySet<CorporateEventCategory> = new Set(['mna','regulatory']);
export type EventAlertImpactGrade = 'major' | 'routine';
export interface EventAlertAffected {
  symbol?: string | null; inWatchlist?: boolean | null; inPortfolio?: boolean | null;
  portfolioAccounts?: unknown[] | null; quantity?: number | null; weightPct?: number | null;
  marketValueBase?: number | null; watchlistError?: string | null; portfolioError?: string | null;
}
export interface EventAlertImpactContext {
  degraded?: boolean | null; whatHappened?: string | null; whyItMatters?: string | null;
  eventCategory?: string | null; eventCategories?: string[] | null; affected?: EventAlertAffected | null;
  relatedAnalysis?: string | null; matchedCount?: number | null; sourceItemId?: number | string | null;
  sourceName?: string | null; sourceUrl?: string | null;
}
export interface EventAlertEventContext {
  whatHappened?: string | null; whyItMatters?: string | null; eventCategory?: string | null;
  eventCategories?: string[] | null; matchedCount?: number | null; sourceItemId?: number | string | null;
  sourceName?: string | null; sourceUrl?: string | null; matchedItems?: unknown[] | null;
}
export interface EventAlertDisplayItem {
  id: number; ruleId?: number | null; target: string; status: string; reason?: string | null;
  dataSource?: string | null; dataTimestamp?: string | null; triggeredAt?: string | null;
  observedValue?: number | null; threshold?: number | null; whatHappened?: string | null;
  whyItMatters?: string | null; eventCategory?: string | null; impactGrade: EventAlertImpactGrade;
  degraded: boolean; inWatchlist: boolean; inPortfolio: boolean; weightPct?: number | null;
  relatedAnalysis?: string | null; matchedCount?: number | null;
  impactContext?: EventAlertImpactContext | null; eventContext?: EventAlertEventContext | null;
}
