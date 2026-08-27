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
  const [detailOpen, setDetailOpen] = useState(false);
  const selectedSignalIdRef = useRef<number | null>(null);
  const selectedRef = useRef<SelectedSignal | null>(null);
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
    const next = { source, item };
    selectedRef.current = next;
    return next;
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
      if (selectedSignalIdRef.current !== null) {
        selectedSignalIdRef.current = null;
        selectedRef.current = null;
        setSelected(null);
        setDetailOpen(false);
      }
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
      selectedRef.current = found;
      setSelected(found);
      setDetailOpen(true);
      return;
    }
    // Memory miss fallback: get() by id (source 'outcome' so list refresh won't drop off-page).
    if (selectedSignalIdRef.current !== null) {
      selectedSignalIdRef.current = null;
      selectedRef.current = null;
      setSelected(null);
    }
    setDetailOpen(false);
    void fetchSignalByIdRef.current(routeSignalId).then((item) => {
      if (!isMountedRef.current() || pendingSelectedSignalIdRef.current !== routeSignalId) return;
      pendingSelectedSignalIdRef.current = null;
      selectedSignalIdRef.current = item.id;
      const next = { source: 'outcome' as const, item };
      selectedRef.current = next;
      onLookupSuccessRef.current?.();
      setSelected(next);
      setDetailOpen(true);
    }).catch((err) => {
      if (!isMountedRef.current() || pendingSelectedSignalIdRef.current !== routeSignalId) return;
      pendingSelectedSignalIdRef.current = null;
      selectedSignalIdRef.current = null;
      selectedRef.current = null;
      setSelected(null);
      setDetailOpen(false);
      onLookupErrorRef.current?.(err);
      updateSearchParamsRef.current({ signal: null });
    });
  }, [routeKey, routeSearch]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const selectSignal = useCallback((item: DecisionSignalItem, source: SelectedSignal['source']) => {
    const previousId = selectedSignalIdRef.current;
    pendingSelectedSignalIdRef.current = null;
    selectedSignalIdRef.current = item.id;
    const next = { source, item };
    selectedRef.current = next;
    setSelected(next);
    setDetailOpen(true);
    updateSearchParams({ signal: item.id }, previousId === item.id);
  }, [updateSearchParams]);

  const closeDetail = useCallback(() => {
    setDetailOpen(false);
  }, []);

  const openDetail = useCallback(() => {
    if (selectedSignalIdRef.current === null) return;
    setDetailOpen(true);
  }, []);

  const adoptSelected = useCallback((item: DecisionSignalItem, source: SelectedSignal['source']) => {
    pendingSelectedSignalIdRef.current = null;
    selectedSignalIdRef.current = item.id;
    const next = { source, item };
    selectedRef.current = next;
    setSelected(next);
    setDetailOpen(true);
    updateSearchParams({ signal: item.id }, true);
  }, [updateSearchParams]);

  const clearSelection = useCallback(() => {
    pendingSelectedSignalIdRef.current = null;
    selectedSignalIdRef.current = null;
    selectedRef.current = null;
    setSelected(null);
    setDetailOpen(false);
    updateSearchParams({ signal: null });
  }, [updateSearchParams]);

  const updateSelected = useCallback((
    updater: (current: SelectedSignal | null) => SelectedSignal | null,
  ) => {
    const current = selectedRef.current;
    const next = updater(current);
    if (next === current) return;
    if (next === null) {
      if (current !== null) clearSelection();
      return;
    }
    selectedRef.current = next;
    selectedSignalIdRef.current = next.item.id;
    setSelected(next);
  }, [clearSelection]);

  const reconcileOwnedSelection = useCallback((
    source: SelectedSignal['source'],
    items: DecisionSignalItem[],
  ) => {
    const restored = takePendingSelection(source, items);
    if (restored) {
      setSelected(restored);
      setDetailOpen(true);
      return;
    }
    const current = selectedRef.current;
    if (!current || current.source !== source) return;
    const refreshed = items.find((item) => item.id === current.item.id);
    if (refreshed) {
      const next = { source, item: refreshed };
      selectedRef.current = next;
      setSelected(next);
      return;
    }
    clearSelection();
  }, [clearSelection, takePendingSelection]);

  useEffect(() => {
    selectedSignalIdRef.current = selected?.item.id ?? null;
    selectedRef.current = selected;
  }, [selected]);

  return {
    selected,
    selectedSignalId: selected?.item.id ?? null,
    selectedSignalIdRef,
    detailOpen,
    selectSignal,
    closeDetail,
    openDetail,
    adoptSelected,
    clearSelection,
    updateSelected,
    setSelected,
    takePendingSelection,
    reconcileOwnedSelection,
  };
}

export default useDecisionSignalSelection;
