import { describe, expect, it } from 'vitest';
import {
  RESEARCH_BACKTEST_PHASE_VALUES,
  RESEARCH_BACKTEST_ROUTE_QUERY_KEYS,
  RESEARCH_DISCOVER_DEFAULT_VALUES,
  RESEARCH_DISCOVER_ROUTE_QUERY_KEYS,
} from '../routes';
import {
  DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE,
  parseResearchBacktestRouteState,
  parseResearchDiscoverRouteState,
  resolveResearchDiscoverRouteState,
  setResearchBacktestRouteState,
  setResearchDiscoverRouteState,
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
    expect(parsed.ownedParams.toString()).toBe(new URLSearchParams({
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: 'quality',
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: '20',
    }).toString());
    expect(parsed.normalizedParams.toString()).toBe(new URLSearchParams({
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: 'quality',
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: '20',
      source: 'report',
    }).toString());
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
    const parsed = parseResearchBacktestRouteState(new URLSearchParams({
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code]: 'aapl',
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.window]: '30',
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.from]: '2026-03-01',
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.to]: '2026-03-31',
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.phase]: RESEARCH_BACKTEST_PHASE_VALUES.intraday,
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.page]: '2',
      ref: 'report',
    }));

    expect(parsed.state).toEqual({
      code: 'AAPL',
      windowDays: 30,
      startDate: '2026-03-01',
      endDate: '2026-03-31',
      phase: RESEARCH_BACKTEST_PHASE_VALUES.intraday,
      page: 2,
    });
    expect(parsed.normalizedParams.toString()).toBe(new URLSearchParams({
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code]: 'AAPL',
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.window]: '30',
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.from]: '2026-03-01',
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.to]: '2026-03-31',
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.phase]: RESEARCH_BACKTEST_PHASE_VALUES.intraday,
      [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.page]: '2',
      ref: 'report',
    }).toString());
    expect(setResearchBacktestRouteState('?ref=report', parsed.state).toString()).toBe(
      new URLSearchParams({
        ref: 'report',
        [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code]: 'AAPL',
        [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.window]: '30',
        [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.from]: '2026-03-01',
        [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.to]: '2026-03-31',
        [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.phase]: RESEARCH_BACKTEST_PHASE_VALUES.intraday,
        [RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.page]: '2',
      }).toString(),
    );
  });

  it('treats malformed explicit Discover state as authoritative defaults instead of stale fallback', () => {
    const parsed = resolveResearchDiscoverRouteState(new URLSearchParams({
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: '<bad>',
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: '999',
    }), {
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
    expect(parsed.ownedParams.toString()).toBe(new URLSearchParams({
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: RESEARCH_DISCOVER_DEFAULT_VALUES.strategy,
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: String(RESEARCH_DISCOVER_DEFAULT_VALUES.count),
    }).toString());
  });

  it('keeps wholly malformed Discover intent explicit after canonical cleanup and refresh', () => {
    const staleTask = {
      market: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
      strategy: 'quality',
      maxResults: 8,
    };
    const parsed = resolveResearchDiscoverRouteState(new URLSearchParams({
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market]: 'unsupported',
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: '<bad>',
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: '999',
      source: 'notification',
    }), staleTask);
    const expectedNormalized = new URLSearchParams({
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market]: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: RESEARCH_DISCOVER_DEFAULT_VALUES.strategy,
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: String(RESEARCH_DISCOVER_DEFAULT_VALUES.count),
      source: 'notification',
    });

    expect(parsed.state).toEqual(DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE);
    expect(parsed.normalizedParams.toString()).toBe(expectedNormalized.toString());
    expect(resolveResearchDiscoverRouteState(parsed.normalizedParams, staleTask).state)
      .toEqual(DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE);
  });

  it('canonicalizes valid Discover state through the same owned-parameter set', () => {
    const parsed = parseResearchDiscoverRouteState(new URLSearchParams({
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.market]: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: 'quality',
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: '20',
      keep: 'yes',
    }));

    expect(parsed.state).toEqual({
      market: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
      strategy: 'quality',
      maxResults: 20,
    });
    expect(parsed.ownedParams.toString()).toBe(new URLSearchParams({
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: 'quality',
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: '20',
    }).toString());
    expect(parsed.normalizedParams.toString()).toBe(new URLSearchParams({
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: 'quality',
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: '20',
      keep: 'yes',
    }).toString());
  });

  it('retains explicit default-valued Discover ownership across normalization and refresh', () => {
    const staleTask = {
      market: RESEARCH_DISCOVER_DEFAULT_VALUES.market,
      strategy: 'quality',
      maxResults: 20,
    };
    const explicitDefaults = new URLSearchParams({
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.strategy]: RESEARCH_DISCOVER_DEFAULT_VALUES.strategy,
      [RESEARCH_DISCOVER_ROUTE_QUERY_KEYS.count]: String(RESEARCH_DISCOVER_DEFAULT_VALUES.count),
      source: 'notification',
    });

    const firstLoad = resolveResearchDiscoverRouteState(explicitDefaults, staleTask);
    const refreshed = resolveResearchDiscoverRouteState(firstLoad.normalizedParams, staleTask);

    expect(firstLoad.state).toEqual(DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE);
    expect(firstLoad.normalizedParams.toString()).toBe(explicitDefaults.toString());
    expect(setResearchDiscoverRouteState(explicitDefaults, firstLoad.state).toString())
      .toBe(explicitDefaults.toString());
    expect(refreshed.state).toEqual(DEFAULT_RESEARCH_DISCOVER_ROUTE_STATE);
    expect(refreshed.hasOwnedParameters).toBe(true);
  });
});
