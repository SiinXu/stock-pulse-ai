import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, BarChart3, RefreshCw, Search, ShieldCheck } from 'lucide-react';
import {
  decisionSignalsApi,
  getDecisionSignalReassessBlockedError,
} from '../api/decisionSignals';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { historyApi } from '../api/history';
import {
  ApiErrorAlert,
  AppPage,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  InlineAlert,
  Input,
  Modal,
  PageHeader,
  Pagination,
  ResponsiveFilterPanel,
  SegmentedControl,
  Select,
  StatePanel,
  useToast,
} from '../components/common';
import {
  DecisionSignalCard,
  DecisionSignalDetails,
} from '../components/decision-signals/DecisionSignalDisplay';
import { DecisionSignalTimeline } from '../components/decision-signals/DecisionSignalTimeline';
import { StockAutocomplete } from '../components/StockAutocomplete';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { useStockIndex } from '../hooks/useStockIndex';
import type { UiTextKey } from '../i18n/uiText';
import type { DecisionAction, MarketPhaseValue, StockBarItem } from '../types/analysis';
import type {
  DecisionSignalItem,
  DecisionSignalFeedbackItem,
  DecisionSignalFeedbackValue,
  DecisionSignalListParams,
  DecisionSignalMarket,
  DecisionSignalOutcomeItem,
  DecisionSignalOutcomeStatsResponse,
  DecisionSignalReassessResponse,
  DecisionSignalReassessBlockedError,
  DecisionSignalSourceType,
  DecisionSignalStatus,
  DecisionProfile,
  DecisionProfileDisplay,
} from '../types/decisionSignals';
import type { Market, StockIndexItem } from '../types/stockIndex';
import { buildDecisionActionLabelMap } from '../utils/decisionAction';
import {
  getDecisionSignalMarketLabel,
  getDecisionSignalMarketPhaseLabel,
  getDecisionSignalSourceTypeLabel,
} from '../utils/decisionSignalLabels';
import { getDecisionProfile } from '../utils/decisionSignalProfile';
import { parseDecisionSignalDate } from '../utils/decisionSignalTime';
import { areStockCodesEquivalent } from '../utils/stockCode';

const PAGE_SIZE = 20;
const TIMELINE_PAGE_SIZE = 100;
const STOCK_CANDIDATE_LIMIT = 8;
const DAY_MS = 86400_000;

type ListFilters = {
  market: '' | DecisionSignalMarket;
  stockCode: string;
  action: '' | DecisionAction;
  marketPhase: '' | MarketPhaseValue;
  sourceType: '' | DecisionSignalSourceType;
  sourceReportId: string;
  status: '' | DecisionSignalStatus;
};

type TimelineRange = '30d' | '90d' | '180d';
type TimelineStatusFilter = 'all' | 'active';

type TimelineFilters = {
  market: '' | DecisionSignalMarket;
  range: TimelineRange;
  status: TimelineStatusFilter;
  decisionProfile: '' | DecisionProfileDisplay;
};

type TimelineMarketSource = 'context' | 'user' | null;

type TimelineFilterUpdate = {
  filters: TimelineFilters;
  marketSource: TimelineMarketSource;
};

type AppliedTimelineContext = TimelineFilters & {
  stockCode: string;
};

type StockContext = {
  code: string;
  displayCode?: string;
  name?: string;
  market?: DecisionSignalMarket;
};

type StockCandidate = StockContext & {
  source: 'history' | 'popular';
};

type PendingStatusChange = {
  item: DecisionSignalItem;
  status: Extract<DecisionSignalStatus, 'closed' | 'invalidated' | 'archived'>;
  message: string;
};

type SelectedSignal = {
  item: DecisionSignalItem;
  source: 'list' | 'latest' | 'timeline' | 'persisted';
};

type DecisionSignalsView = 'signals' | 'latest' | 'timeline' | 'stats';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

const MARKET_OPTIONS: DecisionSignalMarket[] = ['cn', 'hk', 'us', 'jp', 'kr', 'tw'];
const ACTION_OPTIONS: DecisionAction[] = ['buy', 'add', 'hold', 'reduce', 'sell', 'watch', 'avoid', 'alert'];
const PHASE_OPTIONS: MarketPhaseValue[] = ['premarket', 'intraday', 'lunch_break', 'closing_auction', 'postmarket', 'non_trading', 'unknown'];
const SOURCE_OPTIONS: DecisionSignalSourceType[] = ['analysis', 'agent', 'alert', 'market_review', 'manual'];
const STATUS_OPTIONS: DecisionSignalStatus[] = ['active', 'expired', 'invalidated', 'closed', 'archived'];

const STATUS_ACTIONS: Array<PendingStatusChange['status']> = ['closed', 'invalidated', 'archived'];
const REASSESS_PROFILES: DecisionProfile[] = ['conservative', 'balanced', 'aggressive'];

const STATUS_LABEL_KEYS: Record<DecisionSignalStatus, UiTextKey> = {
  active: 'decisionSignals.active',
  expired: 'decisionSignals.expired',
  invalidated: 'decisionSignals.invalidated',
  closed: 'decisionSignals.closed',
  archived: 'decisionSignals.archived',
};

const STATUS_ACTION_LABEL_KEYS: Record<PendingStatusChange['status'], UiTextKey> = {
  closed: 'decisionSignals.close',
  invalidated: 'decisionSignals.invalidate',
  archived: 'decisionSignals.archive',
};

const STATUS_ACTION_CONFIRM_KEYS: Record<PendingStatusChange['status'], UiTextKey> = {
  closed: 'decisionSignals.closeConfirm',
  invalidated: 'decisionSignals.invalidateConfirm',
  archived: 'decisionSignals.archiveConfirm',
};

const DEFAULT_LIST_FILTERS: ListFilters = {
  market: '',
  stockCode: '',
  action: '',
  marketPhase: '',
  sourceType: '',
  sourceReportId: '',
  status: 'active',
};

const DEFAULT_TIMELINE_FILTERS: TimelineFilters = {
  market: '',
  range: '90d',
  status: 'all',
  decisionProfile: '',
};

const TIMELINE_RANGE_DAYS: Record<TimelineRange, number> = {
  '30d': 30,
  '90d': 90,
  '180d': 180,
};

