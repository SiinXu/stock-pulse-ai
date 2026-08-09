// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useRef, useState } from 'react';
import { watchlistGroupsApi } from '../api/watchlistGroups';
import { getParsedApiError } from '../api/error';
import type { WatchlistGroup, WatchlistGroupState } from '../types/watchlist';
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
  reorderGroups: (orderedIds: string[]) => Promise<boolean>;
  reorderMembers: (groupId: string, orderedCodes: string[]) => Promise<boolean>;
  moveMember: (params: {
    stockCode: string;
    sourceGroupId: string;
    targetGroupId: string;
    targetIndex?: number;
  }) => Promise<boolean>;
}

export function useWatchlistGroups({ enabled = true }: { enabled?: boolean } = {}): UseWatchlistGroupsReturn {
  const { t } = useUiLanguage();
  const [groups, setGroups] = useState<WatchlistGroup[]>([]);
  const [revision, setRevision] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(enabled);
  const [isActioning, setIsActioning] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const revisionRef = useRef<number | null>(null);
  const generationRef = useRef(0);
  const actionLeaseRef = useRef(false);

  const applyState = useCallback((next: WatchlistGroupState, generation: number) => {
    if (!mountedRef.current || generationRef.current !== generation) return false;
    revisionRef.current = next.revision;
    setRevision(next.revision);
    setGroups(next.groups);
    return true;
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      actionLeaseRef.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    if (mountedRef.current) setIsLoading(true);
    try {
      const next = await watchlistGroupsApi.list();
      if (applyState(next, generation)) setErrorMessage(null);
      return true;
    } catch (error) {
      if (mountedRef.current && generationRef.current === generation) {
        setErrorMessage(getParsedApiError(error).message || t('watchlist.groupsLoadFailed'));
      }
      return false;
    } finally {
      if (mountedRef.current && generationRef.current === generation) setIsLoading(false);
    }
  }, [applyState, t]);

  useEffect(() => {
    if (!enabled) {
      generationRef.current += 1;
      setIsLoading(false);
      return;
    }
    void refresh();
  }, [enabled, refresh]);

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
      if (applyState(next, generation)) setErrorMessage(null);
      return true;
    } catch (error) {
      if (mountedRef.current && generationRef.current === generation) {
        setErrorMessage(getParsedApiError(error).message || t('watchlist.groupsActionFailed'));
        try {
          const recovered = await watchlistGroupsApi.list();
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
  }, [applyState, t]);

  return {
    groups,
    revision,
    isLoading,
    isActioning,
    errorMessage,
    refresh,
    createGroup: (name) => runAction((current) => watchlistGroupsApi.create(name, current)),
    deleteGroup: (groupId) => runAction((current) => watchlistGroupsApi.remove(groupId, current)),
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
