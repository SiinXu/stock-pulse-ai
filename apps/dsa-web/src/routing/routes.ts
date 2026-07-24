// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

export const APP_ROUTE_PATHS = {
  home: '/',
  login: '/login',
  playground: '/playground',
  playgroundRender: '/playground/render/:componentId/:scenarioId',
  agent: '/chat',
  portfolio: '/portfolio',
  signals: '/signals',
  stockDetails: '/stocks/:stockCode',
  researchAnalysis: '/research/analysis',
  researchMarket: '/research/market',
  researchDiscover: '/research/discover',
  researchBacktest: '/research/backtest',
  settings: '/settings',
} as const;

export const LEGACY_ROUTE_PATHS = {
  usage: '/usage',
  screening: '/screening',
  backtest: '/backtest',
  decisionSignals: '/decision-signals',
  alerts: '/alerts',
} as const;

export const SIGNAL_CENTER_ROUTE_QUERY_KEYS = {
  scope: 'scope',
  tab: 'tab',
  history: 'history',
  createRule: 'createRule',
  stock: 'stock',
} as const;

export const SIGNAL_CENTER_CREATE_RULE_VALUES = {
  requested: '1',
} as const;

export const SIGNAL_FEED_ROUTE_QUERY_KEYS = {
  view: 'view',
} as const;

export const SIGNAL_FEED_VIEW_VALUES = {
  signals: 'signals',
  latest: 'latest',
  timeline: 'timeline',
  stats: 'stats',
} as const;

export const LEGACY_ALERTS_VIEW_VALUES = {
  rules: 'rules',
  history: 'history',
  notifications: 'notifications',
} as const;

export const SIGNAL_CENTER_SCOPE_VALUES = {
  all: 'all',
  holdings: 'holdings',
  watchlist: 'watchlist',
} as const;

export const SIGNAL_CENTER_TAB_VALUES = {
  feed: 'feed',
  rules: 'rules',
  history: 'history',
  review: 'review',
} as const;

export const SIGNAL_CENTER_HISTORY_VALUES = {
  triggers: 'triggers',
  notifications: 'notifications',
} as const;

export type SignalCenterScope =
  (typeof SIGNAL_CENTER_SCOPE_VALUES)[keyof typeof SIGNAL_CENTER_SCOPE_VALUES];
export type SignalCenterTab =
  (typeof SIGNAL_CENTER_TAB_VALUES)[keyof typeof SIGNAL_CENTER_TAB_VALUES];
export type SignalCenterHistoryView =
  (typeof SIGNAL_CENTER_HISTORY_VALUES)[keyof typeof SIGNAL_CENTER_HISTORY_VALUES];

export type SignalCenterHrefOptions = {
  scope?: SignalCenterScope;
  tab?: SignalCenterTab;
  history?: SignalCenterHistoryView;
  createRule?: boolean;
  stock?: string;
};

export function buildSignalCenterHref(options: SignalCenterHrefOptions = {}): string {
  const searchParams = new URLSearchParams();
  const tab = options.createRule
    ? SIGNAL_CENTER_TAB_VALUES.rules
    : options.history
      ? SIGNAL_CENTER_TAB_VALUES.history
      : options.tab;
  if (options.scope) {
    searchParams.set(SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope, options.scope);
  }
  if (tab) {
    searchParams.set(SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab, tab);
  }
  if (
    options.history
    && options.history !== SIGNAL_CENTER_HISTORY_VALUES.triggers
    && tab === SIGNAL_CENTER_TAB_VALUES.history
  ) {
    searchParams.set(SIGNAL_CENTER_ROUTE_QUERY_KEYS.history, options.history);
  }
  if (options.createRule) {
    searchParams.set(
      SIGNAL_CENTER_ROUTE_QUERY_KEYS.createRule,
      SIGNAL_CENTER_CREATE_RULE_VALUES.requested,
    );
  }
  if (options.stock?.trim()) {
    searchParams.set(SIGNAL_CENTER_ROUTE_QUERY_KEYS.stock, options.stock.trim());
  }
  const search = searchParams.toString();
  return search ? `${APP_ROUTE_PATHS.signals}?${search}` : APP_ROUTE_PATHS.signals;
}

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

