// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { watchlistGroupsApi } from '../api/watchlistGroups';
import { getParsedApiError } from '../api/error';
import type { WatchlistGroup, WatchlistGroupRestoreSnapshot, WatchlistGroupState } from '../types/watchlist';
import { useUiLanguage } from '../contexts/UiLanguageContext';

export interface UseWatchlistGroupsReturn {
  groups: WatchlistGroup[];
  revision: number | null;
  isLoading: boolean;
  isActioning: boolean;
  errorMessage: string | null;
  refresh: () => Promise<boolean>;
  createGroup: (name: string) => Promise<boolean>;
  deleteGroup: (groupId: string) => Promise<boolean>;
  restoreGroup: (snapshot: WatchlistGroupRestoreSnapshot) => Promise<boolean>;
  reorderGroups: (orderedIds: string[]) => Promise<boolean>;
  reorderMembers: (groupId: string, orderedCodes: string[]) => Promise<boolean>;
  moveMember: (params: {
    stockCode: string;
    sourceGroupId: string;
    targetGroupId: string;
    targetIndex?: number;
  }) => Promise<boolean>;
}

/** Exact-key cancellation must settle fetchStatus and restore the pre-fetch state. */
export const WATCHLIST_GROUPS_CANCEL = { silent: false, revert: true } as const;

/** Shared GET identity for Home watchlist group observers. */
export const WATCHLIST_GROUPS_QUERY_KEY = ['watchlist', 'groups'] as const;

/** Previous hook never retried, never polled, never focus-refetched, and always called axios offline. */
export const WATCHLIST_GROUPS_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

/**
 * Query cancellation owns stale-result rejection. The axios adapter currently
 * cannot consume Query's AbortSignal, so the shared query function must not
 * translate abort, observer lifetime, or hook generation into a silent
 * CancelledError. Doing so bypasses Query's settlement dispatch and can leave
 * a live successor observer attached to `fetchStatus: fetching` forever.
 */
export async function fetchWatchlistGroups(): Promise<WatchlistGroupState> {
  return watchlistGroupsApi.list();
}

