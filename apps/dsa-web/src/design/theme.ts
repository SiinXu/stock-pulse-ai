// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Theme Contract v1 catalog for apps/dsa-web (Issues #162 / #880).
 *
 * CSS custom properties in `src/index.css` are the runtime authority.
 * This module is the named inventory used by documentation, theme packs,
 * and the theme contract guard — extend the existing design-token system
 * (same ownership model as density tokens); do not invent a parallel palette.
 */

export const THEME_PACK_IDS = ['classic', 'slate'] as const;
export type ThemePackId = (typeof THEME_PACK_IDS)[number];

/**
 * Market price-direction convention via `data-price-direction`.
 * - cn: A-share / HK default — red up, green down (`red_up`)
 * - us: US-style — green up, red down (`green_up`)
 */
export const PRICE_DIRECTION_IDS = ['cn', 'us'] as const;
export type PriceDirectionId = (typeof PRICE_DIRECTION_IDS)[number];

export const THEME_STORAGE_KEYS = {
  pack: 'theme-pack',
  priceDirection: 'price-direction',
  mode: 'theme',
} as const;

export const THEME_LAYER0_CSS_VARS = [
  '--price-red',
  '--price-green',
  '--price-up',
  '--price-down',
] as const;

export const THEME_LAYER1_CSS_VARS = [
  '--background',
  '--foreground',
  '--card',
  '--card-foreground',
  '--popover',
  '--popover-foreground',
  '--primary',
  '--primary-foreground',
  '--secondary',
  '--secondary-foreground',
  '--muted',
  '--muted-foreground',
  '--accent',
  '--accent-foreground',
  '--destructive',
  '--destructive-foreground',
  '--border',
  '--input',
  '--ring',
  '--elevated',
  '--hover',
  '--secondary-text',
  '--muted-text',
  '--color-success',
  '--color-warning',
  '--color-danger',
  '--radius',
] as const;

export const THEME_CORE_CSS_VARS = [
  ...THEME_LAYER0_CSS_VARS,
  ...THEME_LAYER1_CSS_VARS,
] as const;

export const THEME_LEGACY_PRICE_ALIASES = [
  '--home-price-up',
  '--home-price-down',
] as const;

export const THEME_PACK_FORBIDDEN_VARS = [
  ...THEME_LAYER0_CSS_VARS,
  ...THEME_LEGACY_PRICE_ALIASES,
] as const;

export const THEME_DOCUMENT_ATTRS = {
  pack: 'data-theme-pack',
  priceDirection: 'data-price-direction',
} as const;

export function isThemePackId(value: string | null | undefined): value is ThemePackId {
  return value === 'classic' || value === 'slate';
}

export function isPriceDirectionId(
  value: string | null | undefined,
): value is PriceDirectionId {
  return value === 'cn' || value === 'us';
}

export function priceDirectionFromChangeColorPref(
  pref: string | null | undefined,
): PriceDirectionId {
  const normalized = (pref ?? '').trim().toLowerCase().replace(/-/g, '_');
  if (normalized === 'green_up') return 'us';
  return 'cn';
}

export function changeColorPrefFromPriceDirection(
  direction: PriceDirectionId,
): 'red_up' | 'green_up' {
  return direction === 'us' ? 'green_up' : 'red_up';
}
