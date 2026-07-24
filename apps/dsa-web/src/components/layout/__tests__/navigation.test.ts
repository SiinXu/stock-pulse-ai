import { describe, expect, it } from 'vitest';
import {
  ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS,
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  APP_ROUTE_PATHS,
  HOME_WORKSPACE_VALUES,
  LEGACY_ROUTE_PATHS,
  REPORT_ROUTE_QUERY_KEYS,
  RESEARCH_BACKTEST_LIMITS,
  RESEARCH_BACKTEST_PHASE_VALUES,
  RESEARCH_BACKTEST_ROUTE_QUERY_KEYS,
  RESEARCH_DISCOVER_DEFAULT_VALUES,
  RESEARCH_DISCOVER_LIMITS,
  RESEARCH_DISCOVER_MARKET_VALUES,
  RESEARCH_DISCOVER_ROUTE_QUERY_KEYS,
  RUN_FLOW_ROUTE_QUERY_VALUES,
  SIGNAL_CENTER_HISTORY_VALUES,
  SIGNAL_CENTER_ROUTE_QUERY_KEYS,
  SIGNAL_CENTER_SCOPE_VALUES,
  SIGNAL_CENTER_TAB_VALUES,
} from '../../../routing/routes';
import {
  APPLICATION_NAVIGATION_ITEMS,
  shouldDelegateCurrentDocumentNavigation,
} from '../navigation';

describe('application navigation descriptor', () => {
  it('converges to five primary domains with approved secondary routes', () => {
    expect(APPLICATION_NAVIGATION_ITEMS.map(({ key, to }) => [key, to])).toEqual([
      ['home', APP_ROUTE_PATHS.home],
      ['research', APP_ROUTE_PATHS.researchMarket],
      ['portfolio', APP_ROUTE_PATHS.portfolio],
      ['agent', APP_ROUTE_PATHS.agent],
      ['settings', APP_ROUTE_PATHS.settings],
    ]);
    expect(APPLICATION_NAVIGATION_ITEMS[0]?.children?.map(({ key, to }) => [key, to]) ?? []).toEqual([]);
    expect(APPLICATION_NAVIGATION_ITEMS[1]?.children?.map(({ key, to }) => [key, to])).toEqual([
      ['research-market', APP_ROUTE_PATHS.researchMarket],
      ['research-discover', APP_ROUTE_PATHS.researchDiscover],
      ['research-analysis', APP_ROUTE_PATHS.researchAnalysis],
      ['research-backtest', APP_ROUTE_PATHS.researchBacktest],
    ]);
  });

  it('has unique descriptor keys and no legacy or dead utility targets', () => {
    const entries = APPLICATION_NAVIGATION_ITEMS.flatMap((item) => [item, ...(item.children ?? [])]);
    const keys = entries.map(({ key }) => key);
    const targets = entries.map(({ to }) => to);

    expect(new Set(keys).size).toBe(keys.length);
    expect(keys).not.toContain('more');
    expect(keys).not.toContain('usage');
    expect(targets).not.toContain(LEGACY_ROUTE_PATHS.usage);
    expect(targets).not.toContain(LEGACY_ROUTE_PATHS.screening);
    expect(targets).not.toContain(LEGACY_ROUTE_PATHS.backtest);
    expect(targets).not.toContain(LEGACY_ROUTE_PATHS.decisionSignals);
    expect(targets).not.toContain(LEGACY_ROUTE_PATHS.alerts);
    expect(targets).not.toContain('/more');
  });

  it('centralizes Research and shared report URL state names and legal values', () => {
    expect(Object.values(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS)).toEqual([
      'market',
      'strategy',
      'count',
    ]);
    expect(Object.values(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS)).toEqual([
      'code',
      'window',
      'from',
      'to',
      'phase',
      'page',
    ]);
    expect(Object.values(REPORT_ROUTE_QUERY_KEYS)).toEqual([
      'recordId',
      'runFlow',
      'runFlowRecordId',
      'runFlowTaskId',
    ]);
    expect(Object.values(RESEARCH_DISCOVER_MARKET_VALUES)).toEqual(['cn']);
    expect(Object.values(RESEARCH_BACKTEST_PHASE_VALUES)).toEqual([
      'all',
      'premarket',
      'intraday',
      'postmarket',
      'unknown',
    ]);
    expect(Object.values(RUN_FLOW_ROUTE_QUERY_VALUES)).toEqual(['history', 'task']);
    expect(Object.values(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS)).toEqual([
      'segment',
      'recordId',
      'runFlow',
      'runFlowRecordId',
      'runFlowTaskId',
    ]);
    expect(Object.values(ANALYSIS_WORKBENCH_SEGMENT_VALUES)).toEqual([
      'launch',
      'tasks',
      'history',
    ]);
    expect(Object.values(HOME_WORKSPACE_VALUES)).toEqual(['history', 'watchlist', 'today']);
    expect(RESEARCH_DISCOVER_DEFAULT_VALUES).toEqual({
      market: RESEARCH_DISCOVER_MARKET_VALUES.china,
      strategy: 'dual_low',
      count: 3,
    });
    expect(RESEARCH_DISCOVER_LIMITS.maxCount).toBe(100);
    expect(RESEARCH_BACKTEST_LIMITS.maxWindowDays).toBe(120);
    expect(Object.values(SIGNAL_CENTER_ROUTE_QUERY_KEYS)).toEqual([
      'scope',
      'tab',
      'history',
      'createRule',
      'stock',
    ]);
    expect(Object.values(SIGNAL_CENTER_SCOPE_VALUES)).toEqual(['all', 'holdings', 'watchlist']);
    expect(Object.values(SIGNAL_CENTER_TAB_VALUES)).toEqual(['feed', 'rules', 'history', 'review']);
    expect(Object.values(SIGNAL_CENTER_HISTORY_VALUES)).toEqual(['triggers', 'notifications']);
  });

  it('delegates only unmodified primary same-window link activation', () => {
    const currentTarget = document.createElement('a');
    const event = (overrides: Record<string, unknown> = {}) => ({
      defaultPrevented: false,
      button: 0,
      metaKey: false,
      ctrlKey: false,
      shiftKey: false,
      altKey: false,
      currentTarget,
      ...overrides,
    }) as Parameters<typeof shouldDelegateCurrentDocumentNavigation>[0];

    expect(shouldDelegateCurrentDocumentNavigation(event())).toBe(true);
    for (const modifier of ['metaKey', 'ctrlKey', 'shiftKey', 'altKey']) {
      expect(shouldDelegateCurrentDocumentNavigation(event({ [modifier]: true }))).toBe(false);
    }
    expect(shouldDelegateCurrentDocumentNavigation(event({ button: 1 }))).toBe(false);
    expect(shouldDelegateCurrentDocumentNavigation(event({ defaultPrevented: true }))).toBe(false);

    currentTarget.target = '_blank';
    expect(shouldDelegateCurrentDocumentNavigation(event())).toBe(false);
    currentTarget.target = '_self';
    currentTarget.setAttribute('download', 'report.json');
    expect(shouldDelegateCurrentDocumentNavigation(event())).toBe(false);
  });
});
