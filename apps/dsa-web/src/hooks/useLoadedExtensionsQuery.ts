// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings loaded-extensions list GET.
// Do not import this hook from Shell, App, SettingsPage, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { pluginsApi, type PluginInfo, type PluginListResponse } from '../api/plugins';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const LOADED_EXTENSIONS_CANCEL = { silent: true, revert: false } as const;

/** Readonly two-element key. Never prefix-cancel or prefix-remove `['plugins']`. */
export const LOADED_EXTENSIONS_QUERY_KEY = ['plugins', 'list'] as const;

/** Previous panel effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const LOADED_EXTENSIONS_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type LoadedExtensionsLoadMode = 'initial' | 'refresh';

export type UseLoadedExtensionsQueryResult = {
  items: PluginInfo[];
  total: number;
  isLoading: boolean;
  isRefreshing: boolean;
  loadError: ParsedApiError | null;
  load: (mode?: LoadedExtensionsLoadMode) => Promise<void>;
  /** Panel-owned lifecycle patches the last-good roster before the follow-up GET. */
  setItems: Dispatch<SetStateAction<PluginInfo[]>>;
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfLoadedExtensionsCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(LOADED_EXTENSIONS_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchLoadedExtensionsList(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<PluginListResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfLoadedExtensionsCancelled(args.signal, stillActive());
    const response = await pluginsApi.list();
    throwIfLoadedExtensionsCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfLoadedExtensionsCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useLoadedExtensionsQuery(): UseLoadedExtensionsQueryResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [items, setItems] = useState<PluginInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);

  const requestIdRef = useRef(0);

  const discardExactPluginsQuery = useCallback(() => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: LOADED_EXTENSIONS_QUERY_KEY, exact: true },
      LOADED_EXTENSIONS_CANCEL,
    );
    client.removeQueries({ queryKey: LOADED_EXTENSIONS_QUERY_KEY, exact: true });
  }, []);

  const load = useCallback(async (mode: LoadedExtensionsLoadMode = 'initial') => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;

    setLoadError(null);
    if (mode === 'initial') {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactPluginsQuery();

    try {
      const next = await queryClientRef.current.fetchQuery({
        queryKey: LOADED_EXTENSIONS_QUERY_KEY,
        queryFn: ({ signal }) => fetchLoadedExtensionsList({
          signal,
          stillActive,
        }),
        ...LOADED_EXTENSIONS_QUERY_SCHEDULE,
      });
      if (!stillActive()) return;
      setItems(next.items);
      setTotal(next.total);
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return;
      // Keep a previously loaded roster on refresh so a transient GET
      // failure cannot wipe rows after a completed lifecycle change.
      if (mode === 'initial') {
        setItems([]);
        setTotal(0);
      }
      setLoadError(getParsedApiError(err));
    } finally {
      if (stillActive()) {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    }
  }, [discardExactPluginsQuery]);

  useEffect(() => {
    void load('initial');
    return () => {
      requestIdRef.current += 1;
      discardExactPluginsQuery();
    };
  }, [load, discardExactPluginsQuery]);

  return {
    items,
    total,
    isLoading,
    isRefreshing,
    loadError,
    load,
    setItems,
  };
}
