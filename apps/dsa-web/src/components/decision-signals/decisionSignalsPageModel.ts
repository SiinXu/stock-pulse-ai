// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiTextKey } from '../../i18n/uiText';
import type { DecisionAction, MarketPhaseValue, StockBarItem } from '../../types/analysis';
import type {
  DecisionSignalItem,
  DecisionSignalListParams,
  DecisionSignalListResponse,
  DecisionSignalMarket,
  DecisionSignalSourceType,
  DecisionSignalStatus,
  DecisionProfile,
  DecisionProfileDisplay,
} from '../../types/decisionSignals';
import type { StockIndexItem } from '../../types/stockIndex';
import { getDecisionProfile } from '../../utils/decisionSignalProfile';
import { parseDecisionSignalDate } from '../../utils/decisionSignalTime';
import { getDecisionSignalPresentation } from '../../utils/decisionSignalPresentation';
import { areStockCodesEquivalent } from '../../utils/stockCode';
import {
  SIGNAL_CENTER_SCOPE_VALUES,
  type SignalCenterScope,
} from '../../routing/routes';

export const PAGE_SIZE = 20;
export const TIMELINE_PAGE_SIZE = 100;
export const WATCHLIST_SIGNAL_LOOKUP_CONCURRENCY = 6;
export const STOCK_CANDIDATE_LIMIT = 8;
export const DAY_MS = 86400_000;
export const SIGNAL_CENTER_TABS_ID = 'signal-center-tabs';
export const SIGNAL_FEED_TABS_ID = 'signal-center-feed-tabs';

export type RequestSlotQueue = {
  active: number;
  waiters: Array<() => void>;
};

export type ListFilters = {
  market: '' | DecisionSignalMarket;
  stockCode: string;
  action: '' | DecisionAction;
  marketPhase: '' | MarketPhaseValue;
  sourceType: '' | DecisionSignalSourceType;
  sourceReportId: string;
  status: '' | DecisionSignalStatus;
};

export type TimelineRange = '30d' | '90d' | '180d';
export type TimelineStatusFilter = 'all' | 'active';

export type TimelineFilters = {
  market: '' | DecisionSignalMarket;
  range: TimelineRange;
  status: TimelineStatusFilter;
  decisionProfile: '' | DecisionProfileDisplay;
};

export type TimelineMarketSource = 'context' | 'user' | null;

export type TimelineFilterUpdate = {
  filters: TimelineFilters;
  marketSource: TimelineMarketSource;
};

export type AppliedTimelineContext = TimelineFilters & {
  stockCode: string;
};

export type StockContext = {
  code: string;
  displayCode?: string;
  name?: string;
  market?: DecisionSignalMarket;
};

export type StockCandidate = StockContext & {
  source: 'history' | 'popular';
};

export type PendingStatusChange = {
  item: DecisionSignalItem;
  status: Extract<DecisionSignalStatus, 'closed' | 'invalidated' | 'archived'>;
  message: string;
};

export type SelectedSignal = {
  item: DecisionSignalItem;
  source: 'list' | 'latest' | 'timeline' | 'persisted' | 'outcome';
};

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export const MARKET_OPTIONS: DecisionSignalMarket[] = ['cn', 'hk', 'us', 'jp', 'kr', 'tw'];
export const ACTION_OPTIONS: DecisionAction[] = ['buy', 'add', 'hold', 'reduce', 'sell', 'watch', 'avoid', 'alert'];
export const PHASE_OPTIONS: MarketPhaseValue[] = ['premarket', 'intraday', 'lunch_break', 'closing_auction', 'postmarket', 'non_trading', 'unknown'];
export const SOURCE_OPTIONS: DecisionSignalSourceType[] = ['analysis', 'agent', 'alert', 'market_review', 'manual'];
export const STATUS_OPTIONS: DecisionSignalStatus[] = ['active', 'expired', 'invalidated', 'closed', 'archived'];

