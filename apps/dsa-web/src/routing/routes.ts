// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

export const APP_ROUTE_PATHS = {
  home: '/',
  login: '/login',
  playground: '/playground',
  playgroundRender: '/playground/render/:componentId/:scenarioId',
  agent: '/chat',
  portfolio: '/portfolio',
  decisionSignals: '/decision-signals',
  alerts: '/alerts',
  stockDetails: '/stocks/:stockCode',
  researchMarket: '/research/market',
  researchDiscover: '/research/discover',
  researchBacktest: '/research/backtest',
  settings: '/settings',
} as const;

export const LEGACY_ROUTE_PATHS = {
  usage: '/usage',
  screening: '/screening',
  backtest: '/backtest',
} as const;

export const REPORT_ROUTE_QUERY_KEYS = {
  recordId: 'recordId',
  runFlow: 'runFlow',
  runFlowRecordId: 'runFlowRecordId',
  runFlowTaskId: 'runFlowTaskId',
} as const;

export const RUN_FLOW_ROUTE_QUERY_VALUES = {
  history: 'history',
  task: 'task',
} as const;

export const HOME_ROUTE_QUERY_KEYS = {
  stock: 'stock',
  workspace: 'workspace',
} as const;

export const RESEARCH_DISCOVER_ROUTE_QUERY_KEYS = {
  market: 'market',
  strategy: 'strategy',
  count: 'count',
} as const;

export const RESEARCH_DISCOVER_MARKET_VALUES = {
  china: 'cn',
} as const;

export const RESEARCH_BACKTEST_ROUTE_QUERY_KEYS = {
  code: 'code',
  window: 'window',
  from: 'from',
  to: 'to',
  phase: 'phase',
  page: 'page',
} as const;

export const RESEARCH_BACKTEST_PHASE_VALUES = {
  all: 'all',
  premarket: 'premarket',
  intraday: 'intraday',
  postmarket: 'postmarket',
  unknown: 'unknown',
} as const;

export const SETTINGS_ROUTE_QUERY_KEYS = {
  section: 'section',
  view: 'view',
  legacyCategory: 'category',
  legacySub: 'sub',
  source: 'from',
} as const;

export const SETTINGS_SECTION_IDS = {
  usage: 'usage',
} as const;

export type SettingsRouteSearch = {
  section?: string;
  view?: string;
  legacyCategory?: string;
  legacySub?: string;
  source?: string;
};

export function buildSettingsHref(search: SettingsRouteSearch = {}): string {
  const searchParams = new URLSearchParams();
  const entries: Array<[keyof SettingsRouteSearch, string]> = [
    ['section', SETTINGS_ROUTE_QUERY_KEYS.section],
    ['view', SETTINGS_ROUTE_QUERY_KEYS.view],
    ['legacyCategory', SETTINGS_ROUTE_QUERY_KEYS.legacyCategory],
    ['legacySub', SETTINGS_ROUTE_QUERY_KEYS.legacySub],
    ['source', SETTINGS_ROUTE_QUERY_KEYS.source],
  ];

  entries.forEach(([field, queryKey]) => {
    const value = search[field];
    if (value) searchParams.set(queryKey, value);
  });

  const query = searchParams.toString();
  return query ? `${APP_ROUTE_PATHS.settings}?${query}` : APP_ROUTE_PATHS.settings;
}

export function buildSettingsSectionHref(section: string): string {
  return buildSettingsHref({ section });
}
