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
 * per-channel read timestamp counts as unread. Opening the Bell marks every
 * currently available channel seen without hiding items from a failed channel.
 *
 * Each channel fails soft: a failing signals fetch never suppresses alerts and
 * vice versa, so a single degraded endpoint cannot blank the Bell.
 */

const LEGACY_LAST_SEEN_STORAGE_KEY = 'stockpulse.notifications.lastSeenAt';
const SIGNALS_LAST_SEEN_STORAGE_KEY = 'stockpulse.notifications.signalsLastSeenAt';
const ALERTS_LAST_SEEN_STORAGE_KEY = 'stockpulse.notifications.alertsLastSeenAt';
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
  hasPartialError: boolean;
  signalsFailed: boolean;
  alertsFailed: boolean;
  signalLastSeenAt: number;
  alertLastSeenAt: number;
  markAllSeen: () => void;
  refresh: () => void;
};

function readStoredTimestamp(key: string): number | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return null;
    const value = Number(raw);
    return Number.isFinite(value) && value >= 0 ? value : null;
  } catch {
    return null;
  }
}

function readInitialBoundaries(): { signals: number; alerts: number } {
  const legacy = readStoredTimestamp(LEGACY_LAST_SEEN_STORAGE_KEY) ?? 0;
  return {
    signals: readStoredTimestamp(SIGNALS_LAST_SEEN_STORAGE_KEY) ?? legacy,
    alerts: readStoredTimestamp(ALERTS_LAST_SEEN_STORAGE_KEY) ?? legacy,
  };
}

function writeStoredTimestamp(key: string, value: number): void {
  try {
    window.localStorage.setItem(key, String(value));
  } catch {
    // Private-mode / storage-disabled: unread state degrades to session-only.
  }
}

function getSeenThrough<T>(
  current: number,
  items: readonly T[],
  getTimestamp: (item: T) => string | null | undefined,
  failed: boolean,
): number {
  return Math.max(
    current,
    failed ? 0 : Date.now(),
    ...items.map((item) => toTimestamp(getTimestamp(item))),
  );
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
  const [initialBoundaries] = useState(readInitialBoundaries);
  const [signalLastSeenAt, setSignalLastSeenAt] = useState(initialBoundaries.signals);
  const [alertLastSeenAt, setAlertLastSeenAt] = useState(initialBoundaries.alerts);

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
    const signalsSeenThrough = getSeenThrough(
      signalLastSeenAt,
      signalItems,
      (item) => item.createdAt,
      signalsFailed,
    );
    const alertsSeenThrough = getSeenThrough(
      alertLastSeenAt,
      alertItems,
      (item) => item.triggeredAt,
      alertsFailed,
    );
    setSignalLastSeenAt(signalsSeenThrough);
    setAlertLastSeenAt(alertsSeenThrough);
    writeStoredTimestamp(SIGNALS_LAST_SEEN_STORAGE_KEY, signalsSeenThrough);
    writeStoredTimestamp(ALERTS_LAST_SEEN_STORAGE_KEY, alertsSeenThrough);
  }, [alertItems, alertLastSeenAt, alertsFailed, signalItems, signalLastSeenAt, signalsFailed]);

  const unreadSignalCount = useMemo(
    () => countNewerThan(signalItems, signalLastSeenAt, (item) => item.createdAt),
    [signalItems, signalLastSeenAt],
  );
  const unreadAlertCount = useMemo(
    () => countNewerThan(alertItems, alertLastSeenAt, (item) => item.triggeredAt),
    [alertItems, alertLastSeenAt],
  );

  return {
    signalItems,
    alertItems,
    unreadSignalCount,
    unreadAlertCount,
    unreadCount: unreadSignalCount + unreadAlertCount,
    isLoading,
    hasError: signalsFailed && alertsFailed,
    hasPartialError: signalsFailed !== alertsFailed,
    signalsFailed,
    alertsFailed,
    signalLastSeenAt,
    alertLastSeenAt,
    markAllSeen,
    refresh,
  };
}
