// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  APP_ROUTE_PATHS,
  LEGACY_ALERTS_VIEW_VALUES,
  SIGNAL_CENTER_CREATE_RULE_VALUES,
  SIGNAL_CENTER_HISTORY_VALUES,
  SIGNAL_CENTER_ROUTE_QUERY_KEYS,
  SIGNAL_CENTER_SCOPE_VALUES,
  SIGNAL_CENTER_TAB_VALUES,
  SIGNAL_FEED_ROUTE_QUERY_KEYS,
  SIGNAL_FEED_VIEW_VALUES,
  buildSignalCenterHref,
} from '../routes';
import {
  DEFAULT_SIGNAL_CENTER_ROUTE_STATE,
  mapLegacyAlertsSearchParams,
  mapLegacyDecisionSignalsSearchParams,
  parseSignalCenterRouteState,
  setSignalCenterRouteState,
} from '../signalCenterRouteState';

function toQuery(entries: Record<string, string>): string {
  return new URLSearchParams(entries).toString();
}

function toSearch(entries: Record<string, string>): string {
  const query = toQuery(entries);
  return query ? `?${query}` : '';
}

function signalCenterHref(entries: Record<string, string> = {}): string {
  return `${APP_ROUTE_PATHS.signals}${toSearch(entries)}`;
}

