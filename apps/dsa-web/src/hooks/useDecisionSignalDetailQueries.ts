// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useQuery } from '@tanstack/react-query';
import { decisionSignalsApi } from '../api/decisionSignals';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import type {
  DecisionSignalFeedbackItem,
  DecisionSignalOutcomeItem,
} from '../types/decisionSignals';

export const DECISION_SIGNAL_OUTCOMES_QUERY_KEY_ROOT = [
  'decision-signals',
  'outcomes',
] as const;

export const DECISION_SIGNAL_FEEDBACK_QUERY_KEY_ROOT = [
  'decision-signals',
  'feedback',
] as const;

export function buildDecisionSignalOutcomesQueryKey(
  signalId: number | null,
): readonly unknown[] {
  return [...DECISION_SIGNAL_OUTCOMES_QUERY_KEY_ROOT, signalId] as const;
}

export function buildDecisionSignalFeedbackQueryKey(
  signalId: number | null,
): readonly unknown[] {
  return [...DECISION_SIGNAL_FEEDBACK_QUERY_KEY_ROOT, signalId] as const;
}

export type DecisionSignalDetailQueryView = {
  selectedOutcomes: DecisionSignalOutcomeItem[];
  selectedOutcomesLoading: boolean;
  selectedOutcomesError: ParsedApiError | null;
  selectedFeedback: DecisionSignalFeedbackItem | null;
  selectedFeedbackLoading: boolean;
  selectedFeedbackError: ParsedApiError | null;
};

/**
 * TanStack Query loads for the selected Decision Signal detail drawer:
 * outcomes list + feedback item.
 *
 * Parity with the previous selection useEffect:
 * - Loads only when a signal is selected.
 * - No focus refetch / poll (previous effect ran only on selection change).
 * - Independent outcome and feedback requests (`retry: false`).
 * - Loading flags use first-load `isLoading` (not background `isFetching`) so
 *   presentation matches the prior effect start/end flags.
 */
export function useDecisionSignalDetailQueries(
  signalId: number | null,
): DecisionSignalDetailQueryView {
  const outcomesQuery = useQuery({
    queryKey: buildDecisionSignalOutcomesQueryKey(signalId),
    queryFn: async () => {
      if (signalId == null) {
        return [] as DecisionSignalOutcomeItem[];
      }
      const response = await decisionSignalsApi.getSignalOutcomes(signalId);
      return response.items;
    },
    enabled: signalId != null,
    retry: false,
    refetchOnWindowFocus: false,
  });

  const feedbackQuery = useQuery({
    queryKey: buildDecisionSignalFeedbackQueryKey(signalId),
    queryFn: async () => {
      if (signalId == null) {
        return null as DecisionSignalFeedbackItem | null;
      }
      return decisionSignalsApi.getFeedback(signalId);
    },
    enabled: signalId != null,
    retry: false,
    refetchOnWindowFocus: false,
  });

  if (signalId == null) {
    return {
      selectedOutcomes: [],
      selectedOutcomesLoading: false,
      selectedOutcomesError: null,
      selectedFeedback: null,
      selectedFeedbackLoading: false,
      selectedFeedbackError: null,
    };
  }

  return {
    selectedOutcomes: outcomesQuery.isError ? [] : (outcomesQuery.data ?? []),
    selectedOutcomesLoading: outcomesQuery.isLoading,
    selectedOutcomesError: outcomesQuery.isError
      ? getParsedApiError(outcomesQuery.error)
      : null,
    selectedFeedback: feedbackQuery.isError ? null : (feedbackQuery.data ?? null),
    selectedFeedbackLoading: feedbackQuery.isLoading,
    selectedFeedbackError: feedbackQuery.isError
      ? getParsedApiError(feedbackQuery.error)
      : null,
  };
}

export default useDecisionSignalDetailQueries;
