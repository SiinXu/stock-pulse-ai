// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings intelligence items list GET.
// Do not import this hook from Shell, App, SettingsPage, first-paint barrels,
// Local Models files, generation-backend files, Chat, Backtest, Workbench,
// StockScreening, or hooks/index.ts.
// Display state, mutations, sources GET, and templates GET stay panel-owned.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef } from 'react';
import {
  intelligenceApi,
  type IntelligenceItemListResponse,
} from '../api/intelligence';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const INTELLIGENCE_ITEMS_CANCEL = { silent: true, revert: false } as const;

/** Readonly three-element key. Never prefix-cancel or prefix-remove `['intelligence']`. */
export const INTELLIGENCE_ITEMS_LIST_QUERY_KEY = ['intelligence', 'items', 'list'] as const;

/** Previous panel click never retried, never polled, never focus-refetched, and always called axios offline. */
export const INTELLIGENCE_ITEMS_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type UseIntelligenceItemsQueryResult = {
  loadItems: () => Promise<IntelligenceItemListResponse>;
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfIntelligenceItemsCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(INTELLIGENCE_ITEMS_CANCEL);
  }
}

export function isIntelligenceItemsCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchIntelligenceItemsList(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<IntelligenceItemListResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfIntelligenceItemsCancelled(args.signal, stillActive());
    const response = await intelligenceApi.listItems({ pageSize: 20 });
    throwIfIntelligenceItemsCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isIntelligenceItemsCancelledError(error)) throw error;
    throwIfIntelligenceItemsCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useIntelligenceItemsQuery(): UseIntelligenceItemsQueryResult {
  const queryClient = useQueryClient();
  const requestIdRef = useRef(0);

  const discardExactItemsQuery = useCallback(() => {
    void queryClient.cancelQueries(
      { queryKey: INTELLIGENCE_ITEMS_LIST_QUERY_KEY, exact: true },
      INTELLIGENCE_ITEMS_CANCEL,
    );
    queryClient.removeQueries({ queryKey: INTELLIGENCE_ITEMS_LIST_QUERY_KEY, exact: true });
  }, [queryClient]);

  const loadItems = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactItemsQuery();

    return queryClient.fetchQuery({
      queryKey: INTELLIGENCE_ITEMS_LIST_QUERY_KEY,
      queryFn: ({ signal }) => fetchIntelligenceItemsList({
        signal,
        stillActive,
      }),
      ...INTELLIGENCE_ITEMS_QUERY_SCHEDULE,
    });
  }, [discardExactItemsQuery, queryClient]);

  useEffect(() => () => {
    requestIdRef.current += 1;
    discardExactItemsQuery();
  }, [discardExactItemsQuery]);

  return { loadItems };
}
