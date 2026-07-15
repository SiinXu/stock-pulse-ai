import { create } from 'zustand';
import { analysisApi, DuplicateTaskError } from '../api/analysis';
import type { ParsedApiError } from '../api/error';
import { getParsedApiError } from '../api/error';
import { historyApi } from '../api/history';
import type { AnalysisReport, AnalyzeAsyncResponse, HistoryItem, HistoryListResponse, ReportLanguage, StockBarItem, StockHistoryFilters, StockHistoryRange, TaskInfo } from '../types/analysis';
import { getRecentStartDate, getTodayInShanghai } from '../utils/format';
import { normalizeStockCode } from '../utils/stockCode';
import { isObviouslyInvalidStockQuery, looksLikeStockCode, validateStockCode } from '../utils/validation';

const PAGE_SIZE = 20;
const STOCK_HISTORY_PAGE_SIZE = 20;
const MARKET_REVIEW_HISTORY_PAGE_SIZE = 10;
const MARKET_REVIEW_HISTORY_CODE = 'MARKET';

type SelectionSource = 'manual' | 'autocomplete' | 'import' | 'image';

type FetchHistoryOptions = {
  autoSelectFirst?: boolean;
  reset?: boolean;
  silent?: boolean;
  selectLatestForStockCode?: string;
};

type SubmitAnalysisOptions = {
  stockCode?: string;
  stockName?: string;
  originalQuery?: string;
  selectionSource?: SelectionSource;
  notify?: boolean;
  forceRefresh?: boolean;
  skills?: string[];
  reportLanguage?: ReportLanguage;
};

type CompletedTaskSelectionIntent = {
  manualSelectionSeq: number;
  selectedReportId: number | undefined;
};

let reportRequestSeq = 0;
let analyzeRequestSeq = 0;
let historyRequestSeq = 0;
let marketReviewHistoryRequestSeq = 0;
let stockHistoryRequestSeq = 0;
let stockBarRequestSeq = 0;
let activeTaskRequestSeq = 0;
let knownTaskPollSeq = 0;
let activeTaskLocalRevision = 0;
let manualSelectionRequestSeq = 0;
let manualSelectionRequestId = 0;
export const TERMINAL_TASK_RETENTION_MS = 2 * 60 * 1000;

type DismissedTask = {
  expiresAt: number;
  fingerprint: string;
};

const dismissedTasks = new Map<string, DismissedTask>();
const pendingCompletedTaskSelectionKeys = new Map<string, CompletedTaskSelectionIntent>();

const isTerminalTask = (task: Pick<TaskInfo, 'status'>): boolean =>
  task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled';

const taskFingerprint = (task: TaskInfo): string =>
  [task.status, task.progress, task.completedAt ?? '', task.messageCode ?? ''].join('|');

const isRecentlyTerminalTask = (task: TaskInfo, now = Date.now()): boolean => {
  if (!isTerminalTask(task)) {
    return true;
  }
  const timestamp = Date.parse(task.completedAt || task.createdAt);
  return !Number.isFinite(timestamp) || now - timestamp <= TERMINAL_TASK_RETENTION_MS;
};

const isTaskDismissed = (task: TaskInfo, now = Date.now()): boolean => {
  const dismissed = dismissedTasks.get(task.taskId);
  if (!dismissed) {
    return false;
  }
  if (dismissed.expiresAt <= now) {
    dismissedTasks.delete(task.taskId);
    return false;
  }
  return true;
};

export interface StockPoolState {
  query: string;
  selectionSource: SelectionSource;
  notify: boolean;
  inputError?: string;
  duplicateError: string | null;
  duplicateTask: { stockCode: string; existingTaskId: string } | null;
  error: ParsedApiError | null;
  isAnalyzing: boolean;
  historyItems: HistoryItem[];
  selectedHistoryIds: number[];
  isDeletingHistory: boolean;
  isLoadingHistory: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  currentPage: number;
  marketReviewHistoryItems: HistoryItem[];
  selectedMarketReviewHistoryIds: number[];
  isLoadingMarketReviewHistory: boolean;
  isLoadingMoreMarketReviewHistory: boolean;
  isDeletingMarketReviewHistory: boolean;
  marketReviewHistoryHasMore: boolean;
  marketReviewHistoryPage: number;
  selectedReport: AnalysisReport | null;
  // The record the user currently intends to view. Tracked independently of
  // selectedReport so the selection (and its failure state) survives a failed
  // load instead of falling back to the previously displayed report.
  selectedRecordId: number | null;
  // The record whose report is currently being fetched, or null when idle.
  pendingRecordId: number | null;
  isLoadingReport: boolean;
  isHistoryTrendOpen: boolean;
  stockHistoryItems: HistoryItem[];
  stockHistoryTotal: number;
  stockHistoryPage: number;
  stockHistoryHasMore: boolean;
  isLoadingStockHistory: boolean;
  isLoadingMoreStockHistory: boolean;
  stockHistoryError: ParsedApiError | null;
  stockHistoryFilters: StockHistoryFilters;
  activeTasks: TaskInfo[];
  markdownDrawerOpen: boolean;
  stockBarItems: StockBarItem[];
  isLoadingStockBar: boolean;
  stockBarRefreshFailed: boolean;
  setQuery: (query: string) => void;
  clearError: () => void;
  clearInlineMessages: () => void;
  openMarkdownDrawer: () => void;
  closeMarkdownDrawer: () => void;
  openHistoryTrend: () => Promise<void>;
  closeHistoryTrend: () => void;
  setStockHistoryRange: (range: StockHistoryRange) => Promise<void>;
  loadMoreStockHistory: () => Promise<void>;
  loadInitialHistory: () => Promise<void>;
  refreshHistory: (silent?: boolean) => Promise<void>;
  refreshHistoryForCompletedTask: (task: TaskInfo) => Promise<void>;
  loadMoreHistory: () => Promise<void>;
  loadMarketReviewHistory: () => Promise<void>;
  refreshMarketReviewHistory: (silent?: boolean) => Promise<void>;
  loadMoreMarketReviewHistory: () => Promise<void>;
  selectHistoryItem: (recordId: number, isUserInitiated?: boolean) => Promise<void>;
  retrySelectedRecord: () => Promise<void>;
  clearSelectedReportForStock: (stockCode: string) => void;
  toggleHistorySelection: (recordId: number) => void;
  toggleSelectAllVisible: () => void;
  deleteSelectedHistory: () => Promise<void>;
  toggleMarketReviewHistorySelection: (recordId: number) => void;
  toggleSelectAllVisibleMarketReviewHistory: () => void;
  deleteSelectedMarketReviewHistory: () => Promise<void>;
  submitAnalysis: (options?: SubmitAnalysisOptions) => Promise<void>;
  setNotify: (notify: boolean) => void;
  syncTaskCreated: (task: TaskInfo) => void;
  syncTaskUpdated: (task: TaskInfo) => void;
  syncTaskFailed: (task: TaskInfo) => void;
  refreshActiveTasks: () => Promise<void>;
  pollKnownTasks: () => Promise<void>;
  removeTask: (taskId: string) => void;
  resetDashboardState: () => void;
  loadStockBar: () => Promise<void>;
  refreshStockBar: () => Promise<void>;
}

