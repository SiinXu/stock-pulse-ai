// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings Local Models catalog GET.
// Do not import this hook from Shell, App, SettingsPage, first-paint barrels, or hooks/index.ts.
// Combined catalog+runtime initialization, runtime transport, and display state stay panel-owned.

import { CancelledError, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useCallback, useEffect } from 'react';
import { localModelsApi } from '../api/localModels';
import type { LocalModelCatalogResponse } from '../types/localModels';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const LOCAL_MODELS_CATALOG_CANCEL = { silent: true, revert: false } as const;

/** Readonly two-element key. Never prefix-cancel or prefix-remove `['local-models']`. */
export const LOCAL_MODELS_CATALOG_QUERY_KEY = ['local-models', 'catalog'] as const;

/** Previous panel effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const LOCAL_MODELS_CATALOG_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type UseLocalModelsCatalogQueryResult = {
  /**
   * Schedule one catalog GET. Throws on transport failure or silent cancel so
   * the panel can keep catalog+runtime initialization atomic via Promise.all.
   */
  loadCatalog: () => Promise<LocalModelCatalogResponse>;
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfLocalModelsCatalogCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(LOCAL_MODELS_CATALOG_CANCEL);
  }
}

export function isLocalModelsCatalogCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchLocalModelsCatalog(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<LocalModelCatalogResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfLocalModelsCatalogCancelled(args.signal, stillActive());
    const response = await localModelsApi.getCatalog();
    throwIfLocalModelsCatalogCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isLocalModelsCatalogCancelledError(error)) throw error;
    throwIfLocalModelsCatalogCancelled(args.signal, stillActive());
    throw error;
  }
}

type LocalModelsCatalogQueryOwnerState = {
  ownerCount: number;
  fetchGeneration: number;
};

const localModelsCatalogQueryOwners = new WeakMap<QueryClient, LocalModelsCatalogQueryOwnerState>();

function localModelsCatalogQueryOwnerState(
  queryClient: QueryClient,
): LocalModelsCatalogQueryOwnerState {
  const existing = localModelsCatalogQueryOwners.get(queryClient);
  if (existing) return existing;
  const created = { ownerCount: 0, fetchGeneration: 0 };
  localModelsCatalogQueryOwners.set(queryClient, created);
  return created;
}

export function useLocalModelsCatalogQuery(): UseLocalModelsCatalogQueryResult {
  const queryClient = useQueryClient();

  const discardExactLocalModelsCatalogQuery = useCallback(() => {
    void queryClient.cancelQueries(
      { queryKey: LOCAL_MODELS_CATALOG_QUERY_KEY, exact: true },
      LOCAL_MODELS_CATALOG_CANCEL,
    );
    queryClient.removeQueries({ queryKey: LOCAL_MODELS_CATALOG_QUERY_KEY, exact: true });
  }, [queryClient]);

  const loadCatalog = useCallback(async () => {
    const owners = localModelsCatalogQueryOwnerState(queryClient);
    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    // Only the sole living owner may discard; a sibling must join the in-flight exact-key fetch.
    if (owners.ownerCount <= 1) {
      owners.fetchGeneration += 1;
      discardExactLocalModelsCatalogQuery();
    }
    const generation = owners.fetchGeneration;
    const stillActive = () => (
      owners.fetchGeneration === generation && owners.ownerCount > 0
    );

    return queryClient.fetchQuery({
      queryKey: LOCAL_MODELS_CATALOG_QUERY_KEY,
      queryFn: ({ signal }) => fetchLocalModelsCatalog({
        signal,
        stillActive,
      }),
      ...LOCAL_MODELS_CATALOG_QUERY_SCHEDULE,
    });
  }, [discardExactLocalModelsCatalogQuery, queryClient]);

  useEffect(() => {
    const owners = localModelsCatalogQueryOwnerState(queryClient);
    owners.ownerCount += 1;
    return () => {
      owners.ownerCount = Math.max(0, owners.ownerCount - 1);
      if (owners.ownerCount === 0) {
        owners.fetchGeneration += 1;
        discardExactLocalModelsCatalogQuery();
      }
    };
  }, [discardExactLocalModelsCatalogQuery, queryClient]);

  return { loadCatalog };
}