export const STATUS_ACTIONS: Array<PendingStatusChange['status']> = ['closed', 'invalidated', 'archived'];
export const REASSESS_PROFILES: DecisionProfile[] = ['conservative', 'balanced', 'aggressive'];

export const STATUS_LABEL_KEYS: Record<DecisionSignalStatus, UiTextKey> = {
  active: 'decisionSignals.active',
  expired: 'decisionSignals.expired',
  invalidated: 'decisionSignals.invalidated',
  closed: 'decisionSignals.closed',
  archived: 'decisionSignals.archived',
};

export const STATUS_ACTION_LABEL_KEYS: Record<PendingStatusChange['status'], UiTextKey> = {
  closed: 'decisionSignals.close',
  invalidated: 'decisionSignals.invalidate',
  archived: 'decisionSignals.archive',
};

export const STATUS_ACTION_CONFIRM_KEYS: Record<PendingStatusChange['status'], UiTextKey> = {
  closed: 'decisionSignals.closeConfirm',
  invalidated: 'decisionSignals.invalidateConfirm',
  archived: 'decisionSignals.archiveConfirm',
};

export const DEFAULT_LIST_FILTERS: ListFilters = {
  market: '',
  stockCode: '',
  action: '',
  marketPhase: '',
  sourceType: '',
  sourceReportId: '',
  status: 'active',
};

export const DEFAULT_TIMELINE_FILTERS: TimelineFilters = {
  market: '',
  range: '90d',
  status: 'all',
  decisionProfile: '',
};

export const TIMELINE_RANGE_DAYS: Record<TimelineRange, number> = {
  '30d': 30,
  '90d': 90,
  '180d': 180,
};

export function parseSourceReportId(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

export function getInitialFilters(search = typeof window === 'undefined' ? '' : window.location.search): ListFilters {
  const params = new URLSearchParams(search);
  const sourceReportId = parseSourceReportId(params.get('sourceReportId') ?? params.get('source_report_id') ?? '');
  if (sourceReportId !== undefined) {
    return { ...DEFAULT_LIST_FILTERS, sourceReportId: String(sourceReportId) };
  }
  const market = params.get('market');
  const action = params.get('action');
  const marketPhase = params.get('phase');
  const sourceType = params.get('source');
  const status = params.get('status');
  return {
    market: MARKET_OPTIONS.includes(market as DecisionSignalMarket) ? market as DecisionSignalMarket : '',
    stockCode: params.get('listStock')?.trim() ?? '',
    action: ACTION_OPTIONS.includes(action as DecisionAction) ? action as DecisionAction : '',
    marketPhase: PHASE_OPTIONS.includes(marketPhase as MarketPhaseValue) ? marketPhase as MarketPhaseValue : '',
    sourceType: SOURCE_OPTIONS.includes(sourceType as DecisionSignalSourceType) ? sourceType as DecisionSignalSourceType : '',
    sourceReportId: '',
    status: status === 'all'
      ? ''
      : STATUS_OPTIONS.includes(status as DecisionSignalStatus) ? status as DecisionSignalStatus : DEFAULT_LIST_FILTERS.status,
  };
}

export function getInitialPage(search = typeof window === 'undefined' ? '' : window.location.search): number {
  const page = Number(new URLSearchParams(search).get('page'));
  return Number.isInteger(page) && page > 0 ? page : 1;
}

export function getInitialSelectedSignalId(search = typeof window === 'undefined' ? '' : window.location.search): number | null {
  const signalId = Number(new URLSearchParams(search).get('signal'));
  return Number.isInteger(signalId) && signalId > 0 ? signalId : null;
}

export function getInitialTimelineFilters(search = typeof window === 'undefined' ? '' : window.location.search): TimelineFilters {
  const params = new URLSearchParams(search);
  const market = params.get('timelineMarket');
  const range = params.get('timelineRange');
  const status = params.get('timelineStatus');
  const decisionProfile = params.get('timelineProfile');
  return {
    market: MARKET_OPTIONS.includes(market as DecisionSignalMarket) ? market as DecisionSignalMarket : '',
    range: ['30d', '90d', '180d'].includes(range ?? '') ? range as TimelineRange : DEFAULT_TIMELINE_FILTERS.range,
    status: ['all', 'active'].includes(status ?? '') ? status as TimelineStatusFilter : DEFAULT_TIMELINE_FILTERS.status,
    decisionProfile: [...REASSESS_PROFILES, 'unknown'].includes(decisionProfile as DecisionProfileDisplay)
      ? decisionProfile as DecisionProfileDisplay
      : '',
  };
}

export type DecisionSignalSearchValues = Record<string, string | number | null | undefined>;

export function getDecisionSignalLocation(values: DecisionSignalSearchValues): string | null {
  if (typeof window === 'undefined') return null;
  const url = new URL(window.location.href);
  Object.entries(values).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') url.searchParams.delete(key);
    else url.searchParams.set(key, String(value));
  });
  return `${url.pathname}${url.search}${url.hash}`;
}

