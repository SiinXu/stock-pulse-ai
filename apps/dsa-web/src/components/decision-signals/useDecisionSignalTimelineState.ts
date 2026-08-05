// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useReducer } from 'react';
import type { ParsedApiError } from '../../api/error';
import type { DecisionSignalItem } from '../../types/decisionSignals';
import {
  getInitialTimelineFilters,
  type AppliedTimelineContext,
  type TimelineFilters,
} from './decisionSignalsPageModel';

export type DecisionSignalTimelineState = {
  filters: TimelineFilters;
  appliedContext: AppliedTimelineContext | null;
  items: DecisionSignalItem[];
  searched: boolean;
  loading: boolean;
  error: ParsedApiError | null;
  truncated: boolean;
};

type DecisionSignalTimelineAction =
  | { type: 'setFilters'; filters: TimelineFilters | ((current: TimelineFilters) => TimelineFilters) }
  | { type: 'replaceFilters'; filters: TimelineFilters }
  | { type: 'reset' }
  | { type: 'loadStart' }
  | {
    type: 'loadSuccess';
    items: DecisionSignalItem[];
    truncated: boolean;
    appliedContext: AppliedTimelineContext;
  }
  | { type: 'loadFailure'; error: ParsedApiError }
  | { type: 'setItems'; items: DecisionSignalItem[] | ((current: DecisionSignalItem[]) => DecisionSignalItem[]) };

function resolveFilters(
  current: TimelineFilters,
  next: TimelineFilters | ((current: TimelineFilters) => TimelineFilters),
): TimelineFilters {
  return typeof next === 'function' ? next(current) : next;
}

function resolveItems(
  current: DecisionSignalItem[],
  next: DecisionSignalItem[] | ((current: DecisionSignalItem[]) => DecisionSignalItem[]),
): DecisionSignalItem[] {
  return typeof next === 'function' ? next(current) : next;
}

function timelineReducer(
  state: DecisionSignalTimelineState,
  action: DecisionSignalTimelineAction,
): DecisionSignalTimelineState {
  switch (action.type) {
    case 'setFilters':
      return { ...state, filters: resolveFilters(state.filters, action.filters) };
    case 'replaceFilters':
      return { ...state, filters: action.filters };
    case 'reset':
      return {
        ...state,
        items: [],
        searched: false,
        loading: false,
        error: null,
        truncated: false,
        appliedContext: null,
      };
    case 'loadStart':
      return {
        ...state,
        loading: true,
        error: null,
        searched: true,
        items: [],
        truncated: false,
        appliedContext: null,
      };
    case 'loadSuccess':
      return {
        ...state,
        loading: false,
        error: null,
        items: action.items,
        truncated: action.truncated,
        appliedContext: action.appliedContext,
      };
    case 'loadFailure':
      return {
        ...state,
        loading: false,
        items: [],
        truncated: false,
        error: action.error,
      };
    case 'setItems':
      return { ...state, items: resolveItems(state.items, action.items) };
    default:
      return state;
  }
}

function createInitialTimelineState(search?: string): DecisionSignalTimelineState {
  return {
    filters: getInitialTimelineFilters(search),
    appliedContext: null,
    items: [],
    searched: false,
    loading: false,
    error: null,
    truncated: false,
  };
}

export function useDecisionSignalTimelineState(search?: string) {
  const [state, dispatch] = useReducer(timelineReducer, search, createInitialTimelineState);

  const setFilters = useCallback((filters: TimelineFilters | ((current: TimelineFilters) => TimelineFilters)) => {
    dispatch({ type: 'setFilters', filters });
  }, []);

  const replaceFilters = useCallback((filters: TimelineFilters) => {
    dispatch({ type: 'replaceFilters', filters });
  }, []);

  const reset = useCallback(() => {
    dispatch({ type: 'reset' });
  }, []);

  const setItems = useCallback((
    items: DecisionSignalItem[] | ((current: DecisionSignalItem[]) => DecisionSignalItem[]),
  ) => {
    dispatch({ type: 'setItems', items });
  }, []);

  return {
    ...state,
    dispatch,
    setFilters,
    replaceFilters,
    reset,
    setItems,
  };
}
