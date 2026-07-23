// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { StockHistoryPeriod } from '../types/stocks';
import {
  APP_ROUTE_PATHS,
  HOME_ROUTE_QUERY_KEYS,
  HOME_WORKSPACE_VALUES,
  LEGACY_ROUTE_PATHS,
  REPORT_ROUTE_QUERY_KEYS,
  SIGNAL_CENTER_ROUTE_QUERY_KEYS,
  SIGNAL_CENTER_TAB_VALUES,
  type HomeWorkspaceValue,
} from '../routing/routes';
import {
  parseResearchBacktestRouteState,
  parseResearchDiscoverRouteState,
} from '../routing/researchRouteState';
import {
  parseSignalCenterRouteState,
} from '../routing/signalCenterRouteState';
import { normalizeStockCode } from './stockCode';
import { validateStockCode } from './validation';

export type HomeWorkspaceView = HomeWorkspaceValue;
export type DecisionSignalsView = 'signals' | 'latest' | 'timeline' | 'stats';
export type ChatContextState = 'active';

export type DeepLinkTarget =
  | {
      page: 'home';
      recordId?: number;
      stockCode?: string;
      workspace?: HomeWorkspaceView;
    }
  | {
      page: 'chat';
      sessionId?: string;
      stockCode?: string;
      stockName?: string;
      recordId?: number;
      contextState?: ChatContextState;
    }
  | {
      page: 'portfolio';
      accountId?: number;
    }
  | {
      page: 'decision-signals';
      stockCode?: string;
      signalId?: number;
      view?: DecisionSignalsView;
    }
  | {
      page: 'stock';
      stockCode: string;
      period?: StockHistoryPeriod;
      days?: number;
    };

export type DeepLinkIssueCode =
  | 'external_origin'
  | 'invalid_account_id'
  | 'invalid_days'
  | 'invalid_filter'
  | 'invalid_period'
  | 'invalid_record_id'
  | 'invalid_session_id'
  | 'invalid_signal_id'
  | 'invalid_stock_code'
  | 'invalid_stock_name'
  | 'invalid_view'
  | 'invalid_workspace'
  | 'incomplete_chat_context'
  | 'sensitive_parameter'
  | 'unsupported_route';

export type DeepLinkIssue = {
  code: DeepLinkIssueCode;
  parameter?: string;
};

export type ParsedDeepLink = {
  target: DeepLinkTarget | null;
  normalizedHref: string;
  normalizedSearch: string;
  issues: DeepLinkIssue[];
};

const HOME_WORKSPACE_VIEWS = new Set<HomeWorkspaceView>(Object.values(HOME_WORKSPACE_VALUES));
const DECISION_SIGNAL_VIEWS = new Set<DecisionSignalsView>(['signals', 'latest', 'timeline', 'stats']);
const CHAT_CONTEXT_STATES = new Set<ChatContextState>(['active']);
const STOCK_HISTORY_PERIODS = new Set<StockHistoryPeriod>(['daily', 'weekly', 'monthly']);
const DECISION_SIGNAL_MARKETS = new Set(['cn', 'hk', 'us', 'jp', 'kr', 'tw']);
const DECISION_SIGNAL_ACTIONS = new Set(['buy', 'add', 'hold', 'reduce', 'sell', 'watch', 'avoid', 'alert']);
const DECISION_SIGNAL_PHASES = new Set([
  'premarket',
  'intraday',
  'lunch_break',
  'closing_auction',
  'postmarket',
  'non_trading',
  'unknown',
]);
const DECISION_SIGNAL_SOURCES = new Set(['analysis', 'agent', 'alert', 'market_review', 'manual']);
const DECISION_SIGNAL_STATUSES = new Set(['all', 'active', 'expired', 'invalidated', 'closed', 'archived']);
const TIMELINE_RANGES = new Set(['30d', '90d', '180d']);
const TIMELINE_STATUSES = new Set(['all', 'active']);
const TIMELINE_PROFILES = new Set(['conservative', 'balanced', 'aggressive', 'unknown']);
const SESSION_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const MAX_STOCK_NAME_LENGTH = 80;
const DEFAULT_ORIGIN = 'http://stockpulse.local';
const SENSITIVE_PARAMETER_KEYS = new Set([
  'accesstoken',
  'apikey',
  'authorization',
  'bearertoken',
  'clientkey',
  'clientsecret',
  'credential',
  'idtoken',
  'password',
  'passwd',
  'privatekey',
  'pwd',
  'refreshtoken',
  'secret',
  'secretkey',
  'token',
  'webhookurl',
]);
const SENSITIVE_PARAMETER_SUFFIXES = [
  'accesstoken',
  'apikey',
  'apikeys',
  'authorization',
  'bottoken',
  'credential',
  'credentials',
  'idtoken',
  'password',
  'passwd',
  'privatekey',
  'pwd',
  'refreshtoken',
  'secret',
  'secretkey',
  'token',
  'tokens',
  'webhookurl',
];

