// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useQuery } from '@tanstack/react-query';

/** Query key family for Decision Signals list feed loads. */
export const DECISION_SIGNAL_LIST_QUERY_KEY_ROOT = ['decision-signals', 'list'] as const;

export type DecisionSignalListQueryKeyInput = {
  scope: string;
  page: number;
  /** Opaque filter snapshot for cache identity (page owns the ListFilters type). */
  appliedFilters: unknown;
  /** Watchlist transport readiness — included so loads re-run when codes finish loading. */
  watchlistLoading: boolean;
  watchlistCodes: readonly string[];
  watchlistErrorMessage: string | null;
};

export function buildDecisionSignalListQueryKey(
  input: DecisionSignalListQueryKeyInput,
): readonly unknown[] {
  return [
    ...DECISION_SIGNAL_LIST_QUERY_KEY_ROOT,
    input.scope,
    input.page,
    input.appliedFilters,
    input.watchlistLoading,
    input.watchlistCodes,
    input.watchlistErrorMessage,
  ] as const;
}

export type DecisionSignalListQueryResult = {
  ok: true;
};

type UseDecisionSignalListQueryOptions = {
  queryKey: readonly unknown[];
  loadSignals: () => Promise<void>;
  /** Bump in-flight request generations when the query is cancelled (parity with prior effect cleanup). */
  onCancelInFlight?: () => void;
};

/**
 * TanStack Query schedule adapter for the Decision Signals list feed.
 *
 * Behavior parity with the previous page-local useEffect([loadSignals]):
 * - Fetches when the query key changes (filters, page, scope, watchlist readiness).
 * - No interval polling (the page never polled).
 * - No window-focus refetch (the page never did focus refresh for the list).
 * - Errors stay on the existing list reducer / ApiErrorAlert surfaces (`retry: false`).
 * - Presentation state remains in `useDecisionSignalListState`; this hook only owns scheduling.
 */
export function useDecisionSignalListQuery({
  queryKey,
  loadSignals,
  onCancelInFlight,
}: UseDecisionSignalListQueryOptions) {
  return useQuery({
    queryKey,
    queryFn: async ({ signal }): Promise<DecisionSignalListQueryResult> => {
      const onAbort = () => {
        onCancelInFlight?.();
      };
      if (signal.aborted) {
        onAbort();
        return { ok: true };
      }
      signal.addEventListener('abort', onAbort);
      try {
        await loadSignals();
        return { ok: true };
      } finally {
        signal.removeEventListener('abort', onAbort);
      }
    },
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export default useDecisionSignalListQuery;
