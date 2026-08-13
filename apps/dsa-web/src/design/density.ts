// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Shared density token catalog for apps/dsa-web (#877 D5).
 *
 * CSS custom properties and utility classes in `src/index.css` are the runtime
 * authority. This module is the named inventory used by documentation and the
 * density contract guard — do not invent parallel spacing scales in pages.
 */

export const DENSITY_MODES = ['comfortable', 'compact'] as const;
export type DensityMode = (typeof DENSITY_MODES)[number];

/** Required CSS custom properties owned by `src/index.css`. */
export const DENSITY_CSS_VARS = [
  '--density-space-1',
  '--density-space-2',
  '--density-space-3',
  '--density-space-4',
  '--density-space-5',
  '--density-space-6',
  '--density-space-8',
  '--density-tool-gap',
  '--density-inline-gap',
  '--density-stack-gap',
  '--density-header-gap',
  '--density-section-gap',
  '--density-page-gap',
  '--density-surface-pad-sm',
  '--density-surface-pad-md',
  '--density-surface-pad-lg',
  '--density-overlay-pad-x',
  '--density-overlay-pad-y',
  '--shadow-elevation-overlay',
  '--shadow-elevation-popper',
] as const;

/** Structural utility classes owned by `src/index.css`. */
export const DENSITY_UTILITY_CLASSES = [
  'density-surface-pad-sm',
  'density-surface-pad-md',
  'density-surface-pad-lg',
  'density-gap-tools',
  'density-gap-inline',
  'density-gap-stack',
  'density-gap-header',
  'density-gap-section',
  'density-gap-page',
  'density-overlay-pad',
  'density-overlay-pad-x',
  'density-overlay-pad-y',
  'shadow-elevation-overlay',
  'shadow-elevation-popper',
] as const;

/** Surface padding prop → density utility class. */
export const SURFACE_PADDING_DENSITY_CLASS = {
  none: '',
  sm: 'density-surface-pad-sm',
  md: 'density-surface-pad-md',
  lg: 'density-surface-pad-lg',
} as const;

/**
 * Foundation overlay owners that must use semantic elevation tokens instead of
 * raw Tailwind shadow ladders (`shadow-2xl`, `shadow-lg`, …).
 */
export const OVERLAY_ELEVATION_OWNERS = [
  'Modal.tsx',
  'Drawer.tsx',
  'Sheet.tsx',
  'ConfirmDialog.tsx',
] as const;

/** Non-semantic elevation utilities banned on overlay foundation owners. */
export const NON_SEMANTIC_ELEVATION_SHADOWS = [
  'shadow-sm',
  'shadow-md',
  'shadow-lg',
  'shadow-xl',
  'shadow-2xl',
] as const;
