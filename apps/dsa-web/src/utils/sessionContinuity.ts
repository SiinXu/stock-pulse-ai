// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { DeepLinkTarget } from './deepLink';
import { buildDeepLink, parseDeepLink } from './deepLink';
import {
  APP_ROUTE_PATHS,
  HOME_ROUTE_QUERY_KEYS,
  LEGACY_ROUTE_PATHS,
  REPORT_ROUTE_QUERY_KEYS,
  RESEARCH_BACKTEST_ROUTE_QUERY_KEYS,
  RESEARCH_DISCOVER_ROUTE_QUERY_KEYS,
  SIGNAL_CENTER_ROUTE_QUERY_KEYS,
} from '../routing/routes';
import {
  parseResearchBacktestRouteState,
  parseResearchDiscoverRouteState,
} from '../routing/researchRouteState';
import { parseHomeUrlState } from './homeUrlState';
import {
  WEB_SESSION_CONTINUITY_STORAGE_KEY,
  readSessionItem,
  removeSessionItem,
  writeSessionItem,
} from './sessionPersistence';
import { normalizeStockCode } from './stockCode';
import { validateStockCode } from './validation';

type PersistedRouteKey =
  | 'chat'
  | 'decision-signals'
  | 'home'
  | 'portfolio'
  | 'research-backtest'
  | 'research-discover'
  | 'research-market'
  | 'stock';

type PersistedStockContext = {
  stockCode: string;
  stockName?: string;
  recordId?: number;
};

type PersistedSessionContinuity = {
  version: 1;
  routes: Partial<Record<PersistedRouteKey, string>>;
  stockContext?: PersistedStockContext;
};

const EMPTY_STATE: PersistedSessionContinuity = { version: 1, routes: {} };
const MAX_PERSISTED_HREF_LENGTH = 2_048;
const INITIAL_RESTORE_PATHS = new Map<string, PersistedRouteKey>([
  [APP_ROUTE_PATHS.home, 'home'],
  [APP_ROUTE_PATHS.agent, 'chat'],
  [APP_ROUTE_PATHS.signals, 'decision-signals'],
  [APP_ROUTE_PATHS.portfolio, 'portfolio'],
  [APP_ROUTE_PATHS.researchBacktest, 'research-backtest'],
  [APP_ROUTE_PATHS.researchDiscover, 'research-discover'],
  [APP_ROUTE_PATHS.researchMarket, 'research-market'],
]);
const DEEP_LINK_ROUTE_KEYS = new Map<DeepLinkTarget['page'], PersistedRouteKey>([
  ['home', 'home'],
  ['chat', 'chat'],
  ['portfolio', 'portfolio'],
  ['decision-signals', 'decision-signals'],
  ['stock', 'stock'],
]);
const ALLOWED_QUERY_KEYS: Record<PersistedRouteKey, readonly string[]> = {
  home: [
    REPORT_ROUTE_QUERY_KEYS.recordId,
    HOME_ROUTE_QUERY_KEYS.stock,
    HOME_ROUTE_QUERY_KEYS.workspace,
    REPORT_ROUTE_QUERY_KEYS.runFlow,
    REPORT_ROUTE_QUERY_KEYS.runFlowRecordId,
    REPORT_ROUTE_QUERY_KEYS.runFlowTaskId,
  ],
  chat: ['session', 'stock', 'name', REPORT_ROUTE_QUERY_KEYS.recordId, 'context'],
  portfolio: ['account'],
  'decision-signals': [
    SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope,
    SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab,
    SIGNAL_CENTER_ROUTE_QUERY_KEYS.history,
    'stock',
    'signal',
    'view',
    'market',
    'listStock',
    'action',
    'phase',
    'source',
    'status',
    'page',
    'timelineMarket',
    'timelineRange',
    'timelineStatus',
    'timelineProfile',
    'sourceReportId',
  ],
  stock: ['period', 'days'],
  'research-discover': Object.values(RESEARCH_DISCOVER_ROUTE_QUERY_KEYS),
  'research-backtest': Object.values(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS),
  'research-market': Object.values(REPORT_ROUTE_QUERY_KEYS),
};
type SanitizedRoute = {
  href: string;
  key: PersistedRouteKey;
  target: DeepLinkTarget | null;
};

