// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { DecisionSignalItem } from '../../types/decisionSignals';
import {
  findSignalInCandidates,
  getInitialSelectedSignalId,
  type DecisionSignalSelectionCandidateGroup,
  type SelectedSignal,
} from './decisionSignalsPageModel';

export type UseDecisionSignalSelectionOptions = {
  routeSearch: string;
  routeKey: string;
  candidates: readonly DecisionSignalSelectionCandidateGroup[];
  fetchSignalById: (signalId: number) => Promise<DecisionSignalItem>;
  updateSearchParams: (values: { signal: number | null }, replace?: boolean) => void;
  onLookupSuccess?: () => void;
  onLookupError?: (error: unknown) => void;
  isMounted: () => boolean;
};

export function useDecisionSignalSelection({
  routeSearch,
  routeKey,
  candidates,
  fetchSignalById,
  updateSearchParams,
  onLookupSuccess,
  onLookupError,
  isMounted,
}: UseDecisionSignalSelectionOptions) {
  const [selected, setSelected] = useState<SelectedSignal | null>(null);
  const selectedSignalIdRef = useRef<number | null>(null);
  const pendingSelectedSignalIdRef = useRef<number | null>(getInitialSelectedSignalId(routeSearch));
  const candidatesRef = useRef(candidates);
  const fetchSignalByIdRef = useRef(fetchSignalById);
  const onLookupSuccessRef = useRef(onLookupSuccess);
  const onLookupErrorRef = useRef(onLookupError);
  const updateSearchParamsRef = useRef(updateSearchParams);
  const isMountedRef = useRef(isMounted);

  const takePendingSelection = useCallback((
    source: SelectedSignal['source'],
    nextItems: DecisionSignalItem[],
  ): SelectedSignal | null => {
    const pendingId = pendingSelectedSignalIdRef.current;
    if (pendingId === null) return null;
    const item = nextItems.find((candidate) => candidate.id === pendingId);
    if (!item) return null;
    pendingSelectedSignalIdRef.current = null;
    selectedSignalIdRef.current = item.id;
    return { source, item };
  }, []);

  useLayoutEffect(() => {
    candidatesRef.current = candidates;
    fetchSignalByIdRef.current = fetchSignalById;
    onLookupSuccessRef.current = onLookupSuccess;
    onLookupErrorRef.current = onLookupError;
    updateSearchParamsRef.current = updateSearchParams;
    isMountedRef.current = isMounted;
  }, [candidates, fetchSignalById, isMounted, onLookupError, onLookupSuccess, updateSearchParams]);

  /* eslint-disable react-hooks/set-state-in-effect -- URL search is the external selection source */
  useLayoutEffect(() => {
    const routeSignalId = getInitialSelectedSignalId(routeSearch);
    if (routeSignalId === null) {
      pendingSelectedSignalIdRef.current = null;
      if (selectedSignalIdRef.current !== null) setSelected(null);
      return;
    }
    if (selectedSignalIdRef.current === routeSignalId) {
      pendingSelectedSignalIdRef.current = null;
      return;
    }
    pendingSelectedSignalIdRef.current = routeSignalId;
    const found = findSignalInCandidates(routeSignalId, candidatesRef.current);
    if (found) {
      pendingSelectedSignalIdRef.current = null;
      selectedSignalIdRef.current = found.item.id;
      setSelected(found);
      return;
    }
    // Memory miss fallback: get() by id (source 'outcome' so list refresh won't drop off-page).
    if (selectedSignalIdRef.current !== null) setSelected(null);
    void fetchSignalByIdRef.current(routeSignalId).then((item) => {
      if (!isMountedRef.current() || pendingSelectedSignalIdRef.current !== routeSignalId) return;
      pendingSelectedSignalIdRef.current = null;
      selectedSignalIdRef.current = item.id;
      onLookupSuccessRef.current?.();
      setSelected({ source: 'outcome', item });
    }).catch((err) => {
      if (!isMountedRef.current() || pendingSelectedSignalIdRef.current !== routeSignalId) return;
      pendingSelectedSignalIdRef.current = null;
      selectedSignalIdRef.current = null;
      setSelected(null);
      onLookupErrorRef.current?.(err);
      updateSearchParamsRef.current({ signal: null });
    });
  }, [routeKey, routeSearch]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const selectSignal = useCallback((item: DecisionSignalItem, source: SelectedSignal['source']) => {
    const previousId = selectedSignalIdRef.current;
    pendingSelectedSignalIdRef.current = null;
    selectedSignalIdRef.current = item.id;
    setSelected({ source, item });
    updateSearchParams({ signal: item.id }, previousId === item.id);
  }, [updateSearchParams]);

  const closeSignal = useCallback(() => {
    pendingSelectedSignalIdRef.current = null;
    selectedSignalIdRef.current = null;
    setSelected(null);
    updateSearchParams({ signal: null });
  }, [updateSearchParams]);

  useEffect(() => {
    if (pendingSelectedSignalIdRef.current === null) {
      updateSearchParams({ signal: selected?.item.id ?? null });
    }
  }, [selected?.item.id, updateSearchParams]);

  useEffect(() => {
    selectedSignalIdRef.current = selected?.item.id ?? null;
  }, [selected?.item.id]);

  return {
    selected,
    selectedSignalId: selected?.item.id ?? null,
    selectedSignalIdRef,
    selectSignal,
    closeSignal,
    setSelected,
    takePendingSelection,
  };
}

export default useDecisionSignalSelection;
