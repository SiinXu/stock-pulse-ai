// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { BacktestPhaseFilter } from '../types/backtest';
import { normalizeStockCode } from '../utils/stockCode';
import { validateStockCode } from '../utils/validation';
import {
  RESEARCH_BACKTEST_LIMITS,
  RESEARCH_BACKTEST_PHASE_VALUES,
  RESEARCH_BACKTEST_ROUTE_QUERY_KEYS,
  RESEARCH_DISCOVER_DEFAULT_VALUES,
  RESEARCH_DISCOVER_LIMITS,
  RESEARCH_DISCOVER_MARKET_VALUES,
  RESEARCH_DISCOVER_ROUTE_QUERY_KEYS,
} from './routes';

const SAFE_STRATEGY_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;
const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const BACKTEST_PHASES = new Set<BacktestPhaseFilter>(
  Object.values(RESEARCH_BACKTEST_PHASE_VALUES),
);

export type ResearchDiscoverRouteState = {
  market: string;
  strategy: string;
  maxResults: number;
};

export const DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE: ResearchDiscoverRouteState = {
  market: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
  strategy: RESEARCH_DISCOVER_DEFAULT_VALUES.strategy,
  maxResults: RESEARCH_DISCOVER_DEFAULT_VALUES.count,
};

export type ResearchBacktestRouteState = {
  code: string;
  windowDays?: number;
  startDate: string;
  endDate: string;
  phase: BacktestPhaseFilter;
  page: number;
};

export type ParsedResearchRouteState<T> = {
  state: T;
  ownedParams: URLSearchParams;
  normalizedParams: URLSearchParams;
  hasOwnedParameters: boolean;
  invalidKeys: string[];
};

function toSearchParams(search: string | URLSearchParams): URLSearchParams {
  return typeof search === 'string' ? new URLSearchParams(search) : new URLSearchParams(search);
}

