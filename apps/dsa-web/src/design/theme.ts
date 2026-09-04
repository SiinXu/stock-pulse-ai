// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Theme Contract v1 catalog for apps/dsa-web (Issues #162 / #880 / #1300).
 *
 * CSS custom properties in `src/index.css` are the runtime authority.
 * This module is the named inventory used by documentation, theme packs,
 * and the theme contract / token-freeze guards — extend the existing
 * design-token system (same ownership model as density tokens); do not
 * invent a parallel palette. Phase 0 freezes the current name set; it
 * does not delete page-scoped leftovers or bless them as Layer 1.
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

/**
 * Phase 0 token-contract freeze (issue #1300).
 *
 * `src/index.css` remains the only Web runtime token owner. This catalog
 * classifies every defined custom property so new names cannot land as
 * ungoverned tokens or page-scoped bypasses. It does not invent a second
 * palette and does not promote page-scoped leftovers to Layer 1.
 *
 * Intentional addition workflow:
 * 1. Prefer an existing Layer 1 token plus use-site opacity.
 * 2. A new public color/surface token must be added to `THEME_LAYER1_CSS_VARS`
 *    (or Layer 0 only for market paint), defined on `:root` and `.dark`,
 *    and appended to `THEME_DEFINED_TOKEN_NAMES`.
 * 3. Domain geometry may use a domain name (`--nav-*`, `--report-*`,
 *    `--input-surface-*`) — never a page prefix.
 * 4. Do not add `--home-*` / `--settings-*` / `--login-*` / `--chat-*` /
 *    `--backtest-*` / `--portfolio-*` names. `--settings-*` is now zero;
 *    `--home-action-*`, `--home-prose-*`, and leftover title-accent are
 *    collapsed. Keep the prefix ban. Collapse remaining leftover `--home-*`
 *    in T25/T40.
 * 5. Do not classify dead, duplicate, or undefined references as Layer 1.
 *    Record leftover undefined `var(--*)` sites in the freeze guard's
 *    shrink-only debt list (`themeTokenFreeze.ts`) and shrink that list only.
 * 6. Desktop chrome (`apps/dsa-desktop/renderer/*.html`) is a separate
 *    inventory. Do not copy those names into the Web Layer 1 set.
 */
export const THEME_PAGE_SCOPED_PREFIXES = [
  'home',
  'settings',
  'login',
  'chat',
  'backtest',
  'portfolio',
] as const;

export type ThemePageScopedPrefix = (typeof THEME_PAGE_SCOPED_PREFIXES)[number];

export const THEME_TOKEN_CLASSES = [
  'layer0',
  'layer1',
  'layer1-derived',
  'density',
  'elevation',
  'domain',
  'compat-alias',
  'legacy-alias',
  'page-scoped-debt',
  'ungoverned',
] as const;

export type ThemeTokenClass = (typeof THEME_TOKEN_CLASSES)[number];

/** Classes that may grow when a reviewer accepts a new token. */
export const THEME_ADDABLE_TOKEN_CLASSES = [
  'layer0',
  'layer1',
  'layer1-derived',
  'density',
  'elevation',
  'domain',
] as const;

export const THEME_LAYER0_SUPPORT_VARS = [
  '--price-red-hsl',
  '--price-green-hsl',
] as const;

export const THEME_COMPAT_ALIAS_VARS = [
  '--success',
  '--warning',
  '--danger',
  '--color-emerald-400',
  '--color-red-400',
  '--color-amber-400',
] as const;

export const THEME_DOMAIN_EXACT_VARS = [
  '--autocomplete-hover-bg',
  '--gradient-primary',
  '--mask-opaque',
  '--neutral-black',
  '--neutral-white',
  '--overlay-sheet-footer-toast-offset',
  '--page-drawer-overlay-bg',
  '--radius-dot',
  '--shell-sidebar-border',
] as const;

export const DESKTOP_CHROME_TOKEN_OWNERS = [
  '../dsa-desktop/renderer/assistant.html',
  '../dsa-desktop/renderer/loading.html',
] as const;

export function isThemePageScopedToken(token: string): boolean {
  return THEME_PAGE_SCOPED_PREFIXES.some((prefix) => token.startsWith(`--${prefix}-`));
}

export function classifyThemeToken(token: string): ThemeTokenClass {
  if (
    (THEME_LAYER0_CSS_VARS as readonly string[]).includes(token)
    || (THEME_LAYER0_SUPPORT_VARS as readonly string[]).includes(token)
  ) {
    return 'layer0';
  }
  if ((THEME_LEGACY_PRICE_ALIASES as readonly string[]).includes(token)) {
    return 'legacy-alias';
  }
  if ((THEME_LAYER1_CSS_VARS as readonly string[]).includes(token)) {
    return 'layer1';
  }
  if ((THEME_COMPAT_ALIAS_VARS as readonly string[]).includes(token)) {
    return 'compat-alias';
  }
  if (token.startsWith('--density-')) return 'density';
  if (token.startsWith('--shadow-')) return 'elevation';
  if ((THEME_DOMAIN_EXACT_VARS as readonly string[]).includes(token)) {
    return 'domain';
  }
  if (isThemePageScopedToken(token)) return 'page-scoped-debt';
  if (
    token.startsWith('--nav-')
    || token.startsWith('--report-')
    || token.startsWith('--input-surface-')
  ) {
    return 'domain';
  }
  if (token.startsWith('--color-danger-alert-')) return 'layer1-derived';
  if (
    token.startsWith('--bg-')
    || token.startsWith('--border-')
    || token.startsWith('--text-')
    || token.startsWith('--surface-')
    || token.startsWith('--overlay-')
  ) {
    return 'layer1-derived';
  }
  return 'ungoverned';
}

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
