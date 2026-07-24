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
      activeTasks: state.activeTasks,
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
      submitAnalysis: state.submitAnalysis,
      syncTaskCreated: state.syncTaskCreated,
      syncTaskUpdated: state.syncTaskUpdated,
      syncTaskFailed: state.syncTaskFailed,
      refreshActiveTasks: state.refreshActiveTasks,
      pollKnownTasks: state.pollKnownTasks,
      removeTask: state.removeTask,
    })),
  );
}

export default useAnalysisWorkbenchState;
