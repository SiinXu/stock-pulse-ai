// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings notification-channel plugin roster GET.
// Do not import this hook from Shell, App, SettingsPage, SettingsActiveConfigPanel,
// hooks/index.ts, first-paint barrels, LoadedExtensions files, intelligence-sources
// files, generation-backend files, Local Models files, Chat, Backtest, Workbench,
// or StockScreening.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { pluginsApi, type PluginInfo, type PluginListResponse } from '../api/plugins';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const NOTIFICATION_CHANNEL_PLUGINS_CANCEL = { silent: true, revert: false } as const;

/** Readonly two-element key. Never prefix-cancel or prefix-remove `['plugins']`. */
export const NOTIFICATION_CHANNEL_PLUGINS_QUERY_KEY = ['plugins', 'notification-channels'] as const;

/** Previous panel effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const NOTIFICATION_CHANNEL_PLUGINS_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type UseNotificationChannelPluginsQueryResult = {
  items: PluginInfo[];
  isLoading: boolean;
  loadFailed: boolean;
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfNotificationChannelPluginsCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(NOTIFICATION_CHANNEL_PLUGINS_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchNotificationChannelPluginsList(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<PluginListResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfNotificationChannelPluginsCancelled(args.signal, stillActive());
    const response = await pluginsApi.list();
    throwIfNotificationChannelPluginsCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfNotificationChannelPluginsCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useNotificationChannelPluginsQuery(): UseNotificationChannelPluginsQueryResult {
  const queryClient = useQueryClient();

  const [items, setItems] = useState<PluginInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);

  const requestIdRef = useRef(0);

  const discardExactNotificationChannelPluginsQuery = useCallback(() => {
    void queryClient.cancelQueries(
      { queryKey: NOTIFICATION_CHANNEL_PLUGINS_QUERY_KEY, exact: true },
      NOTIFICATION_CHANNEL_PLUGINS_CANCEL,
    );
    queryClient.removeQueries({ queryKey: NOTIFICATION_CHANNEL_PLUGINS_QUERY_KEY, exact: true });
  }, [queryClient]);

  const load = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;

    setLoadFailed(false);
    setIsLoading(true);

    // Same-key successor must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactNotificationChannelPluginsQuery();

    try {
      const next = await queryClient.fetchQuery({
        queryKey: NOTIFICATION_CHANNEL_PLUGINS_QUERY_KEY,
        queryFn: ({ signal }) => fetchNotificationChannelPluginsList({
          signal,
          stillActive,
        }),
        ...NOTIFICATION_CHANNEL_PLUGINS_QUERY_SCHEDULE,
      });
      if (!stillActive()) return;
      setItems(next.items);
      setLoadFailed(false);
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return;
      setItems([]);
      setLoadFailed(true);
    } finally {
      if (stillActive()) {
        setIsLoading(false);
      }
    }
  }, [discardExactNotificationChannelPluginsQuery, queryClient]);

  useEffect(() => {
    void load();
    return () => {
      requestIdRef.current += 1;
      discardExactNotificationChannelPluginsQuery();
    };
  }, [load, discardExactNotificationChannelPluginsQuery]);

  return {
    items,
    isLoading,
    loadFailed,
  };
}
