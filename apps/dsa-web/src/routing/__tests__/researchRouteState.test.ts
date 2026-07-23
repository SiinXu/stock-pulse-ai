import { describe, expect, it } from 'vitest';
import {
  RESEARCH_BACKTEST_PHASE_VALUES,
  RESEARCH_BACKTEST_ROUTE_QUERY_KEYS,
  RESEARCH_DISCOVER_DEFAULT_VALUES,
  RESEARCH_DISCOVER_ROUTE_QUERY_KEYS,
} from '../routes';
import {
  parseResearchBacktestRouteState,
  parseResearchDiscoverRouteState,
  resolveResearchDiscoverRouteState,
  setResearchBacktestRouteState,
} from '../researchRouteState';

describe('Research route state codec', () => {
  it('lets explicit Discover parameters override a stale fallback as one URL-owned state', () => {
    const parsed = resolveResearchDiscoverRouteState(
      `?${RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy}=quality&${RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count}=20&source=report`,
      {
        market: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
        strategy: 'dual_low',
        maxResults: RESEARCH_DISCOVER_DEFAULT_VALUES.count,
      },
    );

    expect(parsed.state).toEqual({
      market: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
      strategy: 'quality',
      maxResults: 20,
    });
    expect(parsed.hasOwnedParameters).toBe(true);
    expect(parsed.ownedParams.toString()).toBe('strategy=quality&count=20');
    expect(parsed.normalizedParams.toString()).toBe('strategy=quality&count=20&source=report');
    expect(parsed.invalidKeys).toEqual([]);
  });

  it('uses the normalized active-task fallback only when Discover has no explicit owned state', () => {
    const parsed = resolveResearchDiscoverRouteState('?source=sidebar', {
      market: 'unsupported',
      strategy: 'quality',
      maxResults: 999,
    });

    expect(parsed.state).toEqual({
      market: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
      strategy: 'quality',
      maxResults: RESEARCH_DISCOVER_DEFAULT_VALUES.count,
    });
    expect(parsed.hasOwnedParameters).toBe(false);
    expect(parsed.normalizedParams.toString()).toBe('source=sidebar');
  });

  it('removes malformed Backtest filters while preserving unrelated query state', () => {
    const parsed = parseResearchBacktestRouteState(new URLSearchParams({
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code]: '<bad>',
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.window]: '121',
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.from]: '2026-99-99',
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.to]: 'not-a-date',
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.phase]: 'after-hours',
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.page]: '0',
      ref: 'dashboard',
    }));

    expect(parsed.state).toEqual({
      code: '',
      windowDays: undefined,
      startDate: '',
      endDate: '',
      phase: RESEARCH_BACKTEST_PHASE_VALUES.all,
      page: 1,
    });
    expect(parsed.ownedParams.toString()).toBe('');
    expect(parsed.normalizedParams.toString()).toBe('ref=dashboard');
    expect(parsed.invalidKeys).toEqual([
      RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code,
      RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.window,
      RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.from,
      RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.to,
      RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.phase,
      RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.page,
    ]);
  });

  it('normalizes and writes valid Backtest state without deleting unrelated parameters', () => {
    const parsed = parseResearchBacktestRouteState(
      '?code=aapl&window=30&from=2026-03-01&to=2026-03-31&phase=intraday&page=2&ref=report',
    );

    expect(parsed.state).toEqual({
      code: 'AAPL',
      windowDays: 30,
      startDate: '2026-03-01',
      endDate: '2026-03-31',
      phase: RESEARCH_BACKTEST_PHASE_VALUES.intraday,
      page: 2,
    });
    expect(parsed.normalizedParams.toString()).toBe(
      'code=AAPL&window=30&from=2026-03-01&to=2026-03-31&phase=intraday&page=2&ref=report',
    );
    expect(setResearchBacktestRouteState('?ref=report', parsed.state).toString()).toBe(
      'ref=report&code=AAPL&window=30&from=2026-03-01&to=2026-03-31&phase=intraday&page=2',
    );
  });

  it('treats malformed explicit Discover state as authoritative defaults instead of stale fallback', () => {
    const parsed = resolveResearchDiscoverRouteState('?strategy=%3Cbad%3E&count=999', {
      market: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
      strategy: 'stale_task_strategy',
      maxResults: 8,
    });

    expect(parsed.state).toEqual({
      market: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
      strategy: RESEARCH_DISCOVER_DEFAULT_VALUES.strategy,
      maxResults: RESEARCH_DISCOVER_DEFAULT_VALUES.count,
    });
    expect(parsed.invalidKeys).toEqual([
      RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy,
      RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count,
    ]);
  });

  it('canonicalizes valid Discover state through the same owned-parameter set', () => {
    const parsed = parseResearchDiscoverRouteState('?market=cn&strategy=quality&count=20&keep=yes');

    expect(parsed.state).toEqual({ market: 'cn', strategy: 'quality', maxResults: 20 });
    expect(parsed.ownedParams.toString()).toBe('strategy=quality&count=20');
    expect(parsed.normalizedParams.toString()).toBe('strategy=quality&count=20&keep=yes');
  });
});
