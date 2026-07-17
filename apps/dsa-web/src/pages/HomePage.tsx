import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BarChart3, Check, SlidersHorizontal, X } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { analysisApi, DuplicateTaskError } from '../api/analysis';
import { historyApi } from '../api/history';
import { agentApi, type SkillInfo } from '../api/agent';
import { systemConfigApi } from '../api/systemConfig';
import { ApiErrorAlert, Button, Drawer, EmptyState, InlineAlert } from '../components/common';
import { OVERLAY_Z } from '../components/common/overlayZ';
import { DashboardStateBlock } from '../components/dashboard';
import { StockAutocomplete } from '../components/StockAutocomplete';
import { StockHistoryTrendDrawer } from '../components/history';
import { ReportMarkdownDrawer } from '../components/report/ReportMarkdownDrawer';
import { ReportSummary } from '../components/report/ReportSummary';
import { RunFlowPanel } from '../components/run-flow';
import { TaskPanel } from '../components/tasks';
import {
  HomeStockWorkspace,
  type HomeWatchlistRow,
  type HomeWorkspaceTab,
  type WatchlistAnalyzeMode,
} from '../components/watchlist/HomeStockWorkspace';
import { useDashboardLifecycle, useHomeDashboardState, useHomeUrlState } from '../hooks';
import { useWatchlist } from '../hooks/useWatchlist';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import type { SetupStatusResponse } from '../types/systemConfig';
import { normalizeReportLanguage } from '../utils/reportLanguage';
import type {
  AnalyzeAsyncResponse,
  HistoryItem,
  StockBarItem,
  TaskInfo,
} from '../types/analysis';
import type { RunFlowSnapshotSource } from '../types/runFlow';
import { getTodayInShanghai } from '../utils/format';
import { normalizeStockCode } from '../utils/stockCode';
import { getStrategyDisplay } from '../utils/strategyDisplay';

type MarketReviewNotice = {
  variant: 'success' | 'warning' | 'danger';
  title: string;
  message: string;
} | null;

type RunFlowDrawerState =
  | { open: false }
  | { open: true; source: RunFlowSnapshotSource; title: string };

type StockAnalysisNavigationState = {
  stockCode?: string;
  stockName?: string;
  autoAnalyze?: boolean;
  selectionSource?: string;
};

type HomeRecordIdentity = {
  id?: number;
  stockCode?: string;
  reportType?: string;
};

type HomeRecordIdentityResolution =
  | { status: 'found'; record: HomeRecordIdentity }
  | { status: 'unavailable'; record: null }
  | { status: 'unresolved'; record: null };

const DUPLICATE_BANNER_AUTO_DISMISS_MS = 5000;
const BATCH_ANALYSIS_CHUNK_SIZE = 50;
const TODAY_ANALYSIS_PAGE_SIZE = 100;
const SERVER_LOCAL_DATE_TIME_PATTERN = /^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/;

type BatchAnalyzeStatus = {
  variant: 'success' | 'warning' | 'danger';
  message: string;
} | null;

type WatchlistHistoryLookupState = {
  signature: string;
  settledKeys: Set<string>;
  failedKeys: Set<string>;
};

function getShanghaiDateKey(value?: string | null): string {
  if (!value) return '';
  const trimmed = value.trim();
  const normalized = SERVER_LOCAL_DATE_TIME_PATTERN.test(trimmed)
    ? `${trimmed.replace(' ', 'T')}+08:00`
    : trimmed;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(date);
}

function getShanghaiTimeValue(value?: string | null): number {
  if (!value) return 0;
  const trimmed = value.trim();
  const normalized = SERVER_LOCAL_DATE_TIME_PATTERN.test(trimmed)
    ? `${trimmed.replace(' ', 'T')}+08:00`
    : trimmed;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? 0 : date.getTime();
}

