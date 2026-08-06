import type React from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  PlusCircle,
  RefreshCw,
  Search,
} from 'lucide-react';
import { useLocation, useNavigate, useNavigationType } from 'react-router-dom';
import {
  decisionSignalsApi,
  getDecisionSignalReassessBlockedError,
} from '../api/decisionSignals';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { historyApi } from '../api/history';
import {
  AppPage,
  Button,
  ConfirmDialog,
  InlineAlert,
  PageHeader,
  SelectionChip,
  TabPanel,
  Tabs,
  ToastViewport,
} from '../components/common';
import { useRouteFocusTarget } from '../components/routing';
import { DecisionSignalCreateDrawer } from '../components/decision-signals/DecisionSignalCreateDrawer';
import DecisionSignalDetailDrawer from '../components/decision-signals/DecisionSignalDetailDrawer';
import DecisionSignalFeedListSection from '../components/decision-signals/DecisionSignalFeedListSection';
import DecisionSignalLatestSection from '../components/decision-signals/DecisionSignalLatestSection';
import DecisionSignalReassessPanel from '../components/decision-signals/DecisionSignalReassessPanel';
import DecisionSignalReviewSection from '../components/decision-signals/DecisionSignalReviewSection';
import DecisionSignalStockContextModal from '../components/decision-signals/DecisionSignalStockContextModal';
import DecisionSignalTimelineSection from '../components/decision-signals/DecisionSignalTimelineSection';
import {
  EMPTY_MANUAL_SIGNAL_DRAFT,
  type ManualSignalDraft,
} from '../components/decision-signals/manualSignalDraft';
import {
  buildNextTimelineFilters,
  draftMatchesStockContext,
  DEFAULT_LIST_FILTERS,
  getCandidateKey,
  getDecisionSignalLocation,
  getInitialSelectedSignalId,
  getListSearchValues,
  getStockSearchValues,
  getTimelineSearchValues,
  isRecord,
  itemMatchesAppliedTimeline,
  itemMatchesStockContext,
  mergeWatchlistSignalResponses,
  normalizeDecisionSignalMarket,
  PAGE_SIZE,
  parseSourceReportId,
  refreshLatestSelection,
  refreshTimelineSelection,
  runWithRequestSlot,
  SIGNAL_CENTER_TABS_ID,
  SIGNAL_FEED_TABS_ID,
  STOCK_CANDIDATE_LIMIT,
  toHistoryCandidate,
  toListParams,
  toPopularCandidates,
  toTimelineParams,
  type AppliedTimelineContext,
  type DecisionSignalSearchValues,
  type ListFilters,
  type PendingStatusChange,
  type RequestSlotQueue,
  type SelectedSignal,
  type StockCandidate,
  type StockContext,
  type TimelineFilterUpdate,
  type TimelineFilters,
  type TimelineMarketSource,
  upsertDecisionSignal,
  WATCHLIST_SIGNAL_LOOKUP_CONCURRENCY,
} from '../components/decision-signals/decisionSignalsPageModel';
import type { Market } from '../types/stockIndex';
import { useDecisionSignalListState } from '../components/decision-signals/useDecisionSignalListState';
import { useDecisionSignalReassessState } from '../components/decision-signals/useDecisionSignalReassessState';
import { useDecisionSignalTimelineState } from '../components/decision-signals/useDecisionSignalTimelineState';
import { AlertsWorkspace, type AlertsView } from '../components/alerts/AlertsWorkspace';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import {
  buildDecisionSignalFeedbackQueryKey,
  buildDecisionSignalListQueryKey,
  useDecisionSignalDetailQueries,
  useDecisionSignalListQuery,
  useDecisionSignalOutcomeStatsQuery,
} from '../hooks';
import { useStockIndex } from '../hooks/useStockIndex';
import { useWatchlist } from '../hooks/useWatchlist';
import type {
  DecisionSignalFeedbackValue,
  DecisionSignalItem,
  DecisionSignalListResponse,
  DecisionSignalMutationResponse,
  DecisionSignalOutcomeStatsResponse,
} from '../types/decisionSignals';
import { parseDeepLink, type DecisionSignalsView } from '../utils/deepLink';
import { areStockCodesEquivalent } from '../utils/stockCode';
import {
  APP_ROUTE_PATHS,
  SIGNAL_CENTER_HISTORY_VALUES,
  SIGNAL_CENTER_ROUTE_QUERY_KEYS,
  SIGNAL_CENTER_SCOPE_VALUES,
  SIGNAL_CENTER_TAB_VALUES,
  SIGNAL_FEED_VIEW_VALUES,
  type SignalCenterScope,
  type SignalCenterTab,
} from '../routing/routes';
import {
  parseSignalCenterRouteState,
  setSignalCenterRouteState,
} from '../routing/signalCenterRouteState';

