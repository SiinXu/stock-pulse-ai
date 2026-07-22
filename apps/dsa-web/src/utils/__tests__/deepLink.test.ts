// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
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
    })).toBe('/chat?stock=HK00700&name=Tencent&recordId=7');
    expect(buildDeepLink({ page: 'portfolio', accountId: 3 })).toBe('/portfolio?account=3');
    expect(buildDeepLink({
      page: 'decision-signals',
      stockCode: 'aapl',
      signalId: 9,
      view: 'timeline',
    })).toBe('/decision-signals?stock=AAPL&signal=9&view=timeline');
    expect(buildDeepLink({
      page: 'stock',
      stockCode: '7203.t',
      period: 'weekly',
      days: 120,
    })).toBe('/stocks/7203.T?period=weekly&days=120');
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
    const parsed = parseDeepLink('/chat?token=query-secret&passwd=legacy-secret&keep=yes#access_token=fragment-secret&tab=history');

    expect(parsed.normalizedHref).toBe('/chat?keep=yes#tab=history');
    expect(parsed.issues).toEqual([
      { code: 'sensitive_parameter', parameter: 'token' },
      { code: 'sensitive_parameter', parameter: 'passwd' },
      { code: 'sensitive_parameter', parameter: 'access_token' },
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

  it('normalizes Decision Signals view and filter state through the shared parser', () => {
    const parsed = parseDeepLink(
      '/decision-signals?stock=00700.HK&view=unknown&market=moon&listStock=aapl&page=0&timelineRange=30d&source_report_id=004&keep=yes',
    );

    expect(parsed.target).toEqual({
      page: 'decision-signals',
      stockCode: 'HK00700',
      signalId: undefined,
      view: 'latest',
    });
    expect(parsed.normalizedHref).toBe(
      '/decision-signals?stock=HK00700&listStock=AAPL&timelineRange=30d&keep=yes&sourceReportId=4',
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

  it('fails closed when an internal caller tries to build an unsafe link', () => {
    expect(() => buildDeepLink({ page: 'chat', sessionId: 'secret session' })).toThrow(TypeError);
    expect(() => buildDeepLink({ page: 'home', stockCode: '<script>' })).toThrow(TypeError);
    expect(() => buildDeepLink({ page: 'chat', recordId: 1 })).toThrow(TypeError);
  });
});
