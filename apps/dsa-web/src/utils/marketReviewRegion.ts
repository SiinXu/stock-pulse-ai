// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { MarketReviewRegion } from '../types/analysis';
import type { UiLanguage } from '../i18n/uiLanguages';
import type { UiTextKey } from '../i18n/uiText';
import { formatUiList } from './uiLocale';

export type { MarketReviewRegion };

export const MARKET_REVIEW_REGION_ORDER: readonly MarketReviewRegion[] = ['cn', 'hk', 'us', 'jp', 'kr'];

/** Stable UI-text keys for market-review region labels (shared by selector + runner). */
export const MARKET_REVIEW_REGION_UI_TEXT_KEYS = {
  cn: 'home.marketRegionCn',
  hk: 'home.marketRegionHk',
  us: 'home.marketRegionUs',
  jp: 'home.marketRegionJp',
  kr: 'home.marketRegionKr',
} as const satisfies Record<MarketReviewRegion, UiTextKey>;

const REGION_TOKEN_SET = new Set<string>(MARKET_REVIEW_REGION_ORDER);

export function isMarketReviewRegion(value: string): value is MarketReviewRegion {
  return REGION_TOKEN_SET.has(value);
}

export function serializeMarketReviewRegions(regions: readonly MarketReviewRegion[]): string {
  const ordered = MARKET_REVIEW_REGION_ORDER.filter((region) => regions.includes(region));
  return ordered.length === MARKET_REVIEW_REGION_ORDER.length ? 'both' : ordered.join(',');
}

/**
 * Parse a backend/canonical region token string (`cn`, `cn,hk`, `both`, …)
 * into ordered MarketReviewRegion values. Unknown tokens are dropped.
 */
export function parseMarketReviewRegionTokens(regionToken: string | null | undefined): MarketReviewRegion[] {
  if (!regionToken || !regionToken.trim()) {
    return [];
  }
  const trimmed = regionToken.trim();
  if (trimmed === 'both') {
    return [...MARKET_REVIEW_REGION_ORDER];
  }
  const seen = new Set<MarketReviewRegion>();
  for (const part of trimmed.split(',')) {
    const token = part.trim().toLowerCase();
    if (isMarketReviewRegion(token)) {
      seen.add(token);
    }
  }
  return MARKET_REVIEW_REGION_ORDER.filter((region) => seen.has(region));
}

/**
 * Format region codes as localized labels joined with a locale-appropriate list separator.
 * Falls back to the raw token when nothing can be resolved (unknown/empty).
 */
export function formatMarketReviewRegionLabels(
  regionToken: string | null | undefined,
  getLabel: (region: MarketReviewRegion) => string,
  language: UiLanguage,
): string {
  const regions = parseMarketReviewRegionTokens(regionToken);
  if (regions.length === 0) {
    return (regionToken ?? '').trim();
  }
  return formatUiList(regions.map(getLabel), language);
}

/**
 * Format an explicit region selection (not a backend token string) for display.
 */
export function formatMarketReviewRegionSelection(
  regions: readonly MarketReviewRegion[],
  getLabel: (region: MarketReviewRegion) => string,
  language: UiLanguage,
): string {
  if (regions.length === 0) {
    return '';
  }
  const ordered = MARKET_REVIEW_REGION_ORDER.filter((region) => regions.includes(region));
  return formatUiList(ordered.map(getLabel), language);
}
