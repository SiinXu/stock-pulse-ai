// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useReducer } from 'react';
import type { ParsedApiError } from '../../api/error';
import type { DecisionSignalItem } from '../../types/decisionSignals';
import {
  getInitialFilters,
  getInitialPage,
  type ListFilters,
} from './decisionSignalsPageModel';

export type DecisionSignalListState = {
  filters: ListFilters;
  appliedFilters: ListFilters;
  page: number;
  items: DecisionSignalItem[];
  total: number;
  loading: boolean;
  error: ParsedApiError | null;
};

type DecisionSignalListAction =
  | { type: 'setFilters'; filters: ListFilters | ((current: ListFilters) => ListFilters) }
  | { type: 'applyFilters'; filters: ListFilters }
  | { type: 'setPage'; page: number }
  | { type: 'loadStart' }
  | {
    type: 'loadSuccess';
    items: DecisionSignalItem[];
    total: number;
    page?: number;
    error?: ParsedApiError | null;
  }
  | { type: 'loadFailure'; error: ParsedApiError; page?: number }
  | { type: 'loadEnd' }
  | { type: 'clearError' };

function resolveFilters(
  current: ListFilters,
  next: ListFilters | ((current: ListFilters) => ListFilters),
): ListFilters {
  return typeof next === 'function' ? next(current) : next;
}

function listReducer(state: DecisionSignalListState, action: DecisionSignalListAction): DecisionSignalListState {
  switch (action.type) {
    case 'setFilters':
      return { ...state, filters: resolveFilters(state.filters, action.filters) };
    case 'applyFilters':
      return {
        ...state,
        filters: action.filters,
        appliedFilters: action.filters,
        page: 1,
      };
    case 'setPage':
      return { ...state, page: action.page };
    case 'loadStart':
      // Match page behavior: loading starts without clearing the prior error until a result arrives.
      return { ...state, loading: true };
    case 'loadSuccess':
      return {
        ...state,
        loading: false,
        error: action.error ?? null,
        items: action.items,
        total: action.total,
        ...(action.page !== undefined ? { page: action.page } : {}),
      };
    case 'loadFailure':
      return {
        ...state,
        loading: false,
        error: action.error,
        items: [],
        total: 0,
        ...(action.page !== undefined ? { page: action.page } : {}),
      };
    case 'loadEnd':
      return { ...state, loading: false };
    case 'clearError':
      return { ...state, error: null };
    default:
      return state;
  }
}

function createInitialListState(search?: string): DecisionSignalListState {
  const filters = getInitialFilters(search);
  return {
    filters,
    appliedFilters: filters,
    page: getInitialPage(search),
    items: [],
    total: 0,
    loading: true,
    error: null,
  };
}

export function useDecisionSignalListState(search?: string) {
  const [state, dispatch] = useReducer(listReducer, search, createInitialListState);

  const setFilters = useCallback((filters: ListFilters | ((current: ListFilters) => ListFilters)) => {
    dispatch({ type: 'setFilters', filters });
  }, []);

  const applyFilters = useCallback((filters: ListFilters) => {
    dispatch({ type: 'applyFilters', filters });
  }, []);

  const setPage = useCallback((page: number) => {
    dispatch({ type: 'setPage', page });
  }, []);

  return {
    ...state,
    dispatch,
    setFilters,
    applyFilters,
    setPage,
  };
}
