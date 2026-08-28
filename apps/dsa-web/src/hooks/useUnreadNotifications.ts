// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { notificationInboxApi } from '../api/notificationInbox';
import type {
  NotificationInboxItem,
  NotificationInboxPage,
  NotificationInboxUnreadCount,
} from '../types/notificationInbox';

const DEFAULT_POLL_MS = 60_000;
const DEFAULT_PAGE_SIZE = 10;

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
const PREVIEW_CANCEL = { silent: true, revert: false } as const;

function unreadPreviewQueryKey(pageSize: number) {
  return ['notifications', 'unread-preview', pageSize] as const;
}

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

type UnreadNotificationsQueryData = {
  items: readonly NotificationInboxItem[];
  unreadCount: number;
  listFailed: boolean;
  countFailed: boolean;
  sourceDegraded: boolean;
};

const EMPTY_QUERY_DATA: UnreadNotificationsQueryData = {
  items: [],
  unreadCount: 0,
  listFailed: false,
  countFailed: false,
  sourceDegraded: false,
};

function hasUnavailableSource(
  statuses: NotificationInboxPage['sourceStatuses'] | NotificationInboxUnreadCount['sourceStatuses'],
): boolean {
  return statuses.some((status) => !status.available);
}

function mergeUnreadPreviewResult(
  previous: UnreadNotificationsQueryData | undefined,
  listResult: PromiseSettledResult<NotificationInboxPage>,
  countResult: PromiseSettledResult<NotificationInboxUnreadCount>,
): UnreadNotificationsQueryData {
  const listOk = listResult.status === 'fulfilled';
  const countOk = countResult.status === 'fulfilled';
  return {
    items: listOk ? listResult.value.items : (previous?.items ?? []),
    unreadCount: countOk ? countResult.value.unreadTotal : (previous?.unreadCount ?? 0),
    listFailed: !listOk,
    countFailed: !countOk,
    sourceDegraded:
      (listOk && hasUnavailableSource(listResult.value.sourceStatuses))
      || (countOk && hasUnavailableSource(countResult.value.sourceStatuses)),
  };
}

async function fetchUnreadNotificationsPreview(
  pageSize: number,
): Promise<[
  PromiseSettledResult<NotificationInboxPage>,
  PromiseSettledResult<NotificationInboxUnreadCount>,
]> {
  return Promise.allSettled([
    notificationInboxApi.list({ pageSize }),
    notificationInboxApi.unreadCount(),
  ]);
}

/**
 * TanStack Query schedule for the header notification-bell preview + unread count.
 *
 * Preserves the previous hook call/return contract:
 * - Defaults: `pollMs=60_000`, `pageSize=10`, `enabled=true`.
 * - `list({ pageSize })` and `unreadCount()` start together; the generation
 *   applies only after `Promise.allSettled` (manual `refresh` too).
 * - Last-good items and unread count are kept independently against live cache
 *   after settlement; flags are per generation. Hard error only when both
 *   reads fail. `sourceStatuses` degradation is bounded to this generation's
 *   fulfilled sides.
 * - `retry: false`; `refetchOnWindowFocus: false`. `refetchIntervalInBackground:
 *   true` so hidden-tab ticks match the previous `setInterval`.
 * - `networkMode: 'always'` keeps the previous offline behavior: the effect
 *   always called the inbox APIs even when `navigator.onLine` was false.
 * - `staleTime: 0` so data is never treated as fresh. Unmount/key-change/disable
 *   `removeQueries` is the remount miss. Default `gcTime` is left unchanged.
 * - Query key includes `pageSize` only. An in-flight previous `pageSize` cannot
 *   write after the active size changes.
 * - `refresh` is void-facing. Query 5 only cancelRefetchs when `data` exists, so
 *   refresh silently cancels then `refetchQueries` (skips disabled/missing
 *   rows) instead of joining the initial pending retryer.
 * - Disable/unmount/key-change share one discard path: bump generation, silent
 *   cancel, remove the row. Disabled returns empty/non-loading.
 * - `markAllSeen` keeps `markAllRead` success / failure / rethrow semantics.
 * - Notification Center page loads stay out of this hook.
 */
