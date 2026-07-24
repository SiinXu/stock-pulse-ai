import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BarChart3, Check, Menu, SlidersHorizontal, X } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { analysisApi } from '../api/analysis';
import { historyApi } from '../api/history';
import { agentApi, type SkillInfo } from '../api/agent';
import { systemConfigApi } from '../api/systemConfig';
import { ApiErrorAlert, Button, Checkbox, Drawer, EmptyState, IconButton, InlineAlert, Modal, Popover, SegmentedControl } from '../components/common';
import { DashboardStateBlock } from '../components/dashboard';
import { StockAutocomplete } from '../components/StockAutocomplete';
import { StockHistoryTrendDrawer } from '../components/history';
import { ReportMarkdownDrawer } from '../components/report/ReportMarkdownDrawer';
import BeginnerReportSummary from '../components/report/BeginnerReportSummary';
import { ReportSummary } from '../components/report/ReportSummary';
import { RunFlowPanel } from '../components/run-flow';
import { TaskPanel } from '../components/tasks';
import {
  HomeStockWorkspace,
  type WatchlistAnalyzeMode,
} from '../components/watchlist/HomeStockWorkspace';
import { useDashboardLifecycle, useHomeDashboardState, useHomeUrlState } from '../hooks';
import { useWatchlistAnalysisCoverage } from '../hooks/useWatchlistAnalysisCoverage';
import { useWatchlist } from '../hooks/useWatchlist';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import type { SetupStatusResponse } from '../types/systemConfig';
import { normalizeReportLanguage } from '../utils/reportLanguage';
import type { StockBarItem, TaskInfo } from '../types/analysis';
import type { RunFlowSnapshotSource } from '../types/runFlow';
import {
  getShanghaiDateKey,
  getShanghaiTimeValue,
  getTodayInShanghai,
} from '../utils/format';
import { buildDeepLink } from '../utils/deepLink';
import { normalizeStockCode } from '../utils/stockCode';
import { normalizeBatchAnalysisCodes, submitBatchAnalysis } from '../utils/batchAnalysis';
import { toStockBarItemFromHistoryItem } from '../utils/stockBar';
import { getStrategyDisplay } from '../utils/strategyDisplay';
import { getUiListSeparator } from '../utils/uiLocale';
import {
  dismissOnboarding,
  readExperienceMode,
  readOnboardingDismissed,
  writeExperienceMode,
  type ExperienceMode,
} from '../utils/onboardingPreferences';
import { APP_ROUTE_PATHS, buildSettingsHref, HOME_WORKSPACE_VALUES } from '../routing/routes';

type RunFlowDrawerState =
  | { open: false }
  | { open: true; source: RunFlowSnapshotSource; title: string };

