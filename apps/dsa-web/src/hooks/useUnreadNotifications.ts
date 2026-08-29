// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';
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
 *   rows) instead of joining the initial pending retryer. After unmount the row
 *   is gone, and `refetchQueries` never recreates a missing row.
 * - Disable/unmount/key-change share one discard path: bump generation, silent
 *   cancel, remove the row.
 * - Disabled reports the empty preview (it owns no cache row) while `markFailed`
 *   stays live, so the returned shape is internally consistent: `markAllSeen`
 *   still calls the server and still sets/clears `markFailed`, but does not
 *   write a row that the disabled shape reports as absent.
 * - `markAllSeen` keeps `markAllRead` success / failure / rethrow semantics.
 * - Notification Center page loads stay out of this hook.
 *
 * Two divergences from the previous `setInterval` implementation, neither
 * reachable from the sole production consumer (`NotificationBell`, which passes
 * no options):
 * - Overlap cadence: a poll tick that fires while a pair is still in flight
 *   joins that fetch instead of starting a second pair and letting the newest
 *   generation win. Requests no longer pile up; freshness is unchanged because
 *   the in-flight pair settles into the same render.
 * - Runtime `pollMs` change: re-arms the Query interval without the previous
 *   effect's immediate refetch and in-flight-generation discard.
 *
 * Cleanup uses `removeQueries({ exact: true })`, which is correct for a single
 * owner but would also wipe the row of a second live instance on the same key.
 * `Shell` mounts `NotificationBell` on mutually exclusive desktop/mobile
 * branches, so only one instance exists; a future second owner needs a
 * refcounted discard instead.
 *
 * Termination invariant: when the `queryFn` itself throws the silent
 * `CancelledError`, `Query#fetch` returns the pending retryer promise and skips
 * the error dispatch, so `fetchStatus` is only unstuck by the successor fetch.
 * Every throw site here is paired with a successor `refetchQueries` or with
 * `removeQueries`; do not add a bare throw path without one.
 */
export function useUnreadNotifications(options?: {
  pollMs?: number;
  pageSize?: number;
  enabled?: boolean;
}): UnreadNotificationsState {
  const pollMs = options?.pollMs ?? DEFAULT_POLL_MS;
  const pageSize = options?.pageSize ?? DEFAULT_PAGE_SIZE;
  const enabled = options?.enabled ?? true;

  const queryClient = useQueryClient();
  const queryKey = useMemo(() => ['notifications', 'unread-preview', pageSize], [pageSize]);
  /** One mutable cell: generation fences stale settlements, enabled fences disable-in-flight. */
  const fence = useRef({ id: 0, enabled: true });
  const [markFailed, setMarkFailed] = useState(false);

  const { data, isFetching } = useQuery({
    queryKey,
    enabled,
    queryFn: async ({ client, queryKey: currentQueryKey, signal }): Promise<UnreadNotificationsQueryData> => {
      const startedAt = fence.current.id;
      const [listResult, countResult] = await Promise.allSettled([
        notificationInboxApi.list({ pageSize: currentQueryKey[2] as number }),
        notificationInboxApi.unreadCount(),
      ]);
      if (signal.aborted || fence.current.id !== startedAt || !fence.current.enabled) {
        throw new CancelledError(PREVIEW_CANCEL);
      }
      const listOk = listResult.status === 'fulfilled';
      const countOk = countResult.status === 'fulfilled';
      const previous = client.getQueryData<UnreadNotificationsQueryData>(currentQueryKey);
      return {
        items: listOk ? listResult.value.items : (previous?.items ?? []),
        unreadCount: countOk ? countResult.value.unreadTotal : (previous?.unreadCount ?? 0),
        listFailed: !listOk,
        countFailed: !countOk,
        sourceDegraded:
          (listOk && hasUnavailableSource(listResult.value.sourceStatuses))
          || (countOk && hasUnavailableSource(countResult.value.sourceStatuses)),
      };
    },
    retry: false,
    refetchOnWindowFocus: false,
    refetchInterval: enabled && pollMs > 0 ? pollMs : false,
    refetchIntervalInBackground: true,
    networkMode: 'always',
    staleTime: 0,
  });

  useLayoutEffect(() => {
    // `fence.current` is the stable cell created once by useRef, never a node.
    const cell = fence.current;
    cell.enabled = enabled;
    if (!enabled) {
      return undefined;
    }
    return () => {
      cell.id += 1;
      void queryClient.cancelQueries({ queryKey, exact: true }, PREVIEW_CANCEL);
      queryClient.removeQueries({ queryKey, exact: true });
    };
  }, [enabled, queryClient, queryKey]);

  const refresh = useCallback(() => {
    if (!fence.current.enabled) return;
    fence.current.id += 1;
    void queryClient.cancelQueries({ queryKey, exact: true }, PREVIEW_CANCEL);
    void queryClient.refetchQueries({ queryKey, exact: true });
  }, [queryClient, queryKey]);

  const markAllSeen = useCallback(async () => {
    try {
      const result = await notificationInboxApi.markAllRead();
      // Disabled owns no cache row; writing one here would resurrect a preview
      // the disabled return shape reports as empty.
      if (fence.current.enabled) {
        queryClient.setQueryData<UnreadNotificationsQueryData>(queryKey, (current) => ({
          ...(current ?? EMPTY_QUERY_DATA),
          items: (current?.items ?? []).map((item) => ({ ...item, isRead: true })),
          unreadCount: result.unreadTotal,
        }));
      }
      setMarkFailed(false);
    } catch (error) {
      setMarkFailed(true);
      throw error;
    }
  }, [queryClient, queryKey]);

  // Disabled reports the empty preview (its cache row is removed) while
  // `markFailed` stays live, matching the previous hook's action-state return.
  const snapshot = (enabled ? data : undefined) ?? EMPTY_QUERY_DATA;
  return {
    items: snapshot.items,
    unreadCount: snapshot.unreadCount,
    isLoading: enabled && isFetching,
    hasError: snapshot.listFailed && snapshot.countFailed,
    hasPartialError: snapshot.sourceDegraded || snapshot.listFailed !== snapshot.countFailed || markFailed,
    listFailed: snapshot.listFailed,
    countFailed: snapshot.countFailed,
    markFailed,
    markAllSeen,
    refresh,
  };
}
