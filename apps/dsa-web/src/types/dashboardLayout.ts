// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Browser-profile dashboard layout preference for the Home customizable board.
 * Safe presets keep every known widget id present exactly once and enforce a
 * minimum visible count so the board cannot be dragged into an unusable state.
 */

export const DASHBOARD_LAYOUT_SCHEMA_VERSION = 1 as const;

export const DASHBOARD_WIDGET_IDS = [
  'watchlist',
  'portfolio_health',
  'alerts',
  'recent_reports',
] as const;

export type DashboardWidgetId = (typeof DASHBOARD_WIDGET_IDS)[number];

export type DashboardWidgetPreference = {
  id: DashboardWidgetId;
  visible: boolean;
};

export type DashboardLayoutPreference = {
  schemaVersion: typeof DASHBOARD_LAYOUT_SCHEMA_VERSION;
  revision: number;
  widgets: DashboardWidgetPreference[];
};

/** At least one widget must stay visible so Home never renders an empty board. */
export const DASHBOARD_LAYOUT_MIN_VISIBLE = 1;

export const DEFAULT_DASHBOARD_LAYOUT: DashboardLayoutPreference = {
  schemaVersion: DASHBOARD_LAYOUT_SCHEMA_VERSION,
  revision: 0,
  widgets: [
    { id: 'watchlist', visible: true },
    { id: 'portfolio_health', visible: true },
    { id: 'alerts', visible: true },
    { id: 'recent_reports', visible: true },
  ],
};

export const DASHBOARD_LAYOUT_STORAGE_KEY = 'dsa.home.dashboardLayout.v1';

const KNOWN_IDS = new Set<string>(DASHBOARD_WIDGET_IDS);

function isWidgetId(value: unknown): value is DashboardWidgetId {
  return typeof value === 'string' && KNOWN_IDS.has(value);
}

/**
 * Normalize any partial/legacy payload into a safe full layout:
 * - every known id appears exactly once
 * - unknown ids are dropped
 * - missing ids are appended with default visibility
 * - visible count is raised to MIN_VISIBLE when needed
 * - revision is a non-negative finite integer
 */
export function normalizeDashboardLayout(raw: unknown): DashboardLayoutPreference {
  const defaultsById = new Map(
    DEFAULT_DASHBOARD_LAYOUT.widgets.map((widget) => [widget.id, widget.visible]),
  );
  const seen = new Set<DashboardWidgetId>();
  const ordered: DashboardWidgetPreference[] = [];

  const sourceWidgets = Array.isArray((raw as { widgets?: unknown })?.widgets)
    ? (raw as { widgets: unknown[] }).widgets
    : [];

  for (const entry of sourceWidgets) {
    if (!entry || typeof entry !== 'object') continue;
    const id = (entry as { id?: unknown }).id;
    if (!isWidgetId(id) || seen.has(id)) continue;
    seen.add(id);
    ordered.push({
      id,
      visible: (entry as { visible?: unknown }).visible !== false,
    });
  }

  for (const id of DASHBOARD_WIDGET_IDS) {
    if (seen.has(id)) continue;
    ordered.push({ id, visible: defaultsById.get(id) ?? true });
  }

  let visibleCount = ordered.filter((widget) => widget.visible).length;
  if (visibleCount < DASHBOARD_LAYOUT_MIN_VISIBLE) {
    for (const widget of ordered) {
      if (widget.visible) continue;
      widget.visible = true;
      visibleCount += 1;
      if (visibleCount >= DASHBOARD_LAYOUT_MIN_VISIBLE) break;
    }
  }

  const revisionRaw = (raw as { revision?: unknown })?.revision;
  const revision = typeof revisionRaw === 'number'
    && Number.isFinite(revisionRaw)
    && revisionRaw >= 0
    ? Math.floor(revisionRaw)
    : 0;

  return {
    schemaVersion: DASHBOARD_LAYOUT_SCHEMA_VERSION,
    revision,
    widgets: ordered,
  };
}

export function visibleDashboardWidgets(
  layout: DashboardLayoutPreference,
): DashboardWidgetPreference[] {
  return layout.widgets.filter((widget) => widget.visible);
}

export function reorderDashboardWidgets(
  layout: DashboardLayoutPreference,
  orderedIds: readonly DashboardWidgetId[],
): DashboardLayoutPreference | null {
  if (orderedIds.length !== DASHBOARD_WIDGET_IDS.length) return null;
  const unique = new Set(orderedIds);
  if (unique.size !== DASHBOARD_WIDGET_IDS.length) return null;
  for (const id of DASHBOARD_WIDGET_IDS) {
    if (!unique.has(id)) return null;
  }
  const byId = new Map(layout.widgets.map((widget) => [widget.id, widget]));
  return {
    ...layout,
    widgets: orderedIds.map((id) => {
      const existing = byId.get(id);
      return existing ?? { id, visible: true };
    }),
  };
}

/**
 * Toggle visibility while respecting MIN_VISIBLE. Returns null when the change
 * would hide the last remaining visible widget.
 */
export function setDashboardWidgetVisible(
  layout: DashboardLayoutPreference,
  id: DashboardWidgetId,
  visible: boolean,
): DashboardLayoutPreference | null {
  const current = layout.widgets.find((widget) => widget.id === id);
  if (!current || current.visible === visible) {
    return {
      ...layout,
      widgets: layout.widgets.map((widget) => (
        widget.id === id ? { ...widget, visible } : widget
      )),
    };
  }
  if (!visible) {
    const visibleCount = layout.widgets.filter((widget) => widget.visible).length;
    if (visibleCount <= DASHBOARD_LAYOUT_MIN_VISIBLE) return null;
  }
  return {
    ...layout,
    widgets: layout.widgets.map((widget) => (
      widget.id === id ? { ...widget, visible } : widget
    )),
  };
}

export function movedIds<T>(items: readonly T[], from: number, to: number): T[] {
  if (from < 0 || to < 0 || from === to || from >= items.length || to >= items.length) {
    return [...items];
  }
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}
