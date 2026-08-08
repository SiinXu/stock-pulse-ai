// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useRef, useState } from 'react';
import { watchlistGroupsApi } from '../api/watchlistGroups';
import { getParsedApiError } from '../api/error';
import type { WatchlistGroup } from '../types/watchlist';
import { useUiLanguage } from '../contexts/UiLanguageContext';

export interface UseWatchlistGroupsReturn {
  groups: WatchlistGroup[];
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
  const [isLoading, setIsLoading] = useState(enabled);
  const [isActioning, setIsActioning] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const requestIdRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestIdRef.current += 1;
    };
  }, []);

  const refresh = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    if (mountedRef.current) setIsLoading(true);
    try {
      const next = await watchlistGroupsApi.list();
      if (mountedRef.current && requestIdRef.current === requestId) {
        setGroups(next);
        setErrorMessage(null);
      }
      return true;
    } catch (error) {
      if (mountedRef.current && requestIdRef.current === requestId) {
        setErrorMessage(getParsedApiError(error).message || t('watchlist.groupsLoadFailed'));
      }
      return false;
    } finally {
      if (mountedRef.current && requestIdRef.current === requestId) {
        setIsLoading(false);
      }
    }
  }, [t]);

  useEffect(() => {
    if (!enabled) {
      requestIdRef.current += 1;
      setIsLoading(false);
      return;
    }
    void refresh();
  }, [enabled, refresh]);

  const runAction = useCallback(async (action: () => Promise<WatchlistGroup[]>) => {
    if (isActioning) return false;
    setIsActioning(true);
    try {
      const next = await action();
      if (mountedRef.current) {
        setGroups(next);
        setErrorMessage(null);
      }
      return true;
    } catch (error) {
      if (mountedRef.current) {
        setErrorMessage(getParsedApiError(error).message || t('watchlist.groupsActionFailed'));
      }
      return false;
    } finally {
      if (mountedRef.current) setIsActioning(false);
    }
  }, [isActioning, t]);

  return {
    groups,
    isLoading,
    isActioning,
    errorMessage,
    refresh,
    createGroup: (name) => runAction(() => watchlistGroupsApi.create(name)),
    deleteGroup: (groupId) => runAction(() => watchlistGroupsApi.remove(groupId)),
    reorderGroups: (orderedIds) => runAction(() => watchlistGroupsApi.reorderGroups(orderedIds)),
    reorderMembers: (groupId, orderedCodes) => runAction(() => watchlistGroupsApi.reorderMembers(groupId, orderedCodes)),
    moveMember: (params) => runAction(() => watchlistGroupsApi.moveMember(params)),
  };
}

export default useWatchlistGroups;
