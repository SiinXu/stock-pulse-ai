// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  APP_ROUTE_PATHS,
  LEGACY_ROUTE_PATHS,
  RESEARCH_BACKTEST_ROUTE_QUERY_KEYS,
  RESEARCH_DISCOVER_ROUTE_QUERY_KEYS,
} from '../../routing/routes';
import { buildDeepLink, parseDeepLink } from '../deepLink';

describe('deepLink', () => {
  it('builds canonical links for the major context-bearing views', () => {
    expect(buildDeepLink({
      page: 'home',
      recordId: 42,
      stockCode: 'SH600519',
      workspace: 'watchlist',
    })).toBe('/?recordId=42&stock=600519&workspace=watchlist');
    expect(buildDeepLink({
      page: 'chat',
      stockCode: '00700.HK',
      stockName: ' Tencent ',
      recordId: 7,
      contextState: 'active',
    })).toBe('/chat?stock=HK00700&name=Tencent&recordId=7&context=active');
    expect(buildDeepLink({ page: 'portfolio', accountId: 3 })).toBe('/portfolio?account=3');
    expect(buildDeepLink({ page: 'market-review', recordId: 42 })).toBe(
      `${APP_ROUTE_PATHS.researchMarket}?recordId=42`,
    );
    expect(buildDeepLink({
      page: 'decision-signals',
      stockCode: 'aapl',
      signalId: 9,
      view: 'timeline',
    })).toBe(`${APP_ROUTE_PATHS.signals}?stock=AAPL&signal=9&view=timeline`);
    expect(buildDeepLink({
      page: 'stock',
      stockCode: '7203.t',
      period: 'weekly',
      days: 120,
    })).toBe('/stocks/7203.T?period=weekly&days=120');
  });

  it('parses canonical Market Review report state through the typed target', () => {
    const parsed = parseDeepLink(`${APP_ROUTE_PATHS.researchMarket}?recordId=007&keep=yes`);

    expect(parsed.target).toEqual({ page: 'market-review', recordId: 7 });
    expect(parsed.normalizedHref).toBe(`${APP_ROUTE_PATHS.researchMarket}?recordId=7&keep=yes`);
    expect(parsed.issues).toEqual([]);
  });

  it('parses and canonicalizes Home state while preserving unrelated parameters', () => {
    const parsed = parseDeepLink('/?ref=notification&recordId=007&stock=00700.HK&workspace=today');

    expect(parsed.target).toEqual({
      page: 'home',
      recordId: 7,
      stockCode: 'HK00700',
      workspace: 'today',
    });
    expect(parsed.normalizedHref).toBe('/?ref=notification&recordId=7&stock=HK00700&workspace=today');
    expect(parsed.issues).toEqual([]);
  });

  it('preserves the legacy Home history workspace for the route redirect owner', () => {
    const parsed = parseDeepLink('/?workspace=history&keep=yes');

    expect(parsed.target).toEqual({
      page: 'home',
      recordId: undefined,
      stockCode: undefined,
      workspace: 'history',
    });
    expect(parsed.normalizedHref).toBe('/?workspace=history&keep=yes');
    expect(parsed.issues).toEqual([]);
  });

  it('removes invalid and sensitive state without dropping benign query context', () => {
    const parsed = parseDeepLink(
      '/?keep=yes&recordId=0&stock=%3Cscript%3E&workspace=unknown&api_key=secret',
    );

    expect(parsed.target).toEqual({
      page: 'home',
      recordId: undefined,
      stockCode: undefined,
      workspace: 'history',
    });
    expect(parsed.normalizedHref).toBe('/?keep=yes');
    expect(parsed.issues.map((issue) => issue.code)).toEqual([
      'sensitive_parameter',
      'invalid_record_id',
      'invalid_stock_code',
      'invalid_workspace',
    ]);
  });

  it('removes common credential aliases from query and fragment state', () => {
    const parsed = parseDeepLink(
      '/chat?token=query-secret&passwd=legacy-secret&openai_api_key=provider-secret&telegram_bot_token=bot-secret&keep=yes#anthropic_api_key=fragment-secret&tab=history',
    );

    expect(parsed.normalizedHref).toBe('/chat?keep=yes#tab=history');
    expect(parsed.issues).toEqual([
      { code: 'sensitive_parameter', parameter: 'token' },
      { code: 'sensitive_parameter', parameter: 'passwd' },
      { code: 'sensitive_parameter', parameter: 'openai_api_key' },
      { code: 'sensitive_parameter', parameter: 'telegram_bot_token' },
      { code: 'sensitive_parameter', parameter: 'anthropic_api_key' },
    ]);
  });

  it('requires chat report context to have a valid stock identity', () => {
    const parsed = parseDeepLink('/chat?session=session-1&stock=%3Cbad%3E&name=Bad&recordId=5&keep=yes');

    expect(parsed.target).toEqual({
      page: 'chat',
      sessionId: 'session-1',
      stockCode: undefined,
      stockName: undefined,
      recordId: undefined,
    });
    expect(parsed.normalizedHref).toBe('/chat?session=session-1&keep=yes');
    expect(parsed.issues).toContainEqual({ code: 'invalid_stock_code', parameter: 'stock' });
  });

  it('normalizes the active Chat context marker through the shared parser', () => {
    const active = parseDeepLink('/chat?stock=AAPL&recordId=7&context=active');
    expect(active.target).toEqual({
      page: 'chat',
      sessionId: undefined,
      stockCode: 'AAPL',
      stockName: undefined,
      recordId: 7,
      contextState: 'active',
    });

    const invalid = parseDeepLink('/chat?stock=AAPL&context=consumed&keep=yes');
    expect(invalid.normalizedHref).toBe('/chat?stock=AAPL&keep=yes');
    expect(invalid.issues).toContainEqual({ code: 'invalid_filter', parameter: 'context' });
  });

  it('normalizes invalid stock-detail controls to their safe defaults', () => {
    const parsed = parseDeepLink('/stocks/sh600519?period=hourly&days=999&keep=yes');

    expect(parsed.target).toEqual({
      page: 'stock',
      stockCode: '600519',
      period: 'daily',
      days: 90,
    });
    expect(parsed.normalizedHref).toBe('/stocks/600519?keep=yes');
    expect(parsed.issues).toEqual([
      { code: 'invalid_period', parameter: 'period' },
      { code: 'invalid_days', parameter: 'days' },
    ]);
  });

  it('redirects an invalid stock path to safe Home state', () => {
    const parsed = parseDeepLink('/stocks/%3Cscript%3E?period=weekly&keep=yes#chart');

    expect(parsed.target).toBeNull();
    expect(parsed.normalizedHref).toBe('/');
    expect(parsed.normalizedSearch).toBe('');
    expect(parsed.issues).toEqual([
      { code: 'invalid_stock_code', parameter: 'stockCode' },
    ]);
  });

  it('normalizes Decision Signals view and filter state through the shared parser', () => {
    const parsed = parseDeepLink(
      `${LEGACY_ROUTE_PATHS.decisionSignals}?stock=00700.HK&view=unknown&market=moon&listStock=aapl&page=0&timelineRange=30d&source_report_id=004&keep=yes`,
    );

    expect(parsed.target).toEqual({
      page: 'decision-signals',
      stockCode: 'HK00700',
      signalId: undefined,
      view: 'latest',
    });
    expect(parsed.normalizedHref).toBe(
      `${APP_ROUTE_PATHS.signals}?stock=HK00700&listStock=AAPL&timelineRange=30d&keep=yes&sourceReportId=4`,
    );
    expect(parsed.issues).toEqual([
      { code: 'invalid_filter', parameter: 'market' },
      { code: 'invalid_filter', parameter: 'page' },
      { code: 'invalid_view', parameter: 'view' },
    ]);
  });

  it('rejects external and unsupported destinations', () => {
    expect(parseDeepLink('https://example.com/chat').issues).toEqual([{ code: 'external_origin' }]);
    expect(parseDeepLink('/admin').issues).toEqual([{ code: 'unsupported_route' }]);
  });

  it('accepts canonical and legacy Research routes without rewriting their state', () => {
    for (const pathname of [
      APP_ROUTE_PATHS.researchMarket,
      APP_ROUTE_PATHS.researchDiscover,
      APP_ROUTE_PATHS.researchBacktest,
      LEGACY_ROUTE_PATHS.screening,
      LEGACY_ROUTE_PATHS.backtest,
    ]) {
      const parsed = parseDeepLink(`${pathname}?keep=yes#section`);
      expect(parsed.normalizedHref).toBe(`${pathname}?keep=yes#section`);
      expect(parsed.issues).toEqual([]);
    }
  });

  it('normalizes canonical and legacy Research filters through the shared codec', () => {
    for (const pathname of [APP_ROUTE_PATHS.researchBacktest, LEGACY_ROUTE_PATHS.backtest]) {
      const parsed = parseDeepLink(
        `${pathname}?${RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code}=aapl&${RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.window}=30&${RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.from}=2026-99-99&keep=yes#results`,
      );

      expect(parsed.normalizedHref).toBe(
        `${pathname}?${RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code}=AAPL&${RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.window}=30&keep=yes#results`,
      );
      expect(parsed.issues).toEqual([
        { code: 'invalid_filter', parameter: RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.from },
      ]);
    }

    const discover = parseDeepLink(
      `${APP_ROUTE_PATHS.researchDiscover}?${RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market}=cn&${RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy}=quality&${RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count}=20&keep=yes#details`,
    );
    expect(discover.normalizedHref).toBe(
      `${APP_ROUTE_PATHS.researchDiscover}?${RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy}=quality&${RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count}=20&keep=yes#details`,
    );
    expect(discover.issues).toEqual([]);
  });

  it('fails closed when an internal caller tries to build an unsafe link', () => {
    expect(() => buildDeepLink({ page: 'chat', sessionId: 'secret session' })).toThrow(TypeError);
    expect(() => buildDeepLink({ page: 'home', stockCode: '<script>' })).toThrow(TypeError);
    expect(() => buildDeepLink({ page: 'chat', recordId: 1 })).toThrow(TypeError);
    expect(() => buildDeepLink({ page: 'chat', contextState: 'active' })).toThrow(TypeError);
  });
});
