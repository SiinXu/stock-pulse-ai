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

  it('resets to the default ordered preset and persists it in localStorage', () => {
    useDashboardLayoutStore.getState().hydrate();
    const first = useDashboardLayoutStore.getState().setVisible('alerts', false, 0);
    expect(first.ok).toBe(true);
    const beforeReset = useDashboardLayoutStore.getState().layout.revision;
    const reset = useDashboardLayoutStore.getState().reset(beforeReset);
    expect(reset.ok).toBe(true);
    expect(useDashboardLayoutStore.getState().layout.widgets.every((w) => w.visible)).toBe(true);
    expect(useDashboardLayoutStore.getState().layout.widgets.map((w) => w.id)).toEqual([...DASHBOARD_WIDGET_IDS]);

    const durable = readDashboardLayoutFromStorage();
    expect(durable.revision).toBe(beforeReset + 1);
    expect(durable.widgets.every((w) => w.visible)).toBe(true);
    expect(durable.widgets.map((w) => w.id)).toEqual([...DASHBOARD_WIDGET_IDS]);
    expect(window.localStorage.getItem(DASHBOARD_LAYOUT_STORAGE_KEY)).toContain('"schemaVersion":1');
  });

  it('keeps concurrent writers with the same revision lease from overwriting each other', () => {
    useDashboardLayoutStore.getState().hydrate();
    const lease = useDashboardLayoutStore.getState().layout.revision;

    // Simulate an external tab winning the lease first (real localStorage write).
    writeDashboardLayoutToStorage(normalizeDashboardLayout({
      revision: lease + 1,
      widgets: [
        { id: 'alerts', visible: true },
        { id: 'watchlist', visible: true },
        { id: 'portfolio_health', visible: true },
        { id: 'recent_reports', visible: true },
      ],
    }));

    const stale = useDashboardLayoutStore.getState().reorder(
      [...DASHBOARD_WIDGET_IDS].reverse() as typeof DASHBOARD_WIDGET_IDS[number][],
      lease,
    );
    expect(stale.ok).toBe(false);
    if (!stale.ok) expect(stale.reason).toBe('revision_conflict');

    const durable = readDashboardLayoutFromStorage();
    expect(durable.revision).toBe(lease + 1);
    expect(durable.widgets.map((w) => w.id)[0]).toBe('alerts');
    // Stale reverse order must not have landed.
    expect(durable.widgets.map((w) => w.id)).not.toEqual([...DASHBOARD_WIDGET_IDS].reverse());
  });
});