type StockAnalysisNavigationState = {
  stockCode?: string;
  stockName?: string;
  autoAnalyze?: boolean;
  selectionSource?: string;
  focusStockSearch?: boolean;
  focusToken?: number;
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
const TODAY_ANALYSIS_PAGE_SIZE = 100;

type BatchAnalyzeStatus = {
  variant: 'success' | 'warning' | 'danger';
  message: string;
} | null;

function shiftDateKey(dateKey: string, days: number): string {
  const date = new Date(`${dateKey}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function getStockCodeKey(code?: string | null): string {
  const trimmed = (code ?? '').trim();
  return trimmed ? normalizeStockCode(trimmed).toUpperCase() : '';
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
  const [analysisSkills, setAnalysisSkills] = useState<SkillInfo[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState('');
  const [strategyMenuOpen, setStrategyMenuOpen] = useState(false);
  const [runFlowRestoreError, setRunFlowRestoreError] = useState<ParsedApiError | null>(null);
  const [duplicateBannerVisible, setDuplicateBannerVisible] = useState(false);
  const [isBatchAnalyzingWatchlist, setIsBatchAnalyzingWatchlist] = useState(false);
  const [batchAnalyzeStatus, setBatchAnalyzeStatus] = useState<BatchAnalyzeStatus>(null);
  const [todayHistoryItems, setTodayHistoryItems] = useState<StockBarItem[]>([]);
  const [isLoadingTodayAnalysisItems, setIsLoadingTodayAnalysisItems] = useState(false);
  const [todayAnalysisLoadFailed, setTodayAnalysisLoadFailed] = useState(false);
  const [todayAnalysisRefreshVersion, setTodayAnalysisRefreshVersion] = useState(0);
  const duplicateBannerTimer = useRef<number | null>(null);
  const homeUrlOwnerActiveRef = useRef(false);
  const closeSidebar = useCallback(() => setSidebarOpen(false), []);
  const strategyButtonRef = useRef<HTMLButtonElement | null>(null);
  const strategyItemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const strategyInitialFocusIndexRef = useRef<number | null>(null);

  useEffect(() => {
    homeUrlOwnerActiveRef.current = true;
    return () => {
      homeUrlOwnerActiveRef.current = false;
    };
  }, []);
  const [setupStatus, setSetupStatus] = useState<SetupStatusResponse | null>(null);
  const [isSetupStatusResolved, setIsSetupStatusResolved] = useState(false);
  const [experiencePreference, setExperiencePreference] = useState<{
    mode: ExperienceMode;
    explicit: boolean;
  }>(() => {
    const storedMode = readExperienceMode();
    return { mode: storedMode ?? 'professional', explicit: storedMode !== null };
  });
  const [onboardingDismissed, setOnboardingDismissed] = useState(readOnboardingDismissed);

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

  const analysisHistoryItems = useMemo(
    () => historyItems.filter((item) => item.reportType !== 'market_review' && item.stockCode !== 'MARKET'),
    [historyItems],
  );

  const homeUrlState = useHomeUrlState({
    defaultRecordId: analysisHistoryItems[0]?.id ?? null,
    isHistoryLoading: isLoadingHistory,
    selectedRecordId,
    selectedReportId: selectedReport?.meta.id ?? null,
    isReportLoading: isLoadingReport,
    reportError: reportDetailError,
    reportSelectionEpoch,
    selectHistoryItem,
    clearSelectedRecord,
  });
  const sidebarWorkspaceTab = homeUrlState.workspace;
  const setSidebarWorkspaceTab = homeUrlState.setWorkspace;
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
      })
      .finally(() => {
        if (active) {
          setIsSetupStatusResolved(true);
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
    if (selectedStrategyId && !analysisSkills.some((skill) => skill.id === selectedStrategyId)) {
      setSelectedStrategyId('');
    }
  }, [analysisSkills, selectedStrategyId]);

  const reportLanguage = normalizeReportLanguage(selectedReport?.meta.reportLanguage);
  const isMarketReviewHistoryReport = selectedReport?.meta.reportType === 'market_review';
  useEffect(() => {
    if (
      !isMarketReviewHistoryReport
      || homeUrlState.recordId === null
      || selectedReport?.meta.id !== homeUrlState.recordId
    ) {
      return;
    }
    navigate(
      {
        pathname: APP_ROUTE_PATHS.researchMarket,
        search: location.search,
        hash: location.hash,
      },
      { replace: true },
    );
  }, [
    homeUrlState.recordId,
    isMarketReviewHistoryReport,
    location.hash,
    location.search,
    navigate,
    selectedReport?.meta.id,
  ]);
  const isHistoryTrendUnavailable = !selectedReport || !selectedReport.meta.stockCode;
  const homeUrlIssueTitle = homeUrlState.urlIssue === 'invalid_record'
    ? t('home.invalidRecordLinkTitle')
    : homeUrlState.urlIssue === 'invalid_run_flow'
      ? t('home.invalidRunFlowLinkTitle')
      : t('home.invalidDeepLinkTitle');
  const homeUrlIssueMessage = homeUrlState.urlIssue === 'invalid_record'
    ? t('home.invalidRecordLinkMessage')
    : homeUrlState.urlIssue === 'invalid_run_flow'
      ? t('home.invalidRunFlowLinkMessage')
      : t('home.invalidDeepLinkMessage');
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
    return requiredNeedsAction.slice(0, 3).join(getUiListSeparator(uiLanguage));
  }, [setupStatus, uiLanguage]);
  const experienceMode = experiencePreference.explicit
    ? experiencePreference.mode
    : setupStatus && !setupStatus.isComplete
      ? 'beginner'
      : 'professional';
  const isExperienceModeReady = experiencePreference.explicit || isSetupStatusResolved;
  const handleExperienceModeChange = useCallback((mode: ExperienceMode) => {
    if (mode === 'beginner') {
      closeHistoryTrend();
    }
    writeExperienceMode(mode);
    setExperiencePreference({ mode, explicit: true });
  }, [closeHistoryTrend]);
  const handleDismissOnboarding = useCallback(() => {
    dismissOnboarding();
    setOnboardingDismissed(true);
  }, []);

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

  const dashboardLifecycle = useDashboardLifecycle({
    loadInitialHistory,
    refreshHistory,
    refreshHistoryForCompletedTask: refreshCompletedTaskHistory,
    loadStockBar,
    refreshStockBar,
    syncTaskCreated,
    syncTaskUpdated,
    syncTaskFailed,
    refreshActiveTasks,
    pollKnownTasks,
    activeTasks,
    removeTask,
    onDashboardDataRefresh: handleDashboardDataRefresh,
    onCompletedTaskDataRefreshed: handleCompletedTaskDataRefreshed,
  });

  const watchlistState = useWatchlist();
  const watchlistCoverage = useWatchlistAnalysisCoverage({
    watchlistCodes: watchlistState.watchlistCodes,
    stockBarItems,
    isLoadingStockBar,
    isInitialStockBarLoadSettled: dashboardLifecycle.isInitialStockBarLoadSettled,
    stockBarRefreshFailed,
    activeTasks,
  });

  const handleHistoryItemClick = useCallback((recordId: number) => {
    homeUrlState.navigateToRecord(recordId);
    setSidebarOpen(false);
  }, [homeUrlState]);

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
    analysisHistoryItems.forEach(rememberRecord);
    stockHistoryItems.forEach(rememberRecord);
    stockBarItems.forEach(rememberRecord);
    todayHistoryItems.forEach(rememberRecord);

    const matchesDeletedStock = (record: HomeRecordIdentity | null): boolean => Boolean(record)
      && record?.reportType !== 'market_review'
      && getStockCodeKey(record?.stockCode) === deletedStockCode;
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
      ]);
      if (!homeUrlOwnerActiveRef.current) {
        return;
      }
      const nextItem = freshHistory?.items.find((item) => (
        item.reportType !== 'market_review'
        && getStockCodeKey(item.stockCode) !== deletedStockCode
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
    analysisHistoryItems,
    isDeletingStock,
    refreshHistory,
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
      if (!isExperienceModeReady) {
        return;
      }
      void submitAnalysis({
        stockCode,
        stockName,
        originalQuery: query,
        selectionSource: selectionSource ?? 'manual',
        reportType: experienceMode === 'beginner' ? 'brief' : 'detailed',
        skills: selectedAnalysisSkills,
      });
    },
    [experienceMode, isExperienceModeReady, query, selectedAnalysisSkills, submitAnalysis],
  );

  useEffect(() => {
    const state = location.state as StockAnalysisNavigationState | null;
    if (!state?.focusStockSearch) return;
    document.getElementById('home-stock-search')?.focus();
    navigate(`${location.pathname}${location.search}${location.hash}`, {
      replace: true,
      state: null,
    });
  }, [location.hash, location.pathname, location.search, location.state, navigate]);

  useEffect(() => {
    const state = location.state as StockAnalysisNavigationState | null;
    const stockCode = typeof state?.stockCode === 'string' ? state.stockCode.trim() : '';
    if (!stockCode) {
      return;
    }
    if (state?.autoAnalyze && !isExperienceModeReady) {
      return;
    }
    const stockName = typeof state?.stockName === 'string' ? state.stockName.trim() : '';
    setQuery(stockCode);
    navigate(`${location.pathname}${location.search}${location.hash}`, {
      replace: true,
      state: null,
    });
    if (state?.autoAnalyze) {
      handleSubmitAnalysis(stockCode, stockName || undefined, 'import');
    }
  }, [handleSubmitAnalysis, isExperienceModeReady, location.hash, location.pathname, location.search, location.state, navigate, setQuery]);

  useEffect(() => {
    setQuery(homeUrlState.stockCode ?? '');
  }, [homeUrlState.stockCode, setQuery]);

  const handleAskFollowUp = useCallback(() => {
    if (selectedReport?.meta.id === undefined || selectedReport.meta.reportType === 'market_review') {
      return;
    }

    const code = selectedReport.meta.stockCode;
    const name = selectedReport.meta.stockName;
    const rid = selectedReport.meta.id;
    navigate(buildDeepLink({
      page: 'chat',
      stockCode: code,
      stockName: name,
      recordId: rid,
    }));
  }, [navigate, selectedReport]);

  const handleReanalyze = useCallback(() => {
    if (!isExperienceModeReady || !selectedReport || selectedReport.meta.reportType === 'market_review') {
      return;
    }

    void submitAnalysis({
      stockCode: selectedReport.meta.stockCode,
      stockName: selectedReport.meta.stockName,
      originalQuery: selectedReport.meta.stockCode,
      selectionSource: 'manual',
      forceRefresh: true,
      reportType: experienceMode === 'beginner' ? 'brief' : 'detailed',
      skills: selectedAnalysisSkills,
    });
  }, [experienceMode, isExperienceModeReady, selectedAnalysisSkills, selectedReport, submitAnalysis]);

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
    const historyItem = analysisHistoryItems.find((item) => item.id === source.recordId);
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
  }, [activeTasks, analysisHistoryItems, homeUrlState.runFlowSource, selectedReport, t]);

  const todayDateKey = getTodayInShanghai();
  useEffect(() => {
    if (sidebarWorkspaceTab !== HOME_WORKSPACE_VALUES.today) {
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

  const {
    rows: watchlistRows,
    analyzedTodayCount: watchlistAnalyzedTodayCount,
    pendingCodes: pendingWatchlistCodes,
    isTodayStatusBlocked: watchlistTodayStatusBlocked,
  } = watchlistCoverage;

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
    if (!isExperienceModeReady) {
      return;
    }
    if (mode === 'pending' && watchlistTodayStatusBlocked) {
      setBatchAnalyzeStatus({
        variant: 'warning',
        message: t('watchlist.pendingStatusUnavailable'),
      });
      return;
    }

    const sourceCodes = mode === 'pending' ? pendingWatchlistCodes : watchlistState.watchlistCodes;
    const targetCodes = normalizeBatchAnalysisCodes(sourceCodes);

    if (targetCodes.length === 0) {
      setBatchAnalyzeStatus({
        variant: 'warning',
        message: mode === 'pending' ? t('watchlist.noPendingAnalyze') : t('watchlist.noStocksAnalyze'),
      });
      return;
    }

    setIsBatchAnalyzingWatchlist(true);
    setBatchAnalyzeStatus(null);
    try {
      const result = await submitBatchAnalysis({
        codes: targetCodes,
        submitChunk: (stockCodes) => analysisApi.analyzeAsync({
          stockCodes,
          reportType: experienceMode === 'beginner' ? 'brief' : 'detailed',
          notify,
          skills: selectedAnalysisSkills,
        }),
        reconcile: refreshActiveTasks,
        parseError: getParsedApiError,
        incompleteResponseMessage: (confirmed, requested) => (
          t('watchlist.batchIncompleteResponse', { confirmed, requested })
        ),
      });
      setSidebarWorkspaceTab(HOME_WORKSPACE_VALUES.watchlist);

      const submissionError = result.submissionError ?? result.reconciliationError;
      if (submissionError) {
        if (result.accepted > 0 || result.duplicates > 0) {
          setBatchAnalyzeStatus({
            variant: 'warning',
            message: t('watchlist.batchPartiallySubmitted', {
              accepted: result.accepted,
              duplicates: result.duplicates,
              unconfirmed: result.unconfirmed,
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
        variant: result.accepted > 0 ? 'success' : 'warning',
        message: t('watchlist.batchSubmitted', {
          accepted: result.accepted,
          duplicates: result.duplicates,
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
    experienceMode,
    isExperienceModeReady,
    notify,
    pendingWatchlistCodes,
    refreshActiveTasks,
    selectedAnalysisSkills,
    setSidebarWorkspaceTab,
    t,
    watchlistTodayStatusBlocked,
    watchlistState.watchlistCodes,
  ]);

  const homeStockBarItems = useMemo<StockBarItem[]>(
    () => stockBarItems.filter((item) => (
      item.stockCode !== 'MARKET' && item.reportType !== 'market_review'
    )),
    [stockBarItems],
  );

  const sidebarContent = useMemo(
    () => (
      <div className="flex min-h-0 h-full flex-col gap-3 overflow-hidden">
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
          watchlistLoadError={Boolean(watchlistState.loadError)}
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
          historyItems={homeStockBarItems}
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
      handleAnalyzeWatchlist,
      handleDeleteStock,
      handleHistoryItemClick,
      isBatchAnalyzingWatchlist,
      isDeletingStock,
      isLoadingStockBar,
      isLoadingTodayAnalysisItems,
      todayAnalysisLoadFailed,
      homeStockBarItems,
      openTaskRunFlow,
      removeTask,
      selectedRecordId,
      selectedReport?.meta.id,
      selectedReport?.meta.stockCode,
      setSidebarWorkspaceTab,
      sidebarWorkspaceTab,
      todayAnalysisItems,
      watchlistAnalyzedTodayCount,
      watchlistRows,
      watchlistState.actionMessage,
      watchlistState.addToWatchlist,
      watchlistState.isActioning,
      watchlistState.isLoading,
      watchlistState.loadError,
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
              <IconButton
                variant="ghost"
                size="comfortable"
                className="-ml-1 md:hidden"
                aria-label={t('home.historyButton')}
                onClick={() => setSidebarOpen(true)}
              >
                <Menu aria-hidden="true" />
              </IconButton>
              <div className="relative min-w-0 flex-1">
                <StockAutocomplete
                  id="home-stock-search"
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
                <Popover
                  open={strategyMenuOpen}
                  onOpenChange={setStrategyMenuOpen}
                  rootClassName="flex-shrink-0"
                  contentRole="menu"
                  contentId="strategy-menu"
                  ariaLabelledBy="strategy-menu-button"
                  closeOnEscape={false}
                  onContentKeyDown={handleStrategyMenuKeyDown}
                  placement="bottom"
                  align="end"
                  contentClassName="max-h-80 w-[min(18rem,calc(100vw-1.5rem))] overflow-y-auto border-subtle p-1.5 text-sm text-foreground shadow-2xl"
                  trigger={({ open, toggle }) => (
                    <button
                      ref={strategyButtonRef}
                      id="strategy-menu-button"
                      type="button"
                      aria-haspopup="menu"
                      aria-expanded={open}
                      aria-controls={open ? 'strategy-menu' : undefined}
                      onClick={toggle}
                      onKeyDown={handleStrategyButtonKeyDown}
                      disabled={isAnalyzing}
                      className="home-surface-button flex h-9 max-w-[8.5rem] items-center gap-1.5 rounded-lg px-2 text-xs text-foreground disabled:cursor-not-allowed disabled:opacity-60 sm:max-w-[11rem]"
                    >
                      <SlidersHorizontal className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                      <span className="truncate">{selectedStrategyDisplay?.name || t('home.strategy')}</span>
                    </button>
                  )}
                >
                  <>
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
                            className="flex min-h-11 w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-hover"
                          >
                            <Check className={`mt-0.5 h-4 w-4 flex-shrink-0 ${selected ? 'opacity-100' : 'opacity-0'}`} aria-hidden="true" />
                            <span className="min-w-0">
                              <span className="block font-medium">{option.name}</span>
                              <span className="mt-0.5 line-clamp-2 block text-xs leading-5 text-muted-text">{option.description}</span>
                            </span>
                          </button>
                        );
                      })}
                  </>
                </Popover>
              ) : null}
            </div>
            <div className="flex min-w-0 flex-wrap items-center gap-2 md:flex-nowrap md:flex-shrink-0">
              <SegmentedControl
                value={experienceMode}
                onChange={handleExperienceModeChange}
                ariaLabel={t('home.experienceModeLabel')}
                options={[
                  { value: 'beginner', label: t('home.beginnerMode') },
                  { value: 'professional', label: t('home.professionalMode') },
                ]}
              />
              <Checkbox
                checked={notify}
                onChange={(event) => setNotify(event.target.checked)}
                containerClassName="h-9 flex-shrink-0 gap-1.5 rounded-lg border border-subtle bg-subtle px-2 text-xs text-secondary-text transition-colors hover:border-subtle-hover hover:text-foreground"
                label={<span className="text-xs font-normal text-secondary-text">{t('home.notify')}</span>}
              />
              <div className="grid flex-1 basis-32 md:flex-none md:basis-auto">
                <Button
                  variant="primary"
                  size="comfortable"
                  className="whitespace-nowrap"
                  disabled={!query || isAnalyzing || !isExperienceModeReady}
                  isLoading={isAnalyzing}
                  loadingText={t('home.analyzing')}
                  onClick={() => handleSubmitAnalysis()}
                >
                  {experienceMode === 'beginner' ? t('home.quickAnalyze') : t('home.analyze')}
                </Button>
              </div>
            </div>
          </div>
        </header>

        {inputError || (duplicateError && duplicateBannerVisible) ? (
          <div className="px-3 pb-2 md:px-4">
            {inputError ? (
              <InlineAlert
                variant="danger"
                size="compact"
                title={t('home.inputInvalid')}
                message={inputError}
              />
            ) : null}
            {!inputError && duplicateError && duplicateBannerVisible ? (
              <InlineAlert
                variant="warning"
                size="compact"
                title={t('home.duplicateTask')}
                message={duplicateTask
                  ? t('home.duplicateTaskMessage', { stock: duplicateTask.stockCode })
                  : getParsedApiError(duplicateError, uiLanguage).message}
                action={(
                  <IconButton
                    variant="ghost"
                    size="compact"
                    aria-label={t('common.close')}
                    onClick={dismissDuplicateBanner}
                  >
                    <X aria-hidden="true" />
                  </IconButton>
                )}
              />
            ) : null}
          </div>
        ) : null}

        {setupNeedsAction && !onboardingDismissed ? (
          <div className="px-3 pb-2 md:px-4">
            <InlineAlert
              variant="warning"
              size="compact"
              title={t('home.setupIncomplete')}
              message={
                setupMissingLabels
                  ? t('home.setupMissingWithLabels', { labels: setupMissingLabels })
                  : t('home.setupMissingGeneric')
              }
              action={(
                <div className="flex items-center gap-1">
                  <Button
                    type="button"
                    variant="secondary"
                    size="default"
                    onClick={() => navigate(buildSettingsHref({
                      section: 'overview',
                      view: 'readiness',
                      source: 'onboarding',
                    }))}
                  >
                    {t('home.startGuidedSetup')}
                  </Button>
                  <IconButton
                    type="button"
                    variant="ghost"
                    size="default"
                    aria-label={t('common.close')}
                    onClick={handleDismissOnboarding}
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                  </IconButton>
                </div>
              )}
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
            variant="navigation"
          >
            {sidebarContent}
          </Drawer>

          <section
            data-testid="home-dashboard-scroll"
            className="flex-1 min-w-0 min-h-0 overflow-x-auto overflow-y-auto px-3 pb-4 md:px-6 touch-pan-y"
          >
            {homeUrlState.urlIssue ? (
              <div className="mb-3">
                <InlineAlert
                  variant="warning"
                  title={homeUrlIssueTitle}
                  message={homeUrlIssueMessage}
                  action={(
                    <IconButton
                      type="button"
                      variant="ghost"
                      size="default"
                      aria-label={t('common.close')}
                      onClick={homeUrlState.dismissUrlIssue}
                    >
                      <X className="h-4 w-4" aria-hidden="true" />
                    </IconButton>
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
            ) : selectedReport && !isMarketReviewHistoryReport ? (
              <div className="space-y-4 pb-8">
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <Button
                    variant="secondary"
                    size="default"
                    disabled={isAnalyzing || !isExperienceModeReady || selectedReport.meta.id === undefined}
                    onClick={handleReanalyze}
                  >
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    {t('home.reanalyze')}
                  </Button>
                  <Button
                    variant="secondary"
                    size="default"
                    disabled={selectedReport.meta.id === undefined}
                    onClick={handleAskFollowUp}
                  >
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                    {t('home.askAi')}
                  </Button>
                  {experienceMode === 'professional' ? (
                    <>
                      <Button
                        variant="secondary"
                        size="default"
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
                        variant="secondary"
                        size="default"
                        disabled={selectedReport.meta.id === undefined}
                        onClick={openMarkdownDrawer}
                      >
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                        {t('home.fullReport')}
                      </Button>
                    </>
                  ) : null}
                </div>
                <InlineAlert variant="info" size="compact" message={t('home.researchDisclaimer')} />
                {experienceMode === 'professional' && isHistoryTrendOpen ? (
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
                ) : experienceMode === 'beginner' ? (
                  <BeginnerReportSummary
                    data={selectedReport}
                    onShowProfessional={() => handleExperienceModeChange('professional')}
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
                  className="max-w-xl"
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
      && !isMarketReviewHistoryReport
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

      {runFlowDrawer.open && !isMarketReviewHistoryReport ? (
        <Modal
          isOpen={runFlowDrawer.open}
          onClose={closeRunFlowDrawer}
          title={t('runFlow.drawerTitle')}
          size="fullscreen"
        >
          <RunFlowPanel
            key={`${runFlowDrawer.source.type}-${runFlowDrawer.source.type === 'task' ? runFlowDrawer.source.taskId : runFlowDrawer.source.recordId}`}
            source={runFlowDrawer.source}
            title={runFlowDrawer.title}
            onUnavailable={handleUnavailableRunFlow}
          />
        </Modal>
      ) : null}

    </div>
  );
};

export default HomePage;
