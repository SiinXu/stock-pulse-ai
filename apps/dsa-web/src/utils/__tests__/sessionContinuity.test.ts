// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it } from 'vitest';
import {
  APP_ROUTE_PATHS,
  LEGACY_ROUTE_PATHS,
  REPORT_ROUTE_QUERY_KEYS,
  RESEARCH_BACKTEST_ROUTE_QUERY_KEYS,
  RESEARCH_DISCOVER_MARKET_VALUES,
  RESEARCH_DISCOVER_ROUTE_QUERY_KEYS,
  RUN_FLOW_ROUTE_QUERY_VALUES,
  SIGNAL_CENTER_SCOPE_VALUES,
  SIGNAL_CENTER_TAB_VALUES,
  buildSignalCenterHref,
} from '../../routing/routes';
import { WEB_SESSION_CONTINUITY_STORAGE_KEY } from '../sessionPersistence';
import {
  recordSessionLocation,
  resolveContextAwareNavigationTarget,
  resolveInitialSessionHref,
} from '../sessionContinuity';

describe('sessionContinuity', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it('restores an allowlisted route snapshot only for an initial bare route', () => {
    recordSessionLocation(`${APP_ROUTE_PATHS.signals}?stock=AAPL&view=timeline&market=us&keep=no`);

    expect(resolveInitialSessionHref(APP_ROUTE_PATHS.signals)).toBe(
      `${APP_ROUTE_PATHS.signals}?stock=AAPL&view=timeline&market=us`,
    );
    expect(resolveInitialSessionHref(`${APP_ROUTE_PATHS.signals}?market=cn`)).toBeNull();
  });

  it('restores Signal Center scope and tab but not the transient create-rule action', () => {
    recordSessionLocation(buildSignalCenterHref({
      scope: SIGNAL_CENTER_SCOPE_VALUES.holdings,
      tab: SIGNAL_CENTER_TAB_VALUES.rules,
      createRule: true,
    }));

    expect(resolveInitialSessionHref(APP_ROUTE_PATHS.signals)).toBe(
      buildSignalCenterHref({
        scope: SIGNAL_CENTER_SCOPE_VALUES.holdings,
        tab: SIGNAL_CENTER_TAB_VALUES.rules,
      }),
    );
  });

  it('restores validated task and history Run Flow context for Home', () => {
    recordSessionLocation('/?recordId=42&stock=AAPL&runFlow=history&runFlowRecordId=42');
    expect(resolveInitialSessionHref('/')).toBe(
      '/?recordId=42&stock=AAPL&runFlow=history&runFlowRecordId=42',
    );

    recordSessionLocation('/?stock=AAPL&runFlow=task&runFlowTaskId=task_01%3Aus-east.2');
    expect(resolveInitialSessionHref('/')).toBe(
      '/?stock=AAPL&runFlow=task&runFlowTaskId=task_01%3Aus-east.2',
    );
  });

  it('overwrites a previous snapshot when the user clears route state', () => {
    recordSessionLocation('/portfolio?account=7');
    expect(resolveInitialSessionHref('/portfolio')).toBe('/portfolio?account=7');

    recordSessionLocation('/portfolio');
    expect(resolveInitialSessionHref('/portfolio')).toBeNull();
  });

  it('uses current explicit route state ahead of a stale snapshot for the same destination', () => {
    recordSessionLocation('/portfolio?account=7');

    expect(resolveContextAwareNavigationTarget('/portfolio', '/portfolio')).toBe('/portfolio');
  });

  it('carries stock context through an intermediate route and retains destination state', () => {
    recordSessionLocation('/chat?session=session-1');
    recordSessionLocation(`${APP_ROUTE_PATHS.signals}?view=timeline&market=us`);
    recordSessionLocation('/stocks/00700.HK?period=weekly&days=120');

    expect(resolveContextAwareNavigationTarget('/chat', APP_ROUTE_PATHS.settings)).toBe(
      '/chat?session=session-1&stock=HK00700',
    );
    expect(resolveContextAwareNavigationTarget(APP_ROUTE_PATHS.signals, APP_ROUTE_PATHS.settings)).toBe(
      `${APP_ROUTE_PATHS.signals}?stock=HK00700&view=timeline&market=us`,
    );
    expect(resolveContextAwareNavigationTarget(APP_ROUTE_PATHS.researchBacktest, APP_ROUTE_PATHS.settings)).toBe(
      `${APP_ROUTE_PATHS.researchBacktest}?code=HK00700`,
    );
  });

  it('carries Home report context into Chat and clears stale report identity for another stock', () => {
    recordSessionLocation('/chat?session=session-1&stock=600519&recordId=3');

    expect(resolveContextAwareNavigationTarget(
      '/chat',
      '/?recordId=9&stock=AAPL&workspace=watchlist',
    )).toBe('/chat?session=session-1&stock=AAPL&recordId=9');
  });

  it('retains same-stock Home pipeline context and drops it when the stock changes', () => {
    recordSessionLocation(
      '/?recordId=9&stock=AAPL&workspace=watchlist&runFlow=history&runFlowRecordId=9',
    );

    expect(resolveContextAwareNavigationTarget('/', APP_ROUTE_PATHS.settings)).toBe(
      '/?recordId=9&stock=AAPL&workspace=watchlist&runFlow=history&runFlowRecordId=9',
    );
    expect(resolveContextAwareNavigationTarget('/', '/stocks/MSFT')).toBe(
      '/?stock=MSFT&workspace=watchlist',
    );
  });

  it('retains consumed Chat context for the same stock and resets it for a new stock', () => {
    recordSessionLocation(
      '/chat?session=session-1&stock=AAPL&name=Apple&recordId=9&context=active',
    );

    expect(resolveContextAwareNavigationTarget('/chat', APP_ROUTE_PATHS.settings)).toBe(
      '/chat?session=session-1&stock=AAPL&name=Apple&recordId=9&context=active',
    );
    expect(resolveContextAwareNavigationTarget('/chat', '/stocks/MSFT')).toBe(
      '/chat?session=session-1&stock=MSFT',
    );
  });

  it('does not reuse stale stock context after a context-owning route clears it', () => {
    recordSessionLocation('/stocks/AAPL');
    recordSessionLocation('/');

    expect(resolveContextAwareNavigationTarget('/chat', '/')).toBe('/chat');
  });

  it('drops unknown and sensitive parameters before writing storage', () => {
    recordSessionLocation('/chat?session=session-1&stock=AAPL&draft=private&openai_api_key=secret');

    const raw = window.sessionStorage.getItem(WEB_SESSION_CONTINUITY_STORAGE_KEY);
    expect(raw).not.toContain('private');
    expect(raw).not.toContain('secret');
    expect(resolveInitialSessionHref('/chat')).toBe('/chat?session=session-1&stock=AAPL');
  });

  it('fails closed for malformed persisted payloads', () => {
    window.sessionStorage.setItem(WEB_SESSION_CONTINUITY_STORAGE_KEY, '{bad json');

    expect(resolveInitialSessionHref('/chat')).toBeNull();
    expect(window.sessionStorage.getItem(WEB_SESSION_CONTINUITY_STORAGE_KEY)).toBeNull();
  });

  it('rewrites tampered stored state without unsafe names or invalid dates', () => {
    window.sessionStorage.setItem(WEB_SESSION_CONTINUITY_STORAGE_KEY, JSON.stringify({
      version: 1,
      routes: { backtest: `${LEGACY_ROUTE_PATHS.backtest}?code=AAPL&from=2026-99-99` },
      stockContext: { stockCode: 'AAPL', stockName: 'Bad\u0000Name' },
    }));

    expect(resolveInitialSessionHref(APP_ROUTE_PATHS.researchBacktest)).toBe(
      `${APP_ROUTE_PATHS.researchBacktest}?code=AAPL`,
    );
    expect(window.sessionStorage.getItem(WEB_SESSION_CONTINUITY_STORAGE_KEY)).not.toContain('Bad');
    expect(window.sessionStorage.getItem(WEB_SESSION_CONTINUITY_STORAGE_KEY)).not.toContain('2026-99-99');
  });

  it('migrates legacy Research snapshots to canonical route keys and paths', () => {
    window.sessionStorage.setItem(WEB_SESSION_CONTINUITY_STORAGE_KEY, JSON.stringify({
      version: 1,
      routes: {
        screening: `${LEGACY_ROUTE_PATHS.screening}?${RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market}=${RESEARCH_DISCOVER_MARKET_VALUES.china}&${RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy}=quality&${RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count}=20`,
        backtest: `${LEGACY_ROUTE_PATHS.backtest}?${RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code}=aapl&${RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.window}=30`,
      },
    }));

    expect(resolveInitialSessionHref(APP_ROUTE_PATHS.researchDiscover)).toBe(
      `${APP_ROUTE_PATHS.researchDiscover}?${RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy}=quality&${RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count}=20`,
    );
    expect(resolveInitialSessionHref(APP_ROUTE_PATHS.researchBacktest)).toBe(
      `${APP_ROUTE_PATHS.researchBacktest}?${RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code}=AAPL&${RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.window}=30`,
    );
    const persisted = window.sessionStorage.getItem(WEB_SESSION_CONTINUITY_STORAGE_KEY) ?? '';
    expect(persisted).toContain('research-discover');
    expect(persisted).toContain('research-backtest');
    expect(persisted).not.toContain('"screening"');
    expect(persisted).not.toContain('"backtest"');
  });

  it('uses the page codec to sanitize Backtest snapshots and drops non-allowlisted context', () => {
    recordSessionLocation(
      `${APP_ROUTE_PATHS.researchBacktest}?${RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code}=aapl&${RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.window}=30&${RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.from}=2026-99-99&keep=yes#results`,
    );

    expect(resolveInitialSessionHref(APP_ROUTE_PATHS.researchBacktest)).toBe(
      `${APP_ROUTE_PATHS.researchBacktest}?${RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code}=AAPL&${RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.window}=30`,
    );
    const persisted = window.sessionStorage.getItem(WEB_SESSION_CONTINUITY_STORAGE_KEY) ?? '';
    expect(persisted).not.toContain('2026-99-99');
    expect(persisted).not.toContain('keep=yes');
    expect(persisted).not.toContain('#results');
  });

  it('restores market review record and Run Flow state on the canonical route', () => {
    recordSessionLocation(
      `${APP_ROUTE_PATHS.researchMarket}?${REPORT_ROUTE_QUERY_KEYS.recordId}=42&${REPORT_ROUTE_QUERY_KEYS.runFlow}=${RUN_FLOW_ROUTE_QUERY_VALUES.history}&${REPORT_ROUTE_QUERY_KEYS.runFlowRecordId}=42`,
    );

    expect(resolveInitialSessionHref(APP_ROUTE_PATHS.researchMarket)).toBe(
      `${APP_ROUTE_PATHS.researchMarket}?${REPORT_ROUTE_QUERY_KEYS.recordId}=42&${REPORT_ROUTE_QUERY_KEYS.runFlow}=${RUN_FLOW_ROUTE_QUERY_VALUES.history}&${REPORT_ROUTE_QUERY_KEYS.runFlowRecordId}=42`,
    );
  });

  it('removes malformed Home pipeline identities from tampered storage', () => {
    window.sessionStorage.setItem(WEB_SESSION_CONTINUITY_STORAGE_KEY, JSON.stringify({
      version: 1,
      routes: { home: '/?runFlow=task&runFlowTaskId=..%2Fprovider_api_key' },
    }));

    expect(resolveInitialSessionHref('/')).toBeNull();
    expect(window.sessionStorage.getItem(WEB_SESSION_CONTINUITY_STORAGE_KEY)).not.toContain('provider_api_key');
  });
});