export function useUnreadNotifications(options: {
  pollMs?: number;
  pageSize?: number;
  enabled?: boolean;
} = {}): UnreadNotificationsState {
  const pollMs = options.pollMs ?? DEFAULT_POLL_MS;
  const pageSize = options.pageSize ?? DEFAULT_PAGE_SIZE;
  const enabled = options.enabled ?? true;

  const queryClient = useQueryClient();
  const queryKey = useMemo(() => unreadPreviewQueryKey(pageSize), [pageSize]);
  const generationRef = useRef(0);
  const enabledRef = useRef(enabled);
  const pageSizeRef = useRef(pageSize);
  const mountedRef = useRef(true);
  const [markFailed, setMarkFailed] = useState(false);

  const { data, isFetching } = useQuery({
    queryKey,
    enabled,
    queryFn: async ({ client, queryKey: currentQueryKey, signal }): Promise<UnreadNotificationsQueryData> => {
      const generation = generationRef.current + 1;
      generationRef.current = generation;
      const requestedPageSize = currentQueryKey[2] as number;
      const [listResult, countResult] = await fetchUnreadNotificationsPreview(requestedPageSize);
      if (
        signal.aborted
        || generationRef.current !== generation
        || !enabledRef.current
        || !mountedRef.current
      ) {
        throw new CancelledError(PREVIEW_CANCEL);
      }
      const previous = client.getQueryData<UnreadNotificationsQueryData>(currentQueryKey);
      return mergeUnreadPreviewResult(previous, listResult, countResult);
    },
    retry: false,
    refetchOnWindowFocus: false,
    refetchInterval: enabled && pollMs > 0 ? pollMs : false,
    refetchIntervalInBackground: true,
    networkMode: 'always',
    staleTime: 0,
  });

  useLayoutEffect(() => {
    enabledRef.current = enabled;
    pageSizeRef.current = pageSize;
  }, [enabled, pageSize]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useLayoutEffect(() => {
    if (!enabled) {
      return undefined;
    }
    return () => {
      generationRef.current += 1;
      void queryClient.cancelQueries({ queryKey, exact: true }, PREVIEW_CANCEL);
      queryClient.removeQueries({ queryKey, exact: true });
    };
  }, [enabled, queryClient, queryKey]);

  const refresh = useCallback(() => {
    if (!enabledRef.current || !mountedRef.current) return;
    const scheduledPageSize = pageSizeRef.current;
    generationRef.current += 1;
    void queryClient.cancelQueries({ queryKey, exact: true }, PREVIEW_CANCEL);
    if (
      !enabledRef.current
      || !mountedRef.current
      || pageSizeRef.current !== scheduledPageSize
    ) {
      return;
    }
    void queryClient.refetchQueries({ queryKey, exact: true });
  }, [queryClient, queryKey]);

  const markAllSeen = useCallback(async () => {
    try {
      const result = await notificationInboxApi.markAllRead();
      queryClient.setQueryData<UnreadNotificationsQueryData>(queryKey, (current) => ({
        items: (current?.items ?? []).map((item) => ({ ...item, isRead: true })),
        unreadCount: result.unreadTotal,
        listFailed: current?.listFailed ?? false,
        countFailed: current?.countFailed ?? false,
        sourceDegraded: current?.sourceDegraded ?? false,
      }));
      setMarkFailed(false);
    } catch (error) {
      setMarkFailed(true);
      throw error;
    }
  }, [queryClient, queryKey]);

  if (!enabled) {
    return {
      items: [],
      unreadCount: 0,
      isLoading: false,
      hasError: false,
      hasPartialError: false,
      listFailed: false,
      countFailed: false,
      markFailed: false,
      markAllSeen,
      refresh,
    };
  }

  const snapshot = data ?? EMPTY_QUERY_DATA;
  const hasError = snapshot.listFailed && snapshot.countFailed;
  return {
    items: snapshot.items,
    unreadCount: snapshot.unreadCount,
    isLoading: isFetching,
    hasError,
    hasPartialError: snapshot.sourceDegraded || snapshot.listFailed !== snapshot.countFailed || markFailed,
    listFailed: snapshot.listFailed,
    countFailed: snapshot.countFailed,
    markFailed,
    markAllSeen,
    refresh,
  };
}
