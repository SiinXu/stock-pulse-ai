// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useEffect, useMemo, useState } from 'react';
import { agentApi, type SkillInfo } from '../../api/agent';
import { historyApi } from '../../api/history';
import { useStockIndex } from '../../hooks/useStockIndex';
import type { HistorySearchItem } from '../../types/analysis';
import type { StockSuggestion } from '../../types/stockIndex';
import { searchStocks } from '../../utils/searchStocks';

export const COMMAND_PALETTE_DEBOUNCE_MS = 200;
export const COMMAND_PALETTE_RESULT_LIMIT = 5;
export const STOCK_SEARCH_MIN_LENGTH = 2;
export const REPORT_SEARCH_MIN_LENGTH = 3;

type ReportState = {
  query: string;
  items: HistorySearchItem[];
  loading: boolean;
  error: boolean;
};

type SkillCatalogState = {
  items: SkillInfo[];
  loading: boolean;
  error: boolean;
  loaded: boolean;
};

export type CommandPaletteSearchResult = {
  stocks: StockSuggestion[];
  reports: HistorySearchItem[];
  skills: SkillInfo[];
  isLoading: boolean;
  hasError: boolean;
  skillSearchError: boolean;
};

export function useCommandPaletteSearch(
  query: string,
  isOpen: boolean,
): CommandPaletteSearchResult {
  const normalizedQuery = query.trim();
  const [settledQuery, setSettledQuery] = useState('');
  const [reportState, setReportState] = useState<ReportState>({
    query: '',
    items: [],
    loading: false,
    error: false,
  });
  const [skillState, setSkillState] = useState<SkillCatalogState>({
    items: [],
    loading: false,
    error: false,
    loaded: false,
  });
  const { index, loading: stockIndexLoading, error: stockIndexError } = useStockIndex(isOpen);

  useEffect(() => {
    if (!isOpen || skillState.loaded) return undefined;

    let active = true;
    // Kick off skill catalog fetch; state transitions happen only in async handlers.
    // Do not list skillState.loading as a dependency: that re-run would cancel this fetch.
    void Promise.resolve().then(() => {
      if (!active) return;
      setSkillState((current) => (
        current.loaded || current.loading
          ? current
          : { ...current, loading: true, error: false }
      ));
    });
    void agentApi.getSkills().then((response) => {
      if (!active) return;
      setSkillState({
        items: response.skills,
        loading: false,
        error: false,
        loaded: true,
      });
    }).catch(() => {
      if (!active) return;
      setSkillState({
        items: [],
        loading: false,
        error: true,
        loaded: true,
      });
    });
    return () => {
      active = false;
    };
  }, [isOpen, skillState.loaded]);

  useEffect(() => {
    if (!isOpen || normalizedQuery.length < STOCK_SEARCH_MIN_LENGTH) {
      return undefined;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setSettledQuery(normalizedQuery);
      if (normalizedQuery.length < REPORT_SEARCH_MIN_LENGTH) return;

      setReportState({ query: normalizedQuery, items: [], loading: true, error: false });
      void historyApi.search(normalizedQuery, {
        limit: COMMAND_PALETTE_RESULT_LIMIT,
        signal: controller.signal,
      }).then((response) => {
        if (controller.signal.aborted) return;
        setReportState({
          query: normalizedQuery,
          items: response.items.slice(0, COMMAND_PALETTE_RESULT_LIMIT),
          loading: false,
          error: false,
        });
      }).catch(() => {
        if (controller.signal.aborted) return;
        setReportState({ query: normalizedQuery, items: [], loading: false, error: true });
      });
    }, COMMAND_PALETTE_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [isOpen, normalizedQuery]);

  const queryIsSettled = normalizedQuery === settledQuery;
  const searchingStocks = normalizedQuery.length >= STOCK_SEARCH_MIN_LENGTH;
  const stocks = useMemo(() => {
    if (!isOpen || !queryIsSettled || settledQuery.length < STOCK_SEARCH_MIN_LENGTH) {
      return [];
    }
    return searchStocks(settledQuery, index, { limit: COMMAND_PALETTE_RESULT_LIMIT });
  }, [index, isOpen, queryIsSettled, settledQuery]);
  const reports = (
    queryIsSettled && reportState.query === normalizedQuery
      ? reportState.items
      : []
  );
  const isDebouncing = isOpen && searchingStocks && !queryIsSettled;

  return {
    stocks,
    reports,
    skills: isOpen ? skillState.items : [],
    isLoading: isDebouncing || (
      searchingStocks && stockIndexLoading
    ) || (
      reportState.query === normalizedQuery
      && reportState.loading
    ) || (
      isOpen && skillState.loading && normalizedQuery.length > 0
    ),
    hasError: (
      reportState.query === normalizedQuery && reportState.error
    ) || Boolean(stockIndexError && searchingStocks),
    skillSearchError: isOpen && skillState.error,
  };
}
