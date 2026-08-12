// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Home dashboard layout preference store (browser profile / localStorage).
 *
 * Mirrors the watchlist-groups concurrency convention on the client:
 * every mutation carries an expected revision; a stale revision fails closed
 * and reloads durable state instead of overwriting a concurrent write.
 */
import { create } from 'zustand';
import {
  DASHBOARD_LAYOUT_STORAGE_KEY,
  DEFAULT_DASHBOARD_LAYOUT,
  type DashboardLayoutPreference,
  type DashboardWidgetId,
  normalizeDashboardLayout,
  reorderDashboardWidgets,
  setDashboardWidgetVisible,
} from '../types/dashboardLayout';

export type DashboardLayoutCommitResult =
  | { ok: true; layout: DashboardLayoutPreference }
  | { ok: false; reason: 'revision_conflict' | 'invalid' | 'lease_busy' | 'storage_failed'; layout: DashboardLayoutPreference };

type DashboardLayoutState = {
  layout: DashboardLayoutPreference;
  isActioning: boolean;
  lastError: DashboardLayoutCommitResult['reason'] | null;
  hydrate: () => void;
  reorder: (orderedIds: readonly DashboardWidgetId[], expectedRevision: number) => DashboardLayoutCommitResult;
  setVisible: (
    id: DashboardWidgetId,
    visible: boolean,
    expectedRevision: number,
  ) => DashboardLayoutCommitResult;
  reset: (expectedRevision: number) => DashboardLayoutCommitResult;
};

function getLocalStorage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function readDashboardLayoutFromStorage(
  storage: Storage | null = getLocalStorage(),
): DashboardLayoutPreference {
  if (!storage) return normalizeDashboardLayout(DEFAULT_DASHBOARD_LAYOUT);
  try {
    const raw = storage.getItem(DASHBOARD_LAYOUT_STORAGE_KEY);
    if (!raw) return normalizeDashboardLayout(DEFAULT_DASHBOARD_LAYOUT);
    return normalizeDashboardLayout(JSON.parse(raw) as unknown);
  } catch {
    return normalizeDashboardLayout(DEFAULT_DASHBOARD_LAYOUT);
  }
}

export function writeDashboardLayoutToStorage(
  layout: DashboardLayoutPreference,
  storage: Storage | null = getLocalStorage(),
): boolean {
  if (!storage) return false;
  try {
    storage.setItem(DASHBOARD_LAYOUT_STORAGE_KEY, JSON.stringify(layout));
    return true;
  } catch {
    return false;
  }
}

let actionLease = false;
let storageListenerBound = false;

function bindStorageListener(set: (partial: Partial<DashboardLayoutState>) => void): void {
  if (storageListenerBound || typeof window === 'undefined') return;
  storageListenerBound = true;
  window.addEventListener('storage', (event) => {
    if (event.key !== DASHBOARD_LAYOUT_STORAGE_KEY) return;
    set({
      layout: readDashboardLayoutFromStorage(),
      lastError: null,
    });
  });
}

function commitWithRevision(
  expectedRevision: number,
  mutator: (current: DashboardLayoutPreference) => DashboardLayoutPreference | null,
  get: () => DashboardLayoutState,
  set: (partial: Partial<DashboardLayoutState>) => void,
): DashboardLayoutCommitResult {
  if (actionLease) {
    return { ok: false, reason: 'lease_busy', layout: get().layout };
  }
  actionLease = true;
  set({ isActioning: true, lastError: null });
  try {
    const current = readDashboardLayoutFromStorage();
    // Prefer durable storage as authority; fall back to in-memory if storage is empty/unavailable.
    const authoritative = current.revision >= get().layout.revision ? current : get().layout;
    if (authoritative.revision !== expectedRevision) {
      const recovered = normalizeDashboardLayout(authoritative);
      set({ layout: recovered, lastError: 'revision_conflict' });
      return { ok: false, reason: 'revision_conflict', layout: recovered };
    }
    const mutated = mutator(authoritative);
    if (!mutated) {
      set({ lastError: 'invalid' });
      return { ok: false, reason: 'invalid', layout: authoritative };
    }
    const next = normalizeDashboardLayout({
      ...mutated,
      revision: authoritative.revision + 1,
    });

    // Shrink the multi-tab race window: re-read durable storage immediately before
    // writing so a concurrent winner is not overwritten by a stale mutator.
    const recheck = readDashboardLayoutFromStorage();
    if (recheck.revision !== expectedRevision) {
      const recovered = normalizeDashboardLayout(recheck);
      set({ layout: recovered, lastError: 'revision_conflict' });
      return { ok: false, reason: 'revision_conflict', layout: recovered };
    }

    const persisted = writeDashboardLayoutToStorage(next);
    if (!persisted && getLocalStorage()) {
      // Storage exists but write failed: do not claim success; keep prior durable state.
      const recovered = readDashboardLayoutFromStorage();
      set({ layout: recovered, lastError: 'storage_failed' });
      return { ok: false, reason: 'storage_failed', layout: recovered };
    }

    // Confirm durable content after write; treat unexpected drift as conflict.
    const confirmed = readDashboardLayoutFromStorage();
    if (
      getLocalStorage()
      && (
        confirmed.revision !== next.revision
        || JSON.stringify(confirmed.widgets) !== JSON.stringify(next.widgets)
      )
    ) {
      set({ layout: confirmed, lastError: 'revision_conflict' });
      return { ok: false, reason: 'revision_conflict', layout: confirmed };
    }

    set({ layout: next, lastError: null });
    return { ok: true, layout: next };
  } finally {
    actionLease = false;
    set({ isActioning: false });
  }
}

export const useDashboardLayoutStore = create<DashboardLayoutState>((set, get) => ({
  layout: normalizeDashboardLayout(DEFAULT_DASHBOARD_LAYOUT),
  isActioning: false,
  lastError: null,
  hydrate: () => {
    bindStorageListener(set);
    set({ layout: readDashboardLayoutFromStorage(), lastError: null });
  },
  reorder: (orderedIds, expectedRevision) => commitWithRevision(
    expectedRevision,
    (current) => reorderDashboardWidgets(current, orderedIds),
    get,
    set,
  ),
  setVisible: (id, visible, expectedRevision) => commitWithRevision(
    expectedRevision,
    (current) => setDashboardWidgetVisible(current, id, visible),
    get,
    set,
  ),
  reset: (expectedRevision) => commitWithRevision(
    expectedRevision,
    () => ({
      ...DEFAULT_DASHBOARD_LAYOUT,
      revision: expectedRevision,
    }),
    get,
    set,
  ),
}));

export function resetDashboardLayoutStoreForTests(): void {
  actionLease = false;
  useDashboardLayoutStore.setState({
    layout: normalizeDashboardLayout(DEFAULT_DASHBOARD_LAYOUT),
    isActioning: false,
    lastError: null,
  });
}
