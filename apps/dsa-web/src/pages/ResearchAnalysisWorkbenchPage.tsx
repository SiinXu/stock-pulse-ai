// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BarChart3,
  FileText,
  FlaskConical,
  History,
  MessageCircle,
  RefreshCw,
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
  AppPage,
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  Modal,
  PageHeader,
  SegmentedControl,
  TabPanel,
  WorkspaceLayout,
  getTabPanelId,
} from '../components/common';
import { AnalysisPhaseSelect } from '../components/analysis';
import type { WorkbenchBatchNotice } from '../components/analysis/AnalysisWorkbenchErrorStack';
import { useToast } from '../components/common/toastContext';
import { DashboardStateBlock } from '../components/dashboard';
import { HistoryList, StockHistoryTrendDrawer } from '../components/history';
import { ReportMarkdownDrawer } from '../components/report/ReportMarkdownDrawer';
import { ReportSummary } from '../components/report/ReportSummary';
import { useRouteFocusTarget } from '../components/routing';
import { RunFlowPanel } from '../components/run-flow';
import { TaskPanel } from '../components/tasks';
import type { WatchlistAnalyzeMode } from '../components/watchlist/HomeStockWorkspace';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { useAnalysisWorkbenchErrorContract } from '../hooks/useAnalysisWorkbenchErrorContract';
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
import { useStockPoolStore, type SubmitAnalysisOptions } from '../stores/stockPoolStore';
import type { AnalysisPhase, StockReportType, TaskInfo } from '../types/analysis';
import type { RunFlowSnapshotSource } from '../types/runFlow';
import { normalizeBatchAnalysisCodes, submitBatchAnalysis } from '../utils/batchAnalysis';
import { buildDeepLink } from '../utils/deepLink';
import { normalizeReportLanguage } from '../utils/reportLanguage';
import { getStrategyDisplay } from '../utils/strategyDisplay';
import {
  readExperienceMode,
  writeExperienceMode,
  type ExperienceMode,
} from '../utils/onboardingPreferences';

type RunFlowDialogState =
  | { open: false }
  | { open: true; source: RunFlowSnapshotSource; title: string };

type WorkbenchNotice = WorkbenchBatchNotice;

type WorkbenchNavigationState = {
  focusStockSearch?: boolean;
};

type BatchLaunchIntent = {
  codes: readonly string[];
  reportType: StockReportType;
  notify: boolean;
  analysisPhase: AnalysisPhase;
  skills?: readonly string[];
};

