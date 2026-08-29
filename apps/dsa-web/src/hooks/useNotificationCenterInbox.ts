// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for the Notification Center page inbox.
// Do not import this hook from Shell, NotificationBell, first-paint barrels, or App.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { notificationInboxApi } from '../api/notificationInbox';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import type {
  NotificationInboxItem,
  NotificationInboxKind,
  NotificationInboxPage,
} from '../types/notificationInbox';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const NOTIFICATION_CENTER_CANCEL = { silent: true, revert: false } as const;

export const NOTIFICATION_CENTER_LIST_QUERY_KEY_ROOT = [
  'notifications',
  'center',
  'list',
] as const;

export const NOTIFICATION_CENTER_PAGE_SIZE = 50;

/** Previous page effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const NOTIFICATION_CENTER_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type ReadFilter = 'all' | 'unread';

export type NotificationCenterLoadMode = 'initial' | 'refresh' | 'more';

export type UseNotificationCenterInboxResult = {
  items: NotificationInboxItem[];
  pageData: NotificationInboxPage | null;
  loading: boolean;
  refreshing: boolean;
  loadingMore: boolean;
  error: ParsedApiError | null;
  readFilter: ReadFilter;
  setReadFilter: Dispatch<SetStateAction<ReadFilter>>;
  kind: '' | NotificationInboxKind;
  setKind: Dispatch<SetStateAction<'' | NotificationInboxKind>>;
  markingId: string | null;
  markingAll: boolean;
  load: (mode?: NotificationCenterLoadMode, cursor?: string) => Promise<void>;
  handleMarkRead: (itemId: string) => Promise<void>;
  handleMarkAllRead: () => Promise<void>;
};

export function buildNotificationCenterListQueryKey(
  kind: '' | NotificationInboxKind,
  unreadOnly: boolean,
  cursor?: string,
): readonly unknown[] {
  return [
    ...NOTIFICATION_CENTER_LIST_QUERY_KEY_ROOT,
    kind || 'all',
    unreadOnly ? 'unread' : 'all',
    NOTIFICATION_CENTER_PAGE_SIZE,
    cursor ?? 'head',
  ] as const;
}

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(NOTIFICATION_CENTER_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

function sameQueryKey(left: readonly unknown[], right: readonly unknown[]): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

export async function fetchNotificationCenterList(args: {
  kind: '' | NotificationInboxKind;
  unreadOnly: boolean;
  cursor?: string;
  signal?: AbortSignal;
  stillActive?: () => boolean;
}): Promise<NotificationInboxPage> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfCancelled(args.signal, stillActive());
    const response = await notificationInboxApi.list({
      page: 1,
      pageSize: NOTIFICATION_CENTER_PAGE_SIZE,
      cursor: args.cursor,
      kind: args.kind || undefined,
      unreadOnly: args.unreadOnly,
    });
    throwIfCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useNotificationCenterInbox(): UseNotificationCenterInboxResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [pageData, setPageData] = useState<NotificationInboxPage | null>(null);
  const [items, setItems] = useState<NotificationInboxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [readFilter, setReadFilter] = useState<ReadFilter>('all');
  const [kind, setKind] = useState<'' | NotificationInboxKind>('');
  const [markingId, setMarkingId] = useState<string | null>(null);
  const [markingAll, setMarkingAll] = useState(false);

  const requestIdRef = useRef(0);
  const kindRef = useRef(kind);
  const readFilterRef = useRef(readFilter);
  const liveKeysRef = useRef<readonly unknown[][]>([]);
  kindRef.current = kind;
  readFilterRef.current = readFilter;

  const discardExactQuery = useCallback((key: readonly unknown[]) => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: key, exact: true },
      NOTIFICATION_CENTER_CANCEL,
    );
    client.removeQueries({ queryKey: key, exact: true });
    liveKeysRef.current = liveKeysRef.current.filter((live) => !sameQueryKey(live, key));
  }, []);

  const discardLiveKeys = useCallback((
    predicate: (key: readonly unknown[]) => boolean,
  ) => {
    for (const live of [...liveKeysRef.current]) {
      if (predicate(live)) discardExactQuery(live);
    }
  }, [discardExactQuery]);

  const load = useCallback(async (
    mode: NotificationCenterLoadMode = 'initial',
    cursor?: string,
  ) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const kindAtStart = kindRef.current;
    const unreadOnly = readFilterRef.current === 'unread';
    const cursorArg = mode === 'more' && cursor ? cursor : undefined;
    const key = buildNotificationCenterListQueryKey(kindAtStart, unreadOnly, cursorArg);

    if (mode === 'initial') setLoading(true);
    if (mode === 'refresh') setRefreshing(true);
    if (mode === 'more') setLoadingMore(true);
    setError(null);

    if (mode === 'more') {
      // Keep the current head row; exact-remove an abandoned more key or same-key more retry.
      discardLiveKeys((live) => sameQueryKey(live, key) || live[live.length - 1] !== 'head');
    } else {
      // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
      // Key-changing initial also exact-removes the abandoned head and any in-flight more key.
      discardLiveKeys(() => true);
    }
    liveKeysRef.current = [...liveKeysRef.current, key];

    try {
      const response = await queryClientRef.current.fetchQuery({
        queryKey: key,
        queryFn: ({ signal }) => fetchNotificationCenterList({
          kind: kindAtStart,
          unreadOnly,
          cursor: cursorArg,
          signal,
          stillActive: () => requestIdRef.current === requestId,
        }),
        ...NOTIFICATION_CENTER_QUERY_SCHEDULE,
      });
      if (requestIdRef.current !== requestId) return;
      setPageData(response);
      setItems((current) => {
        if (mode !== 'more') return response.items;
        const existingIds = new Set(current.map((item) => item.id));
        return [...current, ...response.items.filter((item) => !existingIds.has(item.id))];
      });
    } catch (err) {
      if (requestIdRef.current !== requestId || isCancelledError(err)) return;
      if (mode === 'initial') {
        setPageData(null);
        setItems([]);
      }
      setError(getParsedApiError(err));
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false);
        setRefreshing(false);
        setLoadingMore(false);
      }
    }
  }, [discardLiveKeys]);

  useEffect(() => {
    void load('initial');
    return () => {
      requestIdRef.current += 1;
      discardLiveKeys(() => true);
    };
  }, [load, kind, readFilter, discardLiveKeys]);

  const handleMarkRead = useCallback(async (itemId: string) => {
    const requestId = requestIdRef.current;
    setMarkingId(itemId);
    setError(null);
    try {
      await notificationInboxApi.markRead([itemId]);
      if (requestIdRef.current !== requestId) return;
      await load('refresh');
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      setError(getParsedApiError(err));
    } finally {
      setMarkingId(null);
    }
  }, [load]);

  const handleMarkAllRead = useCallback(async () => {
    const requestId = requestIdRef.current;
    setMarkingAll(true);
    setError(null);
    try {
      await notificationInboxApi.markAllRead(kindRef.current || undefined);
      if (requestIdRef.current !== requestId) return;
      await load('refresh');
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      setError(getParsedApiError(err));
    } finally {
      setMarkingAll(false);
    }
  }, [load]);

  return {
    items,
    pageData,
    loading,
    refreshing,
    loadingMore,
    error,
    readFilter,
    setReadFilter,
    kind,
    setKind,
    markingId,
    markingAll,
    load,
    handleMarkRead,
    handleMarkAllRead,
  };
}