export function getListSearchValues(filters: ListFilters, page: number): DecisionSignalSearchValues {
  const sourceReportId = parseSourceReportId(filters.sourceReportId);
  return {
    sourceReportId,
    source_report_id: null,
    market: sourceReportId ? null : filters.market,
    listStock: sourceReportId ? null : filters.stockCode.trim(),
    action: sourceReportId ? null : filters.action,
    phase: sourceReportId ? null : filters.marketPhase,
    source: sourceReportId ? null : filters.sourceType,
    status: sourceReportId || filters.status === DEFAULT_LIST_FILTERS.status ? null : filters.status || 'all',
    page: page > 1 ? page : null,
  };
}

export function getTimelineSearchValues(filters: TimelineFilters): DecisionSignalSearchValues {
  return {
    timelineMarket: filters.market,
    timelineRange: filters.range === DEFAULT_TIMELINE_FILTERS.range ? null : filters.range,
    timelineStatus: filters.status === DEFAULT_TIMELINE_FILTERS.status ? null : filters.status,
    timelineProfile: filters.decisionProfile,
  };
}

// Reflect current-stock selection in URL history so shared links, refresh, and
// browser navigation restore the same context.
export function getStockSearchValues(code: string | null): DecisionSignalSearchValues {
  return { stock: code };
}

export function toListParams(
  filters: ListFilters,
  page: number,
  scope: SignalCenterScope = SIGNAL_CENTER_SCOPE_VALUES.all,
): DecisionSignalListParams {
  const sourceReportId = parseSourceReportId(filters.sourceReportId);
  if (sourceReportId !== undefined) {
    return {
      sourceReportId,
      sourceType: 'analysis',
      holdingOnly: scope === SIGNAL_CENTER_SCOPE_VALUES.holdings || undefined,
      page,
      pageSize: PAGE_SIZE,
    };
  }

  return {
    market: filters.market || undefined,
    stockCode: filters.stockCode.trim() || undefined,
    action: filters.action || undefined,
    marketPhase: filters.marketPhase || undefined,
    sourceType: filters.sourceType || undefined,
    status: filters.status || undefined,
    holdingOnly: scope === SIGNAL_CENTER_SCOPE_VALUES.holdings || undefined,
    page,
    pageSize: PAGE_SIZE,
  };
}