describe('Signal Center route state', () => {
  it('builds canonical scope, tab, history, and create-rule links', () => {
    expect(buildSignalCenterHref()).toBe(APP_ROUTE_PATHS.signals);
    expect(buildSignalCenterHref({
      scope: SIGNAL_CENTER_SCOPE_VALUES.all,
      tab: SIGNAL_CENTER_TAB_VALUES.feed,
    })).toBe(signalCenterHref({
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.all,
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab]: SIGNAL_CENTER_TAB_VALUES.feed,
    }));
    expect(buildSignalCenterHref({ scope: SIGNAL_CENTER_SCOPE_VALUES.holdings }))
      .toBe(signalCenterHref({
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.holdings,
      }));
    expect(buildSignalCenterHref({
      scope: SIGNAL_CENTER_SCOPE_VALUES.watchlist,
      tab: SIGNAL_CENTER_TAB_VALUES.history,
      history: SIGNAL_CENTER_HISTORY_VALUES.notifications,
    })).toBe(signalCenterHref({
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.watchlist,
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab]: SIGNAL_CENTER_TAB_VALUES.history,
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.history]: SIGNAL_CENTER_HISTORY_VALUES.notifications,
    }));
    expect(buildSignalCenterHref({
      tab: SIGNAL_CENTER_TAB_VALUES.rules,
      createRule: true,
      stock: ' AAPL ',
    })).toBe(signalCenterHref({
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab]: SIGNAL_CENTER_TAB_VALUES.rules,
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.createRule]: SIGNAL_CENTER_CREATE_RULE_VALUES.requested,
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.stock]: 'AAPL',
    }));
    expect(buildSignalCenterHref({ createRule: true }))
      .toBe(signalCenterHref({
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab]: SIGNAL_CENTER_TAB_VALUES.rules,
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.createRule]: SIGNAL_CENTER_CREATE_RULE_VALUES.requested,
      }));
    expect(buildSignalCenterHref({ history: SIGNAL_CENTER_HISTORY_VALUES.notifications }))
      .toBe(signalCenterHref({
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab]: SIGNAL_CENTER_TAB_VALUES.history,
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.history]: SIGNAL_CENTER_HISTORY_VALUES.notifications,
      }));
  });

  it('preserves explicit default ownership while normalizing Signal Center state', () => {
    const explicitDefaults = new URLSearchParams({
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.all,
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab]: SIGNAL_CENTER_TAB_VALUES.feed,
    });

    const parsed = parseSignalCenterRouteState(explicitDefaults);

    expect(parsed.state).toEqual(DEFAULT_SIGNAL_CENTER_ROUTE_STATE);
    expect(parsed.normalizedParams.toString()).toBe(explicitDefaults.toString());
    expect(setSignalCenterRouteState(explicitDefaults, parsed.state).toString())
      .toBe(explicitDefaults.toString());
  });

  it('normalizes malformed owned state without dropping unrelated context', () => {
    const parsed = parseSignalCenterRouteState(
      toSearch({
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: 'portfolio',
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab]: 'unknown',
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.history]: 'delivery',
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.createRule]: 'yes',
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.stock]: 'AAPL',
        keep: 'yes',
      }),
    );

    expect(parsed.state).toEqual(DEFAULT_SIGNAL_CENTER_ROUTE_STATE);
    expect(parsed.normalizedParams.toString()).toBe(toQuery({
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.stock]: 'AAPL',
      keep: 'yes',
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.all,
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab]: SIGNAL_CENTER_TAB_VALUES.feed,
    }));
    expect(parsed.invalidKeys).toEqual([
      SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope,
      SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab,
      SIGNAL_CENTER_ROUTE_QUERY_KEYS.history,
      SIGNAL_CENTER_ROUTE_QUERY_KEYS.createRule,
    ]);
  });

  it('keeps URL state authoritative while preserving legacy signal filters', () => {
    const next = setSignalCenterRouteState(
      toSearch({
        market: 'us',
        [SIGNAL_FEED_ROUTE_QUERY_KEYS.view]: SIGNAL_FEED_VIEW_VALUES.timeline,
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.watchlist,
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab]: SIGNAL_CENTER_TAB_VALUES.history,
      }),
      {
        ...DEFAULT_SIGNAL_CENTER_ROUTE_STATE,
        scope: SIGNAL_CENTER_SCOPE_VALUES.holdings,
        tab: SIGNAL_CENTER_TAB_VALUES.review,
      },
    );

    expect(next.toString()).toBe(toQuery({
      market: 'us',
      [SIGNAL_FEED_ROUTE_QUERY_KEYS.view]: SIGNAL_FEED_VIEW_VALUES.timeline,
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.holdings,
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab]: SIGNAL_CENTER_TAB_VALUES.review,
    }));
  });

  it('normalizes the retired stats view on canonical Signal Center links', () => {
    const parsed = parseSignalCenterRouteState(toSearch({
      [SIGNAL_FEED_ROUTE_QUERY_KEYS.view]: SIGNAL_FEED_VIEW_VALUES.stats,
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.holdings,
      keep: 'yes',
    }));

    expect(parsed.state.tab).toBe(SIGNAL_CENTER_TAB_VALUES.review);
    expect(parsed.normalizedParams.toString()).toBe(toQuery({
      keep: 'yes',
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.holdings,
      [SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab]: SIGNAL_CENTER_TAB_VALUES.review,
    }));
  });

  it.each([
    [
      toSearch({
        [SIGNAL_FEED_ROUTE_QUERY_KEYS.view]: SIGNAL_FEED_VIEW_VALUES.signals,
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.stock]: 'AAPL',
      }),
      toQuery({
        [SIGNAL_FEED_ROUTE_QUERY_KEYS.view]: SIGNAL_FEED_VIEW_VALUES.signals,
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.stock]: 'AAPL',
      }),
    ],
    [
      toSearch({
        [SIGNAL_FEED_ROUTE_QUERY_KEYS.view]: SIGNAL_FEED_VIEW_VALUES.timeline,
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.holdings,
      }),
      toQuery({
        [SIGNAL_FEED_ROUTE_QUERY_KEYS.view]: SIGNAL_FEED_VIEW_VALUES.timeline,
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.holdings,
      }),
    ],
    [
      toSearch({
        [SIGNAL_FEED_ROUTE_QUERY_KEYS.view]: SIGNAL_FEED_VIEW_VALUES.stats,
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.watchlist,
      }),
      toQuery({
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.watchlist,
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab]: SIGNAL_CENTER_TAB_VALUES.review,
      }),
    ],
    [
      toSearch({ [SIGNAL_FEED_ROUTE_QUERY_KEYS.view]: 'unknown', keep: 'yes' }),
      toQuery({ keep: 'yes' }),
    ],
  ])('maps legacy Decision Signals search %s', (search, expected) => {
    const params = new URLSearchParams(search);
    mapLegacyDecisionSignalsSearchParams(params);
    expect(params.toString()).toBe(expected);
  });

  it.each([
    [
      '',
      toQuery({ [SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab]: SIGNAL_CENTER_TAB_VALUES.rules }),
    ],
    [
      toSearch({
        [SIGNAL_FEED_ROUTE_QUERY_KEYS.view]: LEGACY_ALERTS_VIEW_VALUES.rules,
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.holdings,
      }),
      toQuery({
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.holdings,
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab]: SIGNAL_CENTER_TAB_VALUES.rules,
      }),
    ],
    [
      toSearch({
        [SIGNAL_FEED_ROUTE_QUERY_KEYS.view]: LEGACY_ALERTS_VIEW_VALUES.history,
        keep: 'yes',
      }),
      toQuery({
        keep: 'yes',
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab]: SIGNAL_CENTER_TAB_VALUES.history,
      }),
    ],
    [
      toSearch({
        [SIGNAL_FEED_ROUTE_QUERY_KEYS.view]: LEGACY_ALERTS_VIEW_VALUES.notifications,
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.watchlist,
      }),
      toQuery({
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope]: SIGNAL_CENTER_SCOPE_VALUES.watchlist,
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab]: SIGNAL_CENTER_TAB_VALUES.history,
        [SIGNAL_CENTER_ROUTE_QUERY_KEYS.history]: SIGNAL_CENTER_HISTORY_VALUES.notifications,
      }),
    ],
  ])('maps legacy Alerts search %s', (search, expected) => {
    const params = new URLSearchParams(search);
    mapLegacyAlertsSearchParams(params);
    expect(params.toString()).toBe(expected);
  });
});
