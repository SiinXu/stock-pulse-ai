// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import {
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react';
import { useSearchParams } from 'react-router-dom';

export interface FilterQueryCodec<T> {
  /** Reads and normalizes the filter values owned by this pattern. */
  read: (searchParams: URLSearchParams) => T;
  /** Writes only owned keys; unrelated query state must remain untouched. */
  write: (searchParams: URLSearchParams, value: T) => void;
}

export interface UseFilterQueryStateOptions<T> {
  codec: FilterQueryCodec<T>;
  defaultValue: T;
  equals: (left: T, right: T) => boolean;
  getActiveCount?: (value: T) => number;
  clearKeysOnApply?: readonly string[];
  navigation?: 'push' | 'replace';
}

export interface FilterQueryState<T> {
  applied: T;
  draft: T;
  setDraft: Dispatch<SetStateAction<T>>;
  isDirty: boolean;
  activeCount: number;
  draftActiveCount: number;
  applyDraft: () => boolean;
  applyValue: (value: T) => boolean;
  resetDraft: () => void;
  resetApplied: () => boolean;
  discardDraft: () => void;
}

/**
 * Keeps applied filters in React Router search params while drafts stay local.
 * The codec owns normalization and key deletion; the hook preserves all query
 * keys outside that codec and resynchronizes drafts after browser navigation.
 */
export function useFilterQueryState<T>({
  codec,
  defaultValue,
  equals,
  getActiveCount = () => 0,
  clearKeysOnApply = [],
  navigation = 'push',
}: UseFilterQueryStateOptions<T>): FilterQueryState<T> {
  const [searchParams, setSearchParams] = useSearchParams();
  const applied = codec.read(new URLSearchParams(searchParams));
  const [draftState, setDraftState] = useState(() => ({
    applied,
    value: applied,
  }));
  // Adjust before children render so browser navigation never exposes a stale
  // draft for one frame. The equality guard prevents an update on normal renders.
  const appliedChanged = !equals(draftState.applied, applied);
  if (appliedChanged) {
    setDraftState({ applied, value: applied });
  }
  const draft = appliedChanged ? applied : draftState.value;
  const setDraft: Dispatch<SetStateAction<T>> = (nextValue) => {
    setDraftState((current) => {
      const currentValue = equals(current.applied, applied) ? current.value : applied;
      const value = typeof nextValue === 'function'
        ? (nextValue as (previous: T) => T)(currentValue)
        : nextValue;
      return { applied, value };
    });
  };

  const commit = (value: T): boolean => {
    if (equals(value, applied)) {
      setDraft(value);
      return false;
    }

    setDraft(value);
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      clearKeysOnApply.forEach((key) => next.delete(key));
      codec.write(next, value);
      return next;
    }, { replace: navigation === 'replace' });
    return true;
  };

  const applyDraft = () => commit(draft);
  const resetDraft = () => setDraft(defaultValue);
  const resetApplied = () => commit(defaultValue);
  const discardDraft = () => setDraft(applied);

  return {
    applied,
    draft,
    setDraft,
    isDirty: !equals(draft, applied),
    activeCount: getActiveCount(applied),
    draftActiveCount: getActiveCount(draft),
    applyDraft,
    applyValue: commit,
    resetDraft,
    resetApplied,
    discardDraft,
  };
}
