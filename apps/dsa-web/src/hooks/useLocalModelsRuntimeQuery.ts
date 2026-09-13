// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings Local Models runtime GET.
// Do not import this hook from Shell, App, SettingsPage, first-paint barrels,
// LocalModelsWithKronos, FirstRunWizard, LLMChannelEditor, or hooks/index.ts.
// Inject panel transport getRuntime. Combined catalog+runtime initialization,
// detect-after-install, subscribe, mutations, and display state stay panel-owned.

import { CancelledError, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useCallback, useEffect } from 'react';
import type { LocalModelRuntimeState } from '../types/localModels';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const LOCAL_MODELS_RUNTIME_CANCEL = { silent: true, revert: false } as const;

/** Readonly two-element key. Never prefix-cancel or prefix-remove `['local-models']`. */
export const LOCAL_MODELS_RUNTIME_QUERY_KEY = ['local-models', 'runtime'] as const;

/** Previous panel runtime GET never retried, never polled, never focus-refetched, and always ran offline. */
export const LOCAL_MODELS_RUNTIME_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type LocalModelsRuntimeGetter = () => Promise<LocalModelRuntimeState>;

export type UseLocalModelsRuntimeQueryResult = {
  /**
   * Schedule one runtime GET. Throws on transport failure or silent cancel so
   * the panel can keep catalog+runtime initialization atomic via Promise.all.
   */
  loadRuntime: () => Promise<LocalModelRuntimeState>;
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfLocalModelsRuntimeCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(LOCAL_MODELS_RUNTIME_CANCEL);
  }
}

export function isLocalModelsRuntimeCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchLocalModelsRuntime(
  getRuntime: LocalModelsRuntimeGetter,
  args: {
    signal?: AbortSignal;
    stillActive?: () => boolean;
  } = {},
): Promise<LocalModelRuntimeState> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfLocalModelsRuntimeCancelled(args.signal, stillActive());
    const response = await getRuntime();
    throwIfLocalModelsRuntimeCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isLocalModelsRuntimeCancelledError(error)) throw error;
    throwIfLocalModelsRuntimeCancelled(args.signal, stillActive());
    throw error;
  }
}

type LocalModelsRuntimeQueryOwnerState = {
  ownerCount: number;
  fetchGeneration: number;
};

const localModelsRuntimeQueryOwners = new WeakMap<QueryClient, LocalModelsRuntimeQueryOwnerState>();

function localModelsRuntimeQueryOwnerState(
  queryClient: QueryClient,
): LocalModelsRuntimeQueryOwnerState {
  const existing = localModelsRuntimeQueryOwners.get(queryClient);
  if (existing) return existing;
  const created = { ownerCount: 0, fetchGeneration: 0 };
  localModelsRuntimeQueryOwners.set(queryClient, created);
  return created;
}

export function useLocalModelsRuntimeQuery(
  getRuntime: LocalModelsRuntimeGetter,
): UseLocalModelsRuntimeQueryResult {
  const queryClient = useQueryClient();

  const discardExactLocalModelsRuntimeQuery = useCallback(() => {
    void queryClient.cancelQueries(
      { queryKey: LOCAL_MODELS_RUNTIME_QUERY_KEY, exact: true },
      LOCAL_MODELS_RUNTIME_CANCEL,
    );
    queryClient.removeQueries({ queryKey: LOCAL_MODELS_RUNTIME_QUERY_KEY, exact: true });
  }, [queryClient]);

  const loadRuntime = useCallback(async () => {
    const owners = localModelsRuntimeQueryOwnerState(queryClient);
    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    // Only the sole living owner may discard; a sibling must join the in-flight exact-key fetch.
    if (owners.ownerCount <= 1) {
      owners.fetchGeneration += 1;
      discardExactLocalModelsRuntimeQuery();
    }
    const generation = owners.fetchGeneration;
    const stillActive = () => (
      owners.fetchGeneration === generation && owners.ownerCount > 0
    );

    return queryClient.fetchQuery({
      queryKey: LOCAL_MODELS_RUNTIME_QUERY_KEY,
      queryFn: ({ signal }) => fetchLocalModelsRuntime(getRuntime, {
        signal,
        stillActive,
      }),
      ...LOCAL_MODELS_RUNTIME_QUERY_SCHEDULE,
    });
  }, [discardExactLocalModelsRuntimeQuery, getRuntime, queryClient]);

  useEffect(() => {
    const owners = localModelsRuntimeQueryOwnerState(queryClient);
    owners.ownerCount += 1;
    return () => {
      owners.ownerCount = Math.max(0, owners.ownerCount - 1);
      if (owners.ownerCount === 0) {
        owners.fetchGeneration += 1;
        discardExactLocalModelsRuntimeQuery();
      }
    };
  }, [discardExactLocalModelsRuntimeQuery, queryClient]);

  return { loadRuntime };
}