function parsePositiveInteger(value: string | null, maximum = Number.MAX_SAFE_INTEGER): number | null {
  if (!value || !/^\d+$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 && parsed <= maximum ? parsed : null;
}

function isValidIsoDate(value: string): boolean {
  if (!ISO_DATE_PATTERN.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function normalizeSafeStockCode(value: string | null): string | null {
  if (!value) return null;
  const normalized = normalizeStockCode(value).toUpperCase();
  const validation = validateStockCode(normalized);
  return validation.valid ? normalizeStockCode(validation.normalized).toUpperCase() : null;
}

function replaceOwnedParams(
  source: URLSearchParams,
  keys: readonly string[],
  ownedParams: URLSearchParams,
): URLSearchParams {
  const ownedKeys = new Set(keys);
  const next = new URLSearchParams();
  let insertedOwnedParams = false;
  source.forEach((value, key) => {
    if (ownedKeys.has(key)) {
      if (!insertedOwnedParams) {
        ownedParams.forEach((ownedValue, ownedKey) => next.set(ownedKey, ownedValue));
        insertedOwnedParams = true;
      }
      return;
    }
    next.append(key, value);
  });
  if (!insertedOwnedParams) {
    ownedParams.forEach((value, key) => next.set(key, value));
  }
  return next;
}

function encodeResearchDiscoverOwnedParams(
  state: ResearchDiscoverRouteState,
  explicitSource?: URLSearchParams,
): URLSearchParams {
  const ownedParams = new URLSearchParams();
  if (state.market !== DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE.market) {
    ownedParams.set(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market, state.market);
  }
  if (state.strategy !== DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE.strategy) {
    ownedParams.set(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy, state.strategy);
  }
  if (state.maxResults !== DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE.maxResults) {
    ownedParams.set(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count, String(state.maxResults));
  }

  // Keep explicit default-valued state distinguishable from a bare URL so a
  // stale active-task fallback cannot reclaim ownership after refresh.
  if (ownedParams.toString() || !explicitSource) return ownedParams;
  if (explicitSource.has(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market)) {
    ownedParams.set(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market, state.market);
  }
  if (explicitSource.has(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy)) {
    ownedParams.set(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy, state.strategy);
  }
  if (explicitSource.has(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count)) {
    ownedParams.set(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count, String(state.maxResults));
  }
  return ownedParams;
}

export function parseResearchDiscoverRouteState(
  search: string | URLSearchParams,
): ParsedResearchRouteState<ResearchDiscoverRouteState> {
  const source = toSearchParams(search);
  const ownedKeys = Object.values(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS);
  const hasOwnedParameters = ownedKeys.some((key) => source.has(key));
  const invalidKeys: string[] = [];

  const rawMarket = source.get(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market);
  const market = DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE.market;
  if (rawMarket !== null && rawMarket !== RESEARCH_DISCOVER_MARKET_VALUES.china) {
    invalidKeys.push(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market);
  }

  const rawStrategy = source.get(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy)?.trim() ?? '';
  let strategy = DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE.strategy;
  if (rawStrategy) {
    if (SAFE_STRATEGY_PATTERN.test(rawStrategy)) {
      strategy = rawStrategy;
    } else {
      invalidKeys.push(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy);
    }
  }

  const rawCount = source.get(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count);
  const parsedCount = parsePositiveInteger(rawCount, RESEARCH_DISCOVER_LIMITS.maxCount);
  let maxResults = DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE.maxResults;
  if (rawCount !== null) {
    if (parsedCount !== null) {
      maxResults = parsedCount;
    } else {
      invalidKeys.push(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count);
    }
  }

  const state = { market, strategy, maxResults };
  const ownedParams = encodeResearchDiscoverOwnedParams(state, source);

  return {
    state,
    ownedParams,
    normalizedParams: replaceOwnedParams(source, ownedKeys, ownedParams),
    hasOwnedParameters,
    invalidKeys,
  };
}

export function normalizeResearchDiscoverRouteState(
  state: ResearchDiscoverRouteState,
): ResearchDiscoverRouteState {
  const params = new URLSearchParams({
    [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market]: state.market,
    [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: state.strategy,
    [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: String(state.maxResults),
  });
  return parseResearchDiscoverRouteState(params).state;
}

export function resolveResearchDiscoverRouteState(
  search: string | URLSearchParams,
  fallback?: ResearchDiscoverRouteState | null,
): ParsedResearchRouteState<ResearchDiscoverRouteState> {
  const parsed = parseResearchDiscoverRouteState(search);
  if (parsed.hasOwnedParameters || !fallback) return parsed;
  return { ...parsed, state: normalizeResearchDiscoverRouteState(fallback) };
}

export function setResearchDiscoverRouteState(
  search: string | URLSearchParams,
  state: ResearchDiscoverRouteState,
): URLSearchParams {
  const source = toSearchParams(search);
  const normalized = normalizeResearchDiscoverRouteState(state);
  return replaceOwnedParams(
    source,
    Object.values(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS),
    encodeResearchDiscoverOwnedParams(normalized, source),
  );
}

export function parseResearchBacktestRouteState(
  search: string | URLSearchParams,
): ParsedResearchRouteState<ResearchBacktestRouteState> {
  const source = toSearchParams(search);
  const ownedKeys = Object.values(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS);
  const hasOwnedParameters = ownedKeys.some((key) => source.has(key));
  const invalidKeys: string[] = [];

  const rawCode = source.get(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code);
  const normalizedCode = normalizeSafeStockCode(rawCode);
  if (rawCode !== null && normalizedCode === null) invalidKeys.push(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code);

  const rawWindow = source.get(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.window);
  const windowDays = parsePositiveInteger(rawWindow, RESEARCH_BACKTEST_LIMITS.maxWindowDays) ?? undefined;
  if (rawWindow !== null && windowDays === undefined) invalidKeys.push(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.window);

  const rawFrom = source.get(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.from);
  const rawTo = source.get(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.to);
  let startDate = rawFrom && isValidIsoDate(rawFrom) ? rawFrom : '';
  let endDate = rawTo && isValidIsoDate(rawTo) ? rawTo : '';
  if (rawFrom !== null && !startDate) invalidKeys.push(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.from);
  if (rawTo !== null && !endDate) invalidKeys.push(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.to);
  if (startDate && endDate && startDate > endDate) {
    invalidKeys.push(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.from, RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.to);
    startDate = '';
    endDate = '';
  }

  const rawPhase = source.get(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.phase) as BacktestPhaseFilter | null;
  let phase: BacktestPhaseFilter = RESEARCH_BACKTEST_PHASE_VALUES.all;
  if (rawPhase !== null && rawPhase !== RESEARCH_BACKTEST_PHASE_VALUES.all) {
    if (BACKTEST_PHASES.has(rawPhase)) {
      phase = rawPhase;
    } else {
      invalidKeys.push(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.phase);
    }
  }

  const rawPage = source.get(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.page);
  const parsedPage = parsePositiveInteger(rawPage);
  let page = 1;
  if (rawPage !== null) {
    if (parsedPage !== null) {
      page = parsedPage;
    } else {
      invalidKeys.push(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.page);
    }
  }

  const ownedParams = new URLSearchParams();
  if (normalizedCode) ownedParams.set(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code, normalizedCode);
  if (windowDays) ownedParams.set(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.window, String(windowDays));
  if (startDate) ownedParams.set(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.from, startDate);
  if (endDate) ownedParams.set(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.to, endDate);
  if (phase !== RESEARCH_BACKTEST_PHASE_VALUES.all) {
    ownedParams.set(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.phase, phase);
  }
  if (page > 1) ownedParams.set(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.page, String(page));

  return {
    state: {
      code: normalizedCode ?? '',
      windowDays,
      startDate,
      endDate,
      phase,
      page,
    },
    ownedParams,
    normalizedParams: replaceOwnedParams(source, ownedKeys, ownedParams),
    hasOwnedParameters,
    invalidKeys: [...new Set(invalidKeys)],
  };
}

export function setResearchBacktestRouteState(
  search: string | URLSearchParams,
  state: ResearchBacktestRouteState,
): URLSearchParams {
  const encoded = parseResearchBacktestRouteState(new URLSearchParams({
    [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code]: state.code,
    [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.window]: state.windowDays ? String(state.windowDays) : '',
    [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.from]: state.startDate,
    [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.to]: state.endDate,
    [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.phase]: state.phase,
    [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.page]: String(state.page),
  }));
  return replaceOwnedParams(
    toSearchParams(search),
    Object.values(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS),
    encoded.ownedParams,
  );
}
