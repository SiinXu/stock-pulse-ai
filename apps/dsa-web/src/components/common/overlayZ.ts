// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { CSSProperties } from 'react';
// Single source of truth for overlay stacking order. Higher sits closer to the
// user. Shared overlays read this scale through OVERLAY_Z or getOverlayStyle;
// page-owned compatibility surfaces migrate in their target Batch.
//
//   pageDrawer   40   Home/Chat mobile history sidebars
//   drawer       50   shared Drawer default
//   modal        50   centered Modal
//   runFlowDrawer 80  Home run-flow drawer
//   navigationDrawer 90 Shell mobile navigation
//   reportDrawer 100  report markdown drawer
//   dropdown     100  Select / autocomplete popovers
//   tooltip      120  Tooltip / menus
//   settingsModal 140 Settings help modal
//   toast        160  global transient feedback
//   confirm      200  ConfirmDialog — always above every dismissible surface
export const OVERLAY_Z = {
  pageDrawer: 40,
  drawer: 50,
  modal: 50,
  runFlowDrawer: 80,
  navigationDrawer: 90,
  reportDrawer: 100,
  dropdown: 100,
  tooltip: 120,
  settingsModal: 140,
  toast: 160,
  confirm: 200,
} as const;

export type OverlayLayer = keyof typeof OVERLAY_Z;

export function getOverlayStyle(
  layer: OverlayLayer,
  style?: CSSProperties,
): CSSProperties {
  return { ...style, zIndex: OVERLAY_Z[layer] };
}
