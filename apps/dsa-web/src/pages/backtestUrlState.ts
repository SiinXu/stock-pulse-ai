// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Backtest page URL schema (UI-03A / #879 A1).
 *
 * Wire keys for core filters match `RESEARCH_BACKTEST_ROUTE_QUERY_KEYS` so
 * deepLink / sessionContinuity parsers stay compatible. Strategy run options
 * (`minAge`, `limit`) are page-owned replace-mode params via urlState.
 *
 * Core filter *validation* still goes through `parseResearchBacktestRouteState`
 * on mount; writes go through `writeParams` so this page does not invent a
 * parallel search-param writer.
 */
import {
  RESEARCH_BACKTEST_LIMITS,
  RESEARCH_BACKTEST_PHASE_VALUES,
  RESEARCH_BACKTEST_ROUTE_QUERY_KEYS,
} from '../routing/routes';
import {
  parseResearchBacktestRouteState,
  type ResearchBacktestRouteState,
} from '../routing/researchRouteState';
import type { BacktestPhaseFilter } from '../types/backtest';
import {
  defineUrlStateSchema,
  enumParam,
  numberParam,
  readParams,
  stringParam,
  writeParams,
} from '../utils/urlState';

export type BacktestFilterSnapshot = ResearchBacktestRouteState;

/** Default candidate universe size when omitted from the URL. */
export const DEFAULT_CANDIDATE_LIMIT = 200;

export type BacktestStrategySnapshot = {
  minAgeDays: number | null;
  limit: number;
};

export const BACKTEST_URL_SCHEMA = defineUrlStateSchema({
  code: stringParam({ name: RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code, default: '', history: 'replace' }),
  window: numberParam({
    name: RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.window,
    default: null,
    min: 1,
    max: RESEARCH_BACKTEST_LIMITS.maxWindowDays,
    history: 'replace',
  }),
  from: stringParam({ name: RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.from, default: '', history: 'replace' }),
  to: stringParam({ name: RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.to, default: '', history: 'replace' }),
  phase: enumParam({
    name: RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.phase,
    values: [
      RESEARCH_BACKTEST_PHASE_VALUES.all,
      RESEARCH_BACKTEST_PHASE_VALUES.premarket,
      RESEARCH_BACKTEST_PHASE_VALUES.intraday,
      RESEARCH_BACKTEST_PHASE_VALUES.postmarket,
      RESEARCH_BACKTEST_PHASE_VALUES.unknown,
    ],
    default: RESEARCH_BACKTEST_PHASE_VALUES.all,
    history: 'replace',
  }),
  page: numberParam({ name: RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.page, default: 1, min: 1, history: 'replace' }),
  minAge: numberParam({ name: 'minAge', default: null, min: 0, max: 365, history: 'replace' }),
  limit: numberParam({ name: 'limit', default: DEFAULT_CANDIDATE_LIMIT, min: 1, max: 2000, history: 'replace' }),
});

export function getInitialBacktestFilters(
  search = typeof window === 'undefined' ? '' : window.location.search,
): BacktestFilterSnapshot {
  return parseResearchBacktestRouteState(search).state;
}

export function getInitialBacktestStrategy(
  search = typeof window === 'undefined' ? '' : window.location.search,
): { minAgeDays: string; candidateLimit: string } {
  const values = readParams(BACKTEST_URL_SCHEMA, search);
  return {
    minAgeDays: values.minAge == null ? '' : String(values.minAge),
    candidateLimit: String(values.limit ?? DEFAULT_CANDIDATE_LIMIT),
  };
}

export function getBacktestFiltersLocation(
  filters: BacktestFilterSnapshot,
  strategy?: BacktestStrategySnapshot,
): string | null {
  if (typeof window === 'undefined') return null;
  const patch: {
    code: string;
    window: number | null;
    from: string;
    to: string;
    phase: BacktestPhaseFilter;
    page: number | null;
    minAge?: number | null;
    limit?: number | null;
  } = {
    code: filters.code,
    window: filters.windowDays ?? null,
    from: filters.startDate,
    to: filters.endDate,
    phase: filters.phase,
    page: filters.page,
  };
  if (strategy) {
    patch.minAge = strategy.minAgeDays;
    patch.limit = strategy.limit;
  }
  const written = writeParams(BACKTEST_URL_SCHEMA, patch, {
    search: window.location.search,
    history: 'replace',
  });
  const url = new URL(window.location.href);
  url.search = written.params.toString();
  return `${url.pathname}${url.search}${url.hash}`;
}
