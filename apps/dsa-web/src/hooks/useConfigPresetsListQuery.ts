// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings config-presets list GET.
// Do not import this hook from Shell, App, SettingsPage, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { configProfilesApi } from '../api/configProfiles';
import type { ConfigPresetItem, ConfigPresetListResponse } from '../types/configProfiles';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const CONFIG_PRESETS_LIST_CANCEL = { silent: true, revert: false } as const;

/** Readonly two-element key. Never prefix-cancel or prefix-remove `['config-presets']`. */
export const CONFIG_PRESETS_LIST_QUERY_KEY = ['config-presets', 'list'] as const;

/** Previous panel effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const CONFIG_PRESETS_LIST_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type ConfigPresetsListLoadMode = 'initial' | 'refresh';

export type ConfigPresetsListLoadResult = {
  presets: ConfigPresetItem[];
  recommendedPresetId: string | null;
};

export type UseConfigPresetsListQueryResult = {
  presets: ConfigPresetItem[];
  recommendedId: string | null;
  isLoading: boolean;
  loadError: ParsedApiError | null;
  load: (mode?: ConfigPresetsListLoadMode) => Promise<ConfigPresetsListLoadResult | undefined>;
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfConfigPresetsListCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(CONFIG_PRESETS_LIST_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchConfigPresetsList(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<ConfigPresetListResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfConfigPresetsListCancelled(args.signal, stillActive());
    const response = await configProfilesApi.listPresets();
    throwIfConfigPresetsListCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfConfigPresetsListCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useConfigPresetsListQuery(): UseConfigPresetsListQueryResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [presets, setPresets] = useState<ConfigPresetItem[]>([]);
  const [recommendedId, setRecommendedId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);

  const requestIdRef = useRef(0);

  const discardExactConfigPresetsListQuery = useCallback(() => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: CONFIG_PRESETS_LIST_QUERY_KEY, exact: true },
      CONFIG_PRESETS_LIST_CANCEL,
    );
    client.removeQueries({ queryKey: CONFIG_PRESETS_LIST_QUERY_KEY, exact: true });
  }, []);

  const load = useCallback(async (mode: ConfigPresetsListLoadMode = 'initial') => {
    void mode;
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;

    setLoadError(null);
    setIsLoading(true);

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactConfigPresetsListQuery();

    try {
      const next = await queryClientRef.current.fetchQuery({
        queryKey: CONFIG_PRESETS_LIST_QUERY_KEY,
        queryFn: ({ signal }) => fetchConfigPresetsList({
          signal,
          stillActive,
        }),
        ...CONFIG_PRESETS_LIST_QUERY_SCHEDULE,
      });
      if (!stillActive()) return undefined;
      const result: ConfigPresetsListLoadResult = {
        presets: next.presets || [],
        recommendedPresetId: next.recommendedPresetId ?? null,
      };
      setPresets(result.presets);
      setRecommendedId(result.recommendedPresetId);
      return result;
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return undefined;
      setPresets([]);
      setRecommendedId(null);
      setLoadError(getParsedApiError(err));
      return undefined;
    } finally {
      if (stillActive()) {
        setIsLoading(false);
      }
    }
  }, [discardExactConfigPresetsListQuery]);

  useEffect(() => {
    void load('initial');
    return () => {
      requestIdRef.current += 1;
      discardExactConfigPresetsListQuery();
    };
  }, [load, discardExactConfigPresetsListQuery]);

  return {
    presets,
    recommendedId,
    isLoading,
    loadError,
    load,
  };
}