const initialState = {
  query: '',
  selectionSource: 'manual' as SelectionSource,
  notify: true,
  inputError: undefined,
  duplicateError: null,
  duplicateTask: null,
  error: null,
  isAnalyzing: false,
  historyItems: [] as HistoryItem[],
  selectedHistoryIds: [] as number[],
  isDeletingHistory: false,
  isLoadingHistory: false,
  isLoadingMore: false,
  hasMore: true,
  currentPage: 1,
  marketReviewHistoryItems: [] as HistoryItem[],
  selectedMarketReviewHistoryIds: [] as number[],
  isLoadingMarketReviewHistory: false,
  isLoadingMoreMarketReviewHistory: false,
  isDeletingMarketReviewHistory: false,
  marketReviewHistoryHasMore: false,
  marketReviewHistoryPage: 1,
  selectedReport: null as AnalysisReport | null,
  selectedRecordId: null as number | null,
  pendingRecordId: null as number | null,
  isLoadingReport: false,
  isHistoryTrendOpen: false,
  stockHistoryItems: [] as HistoryItem[],
  stockHistoryTotal: 0,
  stockHistoryPage: 1,
  stockHistoryHasMore: false,
  isLoadingStockHistory: false,
  isLoadingMoreStockHistory: false,
  stockHistoryError: null as ParsedApiError | null,
  stockHistoryFilters: {
    range: 'all' as StockHistoryRange,
    model: 'all',
    sort: 'desc' as const,
  },
  activeTasks: [] as TaskInfo[],
  markdownDrawerOpen: false,
  stockBarItems: [] as StockBarItem[],
  isLoadingStockBar: false,
  stockBarRefreshFailed: false,
};

function buildHistoryParams(page: number) {
  return {
    startDate: getRecentStartDate(30),
    endDate: getTodayInShanghai(),
    page,
    limit: PAGE_SIZE,
  };
}

function buildMarketReviewHistoryParams(page: number) {
  return {
    stockCode: MARKET_REVIEW_HISTORY_CODE,
    reportType: 'market_review' as const,
    page,
    limit: MARKET_REVIEW_HISTORY_PAGE_SIZE,
  };
}

function buildStockHistoryParams(stockCode: string, page: number, filters: StockHistoryFilters) {
  const params: {
    stockCode: string;
    reportType?: 'market_review';
    startDate?: string;
    endDate?: string;
    page: number;
    limit: number;
  } = {
    stockCode,
    page,
    limit: STOCK_HISTORY_PAGE_SIZE,
  };

  if (stockCode === MARKET_REVIEW_HISTORY_CODE) {
    params.reportType = 'market_review';
  }

  if (filters.range === '30d') {
    params.startDate = getRecentStartDate(30);
    params.endDate = getTodayInShanghai();
  } else if (filters.range === '90d') {
    params.startDate = getRecentStartDate(90);
    params.endDate = getTodayInShanghai();
  }

  return params;
}

function reportToHistoryItem(report: AnalysisReport): HistoryItem | null {
  if (report.meta.id === undefined) {
    return null;
  }

  return {
    id: report.meta.id,
    queryId: report.meta.queryId,
    stockCode: report.meta.stockCode,
    stockName: report.meta.stockName,
    reportType: report.meta.reportType,
    trendPrediction: report.summary.trendPrediction,
    analysisSummary: report.summary.analysisSummary,
    sentimentScore: report.summary.sentimentScore,
    operationAdvice: report.summary.operationAdvice,
    action: report.summary.action,
    actionLabel: report.summary.actionLabel,
    currentPrice: report.meta.currentPrice,
    changePct: report.meta.changePct,
    modelUsed: report.meta.modelUsed,
    createdAt: report.meta.createdAt,
  };
}