export type RunFlowRouteValue =
  (typeof RUN_FLOW_ROUTE_QUERY_VALUES)[keyof typeof RUN_FLOW_ROUTE_QUERY_VALUES];

export const HOME_ROUTE_QUERY_KEYS = {
  stock: 'stock',
  workspace: 'workspace',
} as const;

export const HOME_WORKSPACE_VALUES = {
  history: 'history',
  watchlist: 'watchlist',
  today: 'today',
} as const;

export type HomeWorkspaceValue = (typeof HOME_WORKSPACE_VALUES)[keyof typeof HOME_WORKSPACE_VALUES];

export const RESEARCH_DISCOVER_ROUTE_QUERY_KEYS = {
  market: 'market',
  strategy: 'strategy',
  count: 'count',
} as const;

export const RESEARCH_DISCOVER_MARKET_VALUES = {
  china: 'cn',
} as const;

export const RESEARCH_DISCOVER_DEFAULT_VALUES = {
  market: RESEARCH_DISCOVER_MARKET_VALUES.china,
  strategy: 'dual_low',
  count: 3,
} as const;

export const RESEARCH_DISCOVER_LIMITS = {
  maxCount: 100,
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

export const RESEARCH_BACKTEST_LIMITS = {
  maxWindowDays: 120,
} as const;

export const ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS = {
  segment: 'segment',
  recordId: 'recordId',
  runFlow: 'runFlow',
  runFlowRecordId: 'runFlowRecordId',
  runFlowTaskId: 'runFlowTaskId',
} as const;

export const ANALYSIS_WORKBENCH_SEGMENT_VALUES = {
  launch: 'launch',
  tasks: 'tasks',
  history: 'history',
} as const;

export type AnalysisWorkbenchSegment =
  (typeof ANALYSIS_WORKBENCH_SEGMENT_VALUES)[keyof typeof ANALYSIS_WORKBENCH_SEGMENT_VALUES];

export type AnalysisWorkbenchHrefOptions = {
  segment?: AnalysisWorkbenchSegment;
  recordId?: number | null;
  runFlow?: RunFlowRouteValue;
  runFlowRecordId?: number | null;
  runFlowTaskId?: string | null;
  stock?: string | null;
};

const ANALYSIS_WORKBENCH_TASK_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

export function isStableAnalysisWorkbenchTaskId(value: string): boolean {
  return ANALYSIS_WORKBENCH_TASK_ID_PATTERN.test(value.trim());
}

function isPositiveSafeInteger(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}

export function buildAnalysisWorkbenchHref(
  options: AnalysisWorkbenchHrefOptions = {},
): string {
  const searchParams = new URLSearchParams();
  if (
    options.segment
    && options.segment !== ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch
  ) {
    searchParams.set(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment, options.segment);
  }
  if (isPositiveSafeInteger(options.recordId)) {
    searchParams.set(
      ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId,
      String(options.recordId),
    );
  }
  if (
    options.runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.history
    && isPositiveSafeInteger(options.runFlowRecordId)
  ) {
    searchParams.set(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow, options.runFlow);
    searchParams.set(
      ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId,
      String(options.runFlowRecordId),
    );
  } else if (
    options.runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.task
    && typeof options.runFlowTaskId === 'string'
    && isStableAnalysisWorkbenchTaskId(options.runFlowTaskId)
  ) {
    searchParams.set(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow, options.runFlow);
    searchParams.set(
      ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowTaskId,
      options.runFlowTaskId.trim(),
    );
  }
  if (options.stock?.trim()) {
    searchParams.set(HOME_ROUTE_QUERY_KEYS.stock, options.stock.trim());
  }
  const search = searchParams.toString();
  return search
    ? `${APP_ROUTE_PATHS.researchAnalysis}?${search}`
    : APP_ROUTE_PATHS.researchAnalysis;
}

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