function parseSourceReportId(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function getInitialFilters(search = typeof window === 'undefined' ? '' : window.location.search): ListFilters {
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

function getInitialStockCode(search = typeof window === 'undefined' ? '' : window.location.search): string {
  return new URLSearchParams(search).get('stock')?.trim() ?? '';
}

function getInitialPage(search = typeof window === 'undefined' ? '' : window.location.search): number {
  const page = Number(new URLSearchParams(search).get('page'));
  return Number.isInteger(page) && page > 0 ? page : 1;
}

function getInitialSelectedSignalId(search = typeof window === 'undefined' ? '' : window.location.search): number | null {
  const signalId = Number(new URLSearchParams(search).get('signal'));
  return Number.isInteger(signalId) && signalId > 0 ? signalId : null;
}

function getInitialTimelineFilters(search = typeof window === 'undefined' ? '' : window.location.search): TimelineFilters {
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

function updateDecisionSignalSearchParams(values: Record<string, string | number | null | undefined>): void {
  if (typeof window === 'undefined') return;
  const url = new URL(window.location.href);
  Object.entries(values).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') url.searchParams.delete(key);
    else url.searchParams.set(key, String(value));
  });
  window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
}

function syncListSearchParams(filters: ListFilters, page: number): void {
  const sourceReportId = parseSourceReportId(filters.sourceReportId);
  updateDecisionSignalSearchParams({
    sourceReportId,
    source_report_id: null,
    market: sourceReportId ? null : filters.market,
    listStock: sourceReportId ? null : filters.stockCode.trim(),
    action: sourceReportId ? null : filters.action,
    phase: sourceReportId ? null : filters.marketPhase,
    source: sourceReportId ? null : filters.sourceType,
    status: sourceReportId || filters.status === DEFAULT_LIST_FILTERS.status ? null : filters.status || 'all',
    page: page > 1 ? page : null,
  });
}

function syncTimelineSearchParams(filters: TimelineFilters): void {
  updateDecisionSignalSearchParams({
    timelineMarket: filters.market,
    timelineRange: filters.range === DEFAULT_TIMELINE_FILTERS.range ? null : filters.range,
    timelineStatus: filters.status === DEFAULT_TIMELINE_FILTERS.status ? null : filters.status,
    timelineProfile: filters.decisionProfile,
  });
}

// Reflect the current-stock scope in the URL (without a new history entry) so
// the page can be shared/refreshed and restore the same stock.
function syncStockSearchParam(code: string | null): void {
  updateDecisionSignalSearchParams({ stock: code });
}

function toListParams(filters: ListFilters, page: number): DecisionSignalListParams {
  const sourceReportId = parseSourceReportId(filters.sourceReportId);
  if (sourceReportId !== undefined) {
    return {
      sourceReportId,
      sourceType: 'analysis',
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
    page,
    pageSize: PAGE_SIZE,
  };
}

function refreshLatestSelection(
  current: SelectedSignal | null,
  latestItems: DecisionSignalItem[],
): SelectedSignal | null {
  if (!current || current.source !== 'latest') return current;
  const refreshed = latestItems.find((item) => item.id === current.item.id);
  return refreshed ? { source: 'latest', item: refreshed } : null;
}

function refreshTimelineSelection(
  current: SelectedSignal | null,
  timelineItems: DecisionSignalItem[],
): SelectedSignal | null {
  if (!current || current.source !== 'timeline') return current;
  const refreshed = timelineItems.find((item) => item.id === current.item.id);
  return refreshed ? { source: 'timeline', item: refreshed } : null;
}

function normalizeDecisionSignalMarket(value: unknown): DecisionSignalMarket | undefined {
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

function getCandidateKey(candidate: Pick<StockCandidate, 'code' | 'market'>): string {
  const code = candidate.code.trim().toUpperCase();
  return candidate.market ? `${candidate.market}:${code}` : code;
}

function toHistoryCandidate(item: StockBarItem): StockCandidate | null {
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

function toPopularCandidates(index: StockIndexItem[], limit = STOCK_CANDIDATE_LIMIT): StockCandidate[] {
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

function toTimelineParams(filters: TimelineFilters, stockCode: string): DecisionSignalListParams {
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

function upsertDecisionSignal(
  current: DecisionSignalItem[],
  item: DecisionSignalItem,
  limit?: number,
): DecisionSignalItem[] {
  const next = [item, ...current.filter((candidate) => candidate.id !== item.id)];
  next.sort((left, right) => {
    const leftTime = parseDecisionSignalDate(left.createdAt)?.getTime() ?? Number.NEGATIVE_INFINITY;
    const rightTime = parseDecisionSignalDate(right.createdAt)?.getTime() ?? Number.NEGATIVE_INFINITY;
    return rightTime - leftTime || right.id - left.id;
  });
  return limit ? next.slice(0, limit) : next;
}

function itemMatchesStockContext(item: DecisionSignalItem, context: StockContext): boolean {
  return areStockCodesEquivalent(item.stockCode, context.code)
    && (!context.market || item.market === context.market);
}

function itemMatchesAppliedTimeline(
  item: DecisionSignalItem,
  context: AppliedTimelineContext,
  now = Date.now(),
): boolean {
  if (!areStockCodesEquivalent(item.stockCode, context.stockCode)) return false;
  if (context.market && item.market !== context.market) return false;
  if (context.status === 'active' && item.status !== 'active') return false;
  if (context.decisionProfile && getDecisionProfile(item) !== context.decisionProfile) return false;
  const createdAt = parseDecisionSignalDate(item.createdAt)?.getTime();
  if (createdAt === undefined) return false;
  return createdAt >= now - TIMELINE_RANGE_DAYS[context.range] * DAY_MS && createdAt <= now;
}

function isSameStockContext(
  previousContext: StockContext | null,
  nextContext: StockContext,
): boolean {
  return previousContext?.code.trim().toUpperCase() === nextContext.code.trim().toUpperCase()
    && previousContext?.market === nextContext.market;
}

function buildNextTimelineFilters(
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

function draftMatchesStockContext(draft: string, context: StockContext | null): context is StockContext {
  if (!context) return false;
  const normalizedDraft = draft.trim().toUpperCase();
  if (!normalizedDraft) return false;
  return normalizedDraft === context.code.trim().toUpperCase()
    || normalizedDraft === String(context.displayCode ?? '').trim().toUpperCase();
}

function formatStatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return Number(value).toFixed(2).replace(/\.?0+$/, '');
}

function formatStatPercent(value: number | null | undefined): string {
  const formatted = formatStatNumber(value);
  return formatted === '-' ? formatted : `${formatted}%`;
}

const DecisionSignalsPage: React.FC = () => {
  const { t } = useUiLanguage();
  const { showToast, dismissToast } = useToast();
  const actionLabels = useMemo(() => buildDecisionActionLabelMap(t), [t]);
  const { index: stockIndex } = useStockIndex();
  const [filters, setFilters] = useState<ListFilters>(() => getInitialFilters());
  const [appliedFilters, setAppliedFilters] = useState<ListFilters>(() => getInitialFilters());
  const [page, setPage] = useState(() => getInitialPage());
  const [items, setItems] = useState<DecisionSignalItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [statusError, setStatusError] = useState<ParsedApiError | null>(null);
  const [selected, setSelected] = useState<SelectedSignal | null>(null);
  const [activeView, setActiveView] = useState<DecisionSignalsView>('signals');
  const [pendingStatus, setPendingStatus] = useState<PendingStatusChange | null>(null);
  const [statusUpdating, setStatusUpdating] = useState(false);
  const [outcomeStats, setOutcomeStats] = useState<DecisionSignalOutcomeStatsResponse | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState<ParsedApiError | null>(null);
  const [stockDraft, setStockDraft] = useState('');
  const [stockContextModalOpen, setStockContextModalOpen] = useState(false);
  const [activeStockContext, setActiveStockContext] = useState<StockContext | null>(null);
  const [historyCandidates, setHistoryCandidates] = useState<StockCandidate[]>([]);
  const [historyCandidatesLoaded, setHistoryCandidatesLoaded] = useState(false);
  const [latestItems, setLatestItems] = useState<DecisionSignalItem[]>([]);
  const [latestSearched, setLatestSearched] = useState(false);
  const [latestLoading, setLatestLoading] = useState(false);
  const [latestError, setLatestError] = useState<ParsedApiError | null>(null);
  const [timelineFilters, setTimelineFilters] = useState<TimelineFilters>(() => getInitialTimelineFilters());
  const [appliedTimelineContext, setAppliedTimelineContext] = useState<AppliedTimelineContext | null>(null);
  const [timelineItems, setTimelineItems] = useState<DecisionSignalItem[]>([]);
  const [timelineSearched, setTimelineSearched] = useState(false);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState<ParsedApiError | null>(null);
  const [timelineTruncated, setTimelineTruncated] = useState(false);
  const [selectedOutcomes, setSelectedOutcomes] = useState<DecisionSignalOutcomeItem[]>([]);
  const [selectedOutcomesLoading, setSelectedOutcomesLoading] = useState(false);
  const [selectedOutcomesError, setSelectedOutcomesError] = useState<ParsedApiError | null>(null);
  const [selectedFeedback, setSelectedFeedback] = useState<DecisionSignalFeedbackItem | null>(null);
  const [selectedFeedbackLoading, setSelectedFeedbackLoading] = useState(false);
  const [selectedFeedbackError, setSelectedFeedbackError] = useState<ParsedApiError | null>(null);
  const [feedbackSaving, setFeedbackSaving] = useState(false);
  const [reassessProfile, setReassessProfile] = useState<DecisionProfile>('balanced');
  const [reassessResponse, setReassessResponse] = useState<DecisionSignalReassessResponse | null>(null);
  const [reassessLoading, setReassessLoading] = useState(false);
  const [reassessPersisting, setReassessPersisting] = useState(false);
  const [reassessPersistConfirm, setReassessPersistConfirm] = useState(false);
  const [reassessPersistBlocked, setReassessPersistBlocked] = useState<DecisionSignalReassessBlockedError | null>(null);
  const [reassessError, setReassessError] = useState<ParsedApiError | null>(null);
  const requestIdRef = useRef(0);
  const statsRequestIdRef = useRef(0);
  const latestRequestIdRef = useRef(0);
  const timelineRequestIdRef = useRef(0);
  const detailRequestIdRef = useRef(0);
  const reassessRequestIdRef = useRef(0);
  const selectedSignalIdRef = useRef<number | null>(null);
  const pendingSelectedSignalIdRef = useRef<number | null>(getInitialSelectedSignalId());
  const statusUpdateInFlightRef = useRef(false);
  const timelineMarketSourceRef = useRef<TimelineMarketSource>(null);
  const mountedRef = useRef(true);
  const statusToastIdRef = useRef<string | null>(null);

  const takePendingSelection = useCallback((
    source: SelectedSignal['source'],
    nextItems: DecisionSignalItem[],
  ): SelectedSignal | null => {
    const pendingId = pendingSelectedSignalIdRef.current;
    if (pendingId === null) return null;
    const item = nextItems.find((candidate) => candidate.id === pendingId);
    if (!item) return null;
    pendingSelectedSignalIdRef.current = null;
    return { source, item };
  }, []);

  const handleSelectSignal = useCallback((source: SelectedSignal['source'], item: DecisionSignalItem) => {
    pendingSelectedSignalIdRef.current = null;
    setSelected({ source, item });
    updateDecisionSignalSearchParams({ signal: item.id });
  }, []);

  const handleCloseSignal = useCallback(() => {
    pendingSelectedSignalIdRef.current = null;
    setStatusError(null);
    setSelected(null);
    updateDecisionSignalSearchParams({ signal: null });
  }, []);

  const popularCandidates = useMemo(
    () => toPopularCandidates(stockIndex, STOCK_CANDIDATE_LIMIT),
    [stockIndex],
  );
  const stockCandidates = historyCandidates.length > 0 ? historyCandidates : popularCandidates;
  const stockCandidateMode: 'history' | 'popular' | 'empty' = historyCandidates.length > 0
    ? 'history'
    : stockCandidates.length > 0
      ? 'popular'
      : 'empty';

  useEffect(() => {
    document.title = t('decisionSignals.pageTitle');
  }, [t]);

  useEffect(() => {
    if (statusUpdating) {
      if (!statusToastIdRef.current) {
        statusToastIdRef.current = showToast({
          title: t('common.processing'),
          message: t('decisionSignals.confirmStatusTitle'),
          tone: 'info',
          durationMs: 0,
        });
      }
      return;
    }
    if (statusToastIdRef.current) {
      dismissToast(statusToastIdRef.current);
      statusToastIdRef.current = null;
    }
  }, [dismissToast, showToast, statusUpdating, t]);

  useEffect(() => () => {
    if (statusToastIdRef.current) {
      dismissToast(statusToastIdRef.current);
      statusToastIdRef.current = null;
    }
  }, [dismissToast]);

  useEffect(() => {
    let mounted = true;
    void historyApi.getStockBarList({ limit: STOCK_CANDIDATE_LIMIT })
      .then((response) => {
        if (!mounted) return;
        const nextCandidates: StockCandidate[] = [];
        const seen = new Set<string>();
        for (const item of response.items) {
          const candidate = toHistoryCandidate(item);
          if (!candidate) continue;
          const key = getCandidateKey(candidate);
          if (seen.has(key)) continue;
          seen.add(key);
          nextCandidates.push(candidate);
          if (nextCandidates.length >= STOCK_CANDIDATE_LIMIT) break;
        }
        setHistoryCandidates(nextCandidates);
      })
      .catch(() => {
        if (mounted) setHistoryCandidates([]);
      })
      .finally(() => {
        if (mounted) setHistoryCandidatesLoaded(true);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const loadSignalsForPage = useCallback(async (nextPage: number) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    try {
      const response = await decisionSignalsApi.list(toListParams(appliedFilters, nextPage));
      if (requestIdRef.current !== requestId) return;
      const lastPage = Math.max(1, Math.ceil(response.total / PAGE_SIZE));
      if (response.total > 0 && nextPage > lastPage) {
        setPage(lastPage);
        syncListSearchParams(appliedFilters, lastPage);
        return;
      }
      setItems(response.items);
      setTotal(response.total);
      setError(null);
      syncListSearchParams(appliedFilters, nextPage);
      const restoredSelection = takePendingSelection('list', response.items);
      if (restoredSelection) {
        setSelected(restoredSelection);
      } else {
        setSelected((current) => {
          if (!current) return current;
          if (current.source !== 'list') return current;
          const refreshed = response.items.find((item) => item.id === current.item.id);
          return refreshed ? { source: 'list', item: refreshed } : null;
        });
      }
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      setError(getParsedApiError(err));
      setItems([]);
      setTotal(0);
      setSelected((current) => (current?.source === 'list' ? null : current));
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  }, [appliedFilters, takePendingSelection]);

  const loadSignals = useCallback(async () => {
    await loadSignalsForPage(page);
  }, [loadSignalsForPage, page]);

  const loadOutcomeStats = useCallback(async () => {
    const requestId = statsRequestIdRef.current + 1;
    statsRequestIdRef.current = requestId;
    setStatsLoading(true);
    try {
      const response = await decisionSignalsApi.getOutcomeStats();
      if (statsRequestIdRef.current !== requestId) return;
      setOutcomeStats(response);
      setStatsError(null);
    } catch (err) {
      if (statsRequestIdRef.current !== requestId) return;
      setOutcomeStats(null);
      setStatsError(getParsedApiError(err));
    } finally {
      if (statsRequestIdRef.current === requestId) {
        setStatsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadSignals();
    return () => {
      requestIdRef.current += 1;
    };
  }, [loadSignals]);

  useEffect(() => {
    void loadOutcomeStats();
    return () => {
      statsRequestIdRef.current += 1;
    };
  }, [loadOutcomeStats]);

  useEffect(() => () => {
    latestRequestIdRef.current += 1;
  }, []);

  useEffect(() => () => {
    timelineRequestIdRef.current += 1;
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      detailRequestIdRef.current += 1;
      reassessRequestIdRef.current += 1;
      selectedSignalIdRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (pendingSelectedSignalIdRef.current === null) {
      updateDecisionSignalSearchParams({ signal: selected?.item.id ?? null });
    }
  }, [selected?.item.id]);

  useEffect(() => {
    selectedSignalIdRef.current = selected?.item.id ?? null;
    if (!selected) {
      detailRequestIdRef.current += 1;
      setSelectedOutcomes([]);
      setSelectedOutcomesError(null);
      setSelectedFeedback(null);
      setSelectedFeedbackError(null);
      setSelectedOutcomesLoading(false);
      setSelectedFeedbackLoading(false);
      return;
    }

    const requestId = detailRequestIdRef.current + 1;
    detailRequestIdRef.current = requestId;
    setSelectedOutcomesLoading(true);
    setSelectedFeedbackLoading(true);
    setSelectedOutcomesError(null);
    setSelectedFeedbackError(null);

    void decisionSignalsApi.getSignalOutcomes(selected.item.id)
      .then((response) => {
        if (detailRequestIdRef.current !== requestId) return;
        setSelectedOutcomes(response.items);
      })
      .catch((err) => {
        if (detailRequestIdRef.current !== requestId) return;
        setSelectedOutcomes([]);
        setSelectedOutcomesError(getParsedApiError(err));
      })
      .finally(() => {
        if (detailRequestIdRef.current === requestId) {
          setSelectedOutcomesLoading(false);
        }
      });

    void decisionSignalsApi.getFeedback(selected.item.id)
      .then((response) => {
        if (detailRequestIdRef.current !== requestId) return;
        setSelectedFeedback(response);
      })
      .catch((err) => {
        if (detailRequestIdRef.current !== requestId) return;
        setSelectedFeedback(null);
        setSelectedFeedbackError(getParsedApiError(err));
      })
      .finally(() => {
        if (detailRequestIdRef.current === requestId) {
          setSelectedFeedbackLoading(false);
        }
      });
  }, [selected]);

  const appliedSourceReportId = parseSourceReportId(appliedFilters.sourceReportId);
  const selectedSourceReportId = selected?.item.sourceReportId ?? undefined;
  const reassessSourceReportId = selected ? selectedSourceReportId : appliedSourceReportId;
  const reassessContextKey = [
    reassessSourceReportId ?? '',
    reassessProfile,
  ].join(':');

  useEffect(() => {
    reassessRequestIdRef.current += 1;
    setReassessResponse(null);
    setReassessError(null);
    setReassessLoading(false);
    setReassessPersisting(false);
    setReassessPersistConfirm(false);
    setReassessPersistBlocked(null);
  }, [reassessContextKey]);

  const handleReassess = useCallback(async () => {
    if (!reassessSourceReportId) return;
    const requestId = reassessRequestIdRef.current + 1;
    reassessRequestIdRef.current = requestId;
    setReassessLoading(true);
    setReassessError(null);
    setReassessPersistBlocked(null);
    try {
      const response = await decisionSignalsApi.reassess({
        sourceReportId: reassessSourceReportId,
        decisionProfile: reassessProfile,
        persist: false,
      });
      if (reassessRequestIdRef.current !== requestId) return;
      setReassessResponse(response);
    } catch (err) {
      if (reassessRequestIdRef.current !== requestId) return;
      setReassessResponse(null);
      setReassessError(getParsedApiError(err));
    } finally {
      if (reassessRequestIdRef.current === requestId) {
        setReassessLoading(false);
      }
    }
  }, [reassessProfile, reassessSourceReportId]);

  const handleApplyFilters = () => {
    setAppliedFilters(filters);
    setPage(1);
    syncListSearchParams(filters, 1);
  };

  const advancedFilterCount = [
    filters.marketPhase,
    filters.sourceType,
    filters.sourceReportId.trim(),
    filters.status !== DEFAULT_LIST_FILTERS.status ? filters.status : '',
  ].filter(Boolean).length;

  const resetLatestView = useCallback(() => {
    latestRequestIdRef.current += 1;
    setLatestItems([]);
    setLatestSearched(false);
    setLatestLoading(false);
    setLatestError(null);
    setSelected((current) => (current?.source === 'latest' ? null : current));
  }, []);

  const loadLatestForContext = useCallback(async (context: StockContext) => {
    const stockCode = context.code.trim();
    if (!stockCode) return;
    const requestId = latestRequestIdRef.current + 1;
    latestRequestIdRef.current = requestId;
    setLatestLoading(true);
    setLatestError(null);
    setLatestSearched(true);
    setLatestItems([]);
    setSelected((current) => (current?.source === 'latest' ? null : current));
    try {
      const response = await decisionSignalsApi.getLatest(stockCode, {
        market: context.market,
        limit: 5,
      });
      if (latestRequestIdRef.current !== requestId) return;
      setLatestItems(response.items);
      const restoredSelection = takePendingSelection('latest', response.items);
      if (restoredSelection) setSelected(restoredSelection);
      else setSelected((current) => refreshLatestSelection(current, response.items));
    } catch (err) {
      if (latestRequestIdRef.current !== requestId) return;
      setLatestItems([]);
      setSelected((current) => refreshLatestSelection(current, []));
      setLatestError(getParsedApiError(err));
    } finally {
      if (latestRequestIdRef.current === requestId) {
        setLatestLoading(false);
      }
    }
  }, [takePendingSelection]);

  const resetTimelineView = useCallback(() => {
    timelineRequestIdRef.current += 1;
    setTimelineItems([]);
    setTimelineSearched(false);
    setTimelineLoading(false);
    setTimelineError(null);
    setTimelineTruncated(false);
    setAppliedTimelineContext(null);
    setSelected((current) => (current?.source === 'timeline' ? null : current));
  }, []);

  const loadTimelineForContext = useCallback(async (
    context: StockContext,
    filtersSnapshot: TimelineFilters,
  ) => {
    const stockCode = context.code.trim();
    if (!stockCode) return;
    const requestId = timelineRequestIdRef.current + 1;
    timelineRequestIdRef.current = requestId;
    setTimelineLoading(true);
    setTimelineError(null);
    setTimelineSearched(true);
    setTimelineItems([]);
    setTimelineTruncated(false);
    setAppliedTimelineContext(null);
    setSelected((current) => (current?.source === 'timeline' ? null : current));
    syncTimelineSearchParams(filtersSnapshot);
    const nextAppliedContext: AppliedTimelineContext = {
      ...filtersSnapshot,
      stockCode,
    };
    try {
      const response = await decisionSignalsApi.list(toTimelineParams(filtersSnapshot, stockCode));
      if (timelineRequestIdRef.current !== requestId) return;
      setAppliedTimelineContext(nextAppliedContext);
      setTimelineItems(response.items);
      setTimelineTruncated(response.total > response.items.length);
      const restoredSelection = takePendingSelection('timeline', response.items);
      if (restoredSelection) setSelected(restoredSelection);
      else setSelected((current) => refreshTimelineSelection(current, response.items));
    } catch (err) {
      if (timelineRequestIdRef.current !== requestId) return;
      setTimelineItems([]);
      setTimelineTruncated(false);
      setSelected((current) => refreshTimelineSelection(current, []));
      setTimelineError(getParsedApiError(err));
    } finally {
      if (timelineRequestIdRef.current === requestId) {
        setTimelineLoading(false);
      }
    }
  }, [takePendingSelection]);

  const handlePersistReassess = useCallback(async () => {
    const preview = reassessResponse?.preview;
    const guardrail = preview && isRecord(preview.metadata.guardrail_result)
      ? preview.metadata.guardrail_result
      : null;
    if (!reassessSourceReportId || !preview || guardrail?.passed !== true) return;

    const requestId = reassessRequestIdRef.current + 1;
    reassessRequestIdRef.current = requestId;
    setReassessPersistConfirm(false);
    setReassessPersisting(true);
    setReassessError(null);
    setReassessPersistBlocked(null);
    try {
      const response = await decisionSignalsApi.reassess({
        sourceReportId: reassessSourceReportId,
        decisionProfile: reassessProfile,
        persist: true,
      });
      if (reassessRequestIdRef.current !== requestId) return;
      if (!response.item || !response.persistStatus) {
        throw new Error('DecisionSignal reassess persist response item and persist_status are required');
      }
      const authoritativeItem = response.item;
      const shouldOptimisticallyUpsert = response.persistStatus !== 'existing';
      setReassessResponse(response);
      setSelected((current) => (
        current
          ? { source: 'persisted', item: authoritativeItem }
          : null
      ));
      if (
        shouldOptimisticallyUpsert
        &&
        activeStockContext
        && authoritativeItem.status === 'active'
        && itemMatchesStockContext(authoritativeItem, activeStockContext)
      ) {
        setLatestItems((current) => upsertDecisionSignal(current, authoritativeItem, 5));
        void loadLatestForContext(activeStockContext);
      }
      if (
        shouldOptimisticallyUpsert
        &&
        appliedTimelineContext
        && itemMatchesAppliedTimeline(authoritativeItem, appliedTimelineContext)
      ) {
        setTimelineItems((current) => upsertDecisionSignal(current, authoritativeItem));
        void loadTimelineForContext(
          {
            code: appliedTimelineContext.stockCode,
            market: appliedTimelineContext.market || undefined,
          },
          appliedTimelineContext,
        );
      }
      void loadSignalsForPage(page);
    } catch (err) {
      if (reassessRequestIdRef.current !== requestId) return;
      const blocked = getDecisionSignalReassessBlockedError(err);
      if (blocked) {
        setReassessPersistBlocked(blocked);
        setReassessError(null);
      } else {
        setReassessError(getParsedApiError(err));
      }
    } finally {
      if (reassessRequestIdRef.current === requestId) {
        setReassessPersisting(false);
      }
    }
  }, [
    activeStockContext,
    appliedTimelineContext,
    loadLatestForContext,
    loadSignalsForPage,
    loadTimelineForContext,
    page,
    reassessProfile,
    reassessResponse,
    reassessSourceReportId,
  ]);

  const applyStockContext = useCallback((nextContext: StockContext) => {
    const nextTimeline = buildNextTimelineFilters(
      timelineFilters,
      activeStockContext,
      nextContext,
      timelineMarketSourceRef.current,
    );
    timelineMarketSourceRef.current = nextTimeline.marketSource;
    setActiveStockContext(nextContext);
    setActiveView('latest');
    setStockDraft(nextContext.displayCode ?? nextContext.code);
    setTimelineFilters(nextTimeline.filters);
    syncStockSearchParam(nextContext.code);
    void loadLatestForContext(nextContext);
    void loadTimelineForContext(nextContext, nextTimeline.filters);
  }, [activeStockContext, loadLatestForContext, loadTimelineForContext, timelineFilters]);

  const handleStockSubmit = useCallback((
    code: string,
    name?: string,
    _source?: 'manual' | 'autocomplete',
    metadata?: { market?: Market; displayCode?: string },
  ) => {
    const trimmedCode = code.trim();
    if (!trimmedCode) return;
    applyStockContext({
      code: trimmedCode,
      displayCode: metadata?.displayCode,
      name,
      market: normalizeDecisionSignalMarket(metadata?.market),
    });
  }, [applyStockContext]);

  const handleCandidateSelect = useCallback((candidate: StockCandidate) => {
    applyStockContext(candidate);
  }, [applyStockContext]);

  const handleStockFormSubmit = useCallback((code: string) => {
    if (draftMatchesStockContext(code, activeStockContext)) {
      applyStockContext(activeStockContext);
      return;
    }
    handleStockSubmit(code);
  }, [activeStockContext, applyStockContext, handleStockSubmit]);

  const handleClearStockContext = useCallback(() => {
    setStockDraft('');
    setActiveStockContext(null);
    timelineMarketSourceRef.current = null;
    setTimelineFilters((current) => ({ ...current, market: '' }));
    syncStockSearchParam(null);
    resetLatestView();
    resetTimelineView();
  }, [resetLatestView, resetTimelineView]);

  // Restore the current-stock scope from the URL once on mount so a shared or
  // refreshed link reopens the same stock context.
  const didRestoreStockFromUrlRef = useRef(false);
  useEffect(() => {
    if (didRestoreStockFromUrlRef.current) return;
    didRestoreStockFromUrlRef.current = true;
    const urlStock = getInitialStockCode();
    if (urlStock) {
      handleStockSubmit(urlStock);
    }
  }, [handleStockSubmit]);

  const handleTimelineSearch = useCallback(() => {
    if (!activeStockContext) return;
    void loadTimelineForContext(activeStockContext, timelineFilters);
  }, [activeStockContext, loadTimelineForContext, timelineFilters]);

  const handleStatusUpdate = async () => {
    if (!pendingStatus || statusUpdateInFlightRef.current) return;
    statusUpdateInFlightRef.current = true;
    setStatusUpdating(true);
    setStatusError(null);
    try {
      const updated = await decisionSignalsApi.updateStatus(pendingStatus.item.id, {
        status: pendingStatus.status,
      });
      if (!mountedRef.current) return;
      setPendingStatus(null);
      setStatusError(null);
      setLatestItems((current) => current.flatMap((item) => {
        if (item.id !== updated.id) return [item];
        return updated.status === 'active' ? [updated] : [];
      }));
      setTimelineItems((current) => current.flatMap((item) => {
        if (item.id !== updated.id) return [item];
        return appliedTimelineContext?.status === 'active' && updated.status !== 'active' ? [] : [updated];
      }));
      setSelected((current) => {
        if (!current || current.item.id !== updated.id) return current;
        if (current.source === 'latest') {
          return updated.status === 'active' ? { source: 'latest', item: updated } : null;
        }
        if (current.source === 'timeline') {
          return appliedTimelineContext?.status === 'active' && updated.status !== 'active'
            ? null
            : { source: 'timeline', item: updated };
        }
        if (current.source === 'persisted') {
          return { source: 'persisted', item: updated };
        }
        if (!parseSourceReportId(appliedFilters.sourceReportId) && appliedFilters.status && updated.status !== appliedFilters.status) return null;
        return { source: 'list', item: updated };
      });
      await loadSignalsForPage(page);
      await loadOutcomeStats();
    } catch (err) {
      if (mountedRef.current) {
        setStatusError(getParsedApiError(err));
      }
    } finally {
      if (mountedRef.current) setStatusUpdating(false);
      statusUpdateInFlightRef.current = false;
    }
  };

  const handleFeedbackSubmit = useCallback(async (feedbackValue: DecisionSignalFeedbackValue) => {
    if (!selected || feedbackSaving) return;
    const signalId = selected.item.id;
    setFeedbackSaving(true);
    try {
      const updated = await decisionSignalsApi.putFeedback(signalId, {
        feedbackValue,
        source: 'web',
      });
      if (!mountedRef.current || selectedSignalIdRef.current !== signalId) return;
      setSelectedFeedback(updated);
      setSelectedFeedbackError(null);
    } catch (err) {
      if (!mountedRef.current || selectedSignalIdRef.current !== signalId) return;
      setSelectedFeedbackError(getParsedApiError(err));
    } finally {
      if (mountedRef.current) setFeedbackSaving(false);
    }
  }, [feedbackSaving, selected]);

  const renderReassessPanel = () => {
    const preview = reassessResponse?.preview ?? null;
    const persistedItem = reassessResponse?.item ?? null;
    const persistStatus = reassessResponse?.persistStatus ?? null;
    const terminalExisting = persistStatus === 'existing' && persistedItem?.status !== 'active';
    const persistedAlertVariant = terminalExisting
      ? 'warning'
      : persistStatus === 'existing'
        ? 'info'
        : 'success';
    const persistedTitleKey: UiTextKey = terminalExisting
      ? 'decisionSignals.reassessPersistedTerminalTitle'
      : persistStatus === 'existing'
        ? 'decisionSignals.reassessPersistedExistingTitle'
        : persistStatus === 'refreshed'
          ? 'decisionSignals.reassessPersistedRefreshedTitle'
          : 'decisionSignals.reassessPersistedCreatedTitle';
    const persistedMessageKey: UiTextKey = terminalExisting
      ? 'decisionSignals.reassessPersistedTerminalExisting'
      : persistStatus === 'existing'
        ? 'decisionSignals.reassessPersistedExisting'
        : persistStatus === 'refreshed'
          ? 'decisionSignals.reassessPersistedRefreshed'
          : 'decisionSignals.reassessPersistedCreated';
    const metadata = preview?.metadata ?? {};
    const guardrail = isRecord(metadata.guardrail_result) ? metadata.guardrail_result : null;
    const rawAction = typeof guardrail?.raw_action === 'string' ? guardrail.raw_action : null;
    const finalAction = typeof guardrail?.final_action === 'string' ? guardrail.final_action : null;
    const passed = typeof guardrail?.passed === 'boolean' ? guardrail.passed : null;
    return (
      <div className="rounded-xl border border-border/60 bg-elevated/30 p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary" />
              <h3 className="text-sm font-semibold text-foreground">{t('decisionSignals.reassessTitle')}</h3>
            </div>
            <p className="mt-1 text-xs text-secondary-text">
              {reassessSourceReportId
                ? t('decisionSignals.reassessSource', { id: reassessSourceReportId })
                : t('decisionSignals.reassessUnsupported')}
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Select
              value={reassessProfile}
              onChange={(value) => setReassessProfile(value as DecisionProfile)}
              ariaLabel={t('decisionSignals.reassessProfile')}
              disabled={!reassessSourceReportId || reassessLoading || reassessPersisting}
              options={REASSESS_PROFILES.map((profile) => ({
                value: profile,
                label: t(`decisionSignals.profile.${profile}` as UiTextKey),
              }))}
            />
            <Button
              type="button"
              variant="secondary"
              size="xl"
              onClick={() => void handleReassess()}
              disabled={!reassessSourceReportId || reassessLoading || reassessPersisting}
              isLoading={reassessLoading}
              loadingText={t('decisionSignals.reassessPreview')}
            >
              <RefreshCw className="h-4 w-4" />
              {t('decisionSignals.reassessPreview')}
            </Button>
          </div>
        </div>

        {!reassessSourceReportId ? (
          <InlineAlert
            className="mt-3"
            variant="warning"
            title={t('decisionSignals.reassessUnsupportedTitle')}
            message={t('decisionSignals.reassessUnsupported')}
          />
        ) : null}
        {reassessError ? <ApiErrorAlert className="mt-3" error={reassessError} /> : null}
        {reassessPersistBlocked ? (
          <div className="mt-3 space-y-2">
            <InlineAlert
              variant="danger"
              title={t('decisionSignals.reassessPersistBlockedTitle')}
              message={reassessPersistBlocked.blockedReason}
            />
            {reassessPersistBlocked.warnings.length ? (
              <ul className="list-disc space-y-1 pl-5 text-sm text-secondary-text">
                {reassessPersistBlocked.warnings.map((warning, index) => (
                  <li key={`${warning.code}-${index}`}>{warning.message || warning.code}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
        {persistedItem ? (
          <InlineAlert
            className="mt-3"
            variant={persistedAlertVariant}
            title={t(persistedTitleKey)}
            message={t(
              persistedMessageKey,
              {
                id: persistedItem.id,
                status: t(STATUS_LABEL_KEYS[persistedItem.status]),
              },
            )}
          />
        ) : null}
        {preview ? (
          <div className="mt-4 space-y-3">
            {reassessResponse?.blockedReason ? (
              <InlineAlert
                variant="warning"
                title={t('decisionSignals.reassessBlockedTitle')}
                message={reassessResponse.blockedReason}
              />
            ) : null}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-lg border border-border/50 bg-background/40 p-3">
                <p className="text-xs text-secondary-text">{t('decisionSignals.action')}</p>
                <p className="mt-1 text-sm font-semibold text-foreground">{actionLabels[preview.action]}</p>
              </div>
              <div className="rounded-lg border border-border/50 bg-background/40 p-3">
                <p className="text-xs text-secondary-text">{t('decisionSignals.score')}</p>
                <p className="mt-1 text-sm font-semibold text-foreground">{preview.score ?? '-'}</p>
              </div>
              <div className="rounded-lg border border-border/50 bg-background/40 p-3">
                <p className="text-xs text-secondary-text">{t('decisionSignals.confidence')}</p>
                <p className="mt-1 text-sm font-semibold text-foreground">{preview.confidence ?? '-'}</p>
              </div>
              <div className="rounded-lg border border-border/50 bg-background/40 p-3">
                <p className="text-xs text-secondary-text">{t('decisionSignals.horizon')}</p>
                <p className="mt-1 text-sm font-semibold text-foreground">{preview.horizon ?? '-'}</p>
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-lg border border-border/50 bg-background/40 p-3">
                <p className="text-xs text-secondary-text">{t('decisionSignals.entryRange')}</p>
                <p className="mt-1 text-sm text-foreground">
                  {preview.entryLow || preview.entryHigh
                    ? `${preview.entryLow ?? '-'} ~ ${preview.entryHigh ?? '-'}`
                    : '-'}
                </p>
              </div>
              <div className="rounded-lg border border-border/50 bg-background/40 p-3">
                <p className="text-xs text-secondary-text">{t('decisionSignals.stopLoss')}</p>
                <p className="mt-1 text-sm text-foreground">{preview.stopLoss ?? '-'}</p>
              </div>
              <div className="rounded-lg border border-border/50 bg-background/40 p-3">
                <p className="text-xs text-secondary-text">{t('decisionSignals.targetPrice')}</p>
                <p className="mt-1 text-sm text-foreground">{preview.targetPrice ?? '-'}</p>
              </div>
              <div className="rounded-lg border border-border/50 bg-background/40 p-3">
                <p className="text-xs text-secondary-text">{t('decisionSignals.reassessRawFinal')}</p>
                <p className="mt-1 text-sm text-foreground">{rawAction ?? '-'} {'->'} {finalAction ?? '-'}</p>
              </div>
            </div>
            <div className="space-y-2 text-sm text-secondary-text">
              {passed === false ? (
                <p className="font-medium text-warning">{t('decisionSignals.reassessBlockedNote')}</p>
              ) : null}
              {preview.invalidation ? <p><span className="text-foreground">{t('decisionSignals.invalidation')}:</span> {preview.invalidation}</p> : null}
              {preview.reason ? <p><span className="text-foreground">{t('decisionSignals.reason')}:</span> {preview.reason}</p> : null}
              {preview.riskSummary ? <p><span className="text-foreground">{t('decisionSignals.riskSummary')}:</span> {preview.riskSummary}</p> : null}
              {preview.watchConditions ? <p><span className="text-foreground">{t('decisionSignals.watchConditions')}:</span> {preview.watchConditions}</p> : null}
            </div>
            {reassessResponse?.warnings.length ? (
              <div className="rounded-lg border border-warning/30 bg-warning/10 p-3">
                <p className="text-xs font-semibold text-warning">{t('decisionSignals.reassessWarnings')}</p>
                <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-secondary-text">
                  {reassessResponse.warnings.map((warning, index) => (
                    <li key={`${warning.code}-${index}`}>{warning.message || warning.code}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {passed === true ? (
              <div className="flex justify-end">
                <Button
                  type="button"
                  variant="primary"
                  size="lg"
                  onClick={() => setReassessPersistConfirm(true)}
                  disabled={reassessLoading || reassessPersisting}
                  isLoading={reassessPersisting}
                  loadingText={t('decisionSignals.reassessPersisting')}
                >
                  <ShieldCheck className="h-4 w-4" />
                  {t('decisionSignals.reassessPersist')}
                </Button>
              </div>
            ) : null}
          </div>
        ) : null}
        {persistedItem && reassessResponse?.warnings.length ? (
          <div className="mt-3 rounded-lg border border-warning/30 bg-warning/10 p-3">
            <p className="text-xs font-semibold text-warning">{t('decisionSignals.reassessWarnings')}</p>
            <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-secondary-text">
              {reassessResponse.warnings.map((warning, index) => (
                <li key={`${warning.code}-${index}`}>{warning.message || warning.code}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    );
  };

  const activeStockLabel = activeStockContext
    ? [
      activeStockContext.displayCode ?? activeStockContext.code,
      activeStockContext.name,
      activeStockContext.market,
    ].filter(Boolean).join(' / ')
    : null;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <AppPage>
      <div className="space-y-5">
        <PageHeader
          eyebrow={t('decisionSignals.activeOnly')}
          title={t('decisionSignals.title')}
          description={t('decisionSignals.description')}
          actions={(
            <>
              <Button
                type="button"
                variant="secondary"
                size="md"
                onClick={() => setStockContextModalOpen(true)}
              >
                <Search className="h-4 w-4" />
                {activeStockLabel
                  ? t('decisionSignals.stockContextCurrent', { stock: activeStockLabel })
                  : t('decisionSignals.stockContextTitle')}
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="md"
                onClick={() => {
                  void loadSignals();
                  void loadOutcomeStats();
                }}
                disabled={loading}
                isLoading={loading}
                loadingText={t('decisionSignals.refresh')}
              >
                <RefreshCw className="h-4 w-4" />
                {t('decisionSignals.refresh')}
              </Button>
            </>
          )}
        />

        <Modal
          isOpen={stockContextModalOpen}
          onClose={() => setStockContextModalOpen(false)}
          title={t('decisionSignals.stockContextTitle')}
          footer={(
            <>
              <Button
                type="submit"
                form="decision-stock-context-form"
                variant="primary"
                size="md"
                disabled={!stockDraft.trim()}
              >
                <Search className="h-4 w-4" aria-hidden="true" />
                {t('decisionSignals.stockContextApply')}
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="md"
                onClick={handleClearStockContext}
                disabled={!activeStockContext && !stockDraft}
              >
                {t('decisionSignals.stockContextClear')}
              </Button>
            </>
          )}
        >
          <p className="mb-3 text-sm text-muted-text">{t('decisionSignals.stockContextDescription')}</p>
          <form
            id="decision-stock-context-form"
            onSubmit={(event) => {
              event.preventDefault();
              handleStockFormSubmit(stockDraft);
              setStockContextModalOpen(false);
            }}
          >
            <div className="min-w-0 flex-1">
              <StockAutocomplete
                value={stockDraft}
                onChange={setStockDraft}
                onSubmit={handleStockSubmit}
                placeholder={t('decisionSignals.stockContextPlaceholder')}
                ariaLabel={t('decisionSignals.stockContextInput')}
              />
            </div>
          </form>

          {activeStockLabel ? (
            <p className="mt-3 text-sm text-secondary-text">
              {t('decisionSignals.stockContextCurrent', { stock: activeStockLabel })}
            </p>
          ) : (
            <p className="mt-3 text-sm text-secondary-text">{t('decisionSignals.stockContextEmpty')}</p>
          )}

          {historyCandidatesLoaded && stockCandidates.length > 0 ? (
            <div className="mt-4">
              <p className="text-xs font-medium text-muted-text">
                {stockCandidateMode === 'history'
                  ? t('decisionSignals.stockContextRecent')
                  : t('decisionSignals.stockContextPopular')}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {stockCandidates.map((candidate) => (
                  <Button
                    key={`${candidate.source}:${getCandidateKey(candidate)}`}
                    type="button"
                    variant="outline"
                    size="xl"
                    className="h-auto min-h-11 whitespace-normal rounded-lg bg-elevated/40 py-1.5 text-sm hover:border-primary/60 hover:text-primary"
                    onClick={() => {
                      handleCandidateSelect(candidate);
                      setStockContextModalOpen(false);
                    }}
                  >
                    <span className="font-mono">{candidate.displayCode ?? candidate.code}</span>
                    {candidate.name ? <span className="ml-1 text-secondary-text">{candidate.name}</span> : null}
                    {candidate.market ? <span className="ml-1 text-muted-text">/ {candidate.market}</span> : null}
                  </Button>
                ))}
              </div>
            </div>
          ) : historyCandidatesLoaded ? (
            <p className="mt-4 text-sm text-secondary-text">{t('decisionSignals.stockContextNoCandidates')}</p>
          ) : null}
        </Modal>

        <SegmentedControl
          value={activeView}
          options={[
            { value: 'signals', label: t('decisionSignals.scopeAllSignals') },
            { value: 'latest', label: t('decisionSignals.stockContextTitle') },
            { value: 'timeline', label: t('decisionSignals.timelineTitle') },
            { value: 'stats', label: t('decisionSignals.statsTitle') },
          ]}
          onChange={setActiveView}
          ariaLabel={t('decisionSignals.title')}
          getPanelId={(view) => `decision-signals-${view}-panel`}
        />

        <div
          className="space-y-5"
          hidden={activeView !== 'signals'}
        >
          <Card padding="sm" variant="bordered" className="bg-card/60">
          <ResponsiveFilterPanel
            filterLabel={t('decisionSignals.filter')}
            drawerTitle={t('decisionSignals.filter')}
            applyLabel={t('decisionSignals.filter')}
            activeCount={advancedFilterCount}
            onApply={handleApplyFilters}
            basicClassName="md:grid-cols-3 [&>*]:min-w-0 [&>*]:!w-full [&_[role=combobox]]:min-h-9 [&_input]:h-9"
            advancedClassName="lg:grid-cols-4 [&>*]:min-w-0 [&>*]:!w-full [&_[role=combobox]]:min-h-9 [&_input]:h-9"
            drawerAdvancedClassName="[&>*]:min-w-0 [&>*]:!w-full"
            basic={(
              <>
                <Select
                  label={t('decisionSignals.market')}
                  value={filters.market}
                  onChange={(value) => setFilters((current) => ({ ...current, market: value as ListFilters['market'] }))}
                  options={[
                    { value: '', label: t('decisionSignals.allMarkets') },
                    ...MARKET_OPTIONS.map((market) => ({ value: market, label: getDecisionSignalMarketLabel(market, t) })),
                  ]}
                />
                <Input
                  label={t('decisionSignals.stockCode')}
                  className="!h-9 !min-h-9 rounded-sm"
                  value={filters.stockCode}
                  onChange={(event) => setFilters((current) => ({ ...current, stockCode: event.target.value }))}
                  placeholder={t('decisionSignals.stockCode')}
                  aria-label={t('decisionSignals.stockCode')}
                />
                <Select
                  label={t('decisionSignals.action')}
                  value={filters.action}
                  onChange={(value) => setFilters((current) => ({ ...current, action: value as ListFilters['action'] }))}
                  options={[
                    { value: '', label: t('decisionSignals.allActions') },
                    ...ACTION_OPTIONS.map((action) => ({ value: action, label: actionLabels[action] })),
                  ]}
                />
              </>
            )}
            advanced={(
              <>
                <Select
                  label={t('decisionSignals.marketPhase')}
                  value={filters.marketPhase}
                  onChange={(value) => setFilters((current) => ({ ...current, marketPhase: value as ListFilters['marketPhase'] }))}
                  options={[
                    { value: '', label: t('decisionSignals.allPhases') },
                    ...PHASE_OPTIONS.map((phase) => ({ value: phase, label: getDecisionSignalMarketPhaseLabel(phase, t) })),
                  ]}
                />
                <Select
                  label={t('decisionSignals.source')}
                  value={filters.sourceType}
                  onChange={(value) => setFilters((current) => ({ ...current, sourceType: value as ListFilters['sourceType'] }))}
                  options={[
                    { value: '', label: t('decisionSignals.allSources') },
                    ...SOURCE_OPTIONS.map((source) => ({ value: source, label: getDecisionSignalSourceTypeLabel(source, t) })),
                  ]}
                />
                <Input
                  label={t('decisionSignals.sourceReportId')}
                  className="!h-9 !min-h-9 rounded-sm"
                  value={filters.sourceReportId}
                  onChange={(event) => setFilters((current) => ({ ...current, sourceReportId: event.target.value }))}
                  placeholder={t('decisionSignals.sourceReportId')}
                  aria-label={t('decisionSignals.sourceReportId')}
                  inputMode="numeric"
                  min={1}
                  step={1}
                  type="number"
                />
                <Select
                  label={t('decisionSignals.status')}
                  value={filters.status}
                  onChange={(value) => setFilters((current) => ({ ...current, status: value as ListFilters['status'] }))}
                  options={[
                    { value: '', label: t('decisionSignals.allStatuses') },
                    ...STATUS_OPTIONS.map((status) => ({ value: status, label: t(STATUS_LABEL_KEYS[status]) })),
                  ]}
                />
              </>
            )}
            />
          </Card>

          {!selected && appliedSourceReportId ? (
            <Card padding="md">
              {renderReassessPanel()}
            </Card>
          ) : null}
        </div>

        <section
          id="decision-signals-stats-panel"
          role="tabpanel"
          aria-label={t('decisionSignals.statsTitle')}
          hidden={activeView !== 'stats'}
        >
          <Card
            title={t('decisionSignals.statsTitle')}
            subtitle={t('decisionSignals.statsDescription')}
            padding="md"
            headerRight={<Badge variant="default" size="sm">{t('decisionSignals.scopeGlobal')}</Badge>}
          >
            <p className="mb-3 text-sm text-secondary-text">{t('decisionSignals.statsGlobalScope')}</p>
            {statsError ? (
              <ApiErrorAlert
                error={{ ...statsError, title: t('decisionSignals.statsErrorTitle') }}
                actionLabel={t('common.retry')}
                onAction={() => void loadOutcomeStats()}
              />
            ) : statsLoading ? (
              <p className="text-sm text-secondary-text">{t('common.loading')}...</p>
            ) : outcomeStats && outcomeStats.total > 0 ? (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                <div className="rounded-xl border border-border/60 bg-elevated/40 px-3 py-3">
                  <p className="text-xs text-secondary-text">{t('decisionSignals.statsTotal')}</p>
                  <p className="mt-1 text-2xl font-semibold text-foreground">{outcomeStats.total}</p>
                </div>
                <div className="rounded-xl border border-border/60 bg-elevated/40 px-3 py-3">
                  <p className="text-xs text-secondary-text">{t('decisionSignals.statsHitRate')}</p>
                  <p className="mt-1 text-2xl font-semibold text-success">{formatStatPercent(outcomeStats.hitRatePct)}</p>
                </div>
                <div className="rounded-xl border border-border/60 bg-elevated/40 px-3 py-3">
                  <p className="text-xs text-secondary-text">{t('decisionSignals.outcome.hit')}</p>
                  <p className="mt-1 text-2xl font-semibold text-success">{outcomeStats.hit}</p>
                </div>
                <div className="rounded-xl border border-border/60 bg-elevated/40 px-3 py-3">
                  <p className="text-xs text-secondary-text">{t('decisionSignals.outcome.miss')}</p>
                  <p className="mt-1 text-2xl font-semibold text-danger">{outcomeStats.miss}</p>
                </div>
                <div className="rounded-xl border border-border/60 bg-elevated/40 px-3 py-3">
                  <p className="text-xs text-secondary-text">{t('decisionSignals.outcome.unable')}</p>
                  <p className="mt-1 text-2xl font-semibold text-warning">{outcomeStats.unable}</p>
                </div>
              </div>
            ) : (
              <StatePanel status="empty"
                className="border-none bg-transparent py-6 shadow-none"
                title={t('decisionSignals.noReviewedStatsTitle')}
                description={t('decisionSignals.noReviewedStatsDescription')}
                icon={<BarChart3 className="h-6 w-6" />}
              />
            )}
          </Card>
        </section>

        <section
          id="decision-signals-latest-panel"
          role="tabpanel"
          aria-label={t('decisionSignals.stockContextTitle')}
          hidden={activeView !== 'latest'}
        >
          <Card
            title={t('decisionSignals.latestTitle')}
            subtitle={t('decisionSignals.latestDescription')}
            padding="md"
            headerRight={activeStockContext ? (
              <Badge variant="info" size="sm">{t('decisionSignals.scopeCurrentStock', { stock: activeStockLabel ?? activeStockContext.code })}</Badge>
            ) : undefined}
          >
            {!activeStockContext ? (
              <StatePanel status="empty"
                className="border-none bg-transparent py-6 shadow-none"
                title={t('decisionSignals.stockContextGuideTitle')}
                description={t('decisionSignals.stockContextGuideDescription')}
                icon={<Activity className="h-6 w-6" />}
              />
            ) : null}
            {latestError ? <ApiErrorAlert className="mt-3" error={latestError} /> : null}
            {latestSearched && !latestLoading && !latestError && latestItems.length === 0 ? (
              <StatePanel status="empty"
                className="mt-4 border-none bg-transparent py-6 shadow-none"
                title={t('decisionSignals.noLatestTitle')}
                description={t('decisionSignals.noLatestDescription')}
                icon={<Activity className="h-6 w-6" />}
              />
            ) : null}
            {latestLoading ? <p className="mt-3 text-sm text-secondary-text">{t('common.loading')}...</p> : null}
            {latestItems.length > 0 ? (
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                {latestItems.map((item) => (
                  <DecisionSignalCard
                    key={item.id}
                    item={item}
                    onSelect={(selectedItem) => handleSelectSignal('latest', selectedItem)}
                    selected={selected?.item.id === item.id}
                  />
                ))}
              </div>
            ) : null}
          </Card>
        </section>

        <section
          id="decision-signals-timeline-panel"
          role="tabpanel"
          aria-label={t('decisionSignals.timelineTitle')}
          hidden={activeView !== 'timeline'}
        >
          <Card
            title={t('decisionSignals.timelineTitle')}
            subtitle={t('decisionSignals.timelineDescription')}
            padding="md"
            headerRight={activeStockContext ? (
              <Badge variant="info" size="sm">{t('decisionSignals.scopeCurrentStock', { stock: activeStockLabel ?? activeStockContext.code })}</Badge>
            ) : undefined}
          >
            <ResponsiveFilterPanel
            filterLabel={t('decisionSignals.timelineSearch')}
            drawerTitle={t('decisionSignals.timelineTitle')}
            applyLabel={t('decisionSignals.timelineSearch')}
            onApply={handleTimelineSearch}
            applyDisabled={timelineLoading || !activeStockContext?.code}
            isApplying={timelineLoading}
            loadingLabel={t('decisionSignals.timelineSearch')}
            activeCount={Number(timelineFilters.status !== 'all') + Number(Boolean(timelineFilters.decisionProfile))}
            basicClassName="sm:grid-cols-2 [&>*]:min-w-0 [&>*]:!w-full [&>*>div]:w-full"
            advancedClassName="lg:grid-cols-2 [&>*]:min-w-0 [&>*]:!w-full [&>*>div]:w-full"
            drawerAdvancedClassName="content-start [&>*]:min-w-0 [&>*]:!w-full [&>*>div]:w-full"
            basic={(
              <>
                <Select
                  label={t('decisionSignals.timelineMarket')}
                  value={timelineFilters.market}
                  onChange={(value) => {
                    const market = value as TimelineFilters['market'];
                    timelineMarketSourceRef.current = market ? 'user' : null;
                    setTimelineFilters((current) => ({ ...current, market }));
                  }}
                  options={[
                    { value: '', label: t('decisionSignals.allMarkets') },
                    ...MARKET_OPTIONS.map((market) => ({ value: market, label: getDecisionSignalMarketLabel(market, t) })),
                  ]}
                />
                <Select
                  label={t('decisionSignals.timelineRange')}
                  value={timelineFilters.range}
                  onChange={(value) => setTimelineFilters((current) => ({ ...current, range: value as TimelineRange }))}
                  options={[
                    { value: '30d', label: t('decisionSignals.timelineRange.30d') },
                    { value: '90d', label: t('decisionSignals.timelineRange.90d') },
                    { value: '180d', label: t('decisionSignals.timelineRange.180d') },
                  ]}
                />
              </>
            )}
            advanced={(
              <>
                <Select
                  label={t('decisionSignals.timelineStatus')}
                  value={timelineFilters.status}
                  onChange={(value) => setTimelineFilters((current) => ({ ...current, status: value as TimelineStatusFilter }))}
                  options={[
                    { value: 'all', label: t('decisionSignals.timelineStatus.all') },
                    { value: 'active', label: t('decisionSignals.timelineStatus.active') },
                  ]}
                />
                <Select
                  label={t('decisionSignals.timelineProfile')}
                  value={timelineFilters.decisionProfile}
                  onChange={(value) => setTimelineFilters((current) => ({
                    ...current,
                    decisionProfile: value as TimelineFilters['decisionProfile'],
                  }))}
                  options={[
                    { value: '', label: t('decisionSignals.allProfiles') },
                    ...REASSESS_PROFILES.map((profile) => ({
                      value: profile,
                      label: t(`decisionSignals.profile.${profile}` as UiTextKey),
                    })),
                    { value: 'unknown', label: t('decisionSignals.profile.unknown') },
                  ]}
                />
              </>
            )}
            />
            <div className="mt-4">
              {!timelineSearched ? (
                <StatePanel status="empty"
                  className="border-none bg-transparent py-6 shadow-none"
                  title={activeStockContext ? t('decisionSignals.timelineGuideTitle') : t('decisionSignals.stockContextGuideTitle')}
                  description={activeStockContext ? t('decisionSignals.timelineGuideDescription') : t('decisionSignals.stockContextGuideDescription')}
                  icon={<Activity className="h-6 w-6" />}
                />
              ) : (
                <DecisionSignalTimeline
                  items={timelineItems}
                  selectedId={selected?.item.id ?? null}
                  loading={timelineLoading}
                  error={timelineError?.message ?? null}
                  truncated={timelineTruncated}
                  onSelect={(selectedItem) => handleSelectSignal('timeline', selectedItem)}
                />
              )}
            </div>
          </Card>
        </section>

        <section
          id="decision-signals-signals-panel"
          role="tabpanel"
          aria-label={t('decisionSignals.scopeAllSignals')}
          className="space-y-5"
          hidden={activeView !== 'signals'}
        >
          {error ? (
          <ApiErrorAlert
            error={{ ...error, title: t('decisionSignals.errorTitle') }}
            actionLabel={t('common.retry')}
            onAction={() => void loadSignals()}
          />
        ) : null}

        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <p className="text-sm text-secondary-text">{t('decisionSignals.total', { total })}</p>
            <Badge variant="default" size="sm">
              {appliedSourceReportId
                ? t('decisionSignals.scopeFromReport', { reportId: appliedSourceReportId })
                : t('decisionSignals.scopeAllSignals')}
            </Badge>
          </div>
          {loading ? <span className="text-xs text-secondary-text">{t('common.loading')}...</span> : null}
        </div>

        {!loading && items.length === 0 ? (
          <StatePanel status="empty"
            title={t('decisionSignals.emptyTitle')}
            description={t('decisionSignals.emptyDescription')}
            icon={<Activity className="h-7 w-7" />}
          />
        ) : (
          <div className="grid gap-3 xl:grid-cols-2">
            {items.map((item) => (
              <DecisionSignalCard
                key={item.id}
                item={item}
                onSelect={(selectedItem) => handleSelectSignal('list', selectedItem)}
                selected={selected?.item.id === item.id}
              />
            ))}
          </div>
        )}

          <Pagination
            currentPage={page}
            totalPages={totalPages}
            onPageChange={(nextPage) => {
              setPage(nextPage);
              syncListSearchParams(appliedFilters, nextPage);
            }}
          />
        </section>
      </div>

      <Modal
        isOpen={Boolean(selected)}
        onClose={handleCloseSignal}
        title={t('decisionSignals.detailTitle')}
        className="max-w-3xl"
        bodyClassName="p-6"
      >
        {selected ? (
          <div className="space-y-4">
            {statusError ? (
              <ApiErrorAlert error={statusError} onDismiss={() => setStatusError(null)} />
            ) : null}
            {renderReassessPanel()}
            <DecisionSignalDetails
              item={selected.item}
              outcomes={selectedOutcomes}
              outcomesLoading={selectedOutcomesLoading}
              outcomesError={selectedOutcomesError?.message ?? null}
              feedback={selectedFeedback}
              feedbackLoading={selectedFeedbackLoading}
              feedbackSaving={feedbackSaving}
              feedbackError={selectedFeedbackError?.message ?? null}
              onFeedbackSubmit={handleFeedbackSubmit}
              actions={STATUS_ACTIONS.map((status) => (
                <Button
                  key={status}
                  type="button"
                  variant="secondary"
                  size="xl"
                  className="px-3 text-xs"
                  onClick={() => {
                    setStatusError(null);
                    setPendingStatus({
                      item: selected.item,
                      status,
                      message: t(STATUS_ACTION_CONFIRM_KEYS[status]),
                    });
                  }}
                  disabled={statusUpdating || selected.item.status === status}
                >
                  {t(STATUS_ACTION_LABEL_KEYS[status])}
                </Button>
              ))}
            />
          </div>
        ) : null}
      </Modal>

      <ConfirmDialog
        isOpen={reassessPersistConfirm}
        title={t('decisionSignals.reassessPersistConfirmTitle')}
        message={t('decisionSignals.reassessPersistConfirmMessage')}
        confirmText={t('decisionSignals.reassessPersist')}
        confirmDisabled={reassessPersisting}
        cancelDisabled={reassessPersisting}
        onConfirm={() => void handlePersistReassess()}
        onCancel={() => setReassessPersistConfirm(false)}
      />

      <ConfirmDialog
        isOpen={Boolean(pendingStatus)}
        title={t('decisionSignals.confirmStatusTitle')}
        message={pendingStatus?.message ?? ''}
        confirmText={t('common.confirm')}
        confirmDisabled={statusUpdating}
        cancelDisabled={statusUpdating}
        error={statusError?.message}
        onConfirm={() => void handleStatusUpdate()}
        onCancel={() => {
          setPendingStatus(null);
          setStatusError(null);
        }}
      />
    </AppPage>
  );
};

export default DecisionSignalsPage;