function normalizeSelectedReport(report: AnalysisReport): AnalysisReport {
  if (report.meta.reportType !== 'market_review' || report.meta.stockCode) {
    return report;
  }
  return {
    ...report,
    meta: {
      ...report.meta,
      stockCode: MARKET_REVIEW_HISTORY_CODE,
    },
  };
}

function normalizeStockCodeKey(stockCode: string | undefined): string {
  const trimmed = (stockCode ?? '').trim();
  return trimmed ? normalizeStockCode(trimmed).toUpperCase() : '';
}

function queueCompletedTaskSelection(
  stockCode: string | undefined,
  selectedReport: AnalysisReport | null,
): void {
  const key = normalizeStockCodeKey(stockCode);
  if (key) {
    pendingCompletedTaskSelectionKeys.set(key, {
      manualSelectionSeq: manualSelectionRequestSeq,
      selectedReportId: selectedReport?.meta.id,
    });
  }
}

function consumeCompletedTaskSelection(items: HistoryItem[], selectedReport: AnalysisReport | null): HistoryItem | undefined {
  if (pendingCompletedTaskSelectionKeys.size === 0) {
    return undefined;
  }
  if (manualSelectionRequestId !== 0) {
    pendingCompletedTaskSelectionKeys.clear();
    return undefined;
  }

  if (selectedReport?.meta.reportType === 'market_review') {
    pendingCompletedTaskSelectionKeys.clear();
    return undefined;
  }

  if (selectedReport) {
    const selectedStockCode = normalizeStockCodeKey(selectedReport.meta.stockCode);
    const pendingSelectionIntent = selectedStockCode
      ? pendingCompletedTaskSelectionKeys.get(selectedStockCode)
      : undefined;
    if (!selectedStockCode || pendingSelectionIntent === undefined) {
      pendingCompletedTaskSelectionKeys.clear();
      return undefined;
    }
    if (pendingSelectionIntent.manualSelectionSeq !== manualSelectionRequestSeq) {
      pendingCompletedTaskSelectionKeys.clear();
      return undefined;
    }
    if (pendingSelectionIntent.selectedReportId !== selectedReport.meta.id) {
      pendingCompletedTaskSelectionKeys.clear();
      return undefined;
    }

    for (const key of Array.from(pendingCompletedTaskSelectionKeys.keys())) {
      if (key !== selectedStockCode) {
        pendingCompletedTaskSelectionKeys.delete(key);
      }
    }

    const latestItem = items.find(
      (item) =>
        item.reportType !== 'market_review' &&
        normalizeStockCodeKey(item.stockCode) === selectedStockCode,
    );
    if (latestItem) {
      pendingCompletedTaskSelectionKeys.delete(selectedStockCode);
    }
    return latestItem;
  }

  const latestItem = items.find((item) => {
    if (item.reportType === 'market_review') {
      return false;
    }
    const stockCode = normalizeStockCodeKey(item.stockCode);
    const pendingSelectionIntent = pendingCompletedTaskSelectionKeys.get(stockCode);
    return stockCode.length > 0 && pendingSelectionIntent?.manualSelectionSeq === manualSelectionRequestSeq;
  });
  if (latestItem) {
    pendingCompletedTaskSelectionKeys.clear();
  }
  return latestItem;
}

function isDateInHistoryRange(createdAt: string | undefined, range: StockHistoryRange): boolean {
  if (range === 'all') {
    return true;
  }
  if (!createdAt) {
    return false;
  }

  const reportDate = createdAt.slice(0, 10);
  const startDate = range === '30d' ? getRecentStartDate(30) : getRecentStartDate(90);
  const endDate = getTodayInShanghai();

  return reportDate >= startDate && reportDate <= endDate;
}

function includeSelectedReport(
  items: HistoryItem[],
  report: AnalysisReport,
  range: StockHistoryRange,
): HistoryItem[] {
  const current = reportToHistoryItem(report);
  if (!current || !isDateInHistoryRange(current.createdAt, range) || items.some((item) => item.id === current.id)) {
    return items;
  }
  return [current, ...items];
}

function dedupeHistoryItems(items: HistoryItem[]): HistoryItem[] {
  const seen = new Set<number>();
  return items.filter((item) => {
    if (seen.has(item.id)) {
      return false;
    }
    seen.add(item.id);
    return true;
  });
}

function resetStockHistoryState(set: (partial: Partial<StockPoolState>) => void) {
  set({
    stockHistoryItems: [],
    stockHistoryTotal: 0,
    stockHistoryPage: 1,
    stockHistoryHasMore: false,
    isLoadingStockHistory: false,
    isLoadingMoreStockHistory: false,
    stockHistoryError: null,
  });
}

