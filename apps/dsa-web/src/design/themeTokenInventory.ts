// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { DENSITY_STRUCTURAL_CSS_VARS } from './density';

/**
 * Frozen unique custom-property names defined by `src/index.css`.
 * Classification lives in `classifyThemeToken()` — this list is the
 * shrink-or-explicit-add ratchet, not a second token system.
 *
 * Spacing scale names come from `DENSITY_STRUCTURAL_CSS_VARS` so this
 * file does not repeat those literals. Repeating them here is measured
 * by the density adoption ratchet as a new consumer
 * (`new-density-aware-file`, densityTokenCount=18). T24 does not change
 * that scanner; WAIT_FOR density integration if catalogs other than
 * `density.ts` should be classified as non-consumers.
 *
 * Update workflow: add or remove a name here only in the same PR that
 * changes the `index.css` definition. New page-scoped names are rejected
 * even if listed. See `src/design/theme.ts`.
 */

const THEME_NON_SPACING_DEFINED_TOKEN_NAMES = [
  '--accent',
  '--accent-foreground',
  '--autocomplete-hover-bg',
  '--background',
  '--bg-base',
  '--bg-card',
  '--bg-elevated',
  '--bg-hover',
  '--bg-subtle',
  '--bg-subtle-raw',
  '--border',
  '--border-accent',
  '--border-default',
  '--border-dim',
  '--border-dim-raw',
  '--border-hover',
  '--border-selected',
  '--border-subtle',
  '--border-subtle-hover',
  '--border-subtle-raw',
  '--card',
  '--card-foreground',
  '--color-amber-400',
  '--color-danger',
  '--color-danger-alert-bg',
  '--color-danger-alert-border',
  '--color-danger-alert-text',
  '--color-emerald-400',
  '--color-red-400',
  '--color-success',
  '--color-warning',
  '--danger',
  '--destructive',
  '--destructive-foreground',
  '--elevated',
  '--foreground',
  '--gradient-primary',
  '--home-accent-bg',
  '--home-accent-bg-hover',
  '--home-accent-border',
  '--home-accent-border-hover',
  '--home-accent-text',
  '--home-cool-surface',
  '--home-cool-surface-strong',
  '--home-divider-border',
  '--home-hero-border',
  '--home-hero-gradient-end',
  '--home-hero-gradient-mid',
  '--home-hero-gradient-start',
  '--home-hero-shadow',
  '--home-history-item-bg',
  '--home-history-item-hover-bg',
  '--home-history-item-selected-bg',
  '--home-insight-surface',
  '--home-insight-tone',
  '--home-mobile-overlay-bg',
  '--home-panel-border',
  '--home-panel-border-hover',
  '--home-panel-border-selected',
  '--home-panel-gradient-end',
  '--home-panel-gradient-mid',
  '--home-panel-gradient-start',
  '--home-panel-selected-shadow',
  '--home-panel-shadow',
  '--home-panel-shadow-hover',
  '--home-panel-subtle-bg',
  '--home-panel-subtle-bg-hover',
  '--home-price-down',
  '--home-price-up',
  '--home-rail-bg',
  '--home-rail-border',
  '--home-rail-shadow',
  '--home-secondary-accent-text',
  '--home-shadow-deep',
  '--home-shadow-neutral',
  '--home-state-icon-muted',
  '--home-surface-button-bg',
  '--home-surface-button-bg-hover',
  '--home-surface-button-border',
  '--home-surface-button-border-hover',
  '--hover',
  '--input',
  '--input-surface-bg',
  '--input-surface-border',
  '--input-surface-border-focus',
  '--input-surface-border-hover',
  '--input-surface-focus-ring',
  '--mask-opaque',
  '--muted',
  '--muted-foreground',
  '--muted-text',
  '--nav-active-bg',
  '--nav-active-border',
  '--nav-active-shadow',
  '--nav-badge-bg',
  '--nav-brand-shadow',
  '--nav-hover-bg',
  '--nav-icon-active',
  '--nav-indicator-bg',
  '--nav-indicator-shadow',
  '--nav-indicator-width',
  '--nav-item-height',
  '--nav-item-padding-x',
  '--neutral-black',
  '--neutral-white',
  '--overlay-hover',
  '--overlay-selected',
  '--overlay-sheet-footer-toast-offset',
  '--page-drawer-overlay-bg',
  '--popover',
  '--popover-foreground',
  '--price-down',
  '--price-green',
  '--price-green-hsl',
  '--price-red',
  '--price-red-hsl',
  '--price-up',
  '--primary',
  '--primary-foreground',
  '--radius',
  '--radius-dot',
  '--report-strategy-buy',
  '--report-strategy-secondary',
  '--report-strategy-stop',
  '--report-strategy-take',
  '--report-strategy-tone',
  '--ring',
  '--secondary',
  '--secondary-foreground',
  '--secondary-text',
  '--shadow-elevation-overlay',
  '--shadow-elevation-popper',
  '--shadow-soft-card',
  '--shadow-soft-card-strong',
  '--shell-sidebar-border',
  '--success',
  '--surface-1',
  '--surface-2',
  '--surface-3',
  '--text-muted-text',
  '--text-primary',
  '--text-secondary-text',
  '--warning',
] as const;

export const THEME_DEFINED_TOKEN_NAMES: readonly string[] = [
  ...THEME_NON_SPACING_DEFINED_TOKEN_NAMES,
  ...DENSITY_STRUCTURAL_CSS_VARS,
].slice().sort((left, right) => left.localeCompare(right));

export type ThemeDefinedTokenName = (typeof THEME_NON_SPACING_DEFINED_TOKEN_NAMES)[number]
  | (typeof DENSITY_STRUCTURAL_CSS_VARS)[number];

/**
 * Hard ceiling for page-scoped leftovers. Never raise this to absorb a new
 * `--home-*` / `--settings-*` / `--chat-*` / `--backtest-*` / `--portfolio-*`
 * name. Shrink only when a Phase 2 domain collapse deletes a leftover.
 * `--login-*`, `--backtest-*`, `--portfolio-*`, `--chat-*`, `--settings-*`,
 * `--home-action-*`, and `--home-prose-*` reached zero; leftover title-accent
 * is also collapsed. Unused `--home-loading-ring-track` and
 * `--home-loading-ring-head` wrappers are deleted with no replacement.
 * Action/prose families consume Layer 1 plus use-site
 * alpha; title-accent inlines Layer 1 `--foreground` with no alpha.
 * Do not reintroduce those prefixes, the action/prose/title-accent
 * leftovers, or the unused loading-ring wrappers. Remaining leftover
 * `--home-*` names stay page-scoped. `home` and `settings` stay in
 * `THEME_PAGE_SCOPED_PREFIXES`.
 */
export const THEME_PAGE_SCOPED_TOKEN_CEILING = 41;

export const DESKTOP_CHROME_DEFINED_TOKENS = {
  assistant: [
    '--accent',
    '--accent-hover',
    '--bg',
    '--blue',
    '--blue-hover',
    '--border',
    '--danger',
    '--danger-bg',
    '--muted',
    '--ready',
    '--shadow',
    '--starting',
    '--surface',
    '--surface-strong',
    '--text',
  ],
  loading: [
    '--accent',
    '--bg',
    '--bg-secondary',
    '--danger-bg',
    '--danger-border',
    '--danger-text',
    '--muted',
    '--panel',
    '--text',
  ],
} as const;