function shiftDateKey(dateKey: string, days: number): string {
  const date = new Date(`${dateKey}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function getStockCodeKey(code?: string | null): string {
  const trimmed = (code ?? '').trim();
  return trimmed ? normalizeStockCode(trimmed).toUpperCase() : '';
}

function chunkStockCodes(codes: string[]): string[][] {
  const chunks: string[][] = [];
  for (let index = 0; index < codes.length; index += BATCH_ANALYSIS_CHUNK_SIZE) {
    chunks.push(codes.slice(index, index + BATCH_ANALYSIS_CHUNK_SIZE));
  }
  return chunks;
}

function countBatchAccepted(result: AnalyzeAsyncResponse): { accepted: number; duplicates: number } {
  if ('accepted' in result) {
    return {
      accepted: result.accepted.length,
      duplicates: result.duplicates.length,
    };
  }
  return { accepted: 1, duplicates: 0 };
}

function toStockBarItemFromHistoryItem(item: HistoryItem): StockBarItem {
  return {
    id: item.id,
    stockCode: item.stockCode,
    stockName: item.stockName,
    reportType: item.reportType,
    sentimentScore: item.sentimentScore,
    operationAdvice: item.operationAdvice,
    action: item.action ?? null,
    actionLabel: item.actionLabel ?? null,
    analysisCount: 0,
    lastAnalysisTime: item.createdAt,
    modelUsed: item.modelUsed,
    marketPhaseSummary: item.marketPhaseSummary ?? null,
  };
}

async function getTodayAnalysisItems(dateKey: string): Promise<StockBarItem[]> {
  const items: StockBarItem[] = [];
  let loadedRecordCount = 0;
  let page = 1;

  while (true) {
    const response = await historyApi.getList({
      // History dates are filtered in the server's local timezone. Query the
      // adjacent dates too, then apply the exact Shanghai-day filter below.
      startDate: shiftDateKey(dateKey, -1),
      endDate: shiftDateKey(dateKey, 1),
      page,
      limit: TODAY_ANALYSIS_PAGE_SIZE,
    });

    loadedRecordCount += response.items.length;
    for (const item of response.items) {
      if (item.stockCode === 'MARKET' || item.reportType === 'market_review') {
        continue;
      }
      items.push(toStockBarItemFromHistoryItem(item));
    }

    if (
      response.items.length === 0
      || response.items.length < TODAY_ANALYSIS_PAGE_SIZE
      || loadedRecordCount >= response.total
    ) {
      break;
    }

    page += 1;
  }

  return items;
}

const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { language: uiLanguage, t } = useUiLanguage();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isSubmittingMarketReview, setIsSubmittingMarketReview] = useState(false);
  const [marketReviewNotice, setMarketReviewNotice] = useState<MarketReviewNotice>(null);
  const [marketReviewError, setMarketReviewError] = useState<ParsedApiError | null>(null);
  const [analysisSkills, setAnalysisSkills] = useState<SkillInfo[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState('');
  const [strategyMenuOpen, setStrategyMenuOpen] = useState(false);
  const [runFlowRestoreError, setRunFlowRestoreError] = useState<ParsedApiError | null>(null);
  const [duplicateBannerVisible, setDuplicateBannerVisible] = useState(false);
  const [sidebarWorkspaceTab, setSidebarWorkspaceTab] = useState<HomeWorkspaceTab>('history');
  const [isBatchAnalyzingWatchlist, setIsBatchAnalyzingWatchlist] = useState(false);
  const [batchAnalyzeStatus, setBatchAnalyzeStatus] = useState<BatchAnalyzeStatus>(null);
  const [watchlistHistoryItemsByCode, setWatchlistHistoryItemsByCode] = useState<Map<string, StockBarItem>>(new Map());
  const [watchlistHistoryLookupState, setWatchlistHistoryLookupState] = useState<WatchlistHistoryLookupState>({
    signature: '',
    settledKeys: new Set(),
    failedKeys: new Set(),
  });
  const [todayHistoryItems, setTodayHistoryItems] = useState<StockBarItem[]>([]);
  const [isLoadingTodayAnalysisItems, setIsLoadingTodayAnalysisItems] = useState(false);
  const [todayAnalysisLoadFailed, setTodayAnalysisLoadFailed] = useState(false);
  const [todayAnalysisRefreshVersion, setTodayAnalysisRefreshVersion] = useState(0);
  const [isStockBarInitialLoadSettled, setIsStockBarInitialLoadSettled] = useState(false);
  const duplicateBannerTimer = useRef<number | null>(null);
  const marketReviewPollTimer = useRef<number | null>(null);
  const marketReviewPollGeneration = useRef(0);
  const homeUrlOwnerActiveRef = useRef(false);
  const closeSidebar = useCallback(() => setSidebarOpen(false), []);
  const stockBarLoadStartedRef = useRef(false);
  const dashboardScrollRef = useRef<HTMLElement | null>(null);
  const strategyMenuRef = useRef<HTMLDivElement | null>(null);
  const strategyButtonRef = useRef<HTMLButtonElement | null>(null);
  const strategyItemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const strategyInitialFocusIndexRef = useRef<number | null>(null);

  const stopMarketReviewPolling = useCallback(() => {
    // Bump the generation so any in-flight poll from the previous run is
    // discarded when it resolves, and cancel the next scheduled tick.
    marketReviewPollGeneration.current += 1;
    if (marketReviewPollTimer.current !== null) {
      window.clearTimeout(marketReviewPollTimer.current);
      marketReviewPollTimer.current = null;
    }
  }, []);

  const scrollMarketReviewFeedbackIntoView = useCallback(() => {
    const scrollContainer = dashboardScrollRef.current;
    if (!scrollContainer) {
      return;
    }

    if (typeof scrollContainer.scrollTo === 'function') {
      scrollContainer.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    scrollContainer.scrollTop = 0;
  }, []);

  useEffect(() => {
    homeUrlOwnerActiveRef.current = true;
    return () => {
      homeUrlOwnerActiveRef.current = false;
      stopMarketReviewPolling();
    };
  }, [stopMarketReviewPolling]);
  const [setupStatus, setSetupStatus] = useState<SetupStatusResponse | null>(null);

  const {
    query,
    inputError,
    duplicateError,
    duplicateTask,
    error,
    reportDetailError,
    reportSelectionEpoch,
    isAnalyzing,
    historyItems,
    isLoadingHistory,
    selectedReport,
    selectedRecordId,
    isLoadingReport,
    isHistoryTrendOpen,
    marketReviewHistoryItems,
    stockHistoryItems,
    stockHistoryTotal,
    stockHistoryHasMore,
    isLoadingStockHistory,
    isLoadingMoreStockHistory,
    stockHistoryError,
    stockHistoryFilters,
    activeTasks,
    markdownDrawerOpen,
    setQuery,
    clearError,
    loadInitialHistory,
    refreshHistory,
    refreshHistoryForCompletedTask,
    loadMarketReviewHistory,
    refreshMarketReviewHistory,
    selectHistoryItem,
    retrySelectedRecord,
    clearSelectedRecord,
    submitAnalysis,
    notify,
    setNotify,
    syncTaskCreated,
    syncTaskUpdated,
    syncTaskFailed,
    refreshActiveTasks,
    pollKnownTasks,
    removeTask,
    openMarkdownDrawer,
    closeMarkdownDrawer,
    openHistoryTrend,
    closeHistoryTrend,
    setStockHistoryRange,
    loadMoreStockHistory,
    stockBarItems,
    isLoadingStockBar,
    stockBarRefreshFailed,
    loadStockBar,
    refreshStockBar,
  } = useHomeDashboardState();

  const homeUrlState = useHomeUrlState({
    defaultRecordId: historyItems[0]?.id ?? null,
    isHistoryLoading: isLoadingHistory,
    selectedRecordId,
    selectedReportId: selectedReport?.meta.id ?? null,
    isReportLoading: isLoadingReport,
    reportError: reportDetailError,
    reportSelectionEpoch,
    selectHistoryItem,
    clearSelectedRecord,
  });
  const homeRecordIdRef = useRef(homeUrlState.recordId);
  homeRecordIdRef.current = homeUrlState.recordId;
  const homeUrlStateRef = useRef(homeUrlState);
  homeUrlStateRef.current = homeUrlState;
  const homeLocationRef = useRef({ key: location.key, search: location.search });
  homeLocationRef.current = { key: location.key, search: location.search };
  const selectedReportRef = useRef(selectedReport);
  selectedReportRef.current = selectedReport;

  const clearDuplicateBannerTimer = useCallback(() => {
    if (duplicateBannerTimer.current !== null) {
      window.clearTimeout(duplicateBannerTimer.current);
      duplicateBannerTimer.current = null;
    }
  }, []);

  const dismissDuplicateBanner = useCallback(() => {
    clearDuplicateBannerTimer();
    setDuplicateBannerVisible(false);
  }, [clearDuplicateBannerTimer]);

  useEffect(() => {
    if (!duplicateError) {
      clearDuplicateBannerTimer();
      setDuplicateBannerVisible(false);
      return undefined;
    }

    setDuplicateBannerVisible(true);
    clearDuplicateBannerTimer();
    duplicateBannerTimer.current = window.setTimeout(() => {
      duplicateBannerTimer.current = null;
      setDuplicateBannerVisible(false);
    }, DUPLICATE_BANNER_AUTO_DISMISS_MS);

    return clearDuplicateBannerTimer;
  }, [clearDuplicateBannerTimer, duplicateError]);

  useEffect(() => {
    document.title = t('home.pageTitle');
  }, [t]);

  useEffect(() => {
    let active = true;
    systemConfigApi.getSetupStatus()
      .then((status) => {
        if (active) {
          setSetupStatus(status);
        }
      })
      .catch(() => {
        if (active) {
          setSetupStatus(null);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    agentApi.getSkills()
      .then((response) => {
        if (active) {
          setAnalysisSkills(response.skills);
        }
      })
      .catch(() => {
        if (active) {
          setAnalysisSkills([]);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!strategyMenuOpen) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (target instanceof Node && strategyMenuRef.current?.contains(target)) {
        return;
      }
      setStrategyMenuOpen(false);
    };

    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [strategyMenuOpen]);

  useEffect(() => {
    if (selectedStrategyId && !analysisSkills.some((skill) => skill.id === selectedStrategyId)) {
      setSelectedStrategyId('');
    }
  }, [analysisSkills, selectedStrategyId]);

  const reportLanguage = normalizeReportLanguage(selectedReport?.meta.reportLanguage);
  const isMarketReviewHistoryReport = selectedReport?.meta.reportType === 'market_review';
  const isHistoryTrendUnavailable = !selectedReport || !selectedReport.meta.stockCode;
  const homeUrlIssueTitle = homeUrlState.urlIssue === 'invalid_record'
    ? t('home.invalidRecordLinkTitle')
    : t('home.invalidRunFlowLinkTitle');
  const homeUrlIssueMessage = homeUrlState.urlIssue === 'invalid_record'
    ? t('home.invalidRecordLinkMessage')
    : t('home.invalidRunFlowLinkMessage');
  const hasUnresolvedReportIntent = homeUrlState.recordId !== null
    && selectedRecordId === homeUrlState.recordId
    && selectedReport?.meta.id !== homeUrlState.recordId
    && !isLoadingReport;
  // A selected record failed to load: keep the failure (with retry) in view
  // instead of the stale previous report or the generic empty state.
  const isReportLoadFailure = Boolean(reportDetailError) && hasUnresolvedReportIntent;
  const visibleReportError = reportDetailError ?? error;

  useEffect(() => {
    if (!isHistoryTrendUnavailable || !isHistoryTrendOpen) {
      return;
    }
    closeHistoryTrend();
  }, [closeHistoryTrend, isHistoryTrendOpen, isHistoryTrendUnavailable]);

  const selectedStrategy = useMemo(
    () => analysisSkills.find((skill) => skill.id === selectedStrategyId),
    [analysisSkills, selectedStrategyId],
  );
  const selectedStrategyDisplay = useMemo(
    () => selectedStrategy ? getStrategyDisplay(selectedStrategy, uiLanguage) : null,
    [selectedStrategy, uiLanguage],
  );
  const selectedAnalysisSkills = useMemo(
    () => (selectedStrategyId ? [selectedStrategyId] : undefined),
    [selectedStrategyId],
  );
  const strategyOptions = useMemo(
    () => [
      { id: '', name: t('home.defaultStrategyName'), description: t('home.defaultStrategyDescription') },
      ...analysisSkills.map((skill) => ({ id: skill.id, ...getStrategyDisplay(skill, uiLanguage) })),
    ],
    [analysisSkills, t, uiLanguage],
  );
  const closeStrategyMenu = useCallback((restoreFocus = false) => {
    setStrategyMenuOpen(false);
    if (restoreFocus) {
      strategyButtonRef.current?.focus();
    }
  }, []);
  const selectStrategy = useCallback((strategyId: string) => {
    setSelectedStrategyId(strategyId);
    setStrategyMenuOpen(false);
  }, []);
  const focusStrategyItem = useCallback((index: number) => {
    const itemCount = strategyOptions.length;
    if (itemCount === 0) {
      return;
    }
    const nextIndex = (index + itemCount) % itemCount;
    strategyItemRefs.current[nextIndex]?.focus();
  }, [strategyOptions.length]);
  const getSelectedStrategyIndex = useCallback(() => {
    const selectedIndex = strategyOptions.findIndex((option) => option.id === selectedStrategyId);
    return selectedIndex >= 0 ? selectedIndex : 0;
  }, [selectedStrategyId, strategyOptions]);
  useEffect(() => {
    strategyItemRefs.current = strategyItemRefs.current.slice(0, strategyOptions.length);
  }, [strategyOptions.length]);
  useEffect(() => {
    if (!strategyMenuOpen) {
      return undefined;
    }

    const targetIndex = strategyInitialFocusIndexRef.current ?? getSelectedStrategyIndex();
    strategyInitialFocusIndexRef.current = null;
    const timeout = window.setTimeout(() => focusStrategyItem(targetIndex), 0);
    return () => window.clearTimeout(timeout);
  }, [focusStrategyItem, getSelectedStrategyIndex, strategyMenuOpen]);
  const handleStrategyButtonKeyDown = useCallback((event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') {
      return;
    }

    event.preventDefault();
    const targetIndex = event.key === 'ArrowUp' ? strategyOptions.length - 1 : 0;
    if (strategyMenuOpen) {
      focusStrategyItem(targetIndex);
      return;
    }
    strategyInitialFocusIndexRef.current = targetIndex;
    setStrategyMenuOpen(true);
  }, [focusStrategyItem, strategyMenuOpen, strategyOptions.length]);
  const handleStrategyMenuKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    const itemCount = strategyOptions.length;
    if (itemCount === 0) {
      return;
    }

    const currentIndex = strategyItemRefs.current.findIndex((item) => item === document.activeElement);
    switch (event.key) {
      case 'Escape':
        event.preventDefault();
        closeStrategyMenu(true);
        break;
      case 'ArrowDown':
        event.preventDefault();
        focusStrategyItem(currentIndex >= 0 ? currentIndex + 1 : 0);
        break;
      case 'ArrowUp':
        event.preventDefault();
        focusStrategyItem(currentIndex >= 0 ? currentIndex - 1 : itemCount - 1);
        break;
      case 'Home':
        event.preventDefault();
        focusStrategyItem(0);
        break;
      case 'End':
        event.preventDefault();
        focusStrategyItem(itemCount - 1);
        break;
      case 'Tab':
        setStrategyMenuOpen(false);
        break;
      default:
        break;
    }
  }, [closeStrategyMenu, focusStrategyItem, strategyOptions.length]);
  const setupNeedsAction = setupStatus ? !setupStatus.isComplete : false;
  const setupMissingLabels = useMemo(() => {
    if (!setupStatus) {
      return '';
    }
    const requiredNeedsAction = setupStatus.checks
      .filter((check) => check.required && check.status === 'needs_action')
      .map((check) => check.title);
    return requiredNeedsAction.slice(0, 3).join(uiLanguage === 'en' ? ', ' : '、');
  }, [setupStatus, uiLanguage]);

  const handleCompletedTaskDataRefreshed = useCallback((task: TaskInfo) => {
    if (task.reportType !== 'market_review') {
      setTodayAnalysisRefreshVersion((version) => version + 1);
    }
  }, []);

  const refreshCompletedTaskHistory = useCallback(async (task: TaskInfo) => {
    const recordIdAtStart = homeUrlState.recordId;
    const locationAtStart = homeLocationRef.current;
    const selectedReportAtStart = selectedReport;
    const selectedStockCode = selectedReportAtStart?.meta.reportType === 'market_review'
      ? ''
      : getStockCodeKey(selectedReportAtStart?.meta.stockCode);
    const taskStockCode = getStockCodeKey(task.stockCode);
    const mayOpenCompletedReport = recordIdAtStart === null || (
      selectedReportAtStart?.meta.id === recordIdAtStart
      && selectedStockCode.length > 0
      && selectedStockCode === taskStockCode
    );

    const nextItem = await refreshHistoryForCompletedTask(task);
    const latestLocation = homeLocationRef.current;
    if (
      !homeUrlOwnerActiveRef.current
      || !mayOpenCompletedReport
      || !nextItem
      || nextItem.id === recordIdAtStart
      || homeRecordIdRef.current !== recordIdAtStart
      || latestLocation.key !== locationAtStart.key
      || latestLocation.search !== locationAtStart.search
    ) {
      return;
    }
    homeUrlStateRef.current.replaceRecord(nextItem.id);
  }, [homeUrlState, refreshHistoryForCompletedTask, selectedReport]);

  const handleDashboardDataRefresh = useCallback(() => {
    setTodayAnalysisRefreshVersion((version) => version + 1);
  }, []);

  useDashboardLifecycle({
    loadInitialHistory,
    refreshHistory,
    refreshHistoryForCompletedTask: refreshCompletedTaskHistory,
    loadMarketReviewHistory,
    refreshMarketReviewHistory,
    loadStockBar,
    refreshStockBar,
    syncTaskCreated,
    syncTaskUpdated,
    syncTaskFailed,
    refreshActiveTasks,
    pollKnownTasks,
    removeTask,
    onDashboardDataRefresh: handleDashboardDataRefresh,
    onCompletedTaskDataRefreshed: handleCompletedTaskDataRefreshed,
  });

  useEffect(() => {
    if (isLoadingStockBar) {
      stockBarLoadStartedRef.current = true;
      return;
    }
    if (stockBarLoadStartedRef.current || stockBarItems.length > 0) {
      setIsStockBarInitialLoadSettled(true);
    }
  }, [isLoadingStockBar, stockBarItems.length]);

  const watchlistState = useWatchlist();
  const watchlistCodesByNormalized = useMemo(() => {
    const codesByNormalized = new Map<string, string>();
    for (const code of watchlistState.watchlistCodes) {
      const key = getStockCodeKey(code);
      if (!key || key === 'MARKET' || codesByNormalized.has(key)) {
        continue;
      }
      codesByNormalized.set(key, code);
    }
    return Array.from(codesByNormalized.entries());
  }, [watchlistState.watchlistCodes]);

  const stockBarItemByCode = useMemo(() => {
    const itemsByCode = new Map<string, StockBarItem>();
    for (const item of stockBarItems) {
      if (item.stockCode === 'MARKET') {
        continue;
      }
      const key = getStockCodeKey(item.stockCode);
      if (key) {
        itemsByCode.set(key, item);
      }
    }
    return itemsByCode;
  }, [stockBarItems]);

  const canLookupWatchlistHistory = !isLoadingStockBar && isStockBarInitialLoadSettled;

  const watchlistMissingHistoryEntries = useMemo(
    () => (
      canLookupWatchlistHistory
        ? watchlistCodesByNormalized.filter(([key]) => !stockBarItemByCode.has(key))
        : []
    ),
    [canLookupWatchlistHistory, stockBarItemByCode, watchlistCodesByNormalized],
  );

  const watchlistMissingHistorySignature = useMemo(
    () => watchlistMissingHistoryEntries.map(([key]) => key).join('\n'),
    [watchlistMissingHistoryEntries],
  );

  useEffect(() => {
    if (!canLookupWatchlistHistory) {
      setWatchlistHistoryItemsByCode(new Map());
      setWatchlistHistoryLookupState({ signature: '', settledKeys: new Set(), failedKeys: new Set() });
      return undefined;
    }

    const missingCodes = watchlistMissingHistoryEntries.map(([, code]) => code);
    const missingKeys = watchlistMissingHistoryEntries.map(([key]) => key);
    const currentSignature = watchlistMissingHistorySignature;

    if (missingCodes.length === 0) {
      setWatchlistHistoryItemsByCode(new Map());
      setWatchlistHistoryLookupState({ signature: '', settledKeys: new Set(), failedKeys: new Set() });
      return;
    }

    let isCanceled = false;
    setWatchlistHistoryLookupState({ signature: currentSignature, settledKeys: new Set(), failedKeys: new Set() });
    void (async () => {
      try {
        const results = await Promise.all(
          missingCodes.map(async (code) => {
            try {
              const response = await historyApi.getList({ stockCode: code, limit: 1 });
              return { code, item: response.items[0] ?? null, failed: false };
            } catch {
              return { code, item: null, failed: true };
            }
          }),
        );

        if (isCanceled) {
          return;
        }

        const next = new Map<string, StockBarItem>();
        const failedKeys = new Set<string>();
        for (const entry of results) {
          const key = getStockCodeKey(entry.code);
          if (!key) {
            continue;
          }
          if (entry.failed) {
            failedKeys.add(key);
            continue;
          }
          if (entry.item) {
            next.set(key, toStockBarItemFromHistoryItem(entry.item));
          }
        }
        setWatchlistHistoryItemsByCode(next);
        setWatchlistHistoryLookupState({
          signature: currentSignature,
          settledKeys: new Set(missingKeys),
          failedKeys,
        });
      } catch {
        if (!isCanceled) {
          setWatchlistHistoryItemsByCode(new Map());
          setWatchlistHistoryLookupState({
            signature: currentSignature,
            settledKeys: new Set(missingKeys),
            failedKeys: new Set(missingKeys),
          });
        }
      }
    })();

    return () => {
      isCanceled = true;
    };
  }, [canLookupWatchlistHistory, watchlistMissingHistoryEntries, watchlistMissingHistorySignature]);

  const clearMarketReviewState = useCallback(() => {
    stopMarketReviewPolling();
    setMarketReviewNotice(null);
    setMarketReviewError(null);
  }, [stopMarketReviewPolling]);

  const handleHistoryItemClick = useCallback((recordId: number) => {
    clearMarketReviewState();
    homeUrlState.navigateToRecord(recordId);
    setSidebarOpen(false);
  }, [clearMarketReviewState, homeUrlState]);

  const [isDeletingStock, setIsDeletingStock] = useState(false);
  const handleDeleteStock = useCallback(async (stockCode: string) => {
    if (isDeletingStock) return;
    const recordIdAtStart = homeRecordIdRef.current;
    const deletedStockCode = getStockCodeKey(stockCode);
    const knownRecords = new Map<number, HomeRecordIdentity>();
    const rememberRecord = (record: HomeRecordIdentity | null | undefined) => {
      if (typeof record?.id === 'number') {
        knownRecords.set(record.id, record);
      }
    };
    rememberRecord(selectedReport?.meta);
    historyItems.forEach(rememberRecord);
    marketReviewHistoryItems.forEach(rememberRecord);
    stockHistoryItems.forEach(rememberRecord);
    stockBarItems.forEach(rememberRecord);
    todayHistoryItems.forEach(rememberRecord);

    const matchesDeletedStock = (record: HomeRecordIdentity | null): boolean => Boolean(record) && (
      stockCode === 'MARKET'
        ? record?.reportType === 'market_review'
        : record?.reportType !== 'market_review'
          && getStockCodeKey(record?.stockCode) === deletedStockCode
    );
    const resolveRecordIdentity = async (recordId: number): Promise<HomeRecordIdentityResolution> => {
      const currentReport = selectedReportRef.current;
      if (currentReport?.meta.id === recordId) {
        rememberRecord(currentReport.meta);
        return { status: 'found', record: currentReport.meta };
      }
      const knownRecord = knownRecords.get(recordId);
      if (knownRecord) {
        return { status: 'found', record: knownRecord };
      }
      try {
        const report = await historyApi.getDetail(recordId);
        rememberRecord(report.meta);
        return { status: 'found', record: report.meta };
      } catch (error) {
        const parsedError = getParsedApiError(error);
        return parsedError.status === 404 || parsedError.code === 'not_found'
          ? { status: 'unavailable', record: null }
          : { status: 'unresolved', record: null };
      }
    };

    setIsDeletingStock(true);
    try {
      if (recordIdAtStart !== null) {
        await resolveRecordIdentity(recordIdAtStart);
      }
      await historyApi.deleteByCode(stockCode);
      const [freshHistory] = await Promise.all([
        refreshHistory(false),
        refreshStockBar(),
        stockCode === 'MARKET' ? refreshMarketReviewHistory(false) : Promise.resolve(),
      ]);
      if (!homeUrlOwnerActiveRef.current) {
        return;
      }
      const nextItem = freshHistory?.items.find((item) => (
        stockCode === 'MARKET'
          ? item.reportType !== 'market_review'
          : getStockCodeKey(item.stockCode) !== deletedStockCode
      ));
      const preserveError = freshHistory === null;

      while (true) {
        const currentRecordId = homeRecordIdRef.current;
        if (currentRecordId === null) {
          break;
        }
        const currentRecord = await resolveRecordIdentity(currentRecordId);
        if (!homeUrlOwnerActiveRef.current) {
          break;
        }
        if (homeRecordIdRef.current !== currentRecordId) {
          continue;
        }
        if (currentRecord.status === 'unavailable' || matchesDeletedStock(currentRecord.record)) {
          clearSelectedRecord(preserveError);
          homeUrlStateRef.current.replaceRecord(nextItem?.id ?? null, preserveError);
        }
        break;
      }
    } finally {
      if (homeUrlOwnerActiveRef.current) {
        setIsDeletingStock(false);
      }
    }
  }, [
    historyItems,
    isDeletingStock,
    marketReviewHistoryItems,
    refreshHistory,
    refreshMarketReviewHistory,
    refreshStockBar,
    selectedReport,
    stockBarItems,
    stockHistoryItems,
    todayHistoryItems,
    clearSelectedRecord,
  ]);

  const handleSubmitAnalysis = useCallback(
    (
      stockCode?: string,
      stockName?: string,
      selectionSource?: 'manual' | 'autocomplete' | 'import' | 'image',
    ) => {
      void submitAnalysis({
        stockCode,
        stockName,
        originalQuery: query,
        selectionSource: selectionSource ?? 'manual',
        skills: selectedAnalysisSkills,
      });
    },
    [query, selectedAnalysisSkills, submitAnalysis],
  );

  useEffect(() => {
    const state = location.state as StockAnalysisNavigationState | null;
    const stockCode = typeof state?.stockCode === 'string' ? state.stockCode.trim() : '';
    if (!stockCode) {
      return;
    }
    const stockName = typeof state?.stockName === 'string' ? state.stockName.trim() : '';
    setQuery(stockCode);
    navigate(location.pathname, { replace: true, state: null });
    if (state?.autoAnalyze) {
      handleSubmitAnalysis(stockCode, stockName || undefined, 'import');
    }
  }, [handleSubmitAnalysis, location.pathname, location.state, navigate, setQuery]);

  const handleAskFollowUp = useCallback(() => {
    if (selectedReport?.meta.id === undefined || selectedReport.meta.reportType === 'market_review') {
      return;
    }

    const code = selectedReport.meta.stockCode;
    const name = selectedReport.meta.stockName;
    const rid = selectedReport.meta.id;
    navigate(`/chat?stock=${encodeURIComponent(code)}&name=${encodeURIComponent(name)}&recordId=${rid}`);
  }, [navigate, selectedReport]);

  const handleReanalyze = useCallback(() => {
    if (!selectedReport || selectedReport.meta.reportType === 'market_review') {
      return;
    }

    void submitAnalysis({
      stockCode: selectedReport.meta.stockCode,
      stockName: selectedReport.meta.stockName,
      originalQuery: selectedReport.meta.stockCode,
      selectionSource: 'manual',
      forceRefresh: true,
      skills: selectedAnalysisSkills,
    });
  }, [selectedAnalysisSkills, selectedReport, submitAnalysis]);

  const openTaskRunFlow = useCallback((task: TaskInfo) => {
    setRunFlowRestoreError(null);
    homeUrlState.openTaskRunFlow(task.taskId);
  }, [homeUrlState]);

  const openHistoryRunFlow = useCallback((recordId: number) => {
    setRunFlowRestoreError(null);
    homeUrlState.openHistoryRunFlow(recordId);
  }, [homeUrlState]);

  const closeRunFlowDrawer = useCallback(() => {
    homeUrlState.closeRunFlow();
  }, [homeUrlState]);

  const handleUnavailableRunFlow = useCallback((runFlowError: ParsedApiError) => {
    setRunFlowRestoreError(runFlowError);
    homeUrlState.removeUnavailableRunFlow();
  }, [homeUrlState]);

  const runFlowDrawer = useMemo<RunFlowDrawerState>(() => {
    const source = homeUrlState.runFlowSource;
    if (!source) {
      return { open: false };
    }

    if (source.type === 'task') {
      const task = activeTasks.find((item) => item.taskId === source.taskId);
      const stock = task?.stockName || task?.stockCode || source.taskId;
      return {
        open: true,
        source,
        title: t('runFlow.taskDrawerTitle', { stock }),
      };
    }

    const reportMeta = selectedReport?.meta.id === source.recordId ? selectedReport.meta : null;
    const historyItem = historyItems.find((item) => item.id === source.recordId);
    const stock = reportMeta?.stockName
      || reportMeta?.stockCode
      || historyItem?.stockName
      || historyItem?.stockCode
      || String(source.recordId);
    return {
      open: true,
      source,
      title: t('runFlow.historyDrawerTitle', { stock }),
    };
  }, [activeTasks, historyItems, homeUrlState.runFlowSource, selectedReport, t]);

  const pollMarketReviewStatus = useCallback(
    async (taskId: string) => {
      stopMarketReviewPolling();
      // Capture this run's generation after stop bumped it; results are only
      // applied while this stays the current generation (single-flight).
      const generation = marketReviewPollGeneration.current;
      const isCurrent = () => generation === marketReviewPollGeneration.current;

      const maxAttempts = 120;
      const intervalMs = 2000;
      let attempts = 0;

      const poll = async (): Promise<boolean> => {
        if (attempts >= maxAttempts) {
          setMarketReviewNotice({
            variant: 'danger',
            title: t('home.marketReviewTimeout'),
            message: t('home.marketReviewTimeoutMessage'),
          });
          scrollMarketReviewFeedbackIntoView();
          return false;
        }

        attempts += 1;

        try {
          const status = await analysisApi.getStatus(taskId);
          // Discard results from a superseded run (page left or a newer review).
          if (!isCurrent()) {
            return false;
          }
          if (status.status === 'pending' || status.status === 'processing') {
            const progress = typeof status.progress === 'number'
              ? `${status.progress}%`
              : t('home.progressActive');
            setMarketReviewNotice({
              variant: 'warning',
              title: t('home.marketReviewInProgress'),
              message: t('home.taskStatus', { status: status.status, progress }),
            });
            return true;
          }

          if (status.status === 'completed') {
            const refreshedHistory = await refreshMarketReviewHistory(true);
            if (!isCurrent() || !homeUrlOwnerActiveRef.current) {
              return false;
            }
            const persistedItem = refreshedHistory?.items.find((item) => (
              item.reportType === 'market_review' && item.queryId === taskId
            ));
            setMarketReviewNotice({
              variant: 'success',
              title: t('home.marketReviewCompleted'),
              message: persistedItem
                ? t('home.marketReviewCompletedWithReport')
                : t('home.marketReviewCompletedWithoutReport'),
            });
            setMarketReviewError(null);
            if (persistedItem) {
              homeUrlStateRef.current.replaceRecord(persistedItem.id);
            }
            scrollMarketReviewFeedbackIntoView();
            return false;
          }

          if (status.status === 'failed') {
            setMarketReviewError(
              getParsedApiError({
                response: {
                  status: 500,
                  data: {
                    error: 'market_review_failed',
                    message: status.error || t('home.marketReviewFailed'),
                  },
                },
              }),
            );
            setMarketReviewNotice(null);
            scrollMarketReviewFeedbackIntoView();
            return false;
          }

          setMarketReviewNotice({
            variant: 'danger',
            title: t('home.marketReviewUnknownStatus'),
            message: t('home.unknownTaskStatus', { status: status.status }),
          });
          scrollMarketReviewFeedbackIntoView();
          return false;
        } catch (err: unknown) {
          if (!isCurrent()) {
            return false;
          }
          const parsed = getParsedApiError(err);
          if (attempts >= maxAttempts) {
            setMarketReviewError(parsed);
            setMarketReviewNotice(null);
            scrollMarketReviewFeedbackIntoView();
            return false;
          }
          return true;
        }
      };

      // Single-flight recursive scheduler: the next tick is only scheduled
      // after the current poll settles, so slow requests never overlap.
      const runPoll = async (): Promise<void> => {
        const shouldContinue = await poll();
        if (!isCurrent() || !shouldContinue) {
          return;
        }
        marketReviewPollTimer.current = window.setTimeout(() => {
          void runPoll();
        }, intervalMs);
      };

      await runPoll();
    },
    [refreshMarketReviewHistory, scrollMarketReviewFeedbackIntoView, stopMarketReviewPolling, t],
  );

  const handleTriggerMarketReview = useCallback(async () => {
    setIsSubmittingMarketReview(true);
    setMarketReviewNotice(null);
    setMarketReviewError(null);
    scrollMarketReviewFeedbackIntoView();
    try {
      const result = await analysisApi.triggerMarketReview({ sendNotification: notify });
      setMarketReviewNotice({
        variant: 'success',
        title: t('home.marketReviewSubmitted'),
        message: result.message,
      });
      scrollMarketReviewFeedbackIntoView();

      if (result.taskId) {
        void pollMarketReviewStatus(result.taskId);
      }
    } catch (err: unknown) {
      setMarketReviewError(getParsedApiError(err));
      setMarketReviewNotice(null);
      scrollMarketReviewFeedbackIntoView();
    } finally {
      setIsSubmittingMarketReview(false);
    }
  }, [notify, pollMarketReviewStatus, scrollMarketReviewFeedbackIntoView, t]);

  const todayDateKey = getTodayInShanghai();
  useEffect(() => {
    if (sidebarWorkspaceTab !== 'today') {
      return undefined;
    }

    let active = true;
    setIsLoadingTodayAnalysisItems(true);
    setTodayAnalysisLoadFailed(false);
    void getTodayAnalysisItems(todayDateKey)
      .then((items) => {
        if (active) {
          setTodayHistoryItems(items);
          setTodayAnalysisLoadFailed(false);
        }
      })
      .catch(() => {
        if (active) {
          setTodayHistoryItems([]);
          setTodayAnalysisLoadFailed(true);
        }
      })
      .finally(() => {
        if (active) {
          setIsLoadingTodayAnalysisItems(false);
        }
      });

    return () => {
      active = false;
    };
  }, [sidebarWorkspaceTab, todayAnalysisRefreshVersion, todayDateKey]);

  const activeTaskByCode = useMemo(() => {
    const tasksByCode = new Map<string, TaskInfo>();
    for (const task of activeTasks) {
      if (!['pending', 'processing', 'cancel_requested'].includes(task.status)) {
        continue;
      }
      if (task.reportType === 'market_review') {
        continue;
      }
      const key = getStockCodeKey(task.stockCode);
      if (key) {
        tasksByCode.set(key, task);
      }
    }
    return tasksByCode;
  }, [activeTasks]);

  const watchlistRows = useMemo<HomeWatchlistRow[]>(() => (
    watchlistState.watchlistCodes.map((code) => {
      const key = getStockCodeKey(code);
      const latestItem = key
        ? stockBarItemByCode.get(key) ?? watchlistHistoryItemsByCode.get(key)
        : undefined;
      const isMissingFromStockBar = Boolean(key && !stockBarItemByCode.has(key));
      const isTodayStatusUnknown = Boolean(
        stockBarRefreshFailed
        || (
          isMissingFromStockBar
          && canLookupWatchlistHistory
          && watchlistHistoryLookupState.signature === watchlistMissingHistorySignature
          && watchlistHistoryLookupState.failedKeys.has(key)
        ),
      );
      const isTodayStatusLoading = Boolean(
        isMissingFromStockBar
        && !isTodayStatusUnknown
        && (
          !canLookupWatchlistHistory
          ||
          watchlistHistoryLookupState.signature !== watchlistMissingHistorySignature
          || !watchlistHistoryLookupState.settledKeys.has(key)
        ),
      );
      return {
        code,
        latestItem,
        analyzedToday: !isTodayStatusLoading && !isTodayStatusUnknown && getShanghaiDateKey(latestItem?.lastAnalysisTime) === todayDateKey,
        isTodayStatusLoading,
        isTodayStatusUnknown,
        activeTask: key ? activeTaskByCode.get(key) : undefined,
      };
    })
  ), [
    activeTaskByCode,
    canLookupWatchlistHistory,
    stockBarRefreshFailed,
    stockBarItemByCode,
    todayDateKey,
    watchlistHistoryItemsByCode,
    watchlistHistoryLookupState,
    watchlistMissingHistorySignature,
    watchlistState.watchlistCodes,
  ]);

  const watchlistAnalyzedTodayCount = useMemo(
    () => watchlistRows.filter((row) => row.analyzedToday).length,
    [watchlistRows],
  );

  const pendingWatchlistCodes = useMemo(
    () => watchlistRows
      .filter((row) => !row.analyzedToday && !row.isTodayStatusLoading && !row.isTodayStatusUnknown)
      .map((row) => row.code),
    [watchlistRows],
  );

  const watchlistTodayStatusBlocked = useMemo(
    () => watchlistRows.some((row) => row.isTodayStatusLoading || row.isTodayStatusUnknown),
    [watchlistRows],
  );

  const todayAnalysisItems = useMemo(() => {
    const itemsById = new Map<number, StockBarItem>();
    const addItem = (item: StockBarItem) => {
      if (item.stockCode === 'MARKET' || item.reportType === 'market_review') {
        return;
      }
      if (getShanghaiDateKey(item.lastAnalysisTime) !== todayDateKey) {
        return;
      }
      itemsById.set(item.id, item);
    };

    for (const item of todayHistoryItems) {
      addItem(item);
    }

    return Array.from(itemsById.values())
      .sort((left, right) => {
        const leftScore = typeof left.sentimentScore === 'number' ? left.sentimentScore : -1;
        const rightScore = typeof right.sentimentScore === 'number' ? right.sentimentScore : -1;
        if (rightScore !== leftScore) {
          return rightScore - leftScore;
        }
        const leftTime = getShanghaiTimeValue(left.lastAnalysisTime);
        const rightTime = getShanghaiTimeValue(right.lastAnalysisTime);
        return rightTime - leftTime;
      });
  }, [todayDateKey, todayHistoryItems]);

  const handleAnalyzeWatchlist = useCallback(async (mode: WatchlistAnalyzeMode) => {
    if (mode === 'pending' && watchlistTodayStatusBlocked) {
      setBatchAnalyzeStatus({
        variant: 'warning',
        message: t('watchlist.pendingStatusUnavailable'),
      });
      return;
    }

    const sourceCodes = mode === 'pending' ? pendingWatchlistCodes : watchlistState.watchlistCodes;
    const seen = new Set<string>();
    const targetCodes = sourceCodes.filter((code) => {
      const key = getStockCodeKey(code);
      if (!key || seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });

    if (targetCodes.length === 0) {
      setBatchAnalyzeStatus({
        variant: 'warning',
        message: mode === 'pending' ? t('watchlist.noPendingAnalyze') : t('watchlist.noStocksAnalyze'),
      });
      return;
    }

    setIsBatchAnalyzingWatchlist(true);
    setBatchAnalyzeStatus(null);
    let acceptedCount = 0;
    let duplicateCount = 0;
    let confirmedCodeCount = 0;
    let submissionError: ParsedApiError | null = null;
    try {
      for (const chunk of chunkStockCodes(targetCodes)) {
        try {
          const result = await analysisApi.analyzeAsync({
            stockCodes: chunk,
            reportType: 'detailed',
            notify,
            skills: selectedAnalysisSkills,
          });
          const counts = countBatchAccepted(result);
          acceptedCount += counts.accepted;
          duplicateCount += counts.duplicates;
          const confirmedInChunk = counts.accepted + counts.duplicates;
          confirmedCodeCount += Math.min(confirmedInChunk, chunk.length);
          if (confirmedInChunk !== chunk.length) {
            submissionError = getParsedApiError(new Error(t('watchlist.batchIncompleteResponse', {
              confirmed: confirmedInChunk,
              requested: chunk.length,
            })));
            break;
          }
        } catch (error: unknown) {
          if (error instanceof DuplicateTaskError && chunk.length === 1) {
            duplicateCount += 1;
            confirmedCodeCount += 1;
            continue;
          }
          submissionError = getParsedApiError(error);
          break;
        }
      }

      // Reconcile even after a failed request: a timeout or disconnect may occur
      // after the server has accepted tasks, and earlier chunks may be running.
      await refreshActiveTasks();
      setSidebarWorkspaceTab('watchlist');

      if (submissionError) {
        if (acceptedCount > 0 || duplicateCount > 0) {
          setBatchAnalyzeStatus({
            variant: 'warning',
            message: t('watchlist.batchPartiallySubmitted', {
              accepted: acceptedCount,
              duplicates: duplicateCount,
              unconfirmed: targetCodes.length - confirmedCodeCount,
              error: submissionError.message || t('watchlist.batchFailed'),
            }),
          });
        } else {
          setBatchAnalyzeStatus({
            variant: 'danger',
            message: submissionError.message || t('watchlist.batchFailed'),
          });
        }
        return;
      }

      setBatchAnalyzeStatus({
        variant: acceptedCount > 0 ? 'success' : 'warning',
        message: t('watchlist.batchSubmitted', {
          accepted: acceptedCount,
          duplicates: duplicateCount,
        }),
      });
    } catch (error: unknown) {
      const parsed = getParsedApiError(error);
      setBatchAnalyzeStatus({
        variant: 'danger',
        message: parsed.message || t('watchlist.batchFailed'),
      });
    } finally {
      setIsBatchAnalyzingWatchlist(false);
    }
  }, [
    notify,
    pendingWatchlistCodes,
    refreshActiveTasks,
    selectedAnalysisSkills,
    t,
    watchlistTodayStatusBlocked,
    watchlistState.watchlistCodes,
  ]);

  const mergedStockBarItems = useMemo<StockBarItem[]>(() => {
    const latestMarketReview = marketReviewHistoryItems[0];
    const stockItems = stockBarItems.filter((item) => item.stockCode !== 'MARKET');
    if (!latestMarketReview) {
      return stockItems;
    }

    const marketReviewItem: StockBarItem = {
      id: latestMarketReview.id,
      stockCode: 'MARKET',
      stockName: latestMarketReview.stockName || t('home.marketReview'),
      reportType: 'market_review',
      sentimentScore: latestMarketReview.sentimentScore,
      operationAdvice: latestMarketReview.operationAdvice,
      analysisCount: Math.max(marketReviewHistoryItems.length, 1),
      lastAnalysisTime: latestMarketReview.createdAt,
      modelUsed: latestMarketReview.modelUsed,
      marketPhaseSummary: latestMarketReview.marketPhaseSummary,
    };

    return [marketReviewItem, ...stockItems].sort((left, right) => {
      const leftTime = left.lastAnalysisTime ? Date.parse(left.lastAnalysisTime) : 0;
      const rightTime = right.lastAnalysisTime ? Date.parse(right.lastAnalysisTime) : 0;
      return rightTime - leftTime;
    });
  }, [marketReviewHistoryItems, stockBarItems, t]);

  const sidebarContent = useMemo(
    () => (
      <div className="flex min-h-0 h-full flex-col gap-3 overflow-hidden">
        <div className="flex justify-end md:hidden">
          <button
            type="button"
            onClick={closeSidebar}
            className="inline-flex h-11 w-11 items-center justify-center rounded-full text-secondary-text transition-colors hover:bg-hover hover:text-foreground"
            aria-label={t('common.closeDrawer')}
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
        {/* StockPulse keeps its task-dismiss interaction (onDismiss); the home
            watchlist workspace is the upstream feature, adapted to StockPulse
            design and wired to StockPulse's pending/selected record logic. */}
        <TaskPanel tasks={activeTasks} onOpenRunFlow={openTaskRunFlow} onDismiss={removeTask} />
        <HomeStockWorkspace
          activeTab={sidebarWorkspaceTab}
          onTabChange={setSidebarWorkspaceTab}
          watchlistRows={watchlistRows}
          watchlistLoading={watchlistState.isLoading}
          watchlistActioning={watchlistState.isActioning}
          watchlistMessage={watchlistState.actionMessage}
          onAddToWatchlist={watchlistState.addToWatchlist}
          onRemoveFromWatchlist={watchlistState.removeFromWatchlist}
          onRefreshWatchlist={watchlistState.refresh}
          onAnalyzeWatchlist={handleAnalyzeWatchlist}
          isBatchAnalyzing={isBatchAnalyzingWatchlist}
          batchStatus={batchAnalyzeStatus}
          todayItems={todayAnalysisItems}
          isLoadingTodayItems={isLoadingTodayAnalysisItems}
          todayLoadError={todayAnalysisLoadFailed}
          watchlistAnalyzedTodayCount={watchlistAnalyzedTodayCount}
          historyItems={mergedStockBarItems}
          isLoadingHistory={isLoadingStockBar}
          selectedStockCode={selectedReport?.meta.stockCode}
          selectedRecordId={selectedRecordId ?? selectedReport?.meta.id}
          onHistoryItemClick={handleHistoryItemClick}
          onDeleteStock={handleDeleteStock}
          isDeleting={isDeletingStock}
          className="flex-1 overflow-hidden"
        />
      </div>
    ),
    [
      activeTasks,
      batchAnalyzeStatus,
      closeSidebar,
      handleAnalyzeWatchlist,
      handleDeleteStock,
      handleHistoryItemClick,
      isBatchAnalyzingWatchlist,
      isDeletingStock,
      isLoadingStockBar,
      isLoadingTodayAnalysisItems,
      todayAnalysisLoadFailed,
      mergedStockBarItems,
      openTaskRunFlow,
      removeTask,
      selectedRecordId,
      selectedReport?.meta.id,
      selectedReport?.meta.stockCode,
      sidebarWorkspaceTab,
      todayAnalysisItems,
      t,
      watchlistAnalyzedTodayCount,
      watchlistRows,
      watchlistState.actionMessage,
      watchlistState.addToWatchlist,
      watchlistState.isActioning,
      watchlistState.isLoading,
      watchlistState.refresh,
      watchlistState.removeFromWatchlist,
    ],
  );

  return (
    <div
      data-testid="home-dashboard"
      className="flex h-[calc(100dvh-5rem)] w-full flex-col overflow-hidden md:flex-row sm:h-[calc(100dvh-5.5rem)] lg:h-[calc(100dvh-2rem)]"
    >
      <div className="flex-1 flex flex-col min-h-0 min-w-0 max-w-full w-full">
        <header className="relative z-30 flex min-w-0 flex-shrink-0 items-center overflow-visible px-3 py-3 md:px-4 md:py-4">
          <div className="flex min-w-0 flex-1 flex-col gap-2.5 md:flex-row md:items-center">
            <div className="flex min-w-0 flex-1 items-center gap-2.5">
              <button
                type="button"
                onClick={() => setSidebarOpen(true)}
                className="-ml-1 inline-flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full text-secondary-text transition-colors hover:bg-hover hover:text-foreground md:hidden"
                aria-label={t('home.historyButton')}
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
              <div className="relative min-w-0 flex-1">
                <StockAutocomplete
                  value={query}
                  onChange={setQuery}
                  onSubmit={(stockCode, stockName, selectionSource) => {
                    handleSubmitAnalysis(stockCode, stockName, selectionSource);
                  }}
                  placeholder={t('home.placeholder')}
                  disabled={isAnalyzing}
                  className={inputError ? 'border-danger/50' : undefined}
                />
              </div>
              {analysisSkills.length > 0 ? (
                <div ref={strategyMenuRef} className="relative flex-shrink-0">
                  <button
                    ref={strategyButtonRef}
                    id="strategy-menu-button"
                    type="button"
                    aria-haspopup="menu"
                    aria-expanded={strategyMenuOpen}
                    aria-controls={strategyMenuOpen ? 'strategy-menu' : undefined}
                    onClick={() => setStrategyMenuOpen((open) => !open)}
                    onKeyDown={handleStrategyButtonKeyDown}
                    disabled={isAnalyzing}
                    className="home-surface-button flex h-11 max-w-[8.5rem] items-center gap-1.5 rounded-full px-3 text-xs text-foreground disabled:cursor-not-allowed disabled:opacity-60 sm:max-w-[11rem]"
                  >
                    <SlidersHorizontal className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                    <span className="truncate">{selectedStrategyDisplay?.name || t('home.strategy')}</span>
                  </button>
                  {strategyMenuOpen ? (
                    <div
                      id="strategy-menu"
                      role="menu"
                      aria-labelledby="strategy-menu-button"
                      onKeyDown={handleStrategyMenuKeyDown}
                      className="absolute right-0 top-11 z-[120] max-h-80 w-[min(18rem,calc(100vw-1.5rem))] overflow-y-auto rounded-xl border border-subtle bg-elevated p-1.5 text-sm text-foreground shadow-2xl"
                    >
                      {strategyOptions.map((option, index) => {
                        const selected = selectedStrategyId === option.id;
                        return (
                          <button
                            key={option.id || 'default'}
                            ref={(node) => {
                              strategyItemRefs.current[index] = node;
                            }}
                            type="button"
                            role="menuitemradio"
                            aria-checked={selected}
                            tabIndex={-1}
                            onClick={() => selectStrategy(option.id)}
                            className="flex min-h-11 w-full items-start gap-2 rounded-full px-2.5 py-2 text-left transition-colors hover:bg-hover"
                          >
                            <Check className={`mt-0.5 h-4 w-4 flex-shrink-0 ${selected ? 'opacity-100' : 'opacity-0'}`} aria-hidden="true" />
                            <span className="min-w-0">
                              <span className="block font-medium">{option.name}</span>
                              <span className="mt-0.5 line-clamp-2 block text-xs leading-5 text-muted-text">{option.description}</span>
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
            <div className="flex min-w-0 flex-wrap items-center gap-2.5 md:flex-nowrap md:flex-shrink-0">
              <label className="flex h-11 flex-shrink-0 cursor-pointer items-center gap-1.5 rounded-xl border border-subtle bg-surface/60 px-3 text-xs text-secondary-text select-none transition-colors hover:border-subtle-hover hover:text-foreground">
                <input
                  type="checkbox"
                  checked={notify}
                  onChange={(e) => setNotify(e.target.checked)}
                  className="chat-skill-checkbox"
                />
                {t('home.notify')}
              </label>
              <Button
                type="button"
                variant="secondary"
                size="md"
                isLoading={isSubmittingMarketReview}
                loadingText={t('home.submitMarketReview')}
                onClick={() => void handleTriggerMarketReview()}
                className="h-10 min-w-0 flex-1 basis-32 whitespace-nowrap md:flex-none md:basis-auto"
              >
                <BarChart3 className="h-4 w-4" aria-hidden="true" />
                {t('home.marketReview')}
              </Button>
              <button
                type="button"
                onClick={() => handleSubmitAnalysis()}
                disabled={!query || isAnalyzing}
                className="btn-primary flex h-11 min-w-0 flex-1 basis-32 items-center justify-center gap-1.5 whitespace-nowrap md:flex-none md:basis-auto"
              >
                {isAnalyzing ? (
                  <>
                    <svg className="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    {t('home.analyzing')}
                  </>
                ) : (
                  t('home.analyze')
                )}
              </button>
            </div>
          </div>
        </header>

        {inputError || (duplicateError && duplicateBannerVisible) ? (
          <div className="px-3 pb-2 md:px-4">
            {inputError ? (
              <InlineAlert
                variant="danger"
                title={t('home.inputInvalid')}
                message={inputError}
                className="rounded-xl px-3 py-2 text-xs shadow-none"
              />
            ) : null}
            {!inputError && duplicateError && duplicateBannerVisible ? (
              <InlineAlert
                variant="warning"
                title={t('home.duplicateTask')}
                message={duplicateTask
                  ? t('home.duplicateTaskMessage', { stock: duplicateTask.stockCode })
                  : getParsedApiError(duplicateError, uiLanguage).message}
                action={(
                  <button
                    type="button"
                    onClick={dismissDuplicateBanner}
                    aria-label={t('common.close')}
                    className="-my-1 -mr-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-full opacity-70 transition-colors hover:bg-warning/15 hover:opacity-100"
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                  </button>
                )}
                className="rounded-xl px-3 py-2 text-xs shadow-none"
              />
            ) : null}
          </div>
        ) : null}

        {setupNeedsAction ? (
          <div className="px-3 pb-2 md:px-4">
            <InlineAlert
              variant="warning"
              title={t('home.setupIncomplete')}
              message={
                setupMissingLabels
                  ? t('home.setupMissingWithLabels', { labels: setupMissingLabels })
                  : t('home.setupMissingGeneric')
              }
              action={(
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => navigate('/settings')}
                >
                  {t('home.goSettings')}
                </Button>
              )}
              className="rounded-xl px-3 py-2 text-xs shadow-none"
            />
          </div>
        ) : null}

        <div className="flex-1 flex min-h-0 overflow-hidden">
          <div className="hidden min-h-0 w-64 shrink-0 flex-col overflow-hidden pl-4 pb-4 md:flex lg:w-72">
            {sidebarContent}
          </div>

          <Drawer
            isOpen={sidebarOpen}
            onClose={closeSidebar}
            title={t('home.historyButton')}
            width="w-72"
            zIndex={OVERLAY_Z.pageDrawer}
            side="left"
            backdropClassName="page-drawer-overlay"
            panelClassName="dashboard-card !rounded-none !rounded-r-xl p-3 shadow-2xl"
            contentClassName="min-h-0 overflow-hidden !p-0"
            showHeader={false}
          >
            {sidebarContent}
          </Drawer>

          <section
            ref={dashboardScrollRef}
            data-testid="home-dashboard-scroll"
            className="flex-1 min-w-0 min-h-0 overflow-x-auto overflow-y-auto px-3 pb-4 md:px-6 touch-pan-y"
          >
            {marketReviewNotice ? (
              <div className="mb-3">
                <InlineAlert
                  variant={marketReviewNotice.variant}
                  title={marketReviewNotice.title}
                  message={marketReviewNotice.message}
                  className="rounded-xl px-3 py-2 text-xs shadow-none"
                />
              </div>
            ) : null}

            {marketReviewError ? (
              <div className="mb-3">
                <ApiErrorAlert
                  error={marketReviewError}
                  className="mb-1"
                  onDismiss={() => setMarketReviewError(null)}
                />
              </div>
            ) : null}

            {homeUrlState.urlIssue ? (
              <div className="mb-3">
                <InlineAlert
                  variant="warning"
                  title={homeUrlIssueTitle}
                  message={homeUrlIssueMessage}
                  action={(
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={t('common.close')}
                      onClick={homeUrlState.dismissUrlIssue}
                    >
                      <X className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  )}
                />
              </div>
            ) : null}

            {runFlowRestoreError ? (
              <ApiErrorAlert
                error={runFlowRestoreError}
                className="mb-3"
                onDismiss={() => setRunFlowRestoreError(null)}
              />
            ) : null}

            {visibleReportError ? (
              <ApiErrorAlert
                error={visibleReportError}
                className="mb-3"
                actionLabel={isReportLoadFailure ? t('common.retry') : undefined}
                onAction={isReportLoadFailure ? () => void retrySelectedRecord() : undefined}
                onDismiss={clearError}
              />
            ) : null}
            {isLoadingReport ? (
              <div className="flex h-full flex-col items-center justify-center">
                <DashboardStateBlock title={t('home.loadingReport')} loading />
              </div>
            ) : selectedReport ? (
              <div className="space-y-4 pb-8">
                <div className="flex flex-wrap items-center justify-end gap-2">
                  {!isMarketReviewHistoryReport ? (
                    <>
                      <Button
                        variant="home-action-ai"
                        size="sm"
                        disabled={isAnalyzing || selectedReport.meta.id === undefined}
                        onClick={handleReanalyze}
                      >
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                        {t('home.reanalyze')}
                      </Button>
                      <Button
                        variant="home-action-ai"
                        size="sm"
                        disabled={selectedReport.meta.id === undefined}
                        onClick={handleAskFollowUp}
                      >
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                        </svg>
                        {t('home.askAi')}
                      </Button>
                    </>
                  ) : (
                    <Button
                      variant="home-action-ai"
                      size="sm"
                      disabled={isSubmittingMarketReview}
                      isLoading={isSubmittingMarketReview}
                      loadingText={t('home.submitMarketReview')}
                      onClick={() => void handleTriggerMarketReview()}
                    >
                      <BarChart3 className="h-4 w-4" />
                      {t('home.rerunMarketReview')}
                    </Button>
                  )}
                  <Button
                    variant="home-action-ai"
                    size="sm"
                    disabled={selectedReport.meta.id === undefined || isHistoryTrendUnavailable}
                    className={isHistoryTrendOpen ? 'border-primary/70 bg-primary/15 text-primary shadow-soft-card' : undefined}
                    onClick={() => {
                      if (isHistoryTrendOpen) {
                        closeHistoryTrend();
                        return;
                      }
                      void openHistoryTrend();
                    }}
                  >
                    <BarChart3 className="h-4 w-4" />
                    {t('home.historyTrend')}
                  </Button>
                  <Button
                    variant="home-action-ai"
                    size="sm"
                    disabled={selectedReport.meta.id === undefined}
                    onClick={openMarkdownDrawer}
                  >
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    {t('home.fullReport')}
                  </Button>
                </div>
                {isHistoryTrendOpen ? (
                  <StockHistoryTrendDrawer
                    key={`stock-history-${selectedReport.meta.id}`}
                    report={selectedReport}
                    items={stockHistoryItems}
                    total={stockHistoryTotal}
                    hasMore={stockHistoryHasMore}
                    isLoading={isLoadingStockHistory}
                    isLoadingMore={isLoadingMoreStockHistory}
                    error={stockHistoryError}
                    filters={stockHistoryFilters}
                    onClose={closeHistoryTrend}
                    onRangeChange={(range) => void setStockHistoryRange(range)}
                    onLoadMore={() => void loadMoreStockHistory()}
                    onSelectRecord={handleHistoryItemClick}
                    onRetry={() => void openHistoryTrend()}
                  />
                ) : (
                  <ReportSummary
                    data={selectedReport}
                    isHistory
                    onOpenRunFlow={openHistoryRunFlow}
                    watchlist={{
                      isInWatchlist: watchlistState.isInWatchlist,
                      onToggle: watchlistState.toggleWatchlist,
                      isActioning: watchlistState.isActioning,
                      actionMessage: watchlistState.actionMessage,
                    }}
                  />
                )}
              </div>
            ) : hasUnresolvedReportIntent && !reportDetailError ? (
              <div className="flex h-full items-center justify-center">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => void retrySelectedRecord()}
                >
                  {t('common.retry')}
                </Button>
              </div>
            ) : !isReportLoadFailure ? (
              <div className="flex h-full items-center justify-center">
                <EmptyState
                  title={t('home.startAnalysisTitle')}
                  description={t('home.startAnalysisDescription')}
                  className="max-w-xl border-dashed"
                  icon={(
                    <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                  )}
                />
              </div>
            ) : null}
          </section>
        </div>
      </div>

      {markdownDrawerOpen
      && !isLoadingReport
      && selectedReport?.meta.id
      && selectedReport.meta.id === homeUrlState.recordId ? (
        <ReportMarkdownDrawer
          key={selectedReport.meta.id}
          recordId={selectedReport.meta.id}
          stockName={selectedReport.meta.stockName || ''}
          stockCode={selectedReport.meta.stockCode}
          reportLanguage={reportLanguage}
          onClose={closeMarkdownDrawer}
        />
      ) : null}

      {runFlowDrawer.open ? (
        <Drawer
          isOpen={runFlowDrawer.open}
          onClose={closeRunFlowDrawer}
          title={t('runFlow.drawerTitle')}
          width="max-w-[96vw]"
          zIndex={OVERLAY_Z.runFlowDrawer}
        >
          <RunFlowPanel
            key={`${runFlowDrawer.source.type}-${runFlowDrawer.source.type === 'task' ? runFlowDrawer.source.taskId : runFlowDrawer.source.recordId}`}
            source={runFlowDrawer.source}
            title={runFlowDrawer.title}
            onUnavailable={handleUnavailableRunFlow}
          />
        </Drawer>
      ) : null}

    </div>
  );
};

export default HomePage;