function assertPositiveInteger(value: number, field: string): number {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new TypeError(`${field} must be a positive safe integer`);
  }
  return value;
}

function parsePositiveInteger(value: string | null): number | undefined {
  if (!value || !/^\d+$/.test(value)) return undefined;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function normalizeSafeStockCode(value: string): string | null {
  const normalized = normalizeStockCode(value).toUpperCase();
  const validation = validateStockCode(normalized);
  return validation.valid ? normalizeStockCode(validation.normalized).toUpperCase() : null;
}

function requireStockCode(value: string): string {
  const normalized = normalizeSafeStockCode(value);
  if (!normalized) {
    throw new TypeError('stockCode must be a supported stock code');
  }
  return normalized;
}

function normalizeStockName(value: string): string | null {
  const normalized = value.trim().replace(/\s+/g, ' ');
  if (!normalized || normalized.length > MAX_STOCK_NAME_LENGTH) return null;
  const hasControlCharacter = Array.from(normalized).some((character) => {
    const code = character.charCodeAt(0);
    return code < 32 || code === 127;
  });
  return hasControlCharacter ? null : normalized;
}

function requireSessionId(value: string): string {
  const normalized = value.trim();
  if (!SESSION_ID_PATTERN.test(normalized)) {
    throw new TypeError('sessionId must be a stable non-sensitive identifier');
  }
  return normalized;
}

function setPositiveInteger(params: URLSearchParams, key: string, value?: number): void {
  if (value !== undefined) params.set(key, String(assertPositiveInteger(value, key)));
}

function stripSensitiveParameters(params: URLSearchParams, issues: DeepLinkIssue[]): void {
  for (const key of [...params.keys()]) {
    const normalizedKey = key.toLowerCase().replace(/[^a-z0-9]/g, '');
    const hasSeparatedKeySuffix = /(?:^|[_.-])keys?$/i.test(key) || /\[keys?\]$/i.test(key);
    const hasSensitiveSuffix = SENSITIVE_PARAMETER_SUFFIXES.some((suffix) => normalizedKey.endsWith(suffix));
    if (!SENSITIVE_PARAMETER_KEYS.has(normalizedKey) && !hasSeparatedKeySuffix && !hasSensitiveSuffix) continue;
    params.delete(key);
    issues.push({ code: 'sensitive_parameter', parameter: key });
  }
}

function stripSensitiveHash(url: URL, issues: DeepLinkIssue[]): void {
  const rawHash = url.hash.slice(1);
  if (!rawHash.includes('=')) return;
  const params = new URLSearchParams(rawHash);
  const issueCount = issues.length;
  stripSensitiveParameters(params, issues);
  if (issues.length === issueCount) return;
  const normalized = params.toString();
  url.hash = normalized ? `#${normalized}` : '';
}

function parseStockParam(
  params: URLSearchParams,
  issues: DeepLinkIssue[],
  key = 'stock',
): string | undefined {
  const raw = params.get(key);
  if (raw === null) return undefined;
  const stockCode = normalizeSafeStockCode(raw);
  if (!stockCode) {
    params.delete(key);
    issues.push({ code: 'invalid_stock_code', parameter: key });
    return undefined;
  }
  params.set(key, stockCode);
  return stockCode;
}

function parsePositiveIntegerParam(
  params: URLSearchParams,
  issues: DeepLinkIssue[],
  key: string,
  issueCode: DeepLinkIssueCode,
): number | undefined {
  const raw = params.get(key);
  if (raw === null) return undefined;
  const value = parsePositiveInteger(raw);
  if (value === undefined) {
    params.delete(key);
    issues.push({ code: issueCode, parameter: key });
    return undefined;
  }
  params.set(key, String(value));
  return value;
}

function parseEnumParam(
  params: URLSearchParams,
  issues: DeepLinkIssue[],
  key: string,
  allowed: ReadonlySet<string>,
): string | undefined {
  const raw = params.get(key);
  if (raw === null) return undefined;
  if (allowed.has(raw)) return raw;
  params.delete(key);
  issues.push({ code: 'invalid_filter', parameter: key });
  return undefined;
}

function toHref(url: URL): string {
  return `${url.pathname}${url.search}${url.hash}`;
}

export function buildDeepLink(target: DeepLinkTarget): string {
  const params = new URLSearchParams();
  let pathname: string = APP_ROUTE_PATHS.home;

  switch (target.page) {
    case 'home':
      setPositiveInteger(params, REPORT_ROUTE_QUERY_KEYS.recordId, target.recordId);
      if (target.stockCode) {
        params.set(HOME_ROUTE_QUERY_KEYS.stock, requireStockCode(target.stockCode));
      }
      if (target.workspace && target.workspace !== HOME_WORKSPACE_VALUES.history) {
        if (!HOME_WORKSPACE_VIEWS.has(target.workspace)) throw new TypeError('Unsupported Home workspace');
        params.set(HOME_ROUTE_QUERY_KEYS.workspace, target.workspace);
      }
      break;
    case 'chat': {
      pathname = APP_ROUTE_PATHS.agent;
      if (target.sessionId) params.set('session', requireSessionId(target.sessionId));
      if (target.stockCode) {
        params.set('stock', requireStockCode(target.stockCode));
        if (target.stockName) {
          const stockName = normalizeStockName(target.stockName);
          if (!stockName) throw new TypeError('stockName contains unsafe characters or is too long');
          params.set('name', stockName);
        }
        setPositiveInteger(params, REPORT_ROUTE_QUERY_KEYS.recordId, target.recordId);
        if (target.contextState) {
          if (!CHAT_CONTEXT_STATES.has(target.contextState)) throw new TypeError('Unsupported Chat context state');
          params.set('context', target.contextState);
        }
      } else if (target.stockName || target.recordId !== undefined) {
        throw new TypeError('Chat stockName and recordId require stockCode');
      } else if (target.contextState) {
        throw new TypeError('Chat context state requires stockCode');
      }
      break;
    }
    case 'portfolio':
      pathname = APP_ROUTE_PATHS.portfolio;
      setPositiveInteger(params, 'account', target.accountId);
      break;
    case 'decision-signals':
      pathname = APP_ROUTE_PATHS.signals;
      if (target.stockCode) params.set('stock', requireStockCode(target.stockCode));
      setPositiveInteger(params, 'signal', target.signalId);
      if (target.view === 'stats') {
        params.set(SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab, SIGNAL_CENTER_TAB_VALUES.review);
      } else if (target.view && target.view !== (target.stockCode ? 'latest' : 'signals')) {
        if (!DECISION_SIGNAL_VIEWS.has(target.view)) throw new TypeError('Unsupported Decision Signals view');
        params.set('view', target.view);
      }
      break;
    case 'stock':
      pathname = `/stocks/${encodeURIComponent(requireStockCode(target.stockCode))}`;
      if (target.period && target.period !== 'daily') {
        if (!STOCK_HISTORY_PERIODS.has(target.period)) throw new TypeError('Unsupported stock period');
        params.set('period', target.period);
      }
      if (target.days !== undefined && target.days !== 90) {
        if (!Number.isInteger(target.days) || target.days < 1 || target.days > 365) {
          throw new TypeError('days must be an integer between 1 and 365');
        }
        params.set('days', String(target.days));
      }
      break;
  }

  const search = params.toString();
  return `${pathname}${search ? `?${search}` : ''}`;
}

export function parseDeepLink(input: string, origin = DEFAULT_ORIGIN): ParsedDeepLink {
  let url: URL;
  try {
    url = new URL(input, origin);
  } catch {
    return {
      target: null,
      normalizedHref: '/',
      normalizedSearch: '',
      issues: [{ code: 'unsupported_route' }],
    };
  }

  const expectedOrigin = new URL(origin).origin;
  if (url.origin !== expectedOrigin) {
    return {
      target: null,
      normalizedHref: '/',
      normalizedSearch: '',
      issues: [{ code: 'external_origin' }],
    };
  }

  let params = new URLSearchParams(url.search);
  const issues: DeepLinkIssue[] = [];
  stripSensitiveParameters(params, issues);
  stripSensitiveHash(url, issues);
  let target: DeepLinkTarget | null = null;

  if (url.pathname === APP_ROUTE_PATHS.home) {
    const recordId = parsePositiveIntegerParam(
      params,
      issues,
      REPORT_ROUTE_QUERY_KEYS.recordId,
      'invalid_record_id',
    );
    const stockCode = parseStockParam(params, issues, HOME_ROUTE_QUERY_KEYS.stock);
    const rawWorkspace = params.get(HOME_ROUTE_QUERY_KEYS.workspace);
    let workspace: HomeWorkspaceView = HOME_WORKSPACE_VALUES.history;
    if (rawWorkspace !== null) {
      if (HOME_WORKSPACE_VIEWS.has(rawWorkspace as HomeWorkspaceView)) {
        workspace = rawWorkspace as HomeWorkspaceView;
        if (workspace === HOME_WORKSPACE_VALUES.history) {
          params.delete(HOME_ROUTE_QUERY_KEYS.workspace);
        }
      } else {
        params.delete(HOME_ROUTE_QUERY_KEYS.workspace);
        issues.push({ code: 'invalid_workspace', parameter: HOME_ROUTE_QUERY_KEYS.workspace });
      }
    }
    target = { page: 'home', recordId, stockCode, workspace };
  } else if (url.pathname === APP_ROUTE_PATHS.agent) {
    const rawSessionId = params.get('session');
    let sessionId: string | undefined;
    if (rawSessionId !== null) {
      const normalized = rawSessionId.trim();
      if (SESSION_ID_PATTERN.test(normalized)) {
        sessionId = normalized;
        params.set('session', normalized);
      } else {
        params.delete('session');
        issues.push({ code: 'invalid_session_id', parameter: 'session' });
      }
    }
    const stockCode = parseStockParam(params, issues);
    const rawStockName = params.get('name');
    const stockName = rawStockName === null ? null : normalizeStockName(rawStockName);
    const recordId = parsePositiveIntegerParam(
      params,
      issues,
      REPORT_ROUTE_QUERY_KEYS.recordId,
      'invalid_record_id',
    );
    const contextState = parseEnumParam(
      params,
      issues,
      'context',
      CHAT_CONTEXT_STATES,
    ) as ChatContextState | undefined;
    if (!stockCode) {
      if (rawStockName !== null || recordId !== undefined || contextState !== undefined) {
        issues.push({ code: 'incomplete_chat_context', parameter: 'stock' });
      }
      params.delete('name');
      params.delete(REPORT_ROUTE_QUERY_KEYS.recordId);
      params.delete('context');
    } else if (rawStockName !== null) {
      if (stockName) params.set('name', stockName);
      else {
        params.delete('name');
        issues.push({ code: 'invalid_stock_name', parameter: 'name' });
      }
    }
    target = {
      page: 'chat',
      sessionId,
      stockCode,
      stockName: stockCode ? stockName ?? undefined : undefined,
      recordId: stockCode ? recordId : undefined,
      ...(stockCode && contextState ? { contextState } : {}),
    };
  } else if (url.pathname === APP_ROUTE_PATHS.portfolio) {
    const accountId = parsePositiveIntegerParam(params, issues, 'account', 'invalid_account_id');
    target = { page: 'portfolio', accountId };
  } else if (
    url.pathname === APP_ROUTE_PATHS.signals
    || url.pathname === LEGACY_ROUTE_PATHS.decisionSignals
  ) {
    if (url.pathname === LEGACY_ROUTE_PATHS.decisionSignals) {
      url.pathname = APP_ROUTE_PATHS.signals;
    }
    const parsedSignalCenter = parseSignalCenterRouteState(params);
    params = parsedSignalCenter.normalizedParams;
    parsedSignalCenter.invalidKeys.forEach((parameter) => {
      issues.push({ code: 'invalid_filter', parameter });
    });
    const stockCode = parseStockParam(params, issues);
    const signalId = parsePositiveIntegerParam(params, issues, 'signal', 'invalid_signal_id');
    parseEnumParam(params, issues, 'market', DECISION_SIGNAL_MARKETS);
    parseStockParam(params, issues, 'listStock');
    parseEnumParam(params, issues, 'action', DECISION_SIGNAL_ACTIONS);
    parseEnumParam(params, issues, 'phase', DECISION_SIGNAL_PHASES);
    parseEnumParam(params, issues, 'source', DECISION_SIGNAL_SOURCES);
    parseEnumParam(params, issues, 'status', DECISION_SIGNAL_STATUSES);
    parsePositiveIntegerParam(params, issues, 'page', 'invalid_filter');
    parseEnumParam(params, issues, 'timelineMarket', DECISION_SIGNAL_MARKETS);
    parseEnumParam(params, issues, 'timelineRange', TIMELINE_RANGES);
    parseEnumParam(params, issues, 'timelineStatus', TIMELINE_STATUSES);
    parseEnumParam(params, issues, 'timelineProfile', TIMELINE_PROFILES);
    const sourceReportId = parsePositiveIntegerParam(params, issues, 'sourceReportId', 'invalid_filter');
    const legacySourceReportId = parsePositiveIntegerParam(
      params,
      issues,
      'source_report_id',
      'invalid_filter',
    );
    if (sourceReportId === undefined && legacySourceReportId !== undefined) {
      params.set('sourceReportId', String(legacySourceReportId));
    }
    params.delete('source_report_id');
    const rawView = params.get('view');
    const defaultView: DecisionSignalsView = stockCode ? 'latest' : 'signals';
    let view: DecisionSignalsView = defaultView;
    if (rawView !== null) {
      if (DECISION_SIGNAL_VIEWS.has(rawView as DecisionSignalsView)) {
        view = rawView as DecisionSignalsView;
        if (view === defaultView) params.delete('view');
      } else {
        params.delete('view');
        issues.push({ code: 'invalid_view', parameter: 'view' });
      }
    }
    if (view === 'stats') {
      params.delete('view');
      params.set(SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab, SIGNAL_CENTER_TAB_VALUES.review);
    }
    target = { page: 'decision-signals', stockCode, signalId, view };
  } else {
    const stockMatch = url.pathname.match(/^\/stocks\/([^/]+)$/);
    if (stockMatch) {
      let rawStockCode = stockMatch[1];
      try {
        rawStockCode = decodeURIComponent(rawStockCode);
      } catch {
        // The validator below reports the malformed path as an invalid stock code.
      }
      const stockCode = normalizeSafeStockCode(rawStockCode);
      if (!stockCode) {
        issues.push({ code: 'invalid_stock_code', parameter: 'stockCode' });
        url.pathname = '/';
        url.hash = '';
        for (const key of [...params.keys()]) params.delete(key);
      } else {
        url.pathname = `/stocks/${encodeURIComponent(stockCode)}`;
        const rawPeriod = params.get('period');
        const period = STOCK_HISTORY_PERIODS.has(rawPeriod as StockHistoryPeriod)
          ? rawPeriod as StockHistoryPeriod
          : 'daily';
        if (rawPeriod !== null && !STOCK_HISTORY_PERIODS.has(rawPeriod as StockHistoryPeriod)) {
          params.delete('period');
          issues.push({ code: 'invalid_period', parameter: 'period' });
        } else if (period === 'daily') {
          params.delete('period');
        }
        const rawDays = params.get('days');
        const parsedDays = Number(rawDays);
        const days = rawDays !== null && Number.isInteger(parsedDays) && parsedDays >= 1 && parsedDays <= 365
          ? parsedDays
          : 90;
        if (rawDays !== null && days === 90) {
          params.delete('days');
          if (parsedDays !== 90) issues.push({ code: 'invalid_days', parameter: 'days' });
        } else if (rawDays !== null) {
          params.set('days', String(days));
        }
        target = { page: 'stock', stockCode, period, days };
      }
    } else if (
      url.pathname === APP_ROUTE_PATHS.researchDiscover
      || url.pathname === LEGACY_ROUTE_PATHS.screening
    ) {
      const parsedResearch = parseResearchDiscoverRouteState(params);
      params = parsedResearch.normalizedParams;
      parsedResearch.invalidKeys.forEach((parameter) => {
        issues.push({ code: 'invalid_filter', parameter });
      });
    } else if (
      url.pathname === APP_ROUTE_PATHS.researchBacktest
      || url.pathname === LEGACY_ROUTE_PATHS.backtest
    ) {
      const parsedResearch = parseResearchBacktestRouteState(params);
      params = parsedResearch.normalizedParams;
      parsedResearch.invalidKeys.forEach((parameter) => {
        issues.push({ code: 'invalid_filter', parameter });
      });
    } else if (!new Set<string>([
      LEGACY_ROUTE_PATHS.alerts,
      APP_ROUTE_PATHS.researchMarket,
      APP_ROUTE_PATHS.settings,
      LEGACY_ROUTE_PATHS.usage,
    ]).has(url.pathname)) {
      issues.push({ code: 'unsupported_route' });
    }
  }

  url.search = params.toString();
  return {
    target,
    normalizedHref: toHref(url),
    normalizedSearch: url.search,
    issues,
  };
}