export const SESSION_RESTORE_SUPPRESS_STATE_KEY = '__stockpulseSkipSessionRestore';

export function markSessionRestoreSuppressed(state: unknown): Record<string, unknown> {
  return {
    ...(state && typeof state === 'object' && !Array.isArray(state)
      ? state as Record<string, unknown>
      : {}),
    [SESSION_RESTORE_SUPPRESS_STATE_KEY]: true,
  };
}

export function isSessionRestoreSuppressed(state: unknown): boolean {
  return Boolean(
    state
    && typeof state === 'object'
    && !Array.isArray(state)
    && (state as Record<string, unknown>)[SESSION_RESTORE_SUPPRESS_STATE_KEY] === true,
  );
}

function normalizeSafeStockCode(value: string): string | null {
  const normalized = normalizeStockCode(value).toUpperCase();
  const validation = validateStockCode(normalized);
  return validation.valid ? normalizeStockCode(validation.normalized).toUpperCase() : null;
}

function normalizeSafeStockName(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const normalized = value.trim().replace(/\s+/g, ' ');
  if (!normalized || normalized.length > 80) return null;
  return Array.from(normalized).some((character) => {
    const code = character.charCodeAt(0);
    return code < 32 || code === 127;
  }) ? null : normalized;
}

function sanitizeStandaloneRoute(url: URL): SanitizedRoute | null {
  const params = new URLSearchParams();
  if (
    url.pathname === APP_ROUTE_PATHS.researchDiscover
    || url.pathname === LEGACY_ROUTE_PATHS.screening
  ) {
    const normalized = parseResearchDiscoverRouteState(url.searchParams).ownedParams;
    return {
      key: 'research-discover',
      href: `${APP_ROUTE_PATHS.researchDiscover}${normalized.size ? `?${normalized}` : ''}`,
      target: null,
    };
  }
  if (
    url.pathname === APP_ROUTE_PATHS.researchBacktest
    || url.pathname === LEGACY_ROUTE_PATHS.backtest
  ) {
    const normalized = parseResearchBacktestRouteState(url.searchParams).ownedParams;
    return {
      key: 'research-backtest',
      href: `${APP_ROUTE_PATHS.researchBacktest}${normalized.size ? `?${normalized}` : ''}`,
      target: null,
    };
  }
  if (url.pathname === APP_ROUTE_PATHS.researchMarket) {
    const normalized = new URLSearchParams(parseHomeUrlState(url.search).normalizedSearch);
    for (const key of ALLOWED_QUERY_KEYS['research-market']) {
      const value = normalized.get(key);
      if (value !== null) params.set(key, value);
    }
    return {
      key: 'research-market',
      href: `${APP_ROUTE_PATHS.researchMarket}${params.size ? `?${params}` : ''}`,
      target: null,
    };
  }
  return null;
}

function sanitizeSessionHref(input: string): SanitizedRoute | null {
  if (!input || input.length > MAX_PERSISTED_HREF_LENGTH) return null;
  const parsed = parseDeepLink(input);
  const url = new URL(parsed.normalizedHref, 'http://stockpulse.local');
  const standalone = sanitizeStandaloneRoute(url);
  if (standalone) return standalone;
  if (!parsed.target) return null;

  const key = DEEP_LINK_ROUTE_KEYS.get(parsed.target.page);
  if (!key) return null;
  const params = new URLSearchParams();
  const sourceParams = key === 'home'
    ? new URLSearchParams(parseHomeUrlState(url.search).normalizedSearch)
    : url.searchParams;
  for (const parameter of ALLOWED_QUERY_KEYS[key]) {
    const value = sourceParams.get(parameter);
    if (value !== null) params.set(parameter, value);
  }
  const href = `${url.pathname}${params.size ? `?${params}` : ''}`;
  return { key, href, target: parseDeepLink(href).target };
}

