// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import {
  SIGNAL_CENTER_HISTORY_VALUES,
  SIGNAL_CENTER_ROUTE_QUERY_KEYS,
  SIGNAL_CENTER_SCOPE_VALUES,
  SIGNAL_CENTER_TAB_VALUES,
  type SignalCenterHistoryView,
  type SignalCenterScope,
  type SignalCenterTab,
} from './routes';

const LEGACY_DECISION_SIGNAL_VIEW_VALUES = new Set(['signals', 'latest', 'timeline']);

export type SignalCenterRouteState = {
  scope: SignalCenterScope;
  tab: SignalCenterTab;
  history: SignalCenterHistoryView;
  createRule: boolean;
};

export type ParsedSignalCenterRouteState = {
  state: SignalCenterRouteState;
  normalizedParams: URLSearchParams;
  invalidKeys: string[];
};

export const DEFAULT_SIGNAL_CENTER_ROUTE_STATE: SignalCenterRouteState = {
  scope: SIGNAL_CENTER_SCOPE_VALUES.all,
  tab: SIGNAL_CENTER_TAB_VALUES.feed,
  history: SIGNAL_CENTER_HISTORY_VALUES.triggers,
  createRule: false,
};

function toSearchParams(search: string | URLSearchParams): URLSearchParams {
  return typeof search === 'string' ? new URLSearchParams(search) : new URLSearchParams(search);
}

function replaceOwnedParams(
  source: URLSearchParams,
  state: SignalCenterRouteState,
): URLSearchParams {
  const ownedKeys = new Set<string>(Object.values(SIGNAL_CENTER_ROUTE_QUERY_KEYS).filter(
    (key) => key !== SIGNAL_CENTER_ROUTE_QUERY_KEYS.stock,
  ));
  const next = new URLSearchParams();
  source.forEach((value, key) => {
    if (!ownedKeys.has(key)) next.append(key, value);
  });
  if (state.scope !== SIGNAL_CENTER_SCOPE_VALUES.all) {
    next.set(SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope, state.scope);
  }
  if (state.tab !== SIGNAL_CENTER_TAB_VALUES.feed) {
    next.set(SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab, state.tab);
  }
  if (
    state.tab === SIGNAL_CENTER_TAB_VALUES.history
    && state.history !== SIGNAL_CENTER_HISTORY_VALUES.triggers
  ) {
    next.set(SIGNAL_CENTER_ROUTE_QUERY_KEYS.history, state.history);
  }
  if (state.tab === SIGNAL_CENTER_TAB_VALUES.rules && state.createRule) {
    next.set(SIGNAL_CENTER_ROUTE_QUERY_KEYS.createRule, '1');
  }
  return next;
}

export function parseSignalCenterRouteState(
  search: string | URLSearchParams,
): ParsedSignalCenterRouteState {
  const source = toSearchParams(search);
  const normalizedSource = new URLSearchParams(source);
  const invalidKeys: string[] = [];

  const rawScope = source.get(SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope);
  const scopes = new Set<SignalCenterScope>(Object.values(SIGNAL_CENTER_SCOPE_VALUES));
  const scope = scopes.has(rawScope as SignalCenterScope)
    ? rawScope as SignalCenterScope
    : DEFAULT_SIGNAL_CENTER_ROUTE_STATE.scope;
  if (rawScope !== null && !scopes.has(rawScope as SignalCenterScope)) {
    invalidKeys.push(SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope);
  }

  const rawTab = source.get(SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab);
  const legacyStatsView = source.get('view') === 'stats';
  const tabs = new Set<SignalCenterTab>(Object.values(SIGNAL_CENTER_TAB_VALUES));
  const tab = tabs.has(rawTab as SignalCenterTab)
    ? rawTab as SignalCenterTab
    : legacyStatsView
      ? SIGNAL_CENTER_TAB_VALUES.review
      : DEFAULT_SIGNAL_CENTER_ROUTE_STATE.tab;
  if (rawTab !== null && !tabs.has(rawTab as SignalCenterTab)) {
    invalidKeys.push(SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab);
  }

  const rawHistory = source.get(SIGNAL_CENTER_ROUTE_QUERY_KEYS.history);
  const historyViews = new Set<SignalCenterHistoryView>(Object.values(SIGNAL_CENTER_HISTORY_VALUES));
  const history = historyViews.has(rawHistory as SignalCenterHistoryView)
    ? rawHistory as SignalCenterHistoryView
    : DEFAULT_SIGNAL_CENTER_ROUTE_STATE.history;
  if (rawHistory !== null && !historyViews.has(rawHistory as SignalCenterHistoryView)) {
    invalidKeys.push(SIGNAL_CENTER_ROUTE_QUERY_KEYS.history);
  }

  const rawCreateRule = source.get(SIGNAL_CENTER_ROUTE_QUERY_KEYS.createRule);
  const createRule = tab === SIGNAL_CENTER_TAB_VALUES.rules && rawCreateRule === '1';
  if (rawCreateRule !== null && rawCreateRule !== '1') {
    invalidKeys.push(SIGNAL_CENTER_ROUTE_QUERY_KEYS.createRule);
  }

  const state = { scope, tab, history, createRule };
  if (legacyStatsView) normalizedSource.delete('view');
  return {
    state,
    normalizedParams: replaceOwnedParams(normalizedSource, state),
    invalidKeys,
  };
}

export function setSignalCenterRouteState(
  search: string | URLSearchParams,
  state: SignalCenterRouteState,
): URLSearchParams {
  return replaceOwnedParams(toSearchParams(search), state);
}

function normalizeLegacyScope(searchParams: URLSearchParams): SignalCenterScope {
  return parseSignalCenterRouteState(searchParams).state.scope;
}

function replaceSearchParams(target: URLSearchParams, source: URLSearchParams): void {
  for (const key of [...target.keys()]) target.delete(key);
  source.forEach((value, key) => target.append(key, value));
}

export function mapLegacyDecisionSignalsSearchParams(searchParams: URLSearchParams): void {
  const view = searchParams.get('view');
  const tab = view === 'stats'
    ? SIGNAL_CENTER_TAB_VALUES.review
    : SIGNAL_CENTER_TAB_VALUES.feed;
  if (view === 'stats') searchParams.delete('view');
  if (view !== null && view !== 'stats' && !LEGACY_DECISION_SIGNAL_VIEW_VALUES.has(view)) {
    searchParams.delete('view');
  }
  const normalized = setSignalCenterRouteState(searchParams, {
    ...DEFAULT_SIGNAL_CENTER_ROUTE_STATE,
    scope: normalizeLegacyScope(searchParams),
    tab,
  });
  replaceSearchParams(searchParams, normalized);
}

export function mapLegacyAlertsSearchParams(searchParams: URLSearchParams): void {
  const legacyView = searchParams.get('view');
  const history = legacyView === 'notifications'
    ? SIGNAL_CENTER_HISTORY_VALUES.notifications
    : SIGNAL_CENTER_HISTORY_VALUES.triggers;
  const tab = legacyView === 'history' || legacyView === 'notifications'
    ? SIGNAL_CENTER_TAB_VALUES.history
    : SIGNAL_CENTER_TAB_VALUES.rules;
  searchParams.delete('view');
  const normalized = setSignalCenterRouteState(searchParams, {
    ...DEFAULT_SIGNAL_CENTER_ROUTE_STATE,
    scope: normalizeLegacyScope(searchParams),
    tab,
    history,
  });
  replaceSearchParams(searchParams, normalized);
}
