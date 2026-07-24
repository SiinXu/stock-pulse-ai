// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { decisionSignalsApi } from '../api/decisionSignals';
import { alertsApi } from '../api/alerts';
import type { DecisionSignalItem } from '../types/decisionSignals';
import type { AlertTriggerItem } from '../types/alerts';

/**
 * IA-5 notification Bell data source.
 *
 * There is no backend "unread" flag, so unread state is a client-side model:
 * the most recent active decision signals and alert triggers are polled from the
 * existing list APIs, and any item created after the locally persisted
 * `lastSeenAt` timestamp counts as unread. Opening the Bell marks everything seen.
 *
 * Each channel fails soft: a failing signals fetch never suppresses alerts and
 * vice versa, so a single degraded endpoint cannot blank the Bell.
 */

const LAST_SEEN_STORAGE_KEY = 'stockpulse.notifications.lastSeenAt';
const DEFAULT_POLL_MS = 60_000;
const DEFAULT_PAGE_SIZE = 20;

export type UnreadNotificationsState = {
  signalItems: readonly DecisionSignalItem[];
  alertItems: readonly AlertTriggerItem[];
  unreadSignalCount: number;
  unreadAlertCount: number;
  unreadCount: number;
  isLoading: boolean;
  hasError: boolean;
  lastSeenAt: number;
  markAllSeen: () => void;
  refresh: () => void;
};

function readLastSeenAt(): number {
  try {
    const raw = window.localStorage.getItem(LAST_SEEN_STORAGE_KEY);
    if (raw === null) return 0;
    const value = Number(raw);
    return Number.isFinite(value) && value >= 0 ? value : 0;
  } catch {
    return 0;
  }
}

function writeLastSeenAt(value: number): void {
  try {
    window.localStorage.setItem(LAST_SEEN_STORAGE_KEY, String(value));
  } catch {
    // Private-mode / storage-disabled: unread state degrades to session-only.
  }
}

function toTimestamp(createdAt: string | null | undefined): number {
  if (!createdAt) return 0;
  const value = Date.parse(createdAt);
  return Number.isFinite(value) ? value : 0;
}

function countNewerThan<T>(
  items: readonly T[],
  since: number,
  getTimestamp: (item: T) => string | null | undefined,
): number {
  return items.reduce((total, item) => (
    toTimestamp(getTimestamp(item)) > since ? total + 1 : total
  ), 0);
}

export function useUnreadNotifications(options: {
  pollMs?: number;
  pageSize?: number;
  enabled?: boolean;
} = {}): UnreadNotificationsState {
  const pollMs = options.pollMs ?? DEFAULT_POLL_MS;
  const pageSize = options.pageSize ?? DEFAULT_PAGE_SIZE;
  const enabled = options.enabled ?? true;

  const [signalItems, setSignalItems] = useState<readonly DecisionSignalItem[]>([]);
  const [alertItems, setAlertItems] = useState<readonly AlertTriggerItem[]>([]);
  const [isLoading, setIsLoading] = useState(enabled);
  const [signalsFailed, setSignalsFailed] = useState(false);
  const [alertsFailed, setAlertsFailed] = useState(false);
  const [lastSeenAt, setLastSeenAt] = useState<number>(() => readLastSeenAt());

  const generationRef = useRef(0);

  const refresh = useCallback(() => {
    if (!enabled) return;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    setIsLoading(true);

    const signalsRequest = decisionSignalsApi
      .list({ status: 'active', page: 1, pageSize })
      .then((response) => {
        if (generationRef.current !== generation) return;
        setSignalItems(response.items ?? []);
        setSignalsFailed(false);
      })
      .catch(() => {
        if (generationRef.current !== generation) return;
        setSignalsFailed(true);
      });

    const alertsRequest = alertsApi
      .listTriggers({ page: 1, pageSize })
      .then((response) => {
        if (generationRef.current !== generation) return;
        setAlertItems(response.items ?? []);
        setAlertsFailed(false);
      })
      .catch(() => {
        if (generationRef.current !== generation) return;
        setAlertsFailed(true);
      });

    void Promise.allSettled([signalsRequest, alertsRequest]).then(() => {
      if (generationRef.current !== generation) return;
      setIsLoading(false);
    });
  }, [enabled, pageSize]);

  useEffect(() => {
    if (!enabled) return undefined;
    const initialTimer = window.setTimeout(refresh, 0);
    const pollTimer = pollMs > 0 ? window.setInterval(refresh, pollMs) : undefined;
    return () => {
      window.clearTimeout(initialTimer);
      if (pollTimer !== undefined) window.clearInterval(pollTimer);
      generationRef.current += 1;
    };
  }, [enabled, pollMs, refresh]);

  const markAllSeen = useCallback(() => {
    const seenThrough = Math.max(
      Date.now(),
      ...signalItems.map((item) => toTimestamp(item.createdAt)),
      ...alertItems.map((item) => toTimestamp(item.triggeredAt)),
    );
    setLastSeenAt(seenThrough);
    writeLastSeenAt(seenThrough);
  }, [alertItems, signalItems]);

  const unreadSignalCount = useMemo(
    () => countNewerThan(signalItems, lastSeenAt, (item) => item.createdAt),
    [signalItems, lastSeenAt],
  );
  const unreadAlertCount = useMemo(
    () => countNewerThan(alertItems, lastSeenAt, (item) => item.triggeredAt),
    [alertItems, lastSeenAt],
  );

  return {
    signalItems,
    alertItems,
    unreadSignalCount,
    unreadAlertCount,
    unreadCount: unreadSignalCount + unreadAlertCount,
    isLoading,
    hasError: signalsFailed && alertsFailed,
    lastSeenAt,
    markAllSeen,
    refresh,
  };
}