function readState(): PersistedSessionContinuity {
  const raw = readSessionItem(WEB_SESSION_CONTINUITY_STORAGE_KEY);
  if (!raw) return EMPTY_STATE;
  try {
    const parsed = JSON.parse(raw) as Partial<PersistedSessionContinuity>;
    if (parsed.version !== 1 || !parsed.routes || typeof parsed.routes !== 'object') {
      removeSessionItem(WEB_SESSION_CONTINUITY_STORAGE_KEY);
      return EMPTY_STATE;
    }
    const routes: PersistedSessionContinuity['routes'] = {};
    for (const value of Object.values(parsed.routes)) {
      if (typeof value !== 'string') continue;
      const sanitized = sanitizeSessionHref(value);
      if (sanitized) routes[sanitized.key] = sanitized.href;
    }
    const stockCode = parsed.stockContext?.stockCode
      ? normalizeSafeStockCode(parsed.stockContext.stockCode)
      : null;
    const stockName = normalizeSafeStockName(parsed.stockContext?.stockName);
    const normalizedState: PersistedSessionContinuity = {
      version: 1,
      routes,
      ...(stockCode
        ? {
            stockContext: {
              stockCode,
              ...(stockName ? { stockName } : {}),
              ...(Number.isSafeInteger(parsed.stockContext?.recordId) && Number(parsed.stockContext?.recordId) > 0
                ? { recordId: Number(parsed.stockContext?.recordId) }
                : {}),
            },
          }
        : {}),
    };
    const normalizedRaw = JSON.stringify(normalizedState);
    if (normalizedRaw !== raw) writeSessionItem(WEB_SESSION_CONTINUITY_STORAGE_KEY, normalizedRaw);
    return normalizedState;
  } catch {
    removeSessionItem(WEB_SESSION_CONTINUITY_STORAGE_KEY);
    return EMPTY_STATE;
  }
}

function writeState(state: PersistedSessionContinuity): void {
  writeSessionItem(WEB_SESSION_CONTINUITY_STORAGE_KEY, JSON.stringify(state));
}

function stockContextFromTarget(target: DeepLinkTarget | null): PersistedStockContext | null {
  if (!target || !('stockCode' in target) || !target.stockCode) return null;
  return {
    stockCode: target.stockCode,
    ...('stockName' in target && target.stockName ? { stockName: target.stockName } : {}),
    ...('recordId' in target && target.recordId ? { recordId: target.recordId } : {}),
  };
}

function stockContextFromRoute(route: SanitizedRoute | null): PersistedStockContext | null {
  const targetContext = stockContextFromTarget(route?.target ?? null);
  if (targetContext) return targetContext;
  if (route?.key !== 'research-backtest') return null;
  const code = new URL(route.href, 'http://stockpulse.local').searchParams.get(
    RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code,
  );
  return code ? { stockCode: code } : null;
}

function routeOwnsStockContext(route: SanitizedRoute | null): boolean {
  return Boolean(route && ['research-backtest', 'chat', 'decision-signals', 'home', 'stock'].includes(route.key));
}

export function recordSessionLocation(href: string): void {
  const sanitized = sanitizeSessionHref(href);
  if (!sanitized) return;
  const current = readState();
  const stockContext = stockContextFromRoute(sanitized);
  writeState({
    version: 1,
    routes: { ...current.routes, [sanitized.key]: sanitized.href },
    ...(stockContext
      ? { stockContext }
      : routeOwnsStockContext(sanitized)
        ? {}
        : current.stockContext
          ? { stockContext: current.stockContext }
          : {}),
  });
}