const WORKBENCH_TABS_ID = 'analysis-workbench-tabs';
const AnalysisWorkbenchErrorStack = lazy(
  () => import('../components/analysis/AnalysisWorkbenchErrorStack'),
);
const AnalysisWorkbenchLaunchPanel = lazy(
  () => import('../components/analysis/AnalysisWorkbenchLaunchPanel'),
);
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
  const isMountedRef = useRef(false);
  useRouteFocusTarget({
    routeId: APP_ROUTE_PATHS.researchAnalysis,
    headingRef: pageHeadingRef,
    ready: true,
  });
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const completedRecordIdsRef = useRef(new Map<string, number>());
  const suppressedHistoryDefaultSearchRef = useRef<string | null>(null);
  const consumedStockContextRef = useRef<string | null>(null);
  const lastAnalysisIntentRef = useRef<SubmitAnalysisOptions | null>(null);
  const lastBatchIntentRef = useRef<BatchLaunchIntent | null>(null);
  const failedRunFlowSourceRef = useRef<RunFlowSnapshotSource | null>(null);
  const [analysisSkills, setAnalysisSkills] = useState<SkillInfo[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState('');
  const [analysisPhase, setAnalysisPhase] = useState<AnalysisPhase>('auto');
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

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

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

  const executeAnalysisIntent = useCallback(
    async (intent: SubmitAnalysisOptions) => {
      const beforeTaskIds = new Set(analysisTasks.map((task) => task.taskId));
      lastAnalysisIntentRef.current = {
        ...intent,
        skills: intent.skills ? [...intent.skills] : undefined,
      };
      await submitAnalysis(lastAnalysisIntentRef.current);
      if (!isMountedRef.current) return;
      const latest = useStockPoolStore.getState();
      const taskAccepted = latest.activeTasks.some(
        (task) => task.reportType !== 'market_review' && !beforeTaskIds.has(task.taskId),
      );
      if (taskAccepted || latest.duplicateTask) {
        lastAnalysisIntentRef.current = null;
        selectSegment(ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks);
      } else if (!latest.error) {
        lastAnalysisIntentRef.current = null;
      }
    },
    [analysisTasks, selectSegment, submitAnalysis],
  );
  const handleSubmitAnalysis = useCallback(
    async (
      stockCode?: string,
      stockName?: string,
      selectionSource: 'manual' | 'autocomplete' | 'import' = 'manual',
    ) => {
      if (!isExperienceModeReady) return;
      const stockInput = (stockCode ?? query).trim();
      if (!stockInput) {
        lastAnalysisIntentRef.current = null;
        await submitAnalysis({ stockCode: stockInput });
        return;
      }
      await executeAnalysisIntent({
        stockCode: stockInput,
        stockName,
        originalQuery: query,
        selectionSource,
        notify,
        reportType: experienceMode === 'beginner' ? 'brief' : 'detailed',
        analysisPhase,
        skills: selectedAnalysisSkills,
      });
    },
    [
      analysisPhase,
      executeAnalysisIntent,
      experienceMode,
      isExperienceModeReady,
      notify,
      query,
      selectedAnalysisSkills,
      submitAnalysis,
    ],
  );
  const retryAnalysis = useCallback(() => {
    const intent = lastAnalysisIntentRef.current;
    if (!intent || useStockPoolStore.getState().isAnalyzing) return;
    void executeAnalysisIntent(intent);
  }, [executeAnalysisIntent]);
  const executeBatchIntent = useCallback(
    async (intent: BatchLaunchIntent) => {
      const codes = normalizeBatchAnalysisCodes(intent.codes);
      lastBatchIntentRef.current = { ...intent, codes };
      setIsBatchSubmitting(true);
      setBatchNotice(null);
      try {
        const result = await submitBatchAnalysis({
          codes,
          submitChunk: (stockCodes) =>
            analysisApi.analyzeAsync({
              stockCodes,
              reportType: intent.reportType,
              notify: intent.notify,
              analysisPhase: intent.analysisPhase,
              skills: intent.skills ? [...intent.skills] : undefined,
            }),
          reconcile: refreshActiveTasks,
          parseError: (error) => getParsedApiError(error, language),
          incompleteResponseMessage: (confirmed, requested) =>
            t('watchlist.batchIncompleteResponse', { confirmed, requested }),
        });
        const submissionError = result.submissionError ?? result.reconciliationError;
        const confirmedCodes = [...result.acceptedCodes, ...result.duplicateCodes];
        if (submissionError) {
          // The async endpoint deduplicates active symbols. Retain only
          // unconfirmed identities so recovery never replays accepted work.
          lastBatchIntentRef.current =
            result.unconfirmedCodes.length > 0
              ? { ...intent, codes: result.unconfirmedCodes }
              : null;
          setBatchNotice(
            result.accepted > 0 || result.duplicates > 0
              ? {
                  variant: 'warning',
                  message: t('watchlist.batchPartiallySubmitted', {
                    accepted: result.accepted,
                    duplicates: result.duplicates,
                    unconfirmed: result.unconfirmed,
                    error: submissionError.message || t('watchlist.batchFailed'),
                  }),
                  error: submissionError,
                  confirmedCodes,
                  unconfirmedCodes: result.unconfirmedCodes,
                  canRetryUnconfirmed: result.stoppedOnIncompleteResponse,
                }
              : {
                  variant: 'danger',
                  message: submissionError.message || t('watchlist.batchFailed'),
                  error: submissionError,
                  confirmedCodes,
                  unconfirmedCodes: result.unconfirmedCodes,
                  canRetryUnconfirmed: result.stoppedOnIncompleteResponse,
                },
          );
        } else {
          lastBatchIntentRef.current = null;
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
        const parsed = getParsedApiError(batchError, language);
        setBatchNotice({
          variant: 'danger',
          message: parsed.message || t('watchlist.batchFailed'),
          error: parsed,
          confirmedCodes: [],
          unconfirmedCodes: codes,
        });
      } finally {
        setIsBatchSubmitting(false);
      }
    },
    [language, refreshActiveTasks, selectSegment, t],
  );
  const submitBatch = useCallback(
    async (sourceCodes: readonly string[]) => {
      if (!isExperienceModeReady) return;
      const codes = normalizeBatchAnalysisCodes(sourceCodes);
      if (codes.length === 0) {
        lastBatchIntentRef.current = null;
        setBatchNotice({
          variant: 'warning',
          message: t('watchlist.noStocksAnalyze'),
        });
        return;
      }
      await executeBatchIntent({
        codes,
        reportType: experienceMode === 'beginner' ? 'brief' : 'detailed',
        notify,
        analysisPhase,
        skills: selectedAnalysisSkills,
      });
    },
    [
      analysisPhase,
      executeBatchIntent,
      experienceMode,
      isExperienceModeReady,
      notify,
      selectedAnalysisSkills,
      t,
    ],
  );
  const retryBatch = useCallback(() => {
    const intent = lastBatchIntentRef.current;
    if (!intent || isBatchSubmitting) return;
    void executeBatchIntent(intent);
  }, [executeBatchIntent, isBatchSubmitting]);
  const submitWatchlistBatch = useCallback(
    async (mode: WatchlistAnalyzeMode) => {
      if (mode === 'pending' && watchlistCoverage.isTodayStatusBlocked) {
        setBatchNotice({
          variant: 'warning',
          message: t('watchlist.pendingStatusUnavailable'),
        });
        return;
      }
      const codes = mode === 'pending' ? watchlistCoverage.pendingCodes : watchlist.watchlistCodes;
      if (codes.length === 0) {
        setBatchNotice({
          variant: 'warning',
          message:
            mode === 'pending' ? t('watchlist.noPendingAnalyze') : t('watchlist.noStocksAnalyze'),
        });
        return;
      }
      await submitBatch(codes);
    },
    [submitBatch, t, watchlist.watchlistCodes, watchlistCoverage],
  );
  const handleImportFile = useCallback(
    async (file: File) => {
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
          setImportNotice({
            variant: 'warning',
            message: t('analysisWorkbench.importEmpty'),
          });
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
    },
    [language, setQuery, t],
  );
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
    const deletesCurrentRecord =
      routeState.recordId !== null && selectedHistoryIds.has(routeState.recordId);
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
        const nextItem = refreshed?.items.find(
          (item) => item.reportType !== 'market_review' && item.stockCode !== 'MARKET',
        );
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
  const openRunFlowSource = useCallback(
    (source: RunFlowSnapshotSource) => {
      setRunFlowError(null);
      failedRunFlowSourceRef.current = null;
      if (source.type === 'task') {
        navigateToState({
          segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
          recordId: null,
          runFlow: RUN_FLOW_ROUTE_QUERY_VALUES.task,
          runFlowRecordId: null,
          runFlowTaskId: source.taskId,
        });
      } else {
        navigateToState({
          segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
          recordId: source.recordId,
          runFlow: RUN_FLOW_ROUTE_QUERY_VALUES.history,
          runFlowRecordId: source.recordId,
          runFlowTaskId: null,
        });
      }
    },
    [navigateToState],
  );
  const openTaskRunFlow = useCallback(
    (task: TaskInfo) => {
      openRunFlowSource({ type: 'task', taskId: task.taskId });
    },
    [openRunFlowSource],
  );
  const openHistoryRunFlow = useCallback(
    (recordId: number) => {
      openRunFlowSource({ type: 'history', recordId });
    },
    [openRunFlowSource],
  );
  const closeRunFlow = useCallback(() => {
    navigateToState(
      {
        ...routeState,
        runFlow: null,
        runFlowRecordId: null,
        runFlowTaskId: null,
      },
      true,
    );
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
      routeState.runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.history &&
      routeState.runFlowRecordId !== null
    ) {
      const historyItem = analysisHistoryItems.find(
        (candidate) => candidate.id === routeState.runFlowRecordId,
      );
      return {
        open: true,
        source: { type: 'history', recordId: routeState.runFlowRecordId },
        title: t('runFlow.historyDrawerTitle', {
          stock:
            historyItem?.stockName || historyItem?.stockCode || String(routeState.runFlowRecordId),
        }),
      };
    }
    return { open: false };
  }, [analysisHistoryItems, analysisTasks, routeState, t]);
  const handleUnavailableRunFlow = useCallback(
    (nextError: ParsedApiError) => {
      if (runFlowDialog.open) {
        failedRunFlowSourceRef.current = runFlowDialog.source;
      }
      setRunFlowError(nextError);
      closeRunFlow();
    },
    [closeRunFlow, runFlowDialog],
  );
  const retryRunFlow = useCallback(() => {
    const source = failedRunFlowSourceRef.current;
    if (!source) return;
    openRunFlowSource(source);
  }, [openRunFlowSource]);
  const runningTaskCount = analysisTasks.filter(
    (task) =>
      task.status === 'pending' ||
      task.status === 'processing' ||
      task.status === 'cancel_requested',
  ).length;
  const tabItems = useMemo(
    () => [
      {
        id: ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch,
        label: t('analysisWorkbench.launch'),
      },
      {
        id: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
        label: (
          <span className="flex items-center gap-2">
            {t('analysisWorkbench.tasks')}
            {runningTaskCount > 0 ? (
              <Badge
                variant="info"
                className="h-4 min-w-4 justify-center px-1 py-0 text-xxs leading-none"
              >
                {runningTaskCount}
              </Badge>
            ) : null}
          </span>
        ),
      },
      {
        id: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
        label: t('analysisWorkbench.history'),
      },
    ],
    [runningTaskCount, t],
  );
  const selectedAnalysisReport =
    selectedReport?.meta.reportType !== 'market_review' &&
    selectedReport?.meta.id === routeState.recordId
      ? selectedReport
      : null;
  const handleReanalyze = useCallback(async () => {
    if (!selectedAnalysisReport || selectedAnalysisReport.meta.reportType === 'market_review')
      return;
    await executeAnalysisIntent({
      stockCode: selectedAnalysisReport.meta.stockCode,
      stockName: selectedAnalysisReport.meta.stockName,
      originalQuery: selectedAnalysisReport.meta.stockCode,
      selectionSource: 'manual',
      notify,
      forceRefresh: true,
      reportType: selectedAnalysisReport.meta.reportType,
      analysisPhase,
      skills: selectedAnalysisSkills,
    });
  }, [
    analysisPhase,
    executeAnalysisIntent,
    notify,
    selectedAnalysisReport,
    selectedAnalysisSkills,
  ]);
  const handleAskFollowUp = useCallback(() => {
    const recordId = selectedAnalysisReport?.meta.id;
    const stockCode = selectedAnalysisReport?.meta.stockCode;
    if (recordId === undefined || !stockCode) return;
    navigate(
      buildDeepLink({
        page: 'chat',
        stockCode,
        stockName: selectedAnalysisReport.meta.stockName || undefined,
        recordId,
      }),
    );
  }, [navigate, selectedAnalysisReport]);
  const isHistoryTrendUnavailable = !selectedReport?.meta.stockCode;
  useEffect(() => {
    if (
      isHistoryTrendOpen &&
      (routeState.segment !== ANALYSIS_WORKBENCH_SEGMENT_VALUES.history ||
        isHistoryTrendUnavailable)
    ) {
      closeHistoryTrend();
    }
  }, [closeHistoryTrend, isHistoryTrendOpen, isHistoryTrendUnavailable, routeState.segment]);
  const hasUnresolvedReportIntent =
    routeState.recordId !== null &&
    selectedRecordId === routeState.recordId &&
    selectedAnalysisReport === null &&
    !isLoadingReport;
  const { launchBlockedByBusy, openBusyTasks } = useAnalysisWorkbenchErrorContract({
    duplicateError,
    duplicateTask,
    error,
    analysisTasks,
    openTaskRunFlow,
    selectSegment,
  });
  const focusStockInput = useCallback(() => {
    selectSegment(ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch);
    window.requestAnimationFrame(() => {
      document.getElementById('analysis-workbench-stock-search')?.focus();
    });
  }, [selectSegment]);
  const dismissPrimaryError = useCallback(() => {
    lastAnalysisIntentRef.current = null;
    clearError();
  }, [clearError]);
  const dismissRunFlowError = useCallback(() => {
    failedRunFlowSourceRef.current = null;
    setRunFlowError(null);
  }, []);
  const dismissBatchNotice = useCallback(() => {
    lastBatchIntentRef.current = null;
    setBatchNotice(null);
  }, []);
  const hasWorkbenchErrorNotice = Boolean(
    inputError
    || duplicateError
    || error
    || reportDetailError
    || runFlowError
    || batchNotice,
  );
  return (
    <AppPage data-testid="analysis-workbench-page">
      <PageHeader
        ref={pageHeadingRef}
        title={t('analysisWorkbench.title')}
        description={t('analysisWorkbench.description')}
        actions={
          <Button
            type="button"
            variant="primary"
            onClick={() => selectSegment(ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch)}
          >
            <FlaskConical className="h-4 w-4" aria-hidden="true" />
            {t('home.analyze')}
          </Button>
        }
      />
      <SegmentedControl
        id={WORKBENCH_TABS_ID}
        className="mt-5"
        ariaLabel={t('analysisWorkbench.tabsLabel')}
        value={routeState.segment}
        options={tabItems.map((item) => ({
          value: item.id as AnalysisWorkbenchSegment,
          label: item.label,
        }))}
        getPanelId={(value) => getTabPanelId(WORKBENCH_TABS_ID, value)}
        onChange={(value) => {
          if (
            Object.values(ANALYSIS_WORKBENCH_SEGMENT_VALUES).includes(
              value as AnalysisWorkbenchSegment,
            )
          ) {
            selectSegment(value as AnalysisWorkbenchSegment);
          }
        }}
      />
      {hasWorkbenchErrorNotice ? (
        <Suspense fallback={null}>
          <AnalysisWorkbenchErrorStack
            inputError={inputError}
            duplicateError={duplicateError}
            duplicateTask={duplicateTask}
            analysisError={error}
            reportDetailError={reportDetailError}
            runFlowError={runFlowError}
            batchNotice={batchNotice}
            isAnalyzing={isAnalyzing}
            isBatchSubmitting={isBatchSubmitting}
            onClearError={dismissPrimaryError}
            onClearRunFlowError={dismissRunFlowError}
            onClearBatchNotice={dismissBatchNotice}
            onFocusInput={focusStockInput}
            onRetryAnalysis={retryAnalysis}
            onRetryReportDetail={() => void retrySelectedRecord()}
            onRetryRunFlow={retryRunFlow}
            onRetryBatch={retryBatch}
            onViewTasks={openBusyTasks}
          />
        </Suspense>
      ) : null}
      <Suspense
        fallback={(
          <TabPanel
            tabsId={WORKBENCH_TABS_ID}
            value={ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch}
            activeValue={routeState.segment}
          />
        )}
      >
        <AnalysisWorkbenchLaunchPanel
          activeSegment={routeState.segment}
          query={query}
          setQuery={setQuery}
          inputError={inputError}
          isAnalyzing={isAnalyzing}
          isBatchSubmitting={isBatchSubmitting}
          isImporting={isImporting}
          isExperienceModeReady={isExperienceModeReady}
          launchBlockedByBusy={launchBlockedByBusy}
          experienceMode={experienceMode}
          onExperienceModeChange={handleExperienceModeChange}
          notify={notify}
          setNotify={setNotify}
          selectedStrategyId={selectedStrategyId}
          setSelectedStrategyId={setSelectedStrategyId}
          strategyOptions={strategyOptions}
          analysisPhase={analysisPhase}
          setAnalysisPhase={setAnalysisPhase}
          onSubmitAnalysis={handleSubmitAnalysis}
          onSubmitWatchlistBatch={submitWatchlistBatch}
          onSubmitImportedBatch={() => submitBatch(importedCodes)}
          onImportFile={handleImportFile}
          importedCodes={importedCodes}
          importNotice={importNotice}
          watchlistLoading={watchlist.isLoading}
          pendingBlocked={watchlistCoverage.isTodayStatusBlocked}
          pendingCount={watchlistCoverage.pendingCodes.length}
          fileInputRef={fileInputRef}
        />
      </Suspense>
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
                    <div className="mb-3 flex flex-wrap items-end justify-end gap-2">
                      <AnalysisPhaseSelect
                        id="analysis-workbench-reanalysis-phase"
                        value={analysisPhase}
                        onChange={setAnalysisPhase}
                        label={t('analysis.phase')}
                        hint={t('analysis.phaseHint')}
                        disabled={isAnalyzing}
                        className="mr-auto w-full sm:w-64"
                      />
                      <Button
                        type="button"
                        variant="secondary"
                        size="default"
                        disabled={isAnalyzing || selectedAnalysisReport.meta.id === undefined}
                        isLoading={isAnalyzing}
                        loadingText={t('home.reanalyze')}
                        onClick={() => void handleReanalyze()}
                      >
                        <RefreshCw className="h-4 w-4" aria-hidden="true" />
                        {t('home.reanalyze')}
                      </Button>
                      <Button
                        type="button"
                        variant="primary"
                        size="default"
                        disabled={selectedAnalysisReport.meta.id === undefined}
                        onClick={handleAskFollowUp}
                      >
                        <MessageCircle className="h-4 w-4" aria-hidden="true" />
                        {t('home.askAi')}
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        size="default"
                        disabled={isHistoryTrendUnavailable}
                        onClick={() => void openHistoryTrend()}
                      >
                        <BarChart3 className="h-4 w-4" aria-hidden="true" />
                        {t('home.historyTrend')}
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        size="default"
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
        confirmText={
          isDeletingHistory
            ? t('common.deleting')
            : deleteError
              ? t('common.retry')
              : t('common.delete')
        }
        confirmDisabled={isDeletingHistory}
        cancelDisabled={isDeletingHistory}
        error={deleteError?.message ?? null}
        focusConfirmOnError
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
        <Modal
          isOpen
          onClose={closeRunFlow}
          title={t('runFlow.drawerTitle')}
          size="fullscreen"
        >
          <RunFlowPanel
            key={`${runFlowDialog.source.type}-${runFlowDialog.source.type === 'task' ? runFlowDialog.source.taskId : runFlowDialog.source.recordId}`}
            source={runFlowDialog.source}
            title={runFlowDialog.title}
            onUnavailable={handleUnavailableRunFlow}
          />
        </Modal>
      ) : null}
    </AppPage>
  );
};

export default ResearchAnalysisWorkbenchPage;
