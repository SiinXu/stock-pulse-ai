// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useMutation } from '@tanstack/react-query';
import { useCallback, useRef, useState } from 'react';
import { decisionSignalsApi } from '../api/decisionSignals';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import type {
  DecisionSignalItem,
  DecisionSignalStatus,
} from '../types/decisionSignals';

export type DecisionSignalStatusMutationInput = {
  signalId: number;
  status: DecisionSignalStatus;
};

export type DecisionSignalStatusMutationResult =
  | { kind: 'ignored' }
  | { kind: 'unmounted' }
  | { kind: 'error'; error: ParsedApiError }
  | { kind: 'ok'; item: DecisionSignalItem };

type UseDecisionSignalStatusMutationOptions = {
  /** Page-owned mount flag. Success/error presentation must not apply after unmount. */
  isMounted: () => boolean;
};

/**
 * TanStack Query schedule adapter for Decision Signals status writes.
 *
 * Parity with the previous page-owned `updateStatus` call:
 * - Transport stays in `decisionSignalsApi.updateStatus`.
 * - Duplicate confirmation clicks are ignored via a synchronous in-flight ref
 *   (do not use `isPending` alone — it can lag one tick).
 * - `retry: false`; errors stay on the existing confirm-dialog / ApiErrorAlert
 *   surfaces via the returned result (no parallel error channel).
 * - List/stats reload and latest/timeline/selection updates remain page-owned.
 * - On success the in-flight ref and `isUpdating` stay true until the page
 *   finishes `loadSignalsForPage` + `loadOutcomeStats` and calls
 *   `releaseStatusUpdate`. Error and unmount paths release immediately.
 */
export function useDecisionSignalStatusMutation({
  isMounted,
}: UseDecisionSignalStatusMutationOptions) {
  const inFlightRef = useRef(false);
  const [guardBusy, setGuardBusy] = useState(false);
  const mutationFn = useCallback((
    { signalId, status }: DecisionSignalStatusMutationInput,
  ) => decisionSignalsApi.updateStatus(signalId, { status }), []);
  const mutation = useMutation({
    mutationFn,
    retry: false,
  });
  const { mutateAsync } = mutation;

  const releaseStatusUpdate = useCallback(() => {
    inFlightRef.current = false;
    if (isMounted()) {
      setGuardBusy(false);
    }
  }, [isMounted]);

  const runStatusUpdate = useCallback(async (
    input: DecisionSignalStatusMutationInput,
  ): Promise<DecisionSignalStatusMutationResult> => {
    if (inFlightRef.current) {
      return { kind: 'ignored' };
    }
    inFlightRef.current = true;
    setGuardBusy(true);
    try {
      const item = await mutateAsync(input);
      if (!isMounted()) {
        inFlightRef.current = false;
        return { kind: 'unmounted' };
      }
      return { kind: 'ok', item };
    } catch (err) {
      inFlightRef.current = false;
      if (!isMounted()) {
        return { kind: 'unmounted' };
      }
      setGuardBusy(false);
      return { kind: 'error', error: getParsedApiError(err) };
    }
  }, [isMounted, mutateAsync]);

  return {
    runStatusUpdate,
    releaseStatusUpdate,
    isUpdating: guardBusy || mutation.isPending,
  };
}

export default useDecisionSignalStatusMutation;