export function useWatchlistGroups({ enabled = true }: { enabled?: boolean } = {}): UseWatchlistGroupsReturn {
  const { t } = useUiLanguage();
  const queryClient = useQueryClient();
  const [isActioning, setIsActioning] = useState(false);
  const [explicitRefreshLoading, setExplicitRefreshLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const revisionRef = useRef<number | null>(null);
  const generationRef = useRef(0);
  const actionLeaseRef = useRef(false);
  const suppressLoadErrorRef = useRef(false);

  const query = useQuery({
    queryKey: WATCHLIST_GROUPS_QUERY_KEY,
    queryFn: fetchWatchlistGroups,
    enabled,
    ...WATCHLIST_GROUPS_QUERY_SCHEDULE,
  });

  const groups = query.data?.groups ?? [];
  const revision = query.data?.revision ?? null;
  revisionRef.current = revision;
  const isLoading = enabled && (
    explicitRefreshLoading || (query.data === undefined && query.isFetching)
  );
  const loadErrorMessage = query.error && !isCancelledError(query.error)
    ? (getParsedApiError(query.error).message || t('watchlist.groupsLoadFailed'))
    : null;
  const publicErrorMessage = suppressLoadErrorRef.current
    ? errorMessage
    : (errorMessage ?? loadErrorMessage);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      actionLeaseRef.current = false;
      const client = queryClient;
      queueMicrotask(() => {
        if (mountedRef.current) return;
        const remaining = client.getQueryCache()
          .find({ queryKey: WATCHLIST_GROUPS_QUERY_KEY, exact: true })
          ?.getObserversCount() ?? 0;
        if (remaining > 0) return;
        void client.cancelQueries(
          { queryKey: WATCHLIST_GROUPS_QUERY_KEY, exact: true },
          WATCHLIST_GROUPS_CANCEL,
        );
        client.removeQueries({ queryKey: WATCHLIST_GROUPS_QUERY_KEY, exact: true });
      });
    };
  }, [queryClient]);

  // Disable must cancel the exact in-flight GET so a later re-enable starts a
  // new request. Do not removeQueries here: other live observers share this
  // key. Last-observer unmount discards the row after a microtask instead.
  useEffect(() => {
    if (enabled) {
      return undefined;
    }
    generationRef.current += 1;
    setExplicitRefreshLoading(false);
    void queryClient.cancelQueries(
      { queryKey: WATCHLIST_GROUPS_QUERY_KEY, exact: true },
      WATCHLIST_GROUPS_CANCEL,
    );
    return undefined;
  }, [enabled, queryClient]);

  const applyState = useCallback((next: WatchlistGroupState, generation: number) => {
    if (!mountedRef.current || generationRef.current !== generation) return false;
    revisionRef.current = next.revision;
    queryClient.setQueryData(WATCHLIST_GROUPS_QUERY_KEY, next);
    return true;
  }, [queryClient]);

  const refresh = useCallback(async () => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    suppressLoadErrorRef.current = false;
    if (mountedRef.current) setExplicitRefreshLoading(true);
    try {
      const next = await queryClient.fetchQuery({
        queryKey: WATCHLIST_GROUPS_QUERY_KEY,
        queryFn: fetchWatchlistGroups,
        ...WATCHLIST_GROUPS_QUERY_SCHEDULE,
      });
      const applied = applyState(next, generation);
      if (applied) setErrorMessage(null);
      return applied;
    } catch (error) {
      if (isCancelledError(error)) {
        return false;
      }
      if (mountedRef.current && generationRef.current === generation) {
        setErrorMessage(getParsedApiError(error).message || t('watchlist.groupsLoadFailed'));
      }
      return false;
    } finally {
      if (mountedRef.current && generationRef.current === generation) {
        setExplicitRefreshLoading(false);
      }
    }
  }, [applyState, queryClient, t]);

  const runAction = useCallback(async (
    action: (expectedRevision: number) => Promise<WatchlistGroupState>,
  ) => {
    const currentRevision = revisionRef.current;
    if (actionLeaseRef.current || currentRevision === null) return false;
    actionLeaseRef.current = true;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    setIsActioning(true);
    try {
      const next = await action(currentRevision);
      if (generationRef.current !== generation) return false;
      void queryClient.cancelQueries(
        { queryKey: WATCHLIST_GROUPS_QUERY_KEY, exact: true },
        WATCHLIST_GROUPS_CANCEL,
      );
      const applied = applyState(next, generation);
      if (applied) {
        suppressLoadErrorRef.current = false;
        setErrorMessage(null);
      }
      return applied;
    } catch (error) {
      if (mountedRef.current && generationRef.current === generation) {
        suppressLoadErrorRef.current = true;
        setErrorMessage(getParsedApiError(error).message || t('watchlist.groupsActionFailed'));
        try {
          const recovered = await queryClient.fetchQuery({
            queryKey: WATCHLIST_GROUPS_QUERY_KEY,
            queryFn: fetchWatchlistGroups,
            ...WATCHLIST_GROUPS_QUERY_SCHEDULE,
          });
          applyState(recovered, generation);
        } catch {
          // Preserve the mutation error; the explicit refresh path remains available.
        }
      }
      return false;
    } finally {
      actionLeaseRef.current = false;
      if (mountedRef.current) setIsActioning(false);
    }
  }, [applyState, queryClient, t]);

  return {
    groups,
    revision,
    isLoading,
    isActioning,
    errorMessage: publicErrorMessage,
    refresh,
    createGroup: (name) => runAction((current) => watchlistGroupsApi.create(name, current)),
    deleteGroup: (groupId) => runAction((current) => watchlistGroupsApi.remove(groupId, current)),
    restoreGroup: (snapshot) => runAction((current) => watchlistGroupsApi.restore(snapshot, current)),
    reorderGroups: (orderedIds) => runAction((current) => watchlistGroupsApi.reorderGroups(orderedIds, current)),
    reorderMembers: (groupId, orderedCodes) => runAction(
      (current) => watchlistGroupsApi.reorderMembers(groupId, orderedCodes, current),
    ),
    moveMember: (params) => runAction((current) => watchlistGroupsApi.moveMember({
      ...params,
      expectedRevision: current,
    })),
  };
}

export default useWatchlistGroups;
