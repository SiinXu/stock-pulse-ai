// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  SIGNAL_CENTER_HISTORY_VALUES,
  SIGNAL_CENTER_SCOPE_VALUES,
  SIGNAL_CENTER_TAB_VALUES,
  buildSignalCenterHref,
} from '../routes';
import {
  DEFAULT_SIGNAL_CENTER_ROUTE_STATE,
  mapLegacyAlertsSearchParams,
  mapLegacyDecisionSignalsSearchParams,
  parseSignalCenterRouteState,
  setSignalCenterRouteState,
} from '../signalCenterRouteState';

describe('Signal Center route state', () => {
  it('builds canonical scope, tab, history, and create-rule links', () => {
    expect(buildSignalCenterHref()).toBe('/signals');
    expect(buildSignalCenterHref({ scope: SIGNAL_CENTER_SCOPE_VALUES.holdings }))
      .toBe('/signals?scope=holdings');
    expect(buildSignalCenterHref({
      scope: SIGNAL_CENTER_SCOPE_VALUES.watchlist,
      tab: SIGNAL_CENTER_TAB_VALUES.history,
      history: SIGNAL_CENTER_HISTORY_VALUES.notifications,
    })).toBe('/signals?scope=watchlist&tab=history&history=notifications');
    expect(buildSignalCenterHref({
      tab: SIGNAL_CENTER_TAB_VALUES.rules,
      createRule: true,
      stock: ' AAPL ',
    })).toBe('/signals?tab=rules&createRule=1&stock=AAPL');
    expect(buildSignalCenterHref({ createRule: true }))
      .toBe('/signals?tab=rules&createRule=1');
    expect(buildSignalCenterHref({ history: SIGNAL_CENTER_HISTORY_VALUES.notifications }))
      .toBe('/signals?tab=history&history=notifications');
  });

  it('normalizes malformed owned state without dropping unrelated context', () => {
    const parsed = parseSignalCenterRouteState(
      '?scope=portfolio&tab=unknown&history=delivery&createRule=yes&stock=AAPL&keep=yes',
    );

    expect(parsed.state).toEqual(DEFAULT_SIGNAL_CENTER_ROUTE_STATE);
    expect(parsed.normalizedParams.toString()).toBe('stock=AAPL&keep=yes');
    expect(parsed.invalidKeys).toEqual(['scope', 'tab', 'history', 'createRule']);
  });

  it('keeps URL state authoritative while preserving legacy signal filters', () => {
    const next = setSignalCenterRouteState(
      '?market=us&view=timeline&scope=watchlist&tab=history',
      {
        ...DEFAULT_SIGNAL_CENTER_ROUTE_STATE,
        scope: SIGNAL_CENTER_SCOPE_VALUES.holdings,
        tab: SIGNAL_CENTER_TAB_VALUES.review,
      },
    );

    expect(next.toString()).toBe('market=us&view=timeline&scope=holdings&tab=review');
  });

  it('normalizes the retired stats view on canonical Signal Center links', () => {
    const parsed = parseSignalCenterRouteState('?view=stats&scope=holdings&keep=yes');

    expect(parsed.state.tab).toBe(SIGNAL_CENTER_TAB_VALUES.review);
    expect(parsed.normalizedParams.toString()).toBe('keep=yes&scope=holdings&tab=review');
  });

  it.each([
    ['?view=signals&stock=AAPL', 'view=signals&stock=AAPL'],
    ['?view=timeline&scope=holdings', 'view=timeline&scope=holdings'],
    ['?view=stats&scope=watchlist', 'scope=watchlist&tab=review'],
    ['?view=unknown&keep=yes', 'keep=yes'],
  ])('maps legacy Decision Signals search %s', (search, expected) => {
    const params = new URLSearchParams(search);
    mapLegacyDecisionSignalsSearchParams(params);
    expect(params.toString()).toBe(expected);
  });

  it.each([
    ['', 'tab=rules'],
    ['?view=rules&scope=holdings', 'scope=holdings&tab=rules'],
    ['?view=history&keep=yes', 'keep=yes&tab=history'],
    ['?view=notifications&scope=watchlist', 'scope=watchlist&tab=history&history=notifications'],
  ])('maps legacy Alerts search %s', (search, expected) => {
    const params = new URLSearchParams(search);
    mapLegacyAlertsSearchParams(params);
    expect(params.toString()).toBe(expected);
  });
});
