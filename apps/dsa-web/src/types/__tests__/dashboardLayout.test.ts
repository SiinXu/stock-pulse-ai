// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  DASHBOARD_WIDGET_IDS,
  DEFAULT_DASHBOARD_LAYOUT,
  normalizeDashboardLayout,
  reorderDashboardWidgets,
  setDashboardWidgetVisible,
  visibleDashboardWidgets,
} from '../dashboardLayout';

describe('dashboardLayout model', () => {
  it('normalizes missing, unknown, and duplicate widget ids into a full safe preset', () => {
    const layout = normalizeDashboardLayout({
      revision: 3.7,
      widgets: [
        { id: 'alerts', visible: false },
        { id: 'unknown_widget', visible: true },
        { id: 'alerts', visible: true },
        { id: 'watchlist', visible: true },
      ],
    });
    expect(layout.revision).toBe(3);
    expect(layout.widgets.map((widget) => widget.id)).toEqual([
      'alerts',
      'watchlist',
      'portfolio_health',
      'recent_reports',
    ]);
    expect(layout.widgets.find((widget) => widget.id === 'alerts')?.visible).toBe(false);
    expect(layout.widgets.find((widget) => widget.id === 'watchlist')?.visible).toBe(true);
    expect(layout.widgets.find((widget) => widget.id === 'portfolio_health')?.visible).toBe(true);
  });

  it('forces at least one visible widget when every entry is hidden', () => {
    const layout = normalizeDashboardLayout({
      widgets: DASHBOARD_WIDGET_IDS.map((id) => ({ id, visible: false })),
    });
    expect(visibleDashboardWidgets(layout).length).toBeGreaterThanOrEqual(1);
  });

  it('rejects incomplete reorder payloads and hide-last-visible attempts', () => {
    const base = normalizeDashboardLayout(DEFAULT_DASHBOARD_LAYOUT);
    expect(reorderDashboardWidgets(base, ['watchlist', 'alerts'] as never)).toBeNull();
    const onlyWatchlist = {
      ...base,
      widgets: base.widgets.map((widget) => ({
        ...widget,
        visible: widget.id === 'watchlist',
      })),
    };
    expect(setDashboardWidgetVisible(onlyWatchlist, 'watchlist', false)).toBeNull();
    const hidden = setDashboardWidgetVisible(base, 'alerts', false);
    expect(hidden?.widgets.find((widget) => widget.id === 'alerts')?.visible).toBe(false);
  });
});
