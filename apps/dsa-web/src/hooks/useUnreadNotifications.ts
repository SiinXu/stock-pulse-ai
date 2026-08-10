// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useRef, useState } from 'react';
import { notificationInboxApi } from '../api/notificationInbox';
import type { NotificationInboxItem } from '../types/notificationInbox';

const DEFAULT_POLL_MS = 60_000;
const DEFAULT_PAGE_SIZE = 10;

export type UnreadNotificationsState = {
  items: readonly NotificationInboxItem[];
  unreadCount: number;
  isLoading: boolean;
  hasError: boolean;
  hasPartialError: boolean;
  listFailed: boolean;
  countFailed: boolean;
  markFailed: boolean;
  markAllSeen: () => Promise<void>;
  refresh: () => void;
};

export function useUnreadNotifications(options: {
  pollMs?: number;
  pageSize?: number;
  enabled?: boolean;
} = {}): UnreadNotificationsState {
  const pollMs = options.pollMs ?? DEFAULT_POLL_MS;
  const pageSize = options.pageSize ?? DEFAULT_PAGE_SIZE;
  const enabled = options.enabled ?? true;

  const [items, setItems] = useState<readonly NotificationInboxItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isLoading, setIsLoading] = useState(enabled);
  const [listFailed, setListFailed] = useState(false);
  const [countFailed, setCountFailed] = useState(false);
  const [markFailed, setMarkFailed] = useState(false);
  const [sourceDegraded, setSourceDegraded] = useState(false);
  const generationRef = useRef(0);

  const refresh = useCallback(() => {
    if (!enabled) return;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    setIsLoading(true);
    setSourceDegraded(false);
    let listSourceDegraded = false;
    let countSourceDegraded = false;

    const listRequest = notificationInboxApi
      .list({ pageSize })
      .then((response) => {
        if (generationRef.current !== generation) return;
        setItems(response.items);
        setListFailed(false);
        listSourceDegraded = response.sourceStatuses.some((status) => !status.available);
      })
      .catch(() => {
        if (generationRef.current !== generation) return;
        setListFailed(true);
      });

    const countRequest = notificationInboxApi
      .unreadCount()
      .then((response) => {
        if (generationRef.current !== generation) return;
        setUnreadCount(response.unreadTotal);
        setCountFailed(false);
        countSourceDegraded = response.sourceStatuses.some((status) => !status.available);
      })
      .catch(() => {
        if (generationRef.current !== generation) return;
        setCountFailed(true);
      });

    void Promise.allSettled([listRequest, countRequest]).then(() => {
      if (generationRef.current !== generation) return;
      setSourceDegraded(listSourceDegraded || countSourceDegraded);
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

  const markAllSeen = useCallback(async () => {
    try {
      const result = await notificationInboxApi.markAllRead();
      setUnreadCount(result.unreadTotal);
      setItems((current) => current.map((item) => ({ ...item, isRead: true })));
      setMarkFailed(false);
    } catch (error) {
      setMarkFailed(true);
      throw error;
    }
  }, []);

  const hasError = listFailed && countFailed;
  return {
    items,
    unreadCount,
    isLoading,
    hasError,
    hasPartialError: sourceDegraded || listFailed !== countFailed || markFailed,
    listFailed,
    countFailed,
    markFailed,
    markAllSeen,
    refresh,
  };
}
