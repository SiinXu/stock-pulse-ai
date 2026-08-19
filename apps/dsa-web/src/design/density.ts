// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Shared density token catalog for apps/dsa-web (#877 D5).
 *
 * CSS custom properties and utility classes in `src/index.css` are the runtime
 * authority. This module is the named inventory used by documentation, the
 * density contract guard, and the density adoption ratchet — do not invent
 * parallel spacing scales in pages, and do not revert density-aware owners to
 * fixed `p-*` / `gap-*` without a listed fixed-geometry exemption.
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

/** Spacing utilities only — elevation shadows are a separate overlay contract. */
export const DENSITY_STRUCTURAL_UTILITY_CLASSES = DENSITY_UTILITY_CLASSES.filter((name) => (
  name.startsWith('density-')
));

/** Spacing custom properties only — elevation aliases stay in `DENSITY_CSS_VARS`. */
export const DENSITY_STRUCTURAL_CSS_VARS = DENSITY_CSS_VARS.filter((name) => (
  name.startsWith('--density-')
));

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

/**
 * Shared components that already consume density tokens and must not drop
 * back to Tailwind/fixed spacing for structural pad/gap. Pages and other
 * modules join this set automatically once they use a density token.
 */
export const DENSITY_REQUIRED_OWNERS = [
  'Surface.tsx',
  'PageHeader.tsx',
  'Toolbar.tsx',
  'Section.tsx',
  'Modal.tsx',
  'Drawer.tsx',
  'Sheet.tsx',
  'ConfirmDialog.tsx',
] as const;

export type DensityFixedGeometryExemption = {
  /** Guard path as reported by the production TypeScript inventory. */
  file: string;
  /** Exact class token, `style:prop:value`, or `computed:` / `alias:` token. */
  token: string;
  /** Why this is geometry or component-owned density, not surface-scale debt. */
  reason: string;
  /** Allowed occurrences of `token` in `file`. Shrink when usages disappear. */
  count: number;
  /** Omit for permanent geometry (safe-area, 44px hit target, table cell maps). */
  removeWhen?: string;
};

/**
 * Explicit exemptions for spacing that is genuinely fixed geometry.
 *
 * Do not dump leftover `gap-4` / `p-4` debt here — that belongs in
 * `densityAdoptionBaseline.json` as shrink-only inventory. Reviewers should
 * reject exemptions that exist only to green CI. DataTable virtualization
 * spacers (#1377) use `p-0` / `padding: 0`; the scanner treats zero as a
 * reset, not density debt, so they stay off this list.
 */
export const DENSITY_FIXED_GEOMETRY_EXEMPTIONS: readonly DensityFixedGeometryExemption[] = [
  {
    file: '../common/Drawer.tsx',
    token: 'pb-[calc(0.75rem+env(safe-area-inset-bottom))]',
    reason: 'Overlay footer must clear the iOS home-indicator inset; this is device geometry, not a density scale step.',
    count: 1,
  },
  {
    file: '../common/Modal.tsx',
    token: 'pb-[calc(0.75rem+env(safe-area-inset-bottom))]',
    reason: 'Overlay footer must clear the iOS home-indicator inset; this is device geometry, not a density scale step.',
    count: 1,
  },
  {
    file: '../common/Sheet.tsx',
    token: 'pb-[calc(0.75rem+env(safe-area-inset-bottom))]',
    reason: 'Overlay footer must clear the iOS home-indicator inset; this is device geometry, not a density scale step.',
    count: 1,
  },
  {
    file: '../common/DataTable.tsx',
    token: 'px-3',
    reason: 'DataTable compact/default cell padding is the table density contract (`DataTableDensity`), not page stack/pad.',
    count: 1,
  },
  {
    file: '../common/DataTable.tsx',
    token: 'py-2',
    reason: 'DataTable compact/default cell padding is the table density contract (`DataTableDensity`), not page stack/pad.',
    count: 1,
  },
  {
    file: '../common/DataTable.tsx',
    token: 'px-4',
    reason: 'DataTable default cell and visible-caption padding is table chrome owned by `data-density`, not a surface token revert.',
    count: 2,
  },
  {
    file: '../common/DataTable.tsx',
    token: 'py-3',
    reason: 'DataTable default cell and visible-caption padding is table chrome owned by `data-density`, not a surface token revert.',
    count: 2,
  },
];
