// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { CSSProperties } from 'react';

/**
 * Authoritative stacking scale for application chrome and portalled UI.
 * Callers choose a semantic layer; numeric z-index values stay private here.
 */
export const OVERLAY_Z = {
  chrome: 40,
  dialog: 80,
  popover: 100,
  tooltip: 120,
  toast: 160,
  confirmation: 200,
} as const;

export type OverlayLayer = keyof typeof OVERLAY_Z;

export function getOverlayStyle(
  layer: OverlayLayer,
  style?: CSSProperties,
): CSSProperties {
  return { ...style, zIndex: OVERLAY_Z[layer] };
}
