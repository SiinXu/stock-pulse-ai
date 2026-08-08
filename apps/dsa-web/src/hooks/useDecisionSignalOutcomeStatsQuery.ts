// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useQuery } from '@tanstack/react-query';

/** Stable query key for Decision Signal outcome stats (mount load + manual refresh). */
export const DECISION_SIGNAL_OUTCOME_STATS_QUERY_KEY = [
  'decision-signals',
  'outcome-stats',
] as const;

export type DecisionSignalOutcomeStatsQueryResult = {
  ok: true;
};

type UseDecisionSignalOutcomeStatsQueryOptions = {
  loadOutcomeStats: () => Promise<void>;
  onCancelInFlight?: () => void;
};

/**
 * TanStack Query schedule adapter for Decision Signal outcome stats.
 *
 * Parity with the previous mount-only useEffect([loadOutcomeStats]):
 * - Single scheduled load on mount / key identity.
 * - No focus refetch, no interval poll.
 * - Errors remain on the existing stats error surface (`retry: false`).
 */
export function useDecisionSignalOutcomeStatsQuery({
  loadOutcomeStats,
  onCancelInFlight,
}: UseDecisionSignalOutcomeStatsQueryOptions) {
  return useQuery({
    queryKey: DECISION_SIGNAL_OUTCOME_STATS_QUERY_KEY,
    queryFn: async ({ signal }): Promise<DecisionSignalOutcomeStatsQueryResult> => {
      const onAbort = () => {
        onCancelInFlight?.();
      };
      if (signal.aborted) {
        onAbort();
        return { ok: true };
      }
      signal.addEventListener('abort', onAbort);
      try {
        await loadOutcomeStats();
        return { ok: true };
      } finally {
        signal.removeEventListener('abort', onAbort);
      }
    },
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export default useDecisionSignalOutcomeStatsQuery;