const DecisionSignalsPage: React.FC = () => {
  const navigate = useNavigate();
  const routeLocation = useLocation();
  const navigationType = useNavigationType();
  const { t } = useUiLanguage();
  const pageHeadingRef = useRef<HTMLHeadingElement>(null);
  useRouteFocusTarget({
    routeId: APP_ROUTE_PATHS.signals,
    headingRef: pageHeadingRef,
    ready: true,
  });
  const parsedSignalCenterRoute = useMemo(
    () => parseSignalCenterRouteState(routeLocation.search),
    [routeLocation.search],
  );
  const signalCenterState = parsedSignalCenterRoute.state;
  const signalCenterScope = signalCenterState.scope;
  const signalCenterTab = signalCenterState.tab;
  const signalCenterHistory = signalCenterState.history;
  const ruleStock = new URLSearchParams(routeLocation.search).get(
    SIGNAL_CENTER_ROUTE_QUERY_KEYS.stock,
  ) ?? undefined;
  const updateSignalCenterRoute = useCallback((
    nextState: typeof signalCenterState,
    replace = false,
  ) => {
    const nextParams = setSignalCenterRouteState(routeLocation.search, nextState);
    const search = nextParams.toString();
    navigate({
      pathname: routeLocation.pathname,
      search: search ? `?${search}` : '',
      hash: routeLocation.hash,
    }, { replace });
  }, [navigate, routeLocation.hash, routeLocation.pathname, routeLocation.search]);
  useEffect(() => {
    const current = new URLSearchParams(routeLocation.search).toString();
    const normalized = parsedSignalCenterRoute.normalizedParams.toString();
    if (current === normalized) return;
    navigate({
      pathname: routeLocation.pathname,
      search: normalized ? `?${normalized}` : '',
      hash: routeLocation.hash,
    }, { replace: true });
  }, [navigate, parsedSignalCenterRoute.normalizedParams, routeLocation.hash, routeLocation.pathname, routeLocation.search]);
  const setSignalCenterTab = useCallback((tab: SignalCenterTab) => {
    updateSignalCenterRoute({
      ...signalCenterState,
      tab,
      createRule: false,
    });
  }, [signalCenterState, updateSignalCenterRoute]);
  const setSignalCenterScope = useCallback((scope: SignalCenterScope) => {
    updateSignalCenterRoute({ ...signalCenterState, scope });
  }, [signalCenterState, updateSignalCenterRoute]);
  const handleAlertsViewChange = useCallback((view: AlertsView) => {
    if (view === 'rules') {
      setSignalCenterTab(SIGNAL_CENTER_TAB_VALUES.rules);
      return;
    }
    updateSignalCenterRoute({
      ...signalCenterState,
      tab: SIGNAL_CENTER_TAB_VALUES.history,
      history: view === 'notifications'
        ? SIGNAL_CENTER_HISTORY_VALUES.notifications
        : SIGNAL_CENTER_HISTORY_VALUES.triggers,
      createRule: false,
    });
  }, [setSignalCenterTab, signalCenterState, updateSignalCenterRoute]);
  const handleCreateRuleRequestHandled = useCallback(() => {
    if (!signalCenterState.createRule) return;
    updateSignalCenterRoute({ ...signalCenterState, createRule: false }, true);
  }, [signalCenterState, updateSignalCenterRoute]);
  const parsedDecisionSignalsLink = useMemo(
    () => parseDeepLink(
      `${routeLocation.pathname}${routeLocation.search}${routeLocation.hash}`,
      window.location.origin,
    ),
    [routeLocation.hash, routeLocation.pathname, routeLocation.search],
  );
  const decisionSignalsTarget = parsedDecisionSignalsLink.target?.page === 'decision-signals'
    ? parsedDecisionSignalsLink.target
    : null;
  const [activeView, setActiveViewState] = useState<DecisionSignalsView>(
    decisionSignalsTarget?.view ?? 'signals',
  );
  const activeViewRef = useRef(activeView);
  activeViewRef.current = activeView;
  const activeFeedView = activeView === SIGNAL_FEED_VIEW_VALUES.stats
    ? SIGNAL_FEED_VIEW_VALUES.signals
    : activeView;
  const scopeControlVisible = (
    signalCenterTab === SIGNAL_CENTER_TAB_VALUES.feed
    && activeFeedView === SIGNAL_FEED_VIEW_VALUES.signals
  ) || signalCenterTab === SIGNAL_CENTER_TAB_VALUES.rules;
  const updateDecisionSignalSearchParams = useCallback((
    values: DecisionSignalSearchValues,
    replace = true,
  ) => {
    const nextValues = { ...values };
    if (!Object.hasOwn(nextValues, 'view')) {
      const currentParams = new URLSearchParams(window.location.search);
      const nextStock = values.stock === null
        ? null
        : values.stock ?? currentParams.get('stock');
      const defaultView: DecisionSignalsView = nextStock ? 'latest' : 'signals';
      nextValues.view = activeViewRef.current === defaultView ? null : activeViewRef.current;
    }
    const nextLocation = getDecisionSignalLocation(nextValues);
    if (nextLocation) navigate(nextLocation, { replace });
  }, [navigate]);
  const syncListSearchParams = useCallback((filters: ListFilters, nextPage: number) => {
    updateDecisionSignalSearchParams(getListSearchValues(filters, nextPage));
  }, [updateDecisionSignalSearchParams]);
  const syncTimelineSearchParams = useCallback((filters: TimelineFilters) => {
    updateDecisionSignalSearchParams(getTimelineSearchValues(filters));
  }, [updateDecisionSignalSearchParams]);
  const syncStockContextSearchParams = useCallback((
    code: string | null,
    timelineSnapshot?: TimelineFilters,
  ) => {
    const defaultView: DecisionSignalsView = code ? 'latest' : 'signals';
    updateDecisionSignalSearchParams({
      ...getStockSearchValues(code),
      ...(timelineSnapshot ? getTimelineSearchValues(timelineSnapshot) : {}),
      view: code || activeViewRef.current === defaultView ? null : activeViewRef.current,
    }, false);
  }, [updateDecisionSignalSearchParams]);
  const setActiveView = useCallback((view: DecisionSignalsView) => {
    const defaultView = decisionSignalsTarget?.stockCode ? 'latest' : 'signals';
    activeViewRef.current = view;
    setActiveViewState(view);
    updateDecisionSignalSearchParams({ view: view === defaultView ? null : view }, false);
  }, [decisionSignalsTarget?.stockCode, updateDecisionSignalSearchParams]);
  const { index: stockIndex } = useStockIndex();
  const watchlistState = useWatchlist({
    enabled: signalCenterScope === SIGNAL_CENTER_SCOPE_VALUES.watchlist,
  });
  const {
    filters,
    appliedFilters,
    page,
    items,
    total,
    loading,
    error,
    dispatch: listDispatch,
    setFilters,
    applyFilters,
    setPage,
  } = useDecisionSignalListState();
  const queryClient = useQueryClient();
  const [statusError, setStatusError] = useState<ParsedApiError | null>(null);
  const [selected, setSelected] = useState<SelectedSignal | null>(null);
  const [pendingStatus, setPendingStatus] = useState<PendingStatusChange | null>(null);
  const [outcomeStats, setOutcomeStats] = useState<DecisionSignalOutcomeStatsResponse | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState<ParsedApiError | null>(null);
  const [feedbackWriteError, setFeedbackWriteError] = useState<ParsedApiError | null>(null);
  const [outcomeExplorerRefreshKey, setOutcomeExplorerRefreshKey] = useState(0);
  const [stockDraft, setStockDraft] = useState('');
  const [stockContextModalOpen, setStockContextModalOpen] = useState(false);
  const [createDrawerOpen, setCreateDrawerOpen] = useState(false);
  const [createDraft, setCreateDraft] = useState<ManualSignalDraft>(() => ({ ...EMPTY_MANUAL_SIGNAL_DRAFT }));
  const [activeStockContext, setActiveStockContext] = useState<StockContext | null>(null);
  const [historyCandidates, setHistoryCandidates] = useState<StockCandidate[]>([]);
  const [historyCandidatesLoaded, setHistoryCandidatesLoaded] = useState(false);
  const [latestItems, setLatestItems] = useState<DecisionSignalItem[]>([]);
  const [latestSearched, setLatestSearched] = useState(false);
  const [latestLoading, setLatestLoading] = useState(false);
  const [latestError, setLatestError] = useState<ParsedApiError | null>(null);
  const {
    filters: timelineFilters,
    appliedContext: appliedTimelineContext,
    items: timelineItems,
    searched: timelineSearched,
    loading: timelineLoading,
    error: timelineError,
    truncated: timelineTruncated,
    dispatch: timelineDispatch,
    setFilters: setTimelineFilters,
    replaceFilters: replaceTimelineFilters,
    reset: resetTimelineState,
    setItems: setTimelineItems,
  } = useDecisionSignalTimelineState();
  const [feedbackSaving, setFeedbackSaving] = useState(false);
  const {
    selectedOutcomes,
    selectedOutcomesLoading,
    selectedOutcomesError,
    selectedFeedback,
    selectedFeedbackLoading,
    selectedFeedbackError: selectedFeedbackLoadError,
  } = useDecisionSignalDetailQueries(selected?.item.id ?? null);
  const selectedFeedbackError = feedbackWriteError ?? selectedFeedbackLoadError;
  const {
    profile: reassessProfile,
    response: reassessResponse,
    loading: reassessLoading,
    persisting: reassessPersisting,
    persistConfirm: reassessPersistConfirm,
    persistBlocked: reassessPersistBlocked,
    error: reassessError,
    dispatch: reassessDispatch,
    setProfile: setReassessProfile,
    resetForContext: resetReassessForContext,
    requestPersistConfirm,
    cancelPersistConfirm,
  } = useDecisionSignalReassessState();
  const requestIdRef = useRef(0);
  const signalListQueueRef = useRef<RequestSlotQueue>({ active: 0, waiters: [] });
  const statsRequestIdRef = useRef(0);
  const latestRequestIdRef = useRef(0);
  const timelineRequestIdRef = useRef(0);
  const reassessRequestIdRef = useRef(0);
  const selectedSignalIdRef = useRef<number | null>(null);
  const pendingSelectedSignalIdRef = useRef<number | null>(getInitialSelectedSignalId());
  const routeSelectionSourcesRef = useRef<Array<{
    source: SelectedSignal['source'];
    items: DecisionSignalItem[];
  }>>([]);
  routeSelectionSourcesRef.current = [
    { source: 'list', items },
    { source: 'latest', items: latestItems },
    { source: 'timeline', items: timelineItems },
  ];
  const statusUpdateInFlightRef = useRef(false);
  const didObserveViewNavigationRef = useRef(false);
  useEffect(() => {
    if (!didObserveViewNavigationRef.current) {
      didObserveViewNavigationRef.current = true;
      return;
    }
    if (navigationType !== 'POP') return;
    const nextView = decisionSignalsTarget?.view ?? 'signals';
    activeViewRef.current = nextView;
    setActiveViewState(nextView);
  }, [decisionSignalsTarget?.view, navigationType, routeLocation.key]);
  const timelineMarketSourceRef = useRef<TimelineMarketSource>(null);
  const pendingStockNavigationRef = useRef<{
    context: StockContext | null;
    timeline?: TimelineFilterUpdate;
  } | null>(null);
  const mountedRef = useRef(true);

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

  useLayoutEffect(() => {
    const routeSignalId = getInitialSelectedSignalId(routeLocation.search);
    if (routeSignalId === null) {
      pendingSelectedSignalIdRef.current = null;
      if (selectedSignalIdRef.current !== null) setSelected(null);
      return;
    }
    if (selectedSignalIdRef.current === routeSignalId) {
      pendingSelectedSignalIdRef.current = null;
      return;
    }
    pendingSelectedSignalIdRef.current = routeSignalId;
    for (const source of routeSelectionSourcesRef.current) {
      const item = source.items.find((candidate) => candidate.id === routeSignalId);
      if (!item) continue;
      pendingSelectedSignalIdRef.current = null;
      setSelected({ source: source.source, item });
      return;
    }
    setSelected(null);
  }, [routeLocation.key, routeLocation.search]);

  const handleSelectSignal = useCallback((source: SelectedSignal['source'], item: DecisionSignalItem) => {
    pendingSelectedSignalIdRef.current = null;
    setSelected({ source, item });
    updateDecisionSignalSearchParams({ signal: item.id });
  }, [updateDecisionSignalSearchParams]);

  const handleOpenOutcomeSignal = useCallback(async (signalId: number) => {
    const item = await decisionSignalsApi.get(signalId);
    if (!mountedRef.current) return;
    handleSelectSignal('outcome', item);
  }, [handleSelectSignal]);

  const handleCloseSignal = useCallback(() => {
    pendingSelectedSignalIdRef.current = null;
    setStatusError(null);
    setSelected(null);
    updateDecisionSignalSearchParams({ signal: null });
  }, [updateDecisionSignalSearchParams]);

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
    listDispatch({ type: 'loadStart' });
    if (signalCenterScope === SIGNAL_CENTER_SCOPE_VALUES.watchlist && watchlistState.isLoading) {
      return;
    }
    try {
      let response: DecisionSignalListResponse;
      let responseError: ParsedApiError | null = null;
      if (signalCenterScope === SIGNAL_CENTER_SCOPE_VALUES.watchlist) {
        if (watchlistState.loadError) {
          listDispatch({ type: 'loadFailure', error: watchlistState.loadError });
          return;
        }
        const requestedStock = appliedFilters.stockCode.trim();
        const scopedCodes = requestedStock
          ? watchlistState.watchlistCodes.filter((code) => areStockCodesEquivalent(code, requestedStock))
          : watchlistState.watchlistCodes;
        const uniqueCodes = scopedCodes.filter((code, index) => (
          scopedCodes.findIndex((candidate) => areStockCodesEquivalent(candidate, code)) === index
        ));
        const perStockPageSize = 100;
        const responses: Array<{ stockCode: string; response: DecisionSignalListResponse }> = [];
        let partialError: ParsedApiError | null = null;
        const loadRequestBatch = async (batch: Array<{ stockCode: string; page: number }>) => {
          const settled = await Promise.all(batch.map(async ({ stockCode, page: stockPage }) => {
            try {
              const result = await runWithRequestSlot(
                signalListQueueRef.current,
                WATCHLIST_SIGNAL_LOOKUP_CONCURRENCY,
                async () => {
                  if (requestIdRef.current !== requestId) return null;
                  return decisionSignalsApi.list({
                    ...toListParams(appliedFilters, stockPage),
                    stockCode,
                    holdingOnly: undefined,
                    page: stockPage,
                    pageSize: perStockPageSize,
                  });
                },
              );
              if (!result) return null;
              return { stockCode, response: result };
            } catch (requestError) {
              if (requestIdRef.current === requestId) {
                partialError ??= getParsedApiError(requestError);
              }
              return null;
            }
          }));
          responses.push(...settled.filter((result): result is {
            stockCode: string;
            response: DecisionSignalListResponse;
          } => (
            result !== null
          )));
        };
        for (let index = 0; index < uniqueCodes.length; index += WATCHLIST_SIGNAL_LOOKUP_CONCURRENCY) {
          await loadRequestBatch(uniqueCodes
            .slice(index, index + WATCHLIST_SIGNAL_LOOKUP_CONCURRENCY)
            .map((stockCode) => ({ stockCode, page: 1 })));
          if (requestIdRef.current !== requestId) return;
        }
        if (partialError && responses.length === 0) throw partialError;
        const firstPageResponses = [...responses];
        const observedTotal = firstPageResponses.reduce(
          (sum, item) => sum + item.response.total,
          0,
        );
        const effectivePage = Math.min(
          nextPage,
          Math.max(1, Math.ceil(observedTotal / PAGE_SIZE)),
        );
        const requiredPerStockPageCount = Math.ceil(
          Math.max(PAGE_SIZE, effectivePage * PAGE_SIZE) / perStockPageSize,
        );
        let nextBatch: Array<{ stockCode: string; page: number }> = [];
        for (const firstPage of firstPageResponses) {
          const availablePageCount = Math.ceil(firstPage.response.total / perStockPageSize);
          const lastRequiredPage = Math.min(requiredPerStockPageCount, availablePageCount);
          for (let stockPage = 2; stockPage <= lastRequiredPage; stockPage += 1) {
            nextBatch.push({ stockCode: firstPage.stockCode, page: stockPage });
            if (nextBatch.length === WATCHLIST_SIGNAL_LOOKUP_CONCURRENCY) {
              await loadRequestBatch(nextBatch);
              if (requestIdRef.current !== requestId) return;
              nextBatch = [];
            }
          }
        }
        if (nextBatch.length > 0) {
          await loadRequestBatch(nextBatch);
          if (requestIdRef.current !== requestId) return;
        }
        response = mergeWatchlistSignalResponses(responses, effectivePage);
        responseError = partialError;
      } else {
        const nextResponse = await runWithRequestSlot(
          signalListQueueRef.current,
          WATCHLIST_SIGNAL_LOOKUP_CONCURRENCY,
          async () => {
            if (requestIdRef.current !== requestId) return null;
            return decisionSignalsApi.list(
              toListParams(appliedFilters, nextPage, signalCenterScope),
            );
          },
        );
        if (!nextResponse) return;
        response = nextResponse;
      }
      if (requestIdRef.current !== requestId) return;
      const lastPage = Math.max(1, Math.ceil(response.total / PAGE_SIZE));
      if (
        signalCenterScope !== SIGNAL_CENTER_SCOPE_VALUES.watchlist
        && response.total > 0
        && nextPage > lastPage
      ) {
        setPage(lastPage);
        listDispatch({ type: 'loadEnd' });
        syncListSearchParams(appliedFilters, lastPage);
        return;
      }
      if (
        signalCenterScope === SIGNAL_CENTER_SCOPE_VALUES.watchlist
        && response.page !== nextPage
      ) {
        setPage(response.page);
      }
      listDispatch({
        type: 'loadSuccess',
        items: response.items,
        total: response.total,
        ...(
          signalCenterScope === SIGNAL_CENTER_SCOPE_VALUES.watchlist
            ? { page: response.page }
            : {}
        ),
        error: responseError,
      });
      syncListSearchParams(appliedFilters, response.page);
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
      listDispatch({ type: 'loadFailure', error: getParsedApiError(err) });
      setSelected((current) => (current?.source === 'list' ? null : current));
    }
  }, [
    appliedFilters,
    listDispatch,
    setPage,
    signalCenterScope,
    syncListSearchParams,
    takePendingSelection,
    watchlistState.isLoading,
    watchlistState.loadError,
    watchlistState.watchlistCodes,
  ]);

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

  const listQueryKey = useMemo(() => buildDecisionSignalListQueryKey({
    scope: signalCenterScope,
    page,
    appliedFilters,
    watchlistLoading: watchlistState.isLoading,
    watchlistCodes: watchlistState.watchlistCodes,
    watchlistErrorMessage: watchlistState.loadError?.message ?? null,
  }), [
    appliedFilters,
    page,
    signalCenterScope,
    watchlistState.isLoading,
    watchlistState.loadError?.message,
    watchlistState.watchlistCodes,
  ]);

  useDecisionSignalListQuery({
    queryKey: listQueryKey,
    loadSignals,
    onCancelInFlight: () => {
      requestIdRef.current += 1;
    },
  });

  useDecisionSignalOutcomeStatsQuery({
    loadOutcomeStats,
    onCancelInFlight: () => {
      statsRequestIdRef.current += 1;
    },
  });

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
      reassessRequestIdRef.current += 1;
      selectedSignalIdRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (pendingSelectedSignalIdRef.current === null) {
      updateDecisionSignalSearchParams({ signal: selected?.item.id ?? null });
    }
  }, [selected?.item.id, updateDecisionSignalSearchParams]);

  useEffect(() => {
    selectedSignalIdRef.current = selected?.item.id ?? null;
    setFeedbackWriteError(null);
  }, [selected?.item.id]);

  const appliedSourceReportId = parseSourceReportId(appliedFilters.sourceReportId);
  const selectedSourceReportId = selected?.item.sourceReportId ?? undefined;
  const reassessSourceReportId = selected ? selectedSourceReportId : appliedSourceReportId;
  const reassessContextKey = [
    reassessSourceReportId ?? '',
    reassessProfile,
  ].join(':');

  useEffect(() => {
    reassessRequestIdRef.current += 1;
    resetReassessForContext();
  }, [reassessContextKey, resetReassessForContext]);

  const handleReassess = useCallback(async () => {
    if (!reassessSourceReportId) return;
    const requestId = reassessRequestIdRef.current + 1;
    reassessRequestIdRef.current = requestId;
    reassessDispatch({ type: 'previewStart' });
    try {
      const response = await decisionSignalsApi.reassess({
        sourceReportId: reassessSourceReportId,
        decisionProfile: reassessProfile,
        persist: false,
      });
      if (reassessRequestIdRef.current !== requestId) return;
      reassessDispatch({ type: 'previewSuccess', response });
    } catch (err) {
      if (reassessRequestIdRef.current !== requestId) return;
      reassessDispatch({ type: 'previewFailure', error: getParsedApiError(err) });
    } finally {
      if (reassessRequestIdRef.current === requestId) {
        reassessDispatch({ type: 'previewEnd' });
      }
    }
  }, [reassessDispatch, reassessProfile, reassessSourceReportId]);

  const handleApplyFilters = () => {
    applyFilters(filters);
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
    resetTimelineState();
    setSelected((current) => (current?.source === 'timeline' ? null : current));
  }, [resetTimelineState]);

  const loadTimelineForContext = useCallback(async (
    context: StockContext,
    filtersSnapshot: TimelineFilters,
    syncUrl = true,
  ) => {
    const stockCode = context.code.trim();
    if (!stockCode) return;
    const requestId = timelineRequestIdRef.current + 1;
    timelineRequestIdRef.current = requestId;
    timelineDispatch({ type: 'loadStart' });
    setSelected((current) => (current?.source === 'timeline' ? null : current));
    if (syncUrl) syncTimelineSearchParams(filtersSnapshot);
    const nextAppliedContext: AppliedTimelineContext = {
      ...filtersSnapshot,
      stockCode,
    };
    try {
      const response = await decisionSignalsApi.list(toTimelineParams(filtersSnapshot, stockCode));
      if (timelineRequestIdRef.current !== requestId) return;
      timelineDispatch({
        type: 'loadSuccess',
        items: response.items,
        truncated: response.total > response.items.length,
        appliedContext: nextAppliedContext,
      });
      const restoredSelection = takePendingSelection('timeline', response.items);
      if (restoredSelection) setSelected(restoredSelection);
      else setSelected((current) => refreshTimelineSelection(current, response.items));
    } catch (err) {
      if (timelineRequestIdRef.current !== requestId) return;
      setSelected((current) => refreshTimelineSelection(current, []));
      timelineDispatch({ type: 'loadFailure', error: getParsedApiError(err) });
    }
  }, [syncTimelineSearchParams, takePendingSelection, timelineDispatch]);

  const handlePersistReassess = useCallback(async () => {
    const preview = reassessResponse?.preview;
    const guardrail = preview && isRecord(preview.metadata.guardrail_result)
      ? preview.metadata.guardrail_result
      : null;
    if (!reassessSourceReportId || !preview || guardrail?.passed !== true) return;

    const requestId = reassessRequestIdRef.current + 1;
    reassessRequestIdRef.current = requestId;
    reassessDispatch({ type: 'persistStart' });
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
      reassessDispatch({ type: 'persistSuccess', response });
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
        reassessDispatch({ type: 'persistBlocked', blocked });
      } else {
        reassessDispatch({ type: 'persistFailure', error: getParsedApiError(err) });
      }
    } finally {
      if (reassessRequestIdRef.current === requestId) {
        reassessDispatch({ type: 'persistEnd' });
      }
    }
  }, [
    activeStockContext,
    appliedTimelineContext,
    loadLatestForContext,
    loadSignalsForPage,
    loadTimelineForContext,
    page,
    reassessDispatch,
    reassessProfile,
    reassessResponse,
    reassessSourceReportId,
    setTimelineItems,
  ]);

  const commitStockContext = useCallback((
    nextContext: StockContext,
    nextTimeline: TimelineFilterUpdate,
    selectLatestView: boolean,
  ) => {
    timelineMarketSourceRef.current = nextTimeline.marketSource;
    setActiveStockContext(nextContext);
    if (selectLatestView) {
      activeViewRef.current = 'latest';
      setActiveViewState('latest');
    }
    setStockDraft(nextContext.displayCode ?? nextContext.code);
    replaceTimelineFilters(nextTimeline.filters);
    void loadLatestForContext(nextContext);
    void loadTimelineForContext(nextContext, nextTimeline.filters, false);
  }, [
    loadLatestForContext,
    loadTimelineForContext,
    replaceTimelineFilters,
  ]);

  const applyStockContext = useCallback((nextContext: StockContext) => {
    const nextTimeline = buildNextTimelineFilters(
      timelineFilters,
      activeStockContext,
      nextContext,
      timelineMarketSourceRef.current,
    );
    pendingStockNavigationRef.current = { context: nextContext, timeline: nextTimeline };
    syncStockContextSearchParams(nextContext.code, nextTimeline.filters);
  }, [activeStockContext, syncStockContextSearchParams, timelineFilters]);

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

  const clearStockContext = useCallback((syncUrl: boolean) => {
    if (syncUrl) {
      pendingStockNavigationRef.current = { context: null };
      syncStockContextSearchParams(null);
      return;
    }
    setStockDraft('');
    setActiveStockContext(null);
    timelineMarketSourceRef.current = null;
    setTimelineFilters((current) => ({ ...current, market: '' }));
    resetLatestView();
    resetTimelineView();
  }, [resetLatestView, resetTimelineView, setTimelineFilters, syncStockContextSearchParams]);

  const handleClearStockContext = useCallback(() => {
    clearStockContext(true);
  }, [clearStockContext]);

  // The URL entry is authoritative. User commands stage metadata, then commit
  // local context only after React Router observes the corresponding entry.
  useLayoutEffect(() => {
    const urlStock = new URLSearchParams(routeLocation.search)
      .get(SIGNAL_CENTER_ROUTE_QUERY_KEYS.stock)
      ?.trim() ?? '';
    const pending = pendingStockNavigationRef.current;
    if (urlStock) {
      const pendingMatches = pending?.context
        ? areStockCodesEquivalent(pending.context.code, urlStock)
        : false;
      if (pendingMatches && pending?.context && pending.timeline) {
        pendingStockNavigationRef.current = null;
        commitStockContext(pending.context, pending.timeline, true);
        return;
      }
      if (pending) pendingStockNavigationRef.current = null;
      if (
        activeStockContext
        && areStockCodesEquivalent(activeStockContext.code, urlStock)
      ) return;
      const nextContext = { code: urlStock };
      const nextTimeline = buildNextTimelineFilters(
        timelineFilters,
        activeStockContext,
        nextContext,
        timelineMarketSourceRef.current,
      );
      commitStockContext(nextContext, nextTimeline, false);
      return;
    }
    if (pending) pendingStockNavigationRef.current = null;
    if (activeStockContext) clearStockContext(false);
  }, [
    activeStockContext,
    clearStockContext,
    commitStockContext,
    routeLocation.key,
    routeLocation.search,
    timelineFilters,
  ]);

  const handleTimelineSearch = useCallback(() => {
    if (!activeStockContext) return;
    void loadTimelineForContext(activeStockContext, timelineFilters);
  }, [activeStockContext, loadTimelineForContext, timelineFilters]);

  const [statusUpdating, setStatusUpdating] = useState(false);

  const handleStatusUpdate = async () => {
    if (!pendingStatus || statusUpdateInFlightRef.current) return;
    statusUpdateInFlightRef.current = true;
    setStatusUpdating(true);
    setStatusError(null);
    try {
      // Status write stays a single-shot page-owned call: the deferred double-click
      // guard and in-flight ref must stay byte-identical to the prior contract.
      // List/detail/stats already use TanStack Query; status can graduate once a
      // shared mutation helper preserves that guard without isPending races.
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
        if (current.source === 'outcome') {
          return { source: 'outcome', item: updated };
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
      queryClient.setQueryData(buildDecisionSignalFeedbackQueryKey(signalId), updated);
      setFeedbackWriteError(null);
    } catch (err) {
      if (!mountedRef.current || selectedSignalIdRef.current !== signalId) return;
      setFeedbackWriteError(getParsedApiError(err));
    } finally {
      if (mountedRef.current) setFeedbackSaving(false);
    }
  }, [feedbackSaving, queryClient, selected]);

  const handleManualSignalCreated = useCallback((result: DecisionSignalMutationResponse) => {
    void loadSignalsForPage(page);
    void loadOutcomeStats();
    const created = result.item;
    if (activeStockContext && areStockCodesEquivalent(created.stockCode, activeStockContext.code)) {
      void loadLatestForContext(activeStockContext);
      if (appliedTimelineContext) {
        void loadTimelineForContext(
          { code: appliedTimelineContext.stockCode, market: appliedTimelineContext.market || undefined },
          appliedTimelineContext,
        );
      }
    }
  }, [
    activeStockContext,
    appliedTimelineContext,
    loadLatestForContext,
    loadOutcomeStats,
    loadSignalsForPage,
    loadTimelineForContext,
    page,
  ]);

  const reassessPanel = (
    <DecisionSignalReassessPanel
      sourceReportId={reassessSourceReportId}
      profile={reassessProfile}
      onProfileChange={setReassessProfile}
      response={reassessResponse}
      loading={reassessLoading}
      persisting={reassessPersisting}
      persistBlocked={reassessPersistBlocked}
      error={reassessError}
      onPreview={() => void handleReassess()}
      onRequestPersist={requestPersistConfirm}
    />
  );

  const activeStockLabel = activeStockContext
    ? [
      activeStockContext.displayCode ?? activeStockContext.code,
      activeStockContext.name,
      activeStockContext.market,
    ].filter(Boolean).join(' / ')
    : null;
  const signalScopeLabel = signalCenterScope === SIGNAL_CENTER_SCOPE_VALUES.holdings
    ? t('decisionSignals.scopeHoldings')
    : signalCenterScope === SIGNAL_CENTER_SCOPE_VALUES.watchlist
      ? t('decisionSignals.scopeWatchlist')
      : t('decisionSignals.scopeAllSignals');

  return (
    <AppPage className="max-w-none">
      <div className="space-y-5">
        <PageHeader
          ref={pageHeadingRef}
          title={t('decisionSignals.title')}
          description={t('decisionSignals.signalCenterDescription')}
          actions={signalCenterTab === SIGNAL_CENTER_TAB_VALUES.feed
            || signalCenterTab === SIGNAL_CENTER_TAB_VALUES.review ? (
            <>
              <Button
                type="button"
                variant="primary"
                size="comfortable"
                onClick={() => setCreateDrawerOpen(true)}
              >
                <PlusCircle className="h-4 w-4" />
                {t('decisionSignals.create.button')}
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="comfortable"
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
                size="comfortable"
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
          ) : undefined}
        />

        <DecisionSignalCreateDrawer
          isOpen={createDrawerOpen}
          onClose={() => setCreateDrawerOpen(false)}
          draft={createDraft}
          onDraftChange={setCreateDraft}
          onCreated={handleManualSignalCreated}
        />

        <DecisionSignalStockContextModal
          isOpen={stockContextModalOpen}
          onClose={() => setStockContextModalOpen(false)}
          stockDraft={stockDraft}
          onStockDraftChange={setStockDraft}
          onSubmit={handleStockFormSubmit}
          onAutocompleteSubmit={handleStockSubmit}
          onClear={handleClearStockContext}
          activeStockContext={activeStockContext}
          activeStockLabel={activeStockLabel}
          stockCandidates={stockCandidates}
          stockCandidateMode={stockCandidateMode}
          historyCandidatesLoaded={historyCandidatesLoaded}
          onCandidateSelect={handleCandidateSelect}
        />

        {scopeControlVisible ? (
          <div
            role="group"
            aria-label={t('decisionSignals.scopeLabel')}
            className="flex flex-wrap items-center gap-2"
          >
            {([
              { value: SIGNAL_CENTER_SCOPE_VALUES.all, label: t('decisionSignals.scopeAll') },
              { value: SIGNAL_CENTER_SCOPE_VALUES.holdings, label: t('decisionSignals.scopeHoldings') },
              { value: SIGNAL_CENTER_SCOPE_VALUES.watchlist, label: t('decisionSignals.scopeWatchlist') },
            ] as const).map((option) => (
              <SelectionChip
                key={option.value}
                label={option.label}
                selected={signalCenterScope === option.value}
                onClick={() => setSignalCenterScope(option.value)}
              />
            ))}
          </div>
        ) : null}

        <Tabs
          id={SIGNAL_CENTER_TABS_ID}
          value={signalCenterTab}
          items={[
            { id: SIGNAL_CENTER_TAB_VALUES.feed, label: t('decisionSignals.tab.feed') },
            { id: SIGNAL_CENTER_TAB_VALUES.rules, label: t('decisionSignals.tab.rules') },
            { id: SIGNAL_CENTER_TAB_VALUES.history, label: t('decisionSignals.tab.history') },
            { id: SIGNAL_CENTER_TAB_VALUES.review, label: t('decisionSignals.tab.review') },
          ]}
          onValueChange={(tab) => setSignalCenterTab(tab as SignalCenterTab)}
          aria-label={t('decisionSignals.title')}
        />

        <TabPanel
          tabsId={SIGNAL_CENTER_TABS_ID}
          value={SIGNAL_CENTER_TAB_VALUES.feed}
          activeValue={signalCenterTab}
          data-signal-center-tab="feed"
          className="space-y-4"
        >
          <Tabs
            id={SIGNAL_FEED_TABS_ID}
            value={activeFeedView}
            items={[
              { id: SIGNAL_FEED_VIEW_VALUES.signals, label: t('decisionSignals.scopeAllSignals') },
              { id: SIGNAL_FEED_VIEW_VALUES.latest, label: t('decisionSignals.stockContextTitle') },
              { id: SIGNAL_FEED_VIEW_VALUES.timeline, label: t('decisionSignals.timelineTitle') },
            ]}
            onValueChange={(view) => setActiveView(view as DecisionSignalsView)}
            aria-label={t('decisionSignals.tab.feed')}
          />

          <TabPanel
            tabsId={SIGNAL_FEED_TABS_ID}
            value={SIGNAL_FEED_VIEW_VALUES.signals}
            activeValue={activeFeedView}
            className="space-y-5"
          >
            <DecisionSignalFeedListSection
              filters={filters}
              onFiltersChange={setFilters}
              onApplyFilters={handleApplyFilters}
              advancedFilterCount={advancedFilterCount}
              appliedSourceReportId={appliedSourceReportId}
              signalScopeLabel={signalScopeLabel}
              loading={loading}
              error={error}
              onRetry={() => void loadSignals()}
              total={total}
              items={items}
              selectedId={selected?.item.id}
              onSelect={(selectedItem) => handleSelectSignal('list', selectedItem)}
              page={page}
              onPageChange={(nextPage) => {
                setPage(nextPage);
                syncListSearchParams(appliedFilters, nextPage);
              }}
              reassessPanel={reassessPanel}
              onCreateFirstRule={() => updateSignalCenterRoute({
                ...signalCenterState,
                tab: SIGNAL_CENTER_TAB_VALUES.rules,
                createRule: true,
              })}
            />
          </TabPanel>

          <TabPanel
            tabsId={SIGNAL_FEED_TABS_ID}
            value={SIGNAL_FEED_VIEW_VALUES.latest}
            activeValue={activeFeedView}
          >
            <DecisionSignalLatestSection
              activeStockContext={activeStockContext}
              activeStockLabel={activeStockLabel}
              loading={latestLoading}
              searched={latestSearched}
              error={latestError}
              items={latestItems}
              selectedId={selected?.item.id}
              onSelect={(selectedItem) => handleSelectSignal('latest', selectedItem)}
            />
          </TabPanel>

          <TabPanel
            tabsId={SIGNAL_FEED_TABS_ID}
            value={SIGNAL_FEED_VIEW_VALUES.timeline}
            activeValue={activeFeedView}
          >
            <DecisionSignalTimelineSection
              activeStockContext={activeStockContext}
              activeStockLabel={activeStockLabel}
              filters={timelineFilters}
              onFiltersChange={setTimelineFilters}
              onMarketSourceUser={(hasMarket) => {
                timelineMarketSourceRef.current = hasMarket ? 'user' : null;
              }}
              onSearch={handleTimelineSearch}
              loading={timelineLoading}
              searched={timelineSearched}
              error={timelineError}
              items={timelineItems}
              truncated={timelineTruncated}
              selectedId={selected?.item.id}
              onSelect={(selectedItem) => handleSelectSignal('timeline', selectedItem)}
            />
          </TabPanel>
        </TabPanel>

        <TabPanel
          tabsId={SIGNAL_CENTER_TABS_ID}
          value={SIGNAL_CENTER_TAB_VALUES.review}
          activeValue={signalCenterTab}
        >
          <DecisionSignalReviewSection
            stats={outcomeStats}
            loading={statsLoading}
            error={statsError}
            onRetryStats={() => void loadOutcomeStats()}
            outcomeExplorerRefreshKey={outcomeExplorerRefreshKey}
            onOpenSignal={handleOpenOutcomeSignal}
            onOutcomeRunCompleted={() => {
              void loadOutcomeStats();
              setOutcomeExplorerRefreshKey((current) => current + 1);
            }}
            showExplorer={signalCenterTab === SIGNAL_CENTER_TAB_VALUES.review}
          />
        </TabPanel>

        <TabPanel
          tabsId={SIGNAL_CENTER_TABS_ID}
          value={SIGNAL_CENTER_TAB_VALUES.rules}
          activeValue={signalCenterTab}
        >
          {signalCenterTab === SIGNAL_CENTER_TAB_VALUES.rules ? (
            <AlertsWorkspace
              embedded
              scope={signalCenterScope}
              activeView="rules"
              onActiveViewChange={handleAlertsViewChange}
              createRuleRequested={signalCenterState.createRule}
              onCreateRuleRequestHandled={handleCreateRuleRequestHandled}
              ruleStock={ruleStock}
            />
          ) : null}
        </TabPanel>

        <TabPanel
          tabsId={SIGNAL_CENTER_TABS_ID}
          value={SIGNAL_CENTER_TAB_VALUES.history}
          activeValue={signalCenterTab}
        >
          {signalCenterTab === SIGNAL_CENTER_TAB_VALUES.history ? (
            <AlertsWorkspace
              embedded
              scope={SIGNAL_CENTER_SCOPE_VALUES.all}
              activeView={signalCenterHistory === SIGNAL_CENTER_HISTORY_VALUES.notifications
                ? 'notifications'
                : 'history'}
              onActiveViewChange={handleAlertsViewChange}
              selectedTriggerId={signalCenterState.triggerId}
            />
          ) : null}
        </TabPanel>
      </div>

      <DecisionSignalDetailDrawer
        selected={selected}
        onClose={handleCloseSignal}
        statusError={statusError}
        onDismissStatusError={() => setStatusError(null)}
        reassessPanel={reassessPanel}
        outcomes={selectedOutcomes}
        outcomesLoading={selectedOutcomesLoading}
        outcomesError={selectedOutcomesError}
        feedback={selectedFeedback}
        feedbackLoading={selectedFeedbackLoading}
        feedbackSaving={feedbackSaving}
        feedbackError={selectedFeedbackError}
        onFeedbackSubmit={handleFeedbackSubmit}
        statusUpdating={statusUpdating}
        onRequestStatusChange={(item, status, message) => {
          setStatusError(null);
          setPendingStatus({ item, status, message });
        }}
      />

      {statusUpdating ? (
        <ToastViewport>
          <InlineAlert
            className="pointer-events-auto ml-auto max-w-sm"
            variant="info"
            title={t('common.processing')}
            message={t('decisionSignals.confirmStatusTitle')}
          />
        </ToastViewport>
      ) : null}

      <ConfirmDialog
        isOpen={reassessPersistConfirm}
        title={t('decisionSignals.reassessPersistConfirmTitle')}
        message={t('decisionSignals.reassessPersistConfirmMessage')}
        confirmText={t('decisionSignals.reassessPersist')}
        confirmDisabled={reassessPersisting}
        cancelDisabled={reassessPersisting}
        onConfirm={() => void handlePersistReassess()}
        onCancel={cancelPersistConfirm}
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