export function mergeWatchlistSignalResponses(
  responses: Array<{ stockCode: string; response: DecisionSignalListResponse }>,
  page: number,
): DecisionSignalListResponse {
  const byId = new Map<number, DecisionSignalItem>();
  const totalByStock = new Map<string, number>();
  responses.forEach(({ stockCode, response }) => {
    response.items.forEach((item) => byId.set(item.id, item));
    totalByStock.set(stockCode, Math.max(totalByStock.get(stockCode) ?? 0, response.total));
  });
  const merged = [...byId.values()].sort((left, right) => {
    const leftTime = parseDecisionSignalDate(getDecisionSignalPresentation(left).timestamp)?.getTime() ?? 0;
    const rightTime = parseDecisionSignalDate(getDecisionSignalPresentation(right).timestamp)?.getTime() ?? 0;
    return rightTime - leftTime;
  });
  const start = (page - 1) * PAGE_SIZE;
  return {
    items: merged.slice(start, start + PAGE_SIZE),
    total: Math.max(merged.length, [...totalByStock.values()].reduce((sum, total) => sum + total, 0)),
    page,
    pageSize: PAGE_SIZE,
  };
}

export function refreshLatestSelection(
  current: SelectedSignal | null,
  latestItems: DecisionSignalItem[],
): SelectedSignal | null {
  if (!current || current.source !== 'latest') return current;
  const refreshed = latestItems.find((item) => item.id === current.item.id);
  return refreshed ? { source: 'latest', item: refreshed } : null;
}

export function refreshTimelineSelection(
  current: SelectedSignal | null,
  timelineItems: DecisionSignalItem[],
): SelectedSignal | null {
  if (!current || current.source !== 'timeline') return current;
  const refreshed = timelineItems.find((item) => item.id === current.item.id);
  return refreshed ? { source: 'timeline', item: refreshed } : null;
}

export function normalizeDecisionSignalMarket(value: unknown): DecisionSignalMarket | undefined {
  const market = String(value ?? '').trim().toUpperCase();
  if (!market || market === 'INDEX' || market === 'ETF' || market === 'UNKNOWN') return undefined;
  if (market === 'CN' || market === 'BSE') return 'cn';
  if (market === 'HK') return 'hk';
  if (market === 'US') return 'us';
  if (market === 'JP') return 'jp';
  if (market === 'KR') return 'kr';
  if (market === 'TW') return 'tw';
  if (MARKET_OPTIONS.includes(market.toLowerCase() as DecisionSignalMarket)) {
    return market.toLowerCase() as DecisionSignalMarket;
  }
  return undefined;
}

export function getCandidateKey(candidate: Pick<StockCandidate, 'code' | 'market'>): string {
  const code = candidate.code.trim().toUpperCase();
  return candidate.market ? `${candidate.market}:${code}` : code;
}

export function toHistoryCandidate(item: StockBarItem): StockCandidate | null {
  const code = String(item.stockCode || '').trim();
  if (!code || code.toUpperCase() === 'MARKET') return null;
  return {
    code,
    displayCode: code,
    name: item.stockName || undefined,
    market: normalizeDecisionSignalMarket(item.marketPhaseSummary?.market),
    source: 'history',
  };
}

export function toPopularCandidates(index: StockIndexItem[], limit = STOCK_CANDIDATE_LIMIT): StockCandidate[] {
  const candidates: StockCandidate[] = [];
  const seen = new Set<string>();
  const sorted = [...index]
    .filter((item) => item.active && item.assetType === 'stock')
    .sort((left, right) => (right.popularity ?? 0) - (left.popularity ?? 0));

  for (const item of sorted) {
    const market = normalizeDecisionSignalMarket(item.market);
    const candidate: StockCandidate = {
      code: item.canonicalCode,
      displayCode: item.displayCode,
      name: item.nameZh,
      market,
      source: 'popular',
    };
    const key = getCandidateKey(candidate);
    if (seen.has(key)) continue;
    seen.add(key);
    candidates.push(candidate);
    if (candidates.length >= limit) break;
  }

  return candidates;
}

export function toTimelineParams(filters: TimelineFilters, stockCode: string): DecisionSignalListParams {
  const days = TIMELINE_RANGE_DAYS[filters.range];
  const createdTo = new Date();
  const createdFrom = new Date(createdTo.getTime() - days * DAY_MS);
  return {
    market: filters.market || undefined,
    stockCode,
    createdFrom: createdFrom.toISOString(),
    createdTo: createdTo.toISOString(),
    status: filters.status === 'active' ? 'active' : undefined,
    decisionProfile: filters.decisionProfile || undefined,
    page: 1,
    pageSize: TIMELINE_PAGE_SIZE,
  };
}

