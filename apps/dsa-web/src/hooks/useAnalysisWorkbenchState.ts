// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useShallow } from 'zustand/react/shallow';
import { useStockPoolStore } from '../stores/stockPoolStore';

/** Select only the shared store state owned by the Analysis Workbench. */
export function useAnalysisWorkbenchState() {
  return useStockPoolStore(
    useShallow((state) => ({
      query: state.query,
      inputError: state.inputError,
      duplicateError: state.duplicateError,
      duplicateTask: state.duplicateTask,
      error: state.error,
      reportDetailError: state.reportDetailError,
      isAnalyzing: state.isAnalyzing,
      historyItems: state.historyItems,
      isLoadingHistory: state.isLoadingHistory,
      isLoadingMore: state.isLoadingMore,
      hasMore: state.hasMore,
      selectedReport: state.selectedReport,
      selectedRecordId: state.selectedRecordId,
      isLoadingReport: state.isLoadingReport,
      isHistoryTrendOpen: state.isHistoryTrendOpen,
      stockHistoryItems: state.stockHistoryItems,
      stockHistoryTotal: state.stockHistoryTotal,
      stockHistoryHasMore: state.stockHistoryHasMore,
      isLoadingStockHistory: state.isLoadingStockHistory,
      isLoadingMoreStockHistory: state.isLoadingMoreStockHistory,
      stockHistoryError: state.stockHistoryError,
      stockHistoryFilters: state.stockHistoryFilters,
      activeTasks: state.activeTasks,
      stockBarItems: state.stockBarItems,
      isLoadingStockBar: state.isLoadingStockBar,
      stockBarRefreshFailed: state.stockBarRefreshFailed,
      notify: state.notify,
      setQuery: state.setQuery,
      setNotify: state.setNotify,
      clearError: state.clearError,
      loadInitialHistory: state.loadInitialHistory,
      refreshHistory: state.refreshHistory,
      refreshHistoryForCompletedTask: state.refreshHistoryForCompletedTask,
      loadMoreHistory: state.loadMoreHistory,
      selectHistoryItem: state.selectHistoryItem,
      retrySelectedRecord: state.retrySelectedRecord,
      clearSelectedRecord: state.clearSelectedRecord,
      openHistoryTrend: state.openHistoryTrend,
      closeHistoryTrend: state.closeHistoryTrend,
      setStockHistoryRange: state.setStockHistoryRange,
      loadMoreStockHistory: state.loadMoreStockHistory,
      submitAnalysis: state.submitAnalysis,
      syncTaskCreated: state.syncTaskCreated,
      syncTaskUpdated: state.syncTaskUpdated,
      syncTaskFailed: state.syncTaskFailed,
      refreshActiveTasks: state.refreshActiveTasks,
      pollKnownTasks: state.pollKnownTasks,
      removeTask: state.removeTask,
      loadStockBar: state.loadStockBar,
      refreshStockBar: state.refreshStockBar,
    })),
  );
}

export default useAnalysisWorkbenchState;
