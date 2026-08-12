// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it } from 'vitest';
import {
  DASHBOARD_LAYOUT_STORAGE_KEY,
  DASHBOARD_WIDGET_IDS,
  normalizeDashboardLayout,
} from '../../types/dashboardLayout';
import {
  readDashboardLayoutFromStorage,
  resetDashboardLayoutStoreForTests,
  useDashboardLayoutStore,
  writeDashboardLayoutToStorage,
} from '../dashboardLayoutStore';

describe('dashboardLayoutStore', () => {
  beforeEach(() => {
    window.localStorage.clear();
    resetDashboardLayoutStoreForTests();
  });

  it('hydrates from localStorage and reorders with revision CAS', () => {
    writeDashboardLayoutToStorage(normalizeDashboardLayout({
      revision: 2,
      widgets: [
        { id: 'alerts', visible: true },
        { id: 'watchlist', visible: true },
        { id: 'portfolio_health', visible: true },
        { id: 'recent_reports', visible: true },
      ],
    }));
    const store = useDashboardLayoutStore.getState();
    store.hydrate();
    expect(useDashboardLayoutStore.getState().layout.revision).toBe(2);

    const reordered = [...DASHBOARD_WIDGET_IDS].reverse() as typeof DASHBOARD_WIDGET_IDS[number][];
    const ok = useDashboardLayoutStore.getState().reorder(reordered, 2);
    expect(ok.ok).toBe(true);
    expect(useDashboardLayoutStore.getState().layout.revision).toBe(3);
    expect(useDashboardLayoutStore.getState().layout.widgets.map((w) => w.id)).toEqual(reordered);

    const conflict = useDashboardLayoutStore.getState().reorder(DASHBOARD_WIDGET_IDS, 2);
    expect(conflict.ok).toBe(false);
    if (!conflict.ok) expect(conflict.reason).toBe('revision_conflict');
  });

  it('blocks hiding the last visible widget and persists visibility toggles', () => {
    useDashboardLayoutStore.getState().hydrate();
    const revision = useDashboardLayoutStore.getState().layout.revision;
    // Hide three widgets, leave watchlist
    for (const id of ['portfolio_health', 'alerts', 'recent_reports'] as const) {
      const current = useDashboardLayoutStore.getState().layout.revision;
      const result = useDashboardLayoutStore.getState().setVisible(id, false, current);
      expect(result.ok).toBe(true);
    }
    const last = useDashboardLayoutStore.getState().layout.revision;
    const blocked = useDashboardLayoutStore.getState().setVisible('watchlist', false, last);
    expect(blocked.ok).toBe(false);
    if (!blocked.ok) expect(blocked.reason).toBe('invalid');

    const stored = readDashboardLayoutFromStorage();
    expect(stored.widgets.find((w) => w.id === 'watchlist')?.visible).toBe(true);
    expect(window.localStorage.getItem(DASHBOARD_LAYOUT_STORAGE_KEY)).toContain('watchlist');
    void revision;
  });

  it('resets to the default ordered preset', () => {
    useDashboardLayoutStore.getState().hydrate();
    const first = useDashboardLayoutStore.getState().setVisible('alerts', false, 0);
    expect(first.ok).toBe(true);
    const reset = useDashboardLayoutStore.getState().reset(useDashboardLayoutStore.getState().layout.revision);
    expect(reset.ok).toBe(true);
    expect(useDashboardLayoutStore.getState().layout.widgets.every((w) => w.visible)).toBe(true);
    expect(useDashboardLayoutStore.getState().layout.widgets.map((w) => w.id)).toEqual([...DASHBOARD_WIDGET_IDS]);
  });
});