export function resolveInitialSessionHref(href: string): string | null {
  const url = new URL(href, 'http://stockpulse.local');
  if (url.search || url.hash) return null;
  const key = INITIAL_RESTORE_PATHS.get(url.pathname);
  if (!key) return null;
  const restored = readState().routes[key];
  return restored && restored !== url.pathname ? restored : null;
}

function targetForHref(href: string | undefined): DeepLinkTarget | null {
  return href ? sanitizeSessionHref(href)?.target ?? null : null;
}

function appendAllowedParameters(
  baseHref: string,
  sourceHref: string,
  key: PersistedRouteKey,
  excluded: ReadonlySet<string> = new Set(),
): string {
  const baseUrl = new URL(baseHref, 'http://stockpulse.local');
  const sourceUrl = new URL(sourceHref, 'http://stockpulse.local');
  const ownedByBase = new Set(baseUrl.searchParams.keys());
  for (const parameter of ALLOWED_QUERY_KEYS[key]) {
    if (ownedByBase.has(parameter) || excluded.has(parameter)) continue;
    const value = sourceUrl.searchParams.get(parameter);
    if (value !== null) baseUrl.searchParams.set(parameter, value);
  }
  return `${baseUrl.pathname}${baseUrl.search}`;
}

export function resolveContextAwareNavigationTarget(to: string, currentHref: string): string {
  const destinationKey = INITIAL_RESTORE_PATHS.get(to);
  if (!destinationKey) return to;

  const state = readState();
  const currentRoute = sanitizeSessionHref(currentHref);
  const persistedHref = state.routes[destinationKey];
  const savedSourceHref = currentRoute?.key === destinationKey
    ? currentRoute.href
    : persistedHref;
  const savedHref = savedSourceHref ?? to;
  const savedTarget = targetForHref(savedSourceHref);
  const sourceContext = stockContextFromRoute(currentRoute)
    ?? (routeOwnsStockContext(currentRoute) ? undefined : state.stockContext);
  if (!sourceContext) return savedHref;

  switch (destinationKey) {
    case 'home': {
      const saved = savedTarget?.page === 'home' ? savedTarget : null;
      const sameStock = saved?.stockCode === sourceContext.stockCode;
      const base = buildDeepLink({
        page: 'home',
        stockCode: sourceContext.stockCode,
        workspace: saved?.workspace,
        recordId: sourceContext.recordId,
      });
      return appendAllowedParameters(
        base,
        savedHref,
        destinationKey,
        sameStock
          ? new Set()
          : new Set(Object.values(REPORT_ROUTE_QUERY_KEYS)),
      );
    }
    case 'chat': {
      const saved = savedTarget?.page === 'chat' ? savedTarget : null;
      const sameStock = saved?.stockCode === sourceContext.stockCode;
      return buildDeepLink({
        page: 'chat',
        sessionId: saved?.sessionId,
        stockCode: sourceContext.stockCode,
        stockName: sourceContext.stockName ?? (sameStock ? saved?.stockName : undefined),
        recordId: sourceContext.recordId ?? (sameStock ? saved?.recordId : undefined),
        contextState: sameStock ? saved?.contextState : undefined,
      });
    }
    case 'decision-signals': {
      const saved = savedTarget?.page === 'decision-signals' ? savedTarget : null;
      const base = buildDeepLink({
        page: 'decision-signals',
        stockCode: sourceContext.stockCode,
        signalId: saved?.stockCode === sourceContext.stockCode ? saved.signalId : undefined,
        view: saved?.view,
      });
      return appendAllowedParameters(
        base,
        savedHref,
        destinationKey,
        saved?.stockCode === sourceContext.stockCode ? new Set() : new Set(['signal']),
      );
    }
    case 'research-backtest': {
      const url = new URL(savedHref, 'http://stockpulse.local');
      url.searchParams.set(RESEARCH_BACKTEST_ROUTE_QUERY_KEYS.code, sourceContext.stockCode);
      return `${url.pathname}${url.search}`;
    }
    default:
      return savedHref;
  }
}