async function fetchStockHistory(
  get: () => StockPoolState,
  set: (partial: Partial<StockPoolState>) => void,
  options: { reset?: boolean } = {},
): Promise<HistoryListResponse | null> {
  const { reset = true } = options;
  const state = get();
  const report = state.selectedReport;

  if (!report || !report.meta.stockCode) {
    resetStockHistoryState(set);
    set({
      isHistoryTrendOpen: false,
    });
    return null;
  }

  const page = reset ? 1 : state.stockHistoryPage + 1;
  const requestId = ++stockHistoryRequestSeq;
  set(
    reset
      ? { isLoadingStockHistory: true, isLoadingMoreStockHistory: false, stockHistoryError: null }
      : { isLoadingMoreStockHistory: true, stockHistoryError: null },
  );

  try {
    const response = await historyApi.getList(
      buildStockHistoryParams(report.meta.stockCode, page, state.stockHistoryFilters),
    );
    if (requestId !== stockHistoryRequestSeq) {
      return null;
    }

    const nextItems = reset
      ? dedupeHistoryItems(includeSelectedReport(response.items, report, state.stockHistoryFilters.range))
      : dedupeHistoryItems([...get().stockHistoryItems, ...response.items]);
    const nextTotal = Math.max(response.total, nextItems.length);
    set({
      stockHistoryItems: nextItems,
      stockHistoryTotal: nextTotal,
      stockHistoryPage: page,
      stockHistoryHasMore: nextItems.length < nextTotal,
    });
    return response;
  } catch (error) {
    if (requestId !== stockHistoryRequestSeq) {
      return null;
    }
    set({ stockHistoryError: getParsedApiError(error) });
    return null;
  } finally {
    if (requestId === stockHistoryRequestSeq) {
      set({
        isLoadingStockHistory: false,
        isLoadingMoreStockHistory: false,
      });
    }
  }
}

async function fetchHistory(
  get: () => StockPoolState,
  set: (partial: Partial<StockPoolState>) => void,
  options: FetchHistoryOptions = {},
): Promise<HistoryListResponse | null> {
  const {
    autoSelectFirst = false,
    reset = true,
    silent = false,
    selectLatestForStockCode,
  } = options;
  const currentState = get();
  const page = reset ? 1 : currentState.currentPage + 1;
  if (reset) {
    queueCompletedTaskSelection(selectLatestForStockCode, currentState.selectedReport);
  }
  const requestId = ++historyRequestSeq;

  if (!silent) {
    set(
      reset
        ? { isLoadingHistory: true, isLoadingMore: false, currentPage: 1 }
        : { isLoadingMore: true },
    );
  }

  try {
    const response = await historyApi.getList(buildHistoryParams(page));
    if (requestId !== historyRequestSeq) {
      return null;
    }

    if (silent && reset) {
      const existingIds = new Set(get().historyItems.map((item) => item.id));
      const newItems = response.items.filter((item) => !existingIds.has(item.id));
      if (newItems.length > 0) {
        set({ historyItems: [...newItems, ...get().historyItems] });
      }
    } else if (reset) {
      set({
        historyItems: response.items,
        currentPage: 1,
      });
    } else {
      set({
        historyItems: [...get().historyItems, ...response.items],
        currentPage: page,
      });
    }

    if (!silent) {
      const totalLoaded = reset ? response.items.length : get().historyItems.length;
      set({ hasMore: totalLoaded < response.total });
    }

    const visibleIds = new Set(get().historyItems.map((item) => item.id));
    set({
      selectedHistoryIds: get().selectedHistoryIds.filter((id) => visibleIds.has(id)),
    });

    if (reset) {
      const latestCompletedTaskItem = consumeCompletedTaskSelection(response.items, get().selectedReport);
      const selectedReport = get().selectedReport;
      if (latestCompletedTaskItem && latestCompletedTaskItem.id !== selectedReport?.meta.id) {
        await get().selectHistoryItem(latestCompletedTaskItem.id, false);
      } else if (autoSelectFirst && response.items.length > 0 && !selectedReport) {
        await get().selectHistoryItem(response.items[0].id, false);
      }
    }

    return response;
  } catch (error) {
    if (requestId !== historyRequestSeq) {
      return null;
    }
    set({ error: getParsedApiError(error) });
    return null;
  } finally {
    if (requestId === historyRequestSeq) {
      set({
        isLoadingHistory: false,
        isLoadingMore: false,
      });
    }
  }
}

async function fetchMarketReviewHistory(
  get: () => StockPoolState,
  set: (partial: Partial<StockPoolState>) => void,
  options: FetchHistoryOptions = {},
): Promise<HistoryListResponse | null> {
  const { reset = true, silent = false } = options;
  const currentState = get();
  const page = reset ? 1 : currentState.marketReviewHistoryPage + 1;
  const requestId = ++marketReviewHistoryRequestSeq;

  if (!silent) {
    set(
      reset
        ? { isLoadingMarketReviewHistory: true, isLoadingMoreMarketReviewHistory: false, marketReviewHistoryPage: 1 }
        : { isLoadingMoreMarketReviewHistory: true },
    );
  }

  try {
    const response = await historyApi.getList(buildMarketReviewHistoryParams(page));
    if (requestId !== marketReviewHistoryRequestSeq) {
      return null;
    }

    if (silent && reset) {
      const existingIds = new Set(get().marketReviewHistoryItems.map((item) => item.id));
      const newItems = response.items.filter((item) => !existingIds.has(item.id));
      if (newItems.length > 0) {
        set({ marketReviewHistoryItems: [...newItems, ...get().marketReviewHistoryItems] });
      }
    } else if (reset) {
      set({
        marketReviewHistoryItems: response.items,
        marketReviewHistoryPage: 1,
      });
    } else {
      set({
        marketReviewHistoryItems: dedupeHistoryItems([...get().marketReviewHistoryItems, ...response.items]),
        marketReviewHistoryPage: page,
      });
    }

    const totalLoaded = reset ? response.items.length : get().marketReviewHistoryItems.length;
    set({ marketReviewHistoryHasMore: totalLoaded < response.total });

    const visibleIds = new Set(get().marketReviewHistoryItems.map((item) => item.id));
    set({
      selectedMarketReviewHistoryIds: get().selectedMarketReviewHistoryIds.filter((id) => visibleIds.has(id)),
    });

    return response;
  } catch (error) {
    if (requestId !== marketReviewHistoryRequestSeq) {
      return null;
    }
    set({ error: getParsedApiError(error) });
    return null;
  } finally {
    if (requestId === marketReviewHistoryRequestSeq) {
      set({
        isLoadingMarketReviewHistory: false,
        isLoadingMoreMarketReviewHistory: false,
      });
    }
  }
}