export function upsertDecisionSignal(
  current: DecisionSignalItem[],
  item: DecisionSignalItem,
  limit?: number,
): DecisionSignalItem[] {
  const next = [item, ...current.filter((candidate) => candidate.id !== item.id)];
  next.sort((left, right) => {
    const leftTime = parseDecisionSignalDate(getDecisionSignalPresentation(left).timestamp)?.getTime()
      ?? Number.NEGATIVE_INFINITY;
    const rightTime = parseDecisionSignalDate(getDecisionSignalPresentation(right).timestamp)?.getTime()
      ?? Number.NEGATIVE_INFINITY;
    return rightTime - leftTime || right.id - left.id;
  });
  return limit ? next.slice(0, limit) : next;
}

export function itemMatchesStockContext(item: DecisionSignalItem, context: StockContext): boolean {
  return areStockCodesEquivalent(item.stockCode, context.code)
    && (!context.market || item.market === context.market);
}

export function itemMatchesAppliedTimeline(
  item: DecisionSignalItem,
  context: AppliedTimelineContext,
  now = Date.now(),
): boolean {
  if (!areStockCodesEquivalent(item.stockCode, context.stockCode)) return false;
  if (context.market && item.market !== context.market) return false;
  if (context.status === 'active' && item.status !== 'active') return false;
  if (context.decisionProfile && getDecisionProfile(item) !== context.decisionProfile) return false;
  const createdAt = parseDecisionSignalDate(getDecisionSignalPresentation(item).timestamp)?.getTime();
  if (createdAt === undefined) return false;
  return createdAt >= now - TIMELINE_RANGE_DAYS[context.range] * DAY_MS && createdAt <= now;
}

export function isSameStockContext(
  previousContext: StockContext | null,
  nextContext: StockContext,
): boolean {
  return previousContext?.code.trim().toUpperCase() === nextContext.code.trim().toUpperCase()
    && previousContext?.market === nextContext.market;
}

export function buildNextTimelineFilters(
  currentFilters: TimelineFilters,
  previousContext: StockContext | null,
  nextContext: StockContext,
  marketSource: TimelineMarketSource,
): TimelineFilterUpdate {
  if (isSameStockContext(previousContext, nextContext)) {
    return { filters: currentFilters, marketSource };
  }
  if (nextContext.market) {
    return {
      filters: { ...currentFilters, market: nextContext.market },
      marketSource: 'context',
    };
  }
  if (marketSource === 'context') {
    return {
      filters: { ...currentFilters, market: '' },
      marketSource: null,
    };
  }
  return { filters: currentFilters, marketSource };
}

export function draftMatchesStockContext(draft: string, context: StockContext | null): context is StockContext {
  if (!context) return false;
  const normalizedDraft = draft.trim().toUpperCase();
  if (!normalizedDraft) return false;
  return normalizedDraft === context.code.trim().toUpperCase()
    || normalizedDraft === String(context.displayCode ?? '').trim().toUpperCase();
}

export function formatStatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return Number(value).toFixed(2).replace(/\.?0+$/, '');
}

export function formatStatPercent(value: number | null | undefined): string {
  const formatted = formatStatNumber(value);
  return formatted === '-' ? formatted : `${formatted}%`;
}

export async function runWithRequestSlot<T>(
  queue: RequestSlotQueue,
  limit: number,
  operation: () => Promise<T>,
): Promise<T> {
  await new Promise<void>((resolve) => {
    const start = () => {
      queue.active += 1;
      resolve();
    };
    if (queue.active < limit) start();
    else queue.waiters.push(start);
  });
  try {
    return await operation();
  } finally {
    queue.active -= 1;
    queue.waiters.shift()?.();
  }
}
