// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BarChart3,
  CheckCircle2,
  FileText,
  FileUp,
  FlaskConical,
  History,
  ListChecks,
  Upload,
  Workflow,
} from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { agentApi, type SkillInfo } from '../api/agent';
import { analysisApi } from '../api/analysis';
import {
  getParsedApiError,
  isPermanentlyUnavailableResourceError,
  type ParsedApiError,
} from '../api/error';
import { historyApi } from '../api/history';
import { stocksApi } from '../api/stocks';
import { systemConfigApi } from '../api/systemConfig';
import {
  ApiErrorAlert,
  AppPage,
  Badge,
  Button,
  Checkbox,
  ConfirmDialog,
  Drawer,
  EmptyState,
  InlineAlert,
  PageHeader,
  SegmentedControl,
  Select,
  Surface,
  TabPanel,
  Tabs,
  WorkspaceLayout,
} from '../components/common';
import { useToast } from '../components/common/toastContext';
import { DashboardStateBlock } from '../components/dashboard';
import { HistoryList, StockHistoryTrendDrawer } from '../components/history';
import { ReportMarkdownDrawer } from '../components/report/ReportMarkdownDrawer';
import { ReportSummary } from '../components/report/ReportSummary';
import { useRouteFocusTarget } from '../components/routing';
import { RunFlowPanel } from '../components/run-flow';
import { StockAutocomplete } from '../components/StockAutocomplete';
import { TaskPanel } from '../components/tasks';
import type { WatchlistAnalyzeMode } from '../components/watchlist/HomeStockWorkspace';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { useAnalysisWorkbenchState } from '../hooks/useAnalysisWorkbenchState';
import { useDashboardLifecycle } from '../hooks/useDashboardLifecycle';
import { useWatchlist } from '../hooks/useWatchlist';
import { useWatchlistAnalysisCoverage } from '../hooks/useWatchlistAnalysisCoverage';
import {
  ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS,
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  APP_ROUTE_PATHS,
  HOME_ROUTE_QUERY_KEYS,
  RUN_FLOW_ROUTE_QUERY_VALUES,
  type AnalysisWorkbenchSegment,
} from '../routing/routes';
import {
  DEFAULT_ANALYSIS_WORKBENCH_ROUTE_STATE,
  parseAnalysisWorkbenchRouteState,
  setAnalysisWorkbenchRouteState,
  type AnalysisWorkbenchRouteState,
} from '../routing/analysisWorkbenchRouteState';
import { useStockPoolStore } from '../stores/stockPoolStore';
import type { TaskInfo } from '../types/analysis';
import type { RunFlowSnapshotSource } from '../types/runFlow';
import { getStrategyDisplay } from '../utils/strategyDisplay';
import { normalizeBatchAnalysisCodes, submitBatchAnalysis } from '../utils/batchAnalysis';
import { normalizeReportLanguage } from '../utils/reportLanguage';
import {
  readExperienceMode,
  writeExperienceMode,
  type ExperienceMode,
} from '../utils/onboardingPreferences';

type RunFlowDialogState =
  | { open: false }
  | { open: true; source: RunFlowSnapshotSource; title: string };

type WorkbenchNotice = {
  variant: 'success' | 'warning' | 'danger';
  message: string;
} | null;

type WorkbenchNavigationState = {
  focusStockSearch?: boolean;
};

const WORKBENCH_TABS_ID = 'analysis-workbench-tabs';
const WORKBENCH_PENDING_REASON_ID = 'analysis-workbench-pending-reason';
function stateForSegment(
  current: AnalysisWorkbenchRouteState,
  segment: AnalysisWorkbenchSegment,
): AnalysisWorkbenchRouteState {
  if (segment === ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch) {
    return { ...DEFAULT_ANALYSIS_WORKBENCH_ROUTE_STATE };
  }
  if (segment === ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks) {
    return {
      segment,
      recordId: null,
      runFlow: current.runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.task ? current.runFlow : null,
      runFlowRecordId: null,
      runFlowTaskId: current.runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.task
        ? current.runFlowTaskId
        : null,
    };
  }
  return {
    segment,
    recordId: current.recordId,
    runFlow: current.runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.history ? current.runFlow : null,
    runFlowRecordId: current.runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.history
      ? current.runFlowRecordId
      : null,
    runFlowTaskId: null,
  };
}

const ResearchAnalysisWorkbenchPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { language, t } = useUiLanguage();
  const { showToast } = useToast();
  const pageHeadingRef = useRef<HTMLHeadingElement>(null);
  useRouteFocusTarget({
    routeId: APP_ROUTE_PATHS.researchAnalysis,
    headingRef: pageHeadingRef,
    ready: true,
  });
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const completedRecordIdsRef = useRef(new Map<string, number>());
  const suppressedHistoryDefaultSearchRef = useRef<string | null>(null);
  const consumedStockContextRef = useRef<string | null>(null);
  const [analysisSkills, setAnalysisSkills] = useState<SkillInfo[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState('');
  const [experiencePreference, setExperiencePreference] = useState<{
    mode: ExperienceMode;
    explicit: boolean;
  }>(() => {
    const storedMode = readExperienceMode();
    return { mode: storedMode ?? 'professional', explicit: storedMode !== null };
  });
  const [setupComplete, setSetupComplete] = useState<boolean | null>(null);
  const [isSetupStatusResolved, setIsSetupStatusResolved] = useState(false);
  const [selectedHistoryIds, setSelectedHistoryIds] = useState<ReadonlySet<number>>(
    () => new Set(),
  );
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const [isDeletingHistory, setIsDeletingHistory] = useState(false);
  const [deleteError, setDeleteError] = useState<ParsedApiError | null>(null);
  const [runFlowError, setRunFlowError] = useState<ParsedApiError | null>(null);
  const [importedCodes, setImportedCodes] = useState<string[]>([]);
  const [isImporting, setIsImporting] = useState(false);
  const [importNotice, setImportNotice] = useState<WorkbenchNotice>(null);
  const [isBatchSubmitting, setIsBatchSubmitting] = useState(false);
  const [batchNotice, setBatchNotice] = useState<WorkbenchNotice>(null);
  const [markdownRecordId, setMarkdownRecordId] = useState<number | null>(null);

  const {
    query,
    inputError,
    duplicateError,
    duplicateTask,
    error,
    reportDetailError,
    isAnalyzing,
    historyItems,
    isLoadingHistory,
    isLoadingMore,
    hasMore,
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
    stockBarItems,
    isLoadingStockBar,
    stockBarRefreshFailed,
    notify,
    setQuery,
    setNotify,
    clearError,
    loadInitialHistory,
    refreshHistory,
    refreshHistoryForCompletedTask,
    loadMoreHistory,
    selectHistoryItem,
    retrySelectedRecord,
    clearSelectedRecord,
    openHistoryTrend,
    closeHistoryTrend,
    setStockHistoryRange,
    loadMoreStockHistory,
    submitAnalysis,
    syncTaskCreated,
    syncTaskUpdated,
    syncTaskFailed,
    refreshActiveTasks,
    pollKnownTasks,
    removeTask,
    loadStockBar,
    refreshStockBar,
  } = useAnalysisWorkbenchState();
  const watchlist = useWatchlist();
  const parsedRoute = useMemo(
    () => parseAnalysisWorkbenchRouteState(location.search),
    [location.search],
  );
  const routeState = parsedRoute.state;
  const canonicalSearch = parsedRoute.normalizedParams.toString();

  const navigateToState = useCallback((
    nextState: AnalysisWorkbenchRouteState,
    replace = false,
  ) => {
    const nextParams = setAnalysisWorkbenchRouteState(location.search, nextState);
    const nextSearch = nextParams.toString();
    navigate(
      {
        pathname: APP_ROUTE_PATHS.researchAnalysis,
        search: nextSearch ? `?${nextSearch}` : '',
        hash: location.hash,
      },
      { replace },
    );
  }, [location.hash, location.search, navigate]);

  const selectSegment = useCallback((segment: AnalysisWorkbenchSegment) => {
    suppressedHistoryDefaultSearchRef.current = null;
    setMarkdownRecordId(null);
    navigateToState(stateForSegment(routeState, segment));
  }, [navigateToState, routeState]);

  const navigateToRecord = useCallback((recordId: number, replace = false) => {
    suppressedHistoryDefaultSearchRef.current = null;
    setMarkdownRecordId(null);
    navigateToState({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      recordId,
      runFlow: null,
      runFlowRecordId: null,
      runFlowTaskId: null,
    }, replace);
  }, [navigateToState]);

  useEffect(() => {
    const expectedSearch = canonicalSearch ? `?${canonicalSearch}` : '';
    if (expectedSearch === location.search) return;
    navigate(
      {
        pathname: APP_ROUTE_PATHS.researchAnalysis,
        search: expectedSearch,
        hash: location.hash,
      },
      { replace: true },
    );
  }, [canonicalSearch, location.hash, location.search, navigate]);

  useEffect(() => {
    document.title = t('analysisWorkbench.documentTitle');
  }, [t]);

  useEffect(() => {
    let active = true;
    void systemConfigApi.getSetupStatus()
      .then((status) => {
        if (active) setSetupComplete(status.isComplete);
      })
      .catch(() => {
        if (active) setSetupComplete(null);
      })
      .finally(() => {
        if (active) setIsSetupStatusResolved(true);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    void agentApi.getSkills()
      .then((response) => {
        if (active) setAnalysisSkills(response.skills);
      })
      .catch(() => {
        if (active) setAnalysisSkills([]);
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

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const stockCode = params.get(HOME_ROUTE_QUERY_KEYS.stock)?.trim() ?? '';
    if (consumedStockContextRef.current === stockCode) return;
    consumedStockContextRef.current = stockCode;
    if (stockCode) setQuery(stockCode);
  }, [location.search, setQuery]);

  useEffect(() => {
    const navigationState = location.state as WorkbenchNavigationState | null;
    if (!navigationState?.focusStockSearch) return;
    document.getElementById('analysis-workbench-stock-search')?.focus();
    navigate(`${location.pathname}${location.search}${location.hash}`, {
      replace: true,
      state: null,
    });
  }, [location.hash, location.pathname, location.search, location.state, navigate]);

  const analysisHistoryItems = useMemo(
    () => historyItems.filter((item) => (
      item.reportType !== 'market_review' && item.stockCode !== 'MARKET'
    )),
    [historyItems],
  );
  const analysisTasks = useMemo(
    () => activeTasks.filter((task) => task.reportType !== 'market_review'),
    [activeTasks],
  );

  useEffect(() => {
    if (
      suppressedHistoryDefaultSearchRef.current !== null
      && routeState.recordId === null
      && suppressedHistoryDefaultSearchRef.current !== location.search
    ) {
      suppressedHistoryDefaultSearchRef.current = null;
    }
    if (
      routeState.segment !== ANALYSIS_WORKBENCH_SEGMENT_VALUES.history
      || isLoadingHistory
      || routeState.recordId !== null
      || analysisHistoryItems.length === 0
      || suppressedHistoryDefaultSearchRef.current === location.search
    ) {
      return;
    }
    navigateToRecord(analysisHistoryItems[0].id, true);
  }, [
    analysisHistoryItems,
    isLoadingHistory,
    location.search,
    navigateToRecord,
    routeState.recordId,
    routeState.segment,
  ]);

  useEffect(() => {
    if (
      routeState.recordId === null
      || selectedRecordId === routeState.recordId
      || suppressedHistoryDefaultSearchRef.current !== null
    ) {
      return;
    }
    void selectHistoryItem(routeState.recordId, true);
  }, [routeState.recordId, selectHistoryItem, selectedRecordId]);

  useEffect(() => {
    if (
      routeState.recordId === null
      || selectedRecordId !== routeState.recordId
      || isLoadingReport
      || !isPermanentlyUnavailableResourceError(reportDetailError)
    ) {
      return;
    }

    const nextState = { ...routeState, recordId: null };
    const nextParams = setAnalysisWorkbenchRouteState(location.search, nextState);
    const nextQuery = nextParams.toString();
    suppressedHistoryDefaultSearchRef.current = nextQuery ? `?${nextQuery}` : '';
    clearSelectedRecord(true);
    navigateToState(nextState, true);
  }, [
    clearSelectedRecord,
    isLoadingReport,
    location.search,
    navigateToState,
    reportDetailError,
    routeState,
    selectedRecordId,
  ]);

  useEffect(() => {
    if (
      routeState.recordId === null
      || selectedReport?.meta.id !== routeState.recordId
      || selectedReport.meta.reportType !== 'market_review'
    ) {
      return;
    }
    const params = new URLSearchParams(location.search);
    params.delete(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment);
    navigate(
      {
        pathname: APP_ROUTE_PATHS.researchMarket,
        search: params.toString() ? `?${params}` : '',
        hash: location.hash,
      },
      { replace: true },
    );
  }, [location.hash, location.search, navigate, routeState.recordId, selectedReport]);

  const refreshCompletedTaskHistory = useCallback(async (task: TaskInfo) => {
    const item = await refreshHistoryForCompletedTask(task);
    if (item) completedRecordIdsRef.current.set(task.taskId, item.id);
    return item;
  }, [refreshHistoryForCompletedTask]);

  const handleCompletedTaskDataRefreshed = useCallback((task: TaskInfo) => {
    if (task.reportType === 'market_review') return;
    const recordId = completedRecordIdsRef.current.get(task.taskId);
    completedRecordIdsRef.current.delete(task.taskId);
    showToast({
      title: t('analysisWorkbench.taskCompletedTitle'),
      message: t('analysisWorkbench.taskCompletedMessage', {
        stock: task.stockName || task.stockCode,
      }),
      tone: 'success',
      action: {
        label: t('analysisWorkbench.viewReport'),
        onClick: () => {
          if (recordId) navigateToRecord(recordId);
          else selectSegment(ANALYSIS_WORKBENCH_SEGMENT_VALUES.history);
        },
      },
    });
  }, [navigateToRecord, selectSegment, showToast, t]);

  const dashboardLifecycle = useDashboardLifecycle({
    loadInitialHistory,
    refreshHistory,
    refreshHistoryForCompletedTask: refreshCompletedTaskHistory,
    refreshActiveTasks,
    pollKnownTasks,
    activeTasks,
    loadStockBar,
    refreshStockBar,
    syncTaskCreated,
    syncTaskUpdated,
    syncTaskFailed,
    removeTask,
    onCompletedTaskDataRefreshed: handleCompletedTaskDataRefreshed,
  });
  const watchlistCoverage = useWatchlistAnalysisCoverage({
    watchlistCodes: watchlist.watchlistCodes,
    stockBarItems,
    isLoadingStockBar,
    isInitialStockBarLoadSettled: dashboardLifecycle.isInitialStockBarLoadSettled,
    stockBarRefreshFailed,
    activeTasks,
  });

  const selectedAnalysisSkills = useMemo(
    () => (selectedStrategyId ? [selectedStrategyId] : undefined),
    [selectedStrategyId],
  );
  const strategyOptions = useMemo(() => [
    {
      value: '',
      label: t('home.defaultStrategyName'),
    },
    ...analysisSkills.map((skill) => ({
      value: skill.id,
      label: getStrategyDisplay(skill, language).name,
    })),
  ], [analysisSkills, language, t]);

  const experienceMode = experiencePreference.explicit
    ? experiencePreference.mode
    : setupComplete === false
      ? 'beginner'
      : 'professional';
  const isExperienceModeReady = experiencePreference.explicit || isSetupStatusResolved;

  const handleExperienceModeChange = useCallback((mode: ExperienceMode) => {
    writeExperienceMode(mode);
    setExperiencePreference({ mode, explicit: true });
  }, []);

  const handleSubmitAnalysis = useCallback(async (
    stockCode?: string,
    stockName?: string,
    selectionSource: 'manual' | 'autocomplete' | 'import' = 'manual',
  ) => {
    if (!isExperienceModeReady) return;
    const stockInput = (stockCode ?? query).trim();
    if (!stockInput) {
      await submitAnalysis({ stockCode: stockInput });
      return;
    }
    const beforeTaskIds = new Set(analysisTasks.map((task) => task.taskId));
    await submitAnalysis({
      stockCode,
      stockName,
      originalQuery: query,
      selectionSource,
      reportType: experienceMode === 'beginner' ? 'brief' : 'detailed',
      skills: selectedAnalysisSkills,
    });
    const latest = useStockPoolStore.getState();
    const taskAccepted = latest.activeTasks.some((task) => (
      task.reportType !== 'market_review' && !beforeTaskIds.has(task.taskId)
    ));
    if (taskAccepted || latest.duplicateTask) {
      selectSegment(ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks);
    }
  }, [analysisTasks, experienceMode, isExperienceModeReady, query, selectSegment, selectedAnalysisSkills, submitAnalysis]);

  const submitBatch = useCallback(async (sourceCodes: readonly string[]) => {
    if (!isExperienceModeReady) return;
    const codes = normalizeBatchAnalysisCodes(sourceCodes);
    if (codes.length === 0) {
      setBatchNotice({ variant: 'warning', message: t('watchlist.noStocksAnalyze') });
      return;
    }

    setIsBatchSubmitting(true);
    setBatchNotice(null);
    try {
      const result = await submitBatchAnalysis({
        codes,
        submitChunk: (stockCodes) => analysisApi.analyzeAsync({
          stockCodes,
          reportType: experienceMode === 'beginner' ? 'brief' : 'detailed',
          notify,
          skills: selectedAnalysisSkills,
        }),
        reconcile: refreshActiveTasks,
        parseError: (error) => getParsedApiError(error, language),
        incompleteResponseMessage: (confirmed, requested) => (
          t('watchlist.batchIncompleteResponse', { confirmed, requested })
        ),
      });
      const submissionError = result.submissionError ?? result.reconciliationError;
      if (submissionError) {
        setBatchNotice(result.accepted > 0 || result.duplicates > 0
          ? {
              variant: 'warning',
              message: t('watchlist.batchPartiallySubmitted', {
                accepted: result.accepted,
                duplicates: result.duplicates,
                unconfirmed: result.unconfirmed,
                error: submissionError.message || t('watchlist.batchFailed'),
              }),
            }
          : {
              variant: 'danger',
              message: submissionError.message || t('watchlist.batchFailed'),
            });
      } else {
        setBatchNotice({
          variant: result.accepted > 0 ? 'success' : 'warning',
          message: t('watchlist.batchSubmitted', {
            accepted: result.accepted,
            duplicates: result.duplicates,
          }),
        });
      }
      if (result.accepted > 0 || result.duplicates > 0) {
        selectSegment(ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks);
      }
    } catch (batchError) {
      setBatchNotice({
        variant: 'danger',
        message: getParsedApiError(batchError, language).message || t('watchlist.batchFailed'),
      });
    } finally {
      setIsBatchSubmitting(false);
    }
  }, [experienceMode, isExperienceModeReady, language, notify, refreshActiveTasks, selectSegment, selectedAnalysisSkills, t]);

  const submitWatchlistBatch = useCallback(async (mode: WatchlistAnalyzeMode) => {
    if (mode === 'pending' && watchlistCoverage.isTodayStatusBlocked) {
      setBatchNotice({
        variant: 'warning',
        message: t('watchlist.pendingStatusUnavailable'),
      });
      return;
    }
    const codes = mode === 'pending'
      ? watchlistCoverage.pendingCodes
      : watchlist.watchlistCodes;
    if (codes.length === 0) {
      setBatchNotice({
        variant: 'warning',
        message: mode === 'pending'
          ? t('watchlist.noPendingAnalyze')
          : t('watchlist.noStocksAnalyze'),
      });
      return;
    }
    await submitBatch(codes);
  }, [submitBatch, t, watchlist.watchlistCodes, watchlistCoverage]);

  const handleImportFile = useCallback(async (file: File) => {
    setImportedCodes([]);
    setIsImporting(true);
    setImportNotice(null);
    try {
      const response = file.type.startsWith('image/')
        ? await stocksApi.extractFromImage(file)
        : await stocksApi.parseImport(file);
      const codes = normalizeBatchAnalysisCodes(response.codes);
      setImportedCodes(codes);
      if (codes.length === 0) {
        setImportNotice({ variant: 'warning', message: t('analysisWorkbench.importEmpty') });
        return;
      }
      setQuery(codes[0]);
      setImportNotice({
        variant: 'success',
        message: t('analysisWorkbench.importReady', { count: codes.length }),
      });
    } catch (importError) {
      setImportedCodes([]);
      setImportNotice({
        variant: 'danger',
        message: getParsedApiError(importError, language).message,
      });
    } finally {
      setIsImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [language, setQuery, t]);

  const toggleHistorySelection = useCallback((recordId: number) => {
    setSelectedHistoryIds((current) => {
      const next = new Set(current);
      if (next.has(recordId)) next.delete(recordId);
      else next.add(recordId);
      return next;
    });
  }, []);

  const toggleAllHistory = useCallback(() => {
    setSelectedHistoryIds((current) => {
      const visibleIds = analysisHistoryItems.map((item) => item.id);
      const allSelected = visibleIds.length > 0 && visibleIds.every((id) => current.has(id));
      if (allSelected) return new Set();
      return new Set(visibleIds);
    });
  }, [analysisHistoryItems]);

  const requestDeleteSelectedHistory = useCallback(() => {
    if (selectedHistoryIds.size === 0 || isDeletingHistory) return;
    setDeleteError(null);
    setIsDeleteConfirmOpen(true);
  }, [isDeletingHistory, selectedHistoryIds.size]);

  const cancelDeleteSelectedHistory = useCallback(() => {
    if (isDeletingHistory) return;
    setIsDeleteConfirmOpen(false);
    setDeleteError(null);
  }, [isDeletingHistory]);

  const deleteSelectedHistory = useCallback(async () => {
    if (selectedHistoryIds.size === 0 || isDeletingHistory) return;
    const recordIds = [...selectedHistoryIds];
    const deletesCurrentRecord = routeState.recordId !== null
      && selectedHistoryIds.has(routeState.recordId);
    setIsDeletingHistory(true);
    setDeleteError(null);
    try {
      await historyApi.deleteRecords(recordIds);
      setSelectedHistoryIds(new Set());
      const emptyHistoryState = {
        ...DEFAULT_ANALYSIS_WORKBENCH_ROUTE_STATE,
        segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      };
      if (deletesCurrentRecord) {
        const nextParams = setAnalysisWorkbenchRouteState(location.search, emptyHistoryState);
        const nextQuery = nextParams.toString();
        suppressedHistoryDefaultSearchRef.current = nextQuery ? `?${nextQuery}` : '';
        clearSelectedRecord();
        navigateToState(emptyHistoryState, true);
      }
      const refreshed = await refreshHistory(false);
      if (deletesCurrentRecord) {
        const nextItem = refreshed?.items.find((item) => (
          item.reportType !== 'market_review' && item.stockCode !== 'MARKET'
        ));
        if (nextItem) navigateToRecord(nextItem.id, true);
      }
      setIsDeleteConfirmOpen(false);
    } catch (historyError) {
      setDeleteError(getParsedApiError(historyError, language));
    } finally {
      setIsDeletingHistory(false);
    }
  }, [
    clearSelectedRecord,
    isDeletingHistory,
    language,
    location.search,
    navigateToState,
    navigateToRecord,
    refreshHistory,
    routeState.recordId,
    selectedHistoryIds,
  ]);

  const openTaskRunFlow = useCallback((task: TaskInfo) => {
    setRunFlowError(null);
    navigateToState({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
      recordId: null,
      runFlow: RUN_FLOW_ROUTE_QUERY_VALUES.task,
      runFlowRecordId: null,
      runFlowTaskId: task.taskId,
    });
  }, [navigateToState]);

  const openHistoryRunFlow = useCallback((recordId: number) => {
    setRunFlowError(null);
    navigateToState({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      recordId,
      runFlow: RUN_FLOW_ROUTE_QUERY_VALUES.history,
      runFlowRecordId: recordId,
      runFlowTaskId: null,
    });
  }, [navigateToState]);

  const closeRunFlow = useCallback(() => {
    navigateToState({
      ...routeState,
      runFlow: null,
      runFlowRecordId: null,
      runFlowTaskId: null,
    }, true);
  }, [navigateToState, routeState]);

  const runFlowDialog = useMemo<RunFlowDialogState>(() => {
    if (routeState.runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.task && routeState.runFlowTaskId) {
      const task = analysisTasks.find((candidate) => candidate.taskId === routeState.runFlowTaskId);
      return {
        open: true,
        source: { type: 'task', taskId: routeState.runFlowTaskId },
        title: t('runFlow.taskDrawerTitle', {
          stock: task?.stockName || task?.stockCode || routeState.runFlowTaskId,
        }),
      };
    }
    if (
      routeState.runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.history
      && routeState.runFlowRecordId !== null
    ) {
      const historyItem = analysisHistoryItems.find(
        (candidate) => candidate.id === routeState.runFlowRecordId,
      );
      return {
        open: true,
        source: { type: 'history', recordId: routeState.runFlowRecordId },
        title: t('runFlow.historyDrawerTitle', {
          stock: historyItem?.stockName
            || historyItem?.stockCode
            || String(routeState.runFlowRecordId),
        }),
      };
    }
    return { open: false };
  }, [analysisHistoryItems, analysisTasks, routeState, t]);

  const handleUnavailableRunFlow = useCallback((nextError: ParsedApiError) => {
    setRunFlowError(nextError);
    closeRunFlow();
  }, [closeRunFlow]);

  const runningTaskCount = analysisTasks.filter((task) => (
    task.status === 'pending'
    || task.status === 'processing'
    || task.status === 'cancel_requested'
  )).length;
  const tabItems = useMemo(() => [
    {
      id: ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch,
      label: t('analysisWorkbench.launch'),
    },
    {
      id: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
      label: (
        <span className="flex items-center gap-2">
          {t('analysisWorkbench.tasks')}
          {runningTaskCount > 0 ? <Badge variant="info">{runningTaskCount}</Badge> : null}
        </span>
      ),
    },
    {
      id: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      label: t('analysisWorkbench.history'),
    },
  ], [runningTaskCount, t]);

  const selectedAnalysisReport = selectedReport?.meta.reportType !== 'market_review'
    && selectedReport?.meta.id === routeState.recordId
    ? selectedReport
    : null;
  const isHistoryTrendUnavailable = !selectedReport?.meta.stockCode;
  useEffect(() => {
    if (
      isHistoryTrendOpen
      && (
        routeState.segment !== ANALYSIS_WORKBENCH_SEGMENT_VALUES.history
        || isHistoryTrendUnavailable
      )
    ) {
      closeHistoryTrend();
    }
  }, [closeHistoryTrend, isHistoryTrendOpen, isHistoryTrendUnavailable, routeState.segment]);
  const hasUnresolvedReportIntent = routeState.recordId !== null
    && selectedRecordId === routeState.recordId
    && selectedAnalysisReport === null
    && !isLoadingReport;
  const visibleError = reportDetailError ?? error;

  return (
    <AppPage data-testid="analysis-workbench-page">
      <PageHeader
        ref={pageHeadingRef}
        title={t('analysisWorkbench.title')}
        description={t('analysisWorkbench.description')}
        actions={(
          <Button
            type="button"
            variant="primary"
            onClick={() => selectSegment(ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch)}
          >
            <FlaskConical className="h-4 w-4" aria-hidden="true" />
            {t('home.analyze')}
          </Button>
        )}
      />

      <Tabs
        id={WORKBENCH_TABS_ID}
        className="mt-5"
        aria-label={t('analysisWorkbench.tabsLabel')}
        value={routeState.segment}
        items={tabItems}
        onValueChange={(value) => {
          if (Object.values(ANALYSIS_WORKBENCH_SEGMENT_VALUES).includes(
            value as AnalysisWorkbenchSegment,
          )) {
            selectSegment(value as AnalysisWorkbenchSegment);
          }
        }}
      />

      <div className="mt-4 space-y-3" aria-live="polite">
        {inputError ? (
          <InlineAlert variant="danger" title={t('home.inputInvalid')} message={inputError} />
        ) : null}
        {duplicateError ? (
          <InlineAlert
            variant="warning"
            title={t('home.duplicateTask')}
            message={duplicateTask
              ? t('home.duplicateTaskMessage', { stock: duplicateTask.stockCode })
              : getParsedApiError(duplicateError, language).message}
          />
        ) : null}
        {visibleError ? <ApiErrorAlert error={visibleError} onDismiss={clearError} /> : null}
        {deleteError && !isDeleteConfirmOpen ? (
          <ApiErrorAlert error={deleteError} onDismiss={() => setDeleteError(null)} />
        ) : null}
        {runFlowError ? <ApiErrorAlert error={runFlowError} onDismiss={() => setRunFlowError(null)} /> : null}
        {batchNotice ? (
          <InlineAlert variant={batchNotice.variant} message={batchNotice.message} />
        ) : null}
      </div>

      <TabPanel
        tabsId={WORKBENCH_TABS_ID}
        value={ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch}
        activeValue={routeState.segment}
      >
        <Surface level="interactive" padding="lg">
          <div className="max-w-4xl space-y-5">
            <div>
              <h2 className="text-lg font-semibold text-foreground">
                {t('analysisWorkbench.launch')}
              </h2>
              <p className="mt-1 text-sm text-secondary-text">
                {t('analysisWorkbench.launchDescription')}
              </p>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <StockAutocomplete
                id="analysis-workbench-stock-search"
                value={query}
                onChange={setQuery}
                onSubmit={(stockCode, stockName, selectionSource) => {
                  void handleSubmitAnalysis(stockCode, stockName, selectionSource);
                }}
                placeholder={t('home.placeholder')}
                disabled={isAnalyzing || !isExperienceModeReady}
                className={inputError ? 'border-danger/50' : undefined}
              />
              <Select
                value={selectedStrategyId}
                onChange={setSelectedStrategyId}
                options={strategyOptions}
                label={t('home.strategy')}
                disabled={isAnalyzing || !isExperienceModeReady}
                className="w-full"
                triggerClassName="w-full"
              />
            </div>

            <div className="flex flex-wrap items-center gap-3">
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
                label={t('home.notify')}
              />
              <Button
                type="button"
                variant="primary"
                disabled={!query || isAnalyzing || !isExperienceModeReady}
                isLoading={isAnalyzing}
                loadingText={t('home.analyzing')}
                onClick={() => void handleSubmitAnalysis()}
              >
                <FlaskConical className="h-4 w-4" aria-hidden="true" />
                {experienceMode === 'beginner' ? t('home.quickAnalyze') : t('home.analyze')}
              </Button>
            </div>

            <div className="border-t border-border pt-5">
              <p className="text-sm text-secondary-text">
                {t('analysisWorkbench.batchDescription')}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  isLoading={isBatchSubmitting}
                  disabled={isBatchSubmitting || watchlist.isLoading || !isExperienceModeReady}
                  onClick={() => void submitWatchlistBatch('all')}
                >
                  <ListChecks className="h-4 w-4" aria-hidden="true" />
                  {t('watchlist.analyzeAll')}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={(
                    isBatchSubmitting
                    || watchlist.isLoading
                    || !isExperienceModeReady
                    || watchlistCoverage.isTodayStatusBlocked
                    || watchlistCoverage.pendingCodes.length === 0
                  )}
                  aria-describedby={watchlistCoverage.isTodayStatusBlocked
                    ? WORKBENCH_PENDING_REASON_ID
                    : undefined}
                  onClick={() => void submitWatchlistBatch('pending')}
                >
                  <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                  {t('watchlist.analyzePending')}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  isLoading={isImporting}
                  loadingText={t('analysisWorkbench.importing')}
                  disabled={isImporting || isBatchSubmitting}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="h-4 w-4" aria-hidden="true" />
                  {t('analysisWorkbench.importAction')}
                </Button>
                {importedCodes.length > 0 ? (
                  <Button
                    type="button"
                    variant="secondary"
                    isLoading={isBatchSubmitting}
                    disabled={isImporting || isBatchSubmitting || !isExperienceModeReady}
                    onClick={() => void submitBatch(importedCodes)}
                  >
                    <FileUp className="h-4 w-4" aria-hidden="true" />
                    {t('analysisWorkbench.analyzeImported', { count: importedCodes.length })}
                  </Button>
                ) : null}
                {watchlistCoverage.isTodayStatusBlocked ? (
                  <p
                    id={WORKBENCH_PENDING_REASON_ID}
                    className="basis-full text-xs text-secondary-text"
                  >
                    {t('watchlist.pendingStatusUnavailable')}
                  </p>
                ) : null}
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept="image/jpeg,image/png,image/webp,image/gif,.csv,.xlsx,.xls,.txt"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void handleImportFile(file);
                  }}
                />
              </div>
              {importNotice ? (
                <InlineAlert
                  className="mt-3"
                  variant={importNotice.variant}
                  message={importNotice.message}
                />
              ) : null}
            </div>
          </div>
        </Surface>
      </TabPanel>

      <TabPanel
        tabsId={WORKBENCH_TABS_ID}
        value={ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks}
        activeValue={routeState.segment}
      >
        {analysisTasks.length > 0 ? (
          <TaskPanel
            tasks={analysisTasks}
            onOpenRunFlow={openTaskRunFlow}
            onDismiss={removeTask}
          />
        ) : (
          <EmptyState
            title={t('analysisWorkbench.tasksEmptyTitle')}
            description={t('analysisWorkbench.tasksEmptyDescription')}
            icon={<Workflow className="h-6 w-6" aria-hidden="true" />}
            action={(
              <Button
                type="button"
                variant="primary"
                onClick={() => selectSegment(ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch)}
              >
                {t('analysisWorkbench.launch')}
              </Button>
            )}
          />
        )}
      </TabPanel>

      <TabPanel
        tabsId={WORKBENCH_TABS_ID}
        value={ANALYSIS_WORKBENCH_SEGMENT_VALUES.history}
        activeValue={routeState.segment}
      >
        {!isLoadingHistory && analysisHistoryItems.length === 0 ? (
          <EmptyState
            title={t('history.defaultEmptyTitle')}
            description={t('history.defaultEmptyDescription')}
            icon={<History className="h-6 w-6" aria-hidden="true" />}
            action={(
              <Button
                type="button"
                variant="primary"
                onClick={() => selectSegment(ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch)}
              >
                {t('analysisWorkbench.launch')}
              </Button>
            )}
          />
        ) : (
          <WorkspaceLayout
            railPosition="start"
            rail={(
              <HistoryList
                className="min-h-96"
                items={analysisHistoryItems}
                isLoading={isLoadingHistory}
                isLoadingMore={isLoadingMore}
                hasMore={hasMore}
                selectedId={routeState.recordId ?? undefined}
                selectedIds={new Set(selectedHistoryIds)}
                isDeleting={isDeletingHistory}
                onItemClick={navigateToRecord}
                onLoadMore={() => void loadMoreHistory()}
                onToggleItemSelection={toggleHistorySelection}
                onToggleSelectAll={toggleAllHistory}
                onDeleteSelected={requestDeleteSelectedHistory}
              />
            )}
          >
            <section className="min-w-0" aria-label={t('analysisWorkbench.history')}>
              {isLoadingReport ? (
                <DashboardStateBlock title={t('home.loadingReport')} loading />
              ) : selectedAnalysisReport ? (
                <>
                  {!isHistoryTrendOpen ? (
                    <div className="mb-3 flex flex-wrap justify-end gap-2">
                      <Button
                        type="button"
                        variant="secondary"
                        disabled={isHistoryTrendUnavailable}
                        onClick={() => void openHistoryTrend()}
                      >
                        <BarChart3 className="h-4 w-4" aria-hidden="true" />
                        {t('home.historyTrend')}
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => setMarkdownRecordId(selectedAnalysisReport.meta.id ?? null)}
                      >
                        <FileText className="h-4 w-4" aria-hidden="true" />
                        {t('home.fullReport')}
                      </Button>
                    </div>
                  ) : null}
                  {isHistoryTrendOpen ? (
                    <StockHistoryTrendDrawer
                      key={`workbench-stock-history-${selectedAnalysisReport.meta.id}`}
                      report={selectedAnalysisReport}
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
                      onSelectRecord={navigateToRecord}
                      onRetry={() => void openHistoryTrend()}
                    />
                  ) : (
                    <ReportSummary
                      data={selectedAnalysisReport}
                      isHistory
                      onOpenRunFlow={openHistoryRunFlow}
                      watchlist={{
                        isInWatchlist: watchlist.isInWatchlist,
                        onToggle: watchlist.toggleWatchlist,
                        isActioning: watchlist.isActioning,
                        actionMessage: watchlist.actionMessage,
                      }}
                    />
                  )}
                </>
              ) : hasUnresolvedReportIntent && !reportDetailError ? (
                <DashboardStateBlock
                  title={t('home.loadingReport')}
                  action={(
                    <Button type="button" variant="secondary" onClick={() => void retrySelectedRecord()}>
                      {t('common.retry')}
                    </Button>
                  )}
                />
              ) : (
                <EmptyState
                  title={t('analysisWorkbench.reportEmptyTitle')}
                  description={t('analysisWorkbench.reportEmptyDescription')}
                  icon={<History className="h-6 w-6" aria-hidden="true" />}
                  action={(
                    <Button
                      type="button"
                      variant="primary"
                      onClick={() => selectSegment(ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch)}
                    >
                      {t('analysisWorkbench.launch')}
                    </Button>
                  )}
                />
              )}
            </section>
          </WorkspaceLayout>
        )}
      </TabPanel>

      <ConfirmDialog
        isOpen={isDeleteConfirmOpen}
        title={t('history.deleteConfirmTitle')}
        message={t('history.deleteConfirmBatch', { count: selectedHistoryIds.size })}
        confirmText={isDeletingHistory ? t('common.deleting') : t('common.delete')}
        confirmDisabled={isDeletingHistory}
        cancelDisabled={isDeletingHistory}
        error={deleteError?.message ?? null}
        isDanger
        onConfirm={() => void deleteSelectedHistory()}
        onCancel={cancelDeleteSelectedHistory}
      />

      {markdownRecordId !== null
      && selectedAnalysisReport?.meta.id === markdownRecordId ? (
        <ReportMarkdownDrawer
          key={markdownRecordId}
          recordId={markdownRecordId}
          stockName={selectedAnalysisReport.meta.stockName || ''}
          stockCode={selectedAnalysisReport.meta.stockCode}
          reportLanguage={normalizeReportLanguage(selectedAnalysisReport.meta.reportLanguage)}
          onClose={() => setMarkdownRecordId(null)}
        />
      ) : null}

      {runFlowDialog.open ? (
        <Drawer
          isOpen
          onClose={closeRunFlow}
          title={t('runFlow.drawerTitle')}
          variant="detail"
          size="wide"
        >
          <RunFlowPanel
            key={`${runFlowDialog.source.type}-${runFlowDialog.source.type === 'task' ? runFlowDialog.source.taskId : runFlowDialog.source.recordId}`}
            source={runFlowDialog.source}
            title={runFlowDialog.title}
            onUnavailable={handleUnavailableRunFlow}
          />
        </Drawer>
      ) : null}
    </AppPage>
  );
};

export default ResearchAnalysisWorkbenchPage;