export const useStockPoolStore = create<StockPoolState>((set, get) => ({
  ...initialState,

  setQuery: (query) => {
    set({
      query,
      selectionSource: 'manual',
      inputError: undefined,
      duplicateError: null,
      duplicateTask: null,
    });
  },

  clearError: () => set({ error: null }),

  clearInlineMessages: () => set({ inputError: undefined, duplicateError: null, duplicateTask: null }),

  setNotify: (notify) => set({ notify }),

  openMarkdownDrawer: () => set({ markdownDrawerOpen: true }),

  closeMarkdownDrawer: () => set({ markdownDrawerOpen: false }),

  openHistoryTrend: async () => {
    if (!get().selectedReport || !get().selectedReport?.meta.stockCode) {
      return;
    }
    set({ isHistoryTrendOpen: true });
    await fetchStockHistory(get, set, { reset: true });
  },

  closeHistoryTrend: () => {
    stockHistoryRequestSeq += 1;
    resetStockHistoryState(set);
    set({
      isHistoryTrendOpen: false,
    });
  },

  setStockHistoryRange: async (range) => {
    set({
      stockHistoryFilters: {
        ...get().stockHistoryFilters,
        range,
      },
    });
    if (get().isHistoryTrendOpen) {
      await fetchStockHistory(get, set, { reset: true });
    }
  },

  loadMoreStockHistory: async () => {
    const state = get();
    if (!state.isHistoryTrendOpen || state.isLoadingMoreStockHistory || !state.stockHistoryHasMore) {
      return;
    }
    await fetchStockHistory(get, set, { reset: false });
  },

  loadInitialHistory: async () => {
    await fetchHistory(get, set, { autoSelectFirst: true, reset: true });
  },

  refreshHistory: async (silent = false) => {
    await fetchHistory(get, set, { reset: true, silent });
  },

  refreshHistoryForCompletedTask: async (task) => {
    await fetchHistory(get, set, {
      reset: true,
      silent: true,
      selectLatestForStockCode: task.reportType === 'market_review' ? undefined : task.stockCode,
    });
  },

  loadMoreHistory: async () => {
    const state = get();
    if (state.isLoadingMore || !state.hasMore) {
      return;
    }
    await fetchHistory(get, set, { reset: false });
  },

  loadMarketReviewHistory: async () => {
    await fetchMarketReviewHistory(get, set, { reset: true });
  },

  refreshMarketReviewHistory: async (silent = false) => {
    await fetchMarketReviewHistory(get, set, { reset: true, silent });
  },

  loadMoreMarketReviewHistory: async () => {
    const state = get();
    if (state.isLoadingMoreMarketReviewHistory || !state.marketReviewHistoryHasMore) {
      return;
    }
    await fetchMarketReviewHistory(get, set, { reset: false });
  },

  clearSelectedReportForStock: (stockCode) => {
    const { selectedReport } = get();
    if (!selectedReport) {
      return;
    }
    const matchesDeletedStock = stockCode === 'MARKET'
      ? selectedReport.meta.reportType === 'market_review'
      : selectedReport.meta.stockCode === stockCode;
    if (matchesDeletedStock) {
      set({ selectedReport: null, selectedRecordId: null, pendingRecordId: null });
    }
  },

  selectHistoryItem: async (recordId, isUserInitiated = true) => {
    const requestId = ++reportRequestSeq;
    if (isUserInitiated) {
      manualSelectionRequestSeq += 1;
      manualSelectionRequestId = requestId;
    }
    // A user-initiated switch immediately enters a loading state so the panel
    // shows "loading the selected record" instead of the previous report.
    // Background refreshes keep the current report visible until the new one
    // is ready to avoid flicker.
    const shouldShowLoading = isUserInitiated || !get().selectedReport;

    set({
      selectedRecordId: recordId,
      pendingRecordId: recordId,
      error: null,
      ...(shouldShowLoading ? { isLoadingReport: true } : {}),
    });

    try {
      const report = normalizeSelectedReport(await historyApi.getDetail(recordId));
      if (requestId !== reportRequestSeq) {
        return;
      }

      set({
        selectedReport: report,
        error: null,
        isLoadingReport: false,
        pendingRecordId: null,
      });

      if (!report.meta.stockCode) {
        stockHistoryRequestSeq += 1;
        resetStockHistoryState(set);
        set({ isHistoryTrendOpen: false });
        return;
      }

      if (get().isHistoryTrendOpen) {
        await fetchStockHistory(get, set, { reset: true });
      }
    } catch (error) {
      if (requestId !== reportRequestSeq) {
        return;
      }

      set({
        error: getParsedApiError(error),
        isLoadingReport: false,
        pendingRecordId: null,
        // Drop the stale report on a failed user switch so the page shows the
        // failure for the selected record rather than the previous report.
        ...(isUserInitiated ? { selectedReport: null } : {}),
      });
    } finally {
      if (isUserInitiated && manualSelectionRequestId === requestId) {
        manualSelectionRequestId = 0;
      }
    }
  },

  retrySelectedRecord: async () => {
    const { selectedRecordId, pendingRecordId } = get();
    if (selectedRecordId === null || pendingRecordId !== null) {
      return;
    }
    await get().selectHistoryItem(selectedRecordId, true);
  },

  toggleHistorySelection: (recordId) => {
    const selected = new Set(get().selectedHistoryIds);
    if (selected.has(recordId)) {
      selected.delete(recordId);
    } else {
      selected.add(recordId);
    }

    set({ selectedHistoryIds: Array.from(selected) });
  },

  toggleSelectAllVisible: () => {
    const visibleIds = get().historyItems.map((item) => item.id);
    const selectedIds = get().selectedHistoryIds;
    const visibleSet = new Set(visibleIds);
    const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id));

    set({
      selectedHistoryIds: allSelected
        ? selectedIds.filter((id) => !visibleSet.has(id))
        : Array.from(new Set([...selectedIds, ...visibleIds])),
    });
  },

  deleteSelectedHistory: async () => {
    const state = get();
    const recordIds = Array.from(new Set(state.selectedHistoryIds));
    if (recordIds.length === 0 || state.isDeletingHistory) {
      return;
    }

    set({ isDeletingHistory: true });
    try {
      await historyApi.deleteRecords(recordIds);

      const deletedIds = new Set(recordIds);
      const selectedWasDeleted = state.selectedReport?.meta.id !== undefined
        && deletedIds.has(state.selectedReport.meta.id);

      set({ selectedHistoryIds: [] });

      const freshPage = await fetchHistory(get, set, { reset: true });

      if (selectedWasDeleted) {
        const nextItem = freshPage?.items?.[0];
        if (nextItem) {
          await get().selectHistoryItem(nextItem.id, false);
        } else {
          stockHistoryRequestSeq += 1;
          resetStockHistoryState(set);
          set({
            isHistoryTrendOpen: false,
            selectedReport: null,
            selectedRecordId: null,
            pendingRecordId: null,
          });
        }
      }
    } catch (error) {
      set({ error: getParsedApiError(error) });
    } finally {
      set({ isDeletingHistory: false });
    }
  },

  toggleMarketReviewHistorySelection: (recordId) => {
    const selected = new Set(get().selectedMarketReviewHistoryIds);
    if (selected.has(recordId)) {
      selected.delete(recordId);
    } else {
      selected.add(recordId);
    }

    set({ selectedMarketReviewHistoryIds: Array.from(selected) });
  },

  toggleSelectAllVisibleMarketReviewHistory: () => {
    const visibleIds = get().marketReviewHistoryItems.map((item) => item.id);
    const selectedIds = get().selectedMarketReviewHistoryIds;
    const visibleSet = new Set(visibleIds);
    const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id));

    set({
      selectedMarketReviewHistoryIds: allSelected
        ? selectedIds.filter((id) => !visibleSet.has(id))
        : Array.from(new Set([...selectedIds, ...visibleIds])),
    });
  },

  deleteSelectedMarketReviewHistory: async () => {
    const state = get();
    const recordIds = Array.from(new Set(state.selectedMarketReviewHistoryIds));
    if (recordIds.length === 0 || state.isDeletingMarketReviewHistory) {
      return;
    }

    set({ isDeletingMarketReviewHistory: true });
    try {
      await historyApi.deleteRecords(recordIds);

      const deletedIds = new Set(recordIds);
      const selectedWasDeleted = state.selectedReport?.meta.id !== undefined
        && state.selectedReport.meta.reportType === 'market_review'
        && deletedIds.has(state.selectedReport.meta.id);

      set({ selectedMarketReviewHistoryIds: [] });

      const freshPage = await fetchMarketReviewHistory(get, set, { reset: true });

      if (selectedWasDeleted) {
        const nextItem = freshPage?.items?.[0];
        if (nextItem) {
          await get().selectHistoryItem(nextItem.id, false);
        } else {
          set({ selectedReport: null, selectedRecordId: null, pendingRecordId: null });
        }
      }
    } catch (error) {
      set({ error: getParsedApiError(error) });
    } finally {
      set({ isDeletingMarketReviewHistory: false });
    }
  },

  submitAnalysis: async (options) => {
    const state = get();
    const rawStockCode = options?.stockCode ?? state.query;
    const stockCodeInput = rawStockCode.trim();
    const stockName = options?.stockName;
    const selectionSource = options?.selectionSource ?? state.selectionSource;
    const originalQuery = (options?.originalQuery ?? state.query).trim();
    const notify = options?.notify ?? state.notify;
    const forceRefresh = options?.forceRefresh ?? false;
    const skills = options?.skills;

    if (!stockCodeInput) {
      set({ inputError: '请输入股票代码', duplicateError: null, duplicateTask: null });
      return;
    }

    if (selectionSource !== 'autocomplete' && isObviouslyInvalidStockQuery(stockCodeInput)) {
      set({ inputError: '请输入有效的股票代码或股票名称', duplicateError: null, duplicateTask: null });
      return;
    }

    let normalizedStockCode = stockCodeInput;
    if (selectionSource === 'autocomplete' || looksLikeStockCode(stockCodeInput)) {
      const { valid, message, normalized } = validateStockCode(stockCodeInput);
      if (!valid) {
        set({ inputError: message, duplicateError: null, duplicateTask: null });
        return;
      }
      normalizedStockCode = normalized;
    }

    set({
      inputError: undefined,
      duplicateError: null,
      duplicateTask: null,
      error: null,
      isAnalyzing: true,
    });

    const requestId = ++analyzeRequestSeq;
    try {
      const response = await analysisApi.analyzeAsync({
        stockCode: normalizedStockCode,
        reportType: 'detailed',
        stockName,
        originalQuery: originalQuery || stockCodeInput,
        selectionSource,
        notify,
        forceRefresh,
        skills,
        ...(options?.reportLanguage !== undefined && { reportLanguage: options.reportLanguage }),
      });

      if (requestId !== analyzeRequestSeq) {
        return;
      }

      // Immediately reflect the accepted task(s) locally so the task panel shows
      // the submission without waiting for the SSE task_created event, which may
      // be delayed, lost, or race a very short task. syncTaskCreated dedupes by
      // taskId, so the later SSE event won't create a visual duplicate.
      const createdAt = new Date().toISOString();
      const registerTask = (
        taskId: string,
        taskStockCode: string,
        status: TaskInfo['status'],
        analysisPhase?: TaskInfo['analysisPhase'],
        messageCode?: string,
        messageParams?: Record<string, unknown>,
      ) => {
        get().syncTaskCreated({
          taskId,
          stockCode: taskStockCode,
          stockName,
          status,
          progress: 0,
          reportType: 'detailed',
          createdAt,
          messageCode: messageCode || 'task.queued',
          messageParams: messageParams || { stockCode: taskStockCode },
          originalQuery: originalQuery || stockCodeInput,
          selectionSource,
          ...(analysisPhase !== undefined ? { analysisPhase } : {}),
          ...(skills && skills.length ? { skills } : {}),
        });
      };

      const accepted: AnalyzeAsyncResponse | undefined = response;
      if (accepted && 'taskId' in accepted) {
        registerTask(
          accepted.taskId,
          normalizedStockCode,
          accepted.status,
          accepted.analysisPhase,
          accepted.messageCode,
          accepted.messageParams,
        );
      } else if (accepted && 'accepted' in accepted) {
        for (const item of accepted.accepted) {
          registerTask(
            item.taskId,
            item.stockCode,
            item.status,
            item.analysisPhase,
            item.messageCode,
            item.messageParams,
          );
        }
      }

      set({
        query: '',
        selectionSource: 'manual',
      });
    } catch (error) {
      if (requestId !== analyzeRequestSeq) {
        return;
      }

      if (error instanceof DuplicateTaskError) {
        set({
          duplicateError: error.message,
          duplicateTask: {
            stockCode: error.stockCode,
            existingTaskId: error.existingTaskId,
          },
        });
        return;
      }

      set({ error: getParsedApiError(error) });
    } finally {
      if (requestId === analyzeRequestSeq) {
        set({ isAnalyzing: false });
      }
    }
  },

  syncTaskCreated: (task) => {
    if (isTaskDismissed(task)) {
      return;
    }
    const currentTasks = get().activeTasks;
    const index = currentTasks.findIndex((item) => item.taskId === task.taskId);
    if (index >= 0) {
      const nextTasks = [...currentTasks];
      nextTasks[index] = { ...nextTasks[index], ...task };
      activeTaskLocalRevision += 1;
      set({ activeTasks: nextTasks });
    } else {
      activeTaskLocalRevision += 1;
      set({ activeTasks: [...currentTasks, task] });
    }
  },

  syncTaskUpdated: (task) => {
    if (isTaskDismissed(task)) {
      return;
    }
    const nextTasks = [...get().activeTasks];
    const index = nextTasks.findIndex((item) => item.taskId === task.taskId);
    if (index < 0) {
      return;
    }
    nextTasks[index] = { ...nextTasks[index], ...task };
    activeTaskLocalRevision += 1;
    set({ activeTasks: nextTasks });
  },

  syncTaskFailed: (task) => {
    get().syncTaskUpdated(task);
    set({
      error: getParsedApiError({
        error: 'analysis_failed',
        message: task.error || task.message || 'Analysis failed',
        trace_id: task.traceId,
      }),
    });
  },

  refreshActiveTasks: async () => {
    const requestId = ++activeTaskRequestSeq;
    const localRevisionAtRequest = activeTaskLocalRevision;
    try {
      const response = await analysisApi.getTasks({
        status: 'pending,processing,cancel_requested,completed,failed,cancelled',
        limit: 100,
      });
      if (requestId !== activeTaskRequestSeq) {
        return;
      }

      const now = Date.now();
      const remoteTasks = response.tasks
        .filter((task) => isRecentlyTerminalTask(task, now))
        .filter((task) => !isTaskDismissed(task, now));
      const remoteTaskIds = new Set(remoteTasks.map((task) => task.taskId));
      const remoteTaskById = new Map(remoteTasks.map((task) => [task.taskId, task]));
      const isCompleteSnapshot = response.tasks.length >= Math.min(response.total, 100);
      const canPruneLocalTasks = isCompleteSnapshot && activeTaskLocalRevision === localRevisionAtRequest;

      const currentTasks = get().activeTasks;
      const nextTasks = currentTasks
        .filter((task) => isRecentlyTerminalTask(task, now))
        .filter((task) => !isTaskDismissed(task, now))
        .filter((task) => !canPruneLocalTasks || remoteTaskIds.has(task.taskId))
        .map((task) => remoteTaskById.get(task.taskId) ?? task);

      const localTaskIds = new Set(nextTasks.map((task) => task.taskId));
      for (const task of remoteTasks) {
        if (!localTaskIds.has(task.taskId)) {
          nextTasks.push(task);
        }
      }

      const hasActiveTaskChanges = nextTasks.length !== currentTasks.length
        || nextTasks.some((task, index) => task !== currentTasks[index]);
      if (hasActiveTaskChanges) {
        activeTaskLocalRevision += 1;
        set({ activeTasks: nextTasks });
      }
    } catch {
      // Keep the current task panel when reconciliation cannot reach the API.
    }
  },

  pollKnownTasks: async () => {
    const knownTasks = get().activeTasks.filter((task) => !isTerminalTask(task));
    if (knownTasks.length === 0) {
      return;
    }

    const requestId = ++knownTaskPollSeq;
    const results = await Promise.allSettled(
      knownTasks.map(async (task) => ({ task, status: await analysisApi.getStatus(task.taskId) })),
    );
    if (requestId !== knownTaskPollSeq) {
      return;
    }

    for (const result of results) {
      if (result.status !== 'fulfilled') {
        continue;
      }
      const { task, status } = result.value;
      if (!status || typeof status.status !== 'string') {
        continue;
      }
      const updated: TaskInfo = {
        ...task,
        status: status.status,
        progress: status.progress ?? task.progress,
        message: status.message ?? task.message,
        messageCode: status.messageCode ?? task.messageCode,
        messageParams: status.messageParams ?? task.messageParams,
        error: status.error ?? task.error,
        traceId: status.traceId ?? task.traceId,
        stockName: status.stockName ?? task.stockName,
        originalQuery: status.originalQuery ?? task.originalQuery,
        selectionSource: status.selectionSource ?? task.selectionSource,
        analysisPhase: status.analysisPhase ?? task.analysisPhase,
        skills: status.skills ?? task.skills,
        completedAt: isTerminalTask(status) ? task.completedAt ?? new Date().toISOString() : task.completedAt,
      };
      get().syncTaskUpdated(updated);
      if (updated.status === 'failed') {
        get().syncTaskFailed(updated);
      }
    }
  },

  removeTask: (taskId) => {
    const currentTasks = get().activeTasks;
    const removed = currentTasks.find((task) => task.taskId === taskId);
    if (removed) {
      dismissedTasks.set(taskId, {
        expiresAt: Date.now() + TERMINAL_TASK_RETENTION_MS,
        fingerprint: taskFingerprint(removed),
      });
    }
    const nextTasks = currentTasks.filter((task) => task.taskId !== taskId);
    if (nextTasks.length !== currentTasks.length) {
      activeTaskLocalRevision += 1;
    }
    set({ activeTasks: nextTasks });
  },

  resetDashboardState: () => {
    historyRequestSeq += 1;
    marketReviewHistoryRequestSeq += 1;
    stockHistoryRequestSeq += 1;
    reportRequestSeq = 0;
    analyzeRequestSeq = 0;
    manualSelectionRequestSeq = 0;
    manualSelectionRequestId = 0;
    stockBarRequestSeq += 1;
    activeTaskRequestSeq += 1;
    activeTaskLocalRevision += 1;
    knownTaskPollSeq += 1;
    dismissedTasks.clear();
    pendingCompletedTaskSelectionKeys.clear();
    set({ ...initialState });
  },

  loadStockBar: async () => {
    const state = get();
    if (state.isLoadingStockBar) return;
    const requestSeq = ++stockBarRequestSeq;
    set({ isLoadingStockBar: true });
    try {
      const response = await historyApi.getStockBarList({
        startDate: getRecentStartDate(90),
        endDate: getTodayInShanghai(),
      });
      if (requestSeq !== stockBarRequestSeq) {
        return;
      }
      set({ stockBarItems: response.items, stockBarRefreshFailed: false });
    } catch {
      if (requestSeq !== stockBarRequestSeq) {
        return;
      }
      set({ stockBarRefreshFailed: true });
    } finally {
      if (requestSeq === stockBarRequestSeq) {
        set({ isLoadingStockBar: false });
      }
    }
  },

  refreshStockBar: async () => {
    const requestSeq = ++stockBarRequestSeq;
    try {
      const response = await historyApi.getStockBarList({
        startDate: getRecentStartDate(90),
        endDate: getTodayInShanghai(),
      });
      if (requestSeq !== stockBarRequestSeq) {
        return;
      }
      set({ stockBarItems: response.items, stockBarRefreshFailed: false });
    } catch {
      if (requestSeq !== stockBarRequestSeq) {
        return;
      }
      set({ stockBarRefreshFailed: true });
    } finally {
      if (requestSeq === stockBarRequestSeq) {
        set({ isLoadingStockBar: false });
      }
    }
  },
}));
