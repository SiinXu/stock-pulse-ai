// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useMemo } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { useStockPoolStore } from '../stores/stockPoolStore';

/** Select the existing market-review consumer state without introducing a new store contract. */
export function useMarketReviewState() {
  const state = useStockPoolStore(
    useShallow((store) => ({
      error: store.error,
      reportDetailError: store.reportDetailError,
      reportSelectionEpoch: store.reportSelectionEpoch,
      marketReviewHistoryItems: store.marketReviewHistoryItems,
      selectedMarketReviewHistoryIds: store.selectedMarketReviewHistoryIds,
      isLoadingMarketReviewHistory: store.isLoadingMarketReviewHistory,
      isLoadingMoreMarketReviewHistory: store.isLoadingMoreMarketReviewHistory,
      isDeletingMarketReviewHistory: store.isDeletingMarketReviewHistory,
      marketReviewHistoryHasMore: store.marketReviewHistoryHasMore,
      selectedReport: store.selectedReport,
      selectedRecordId: store.selectedRecordId,
      isLoadingReport: store.isLoadingReport,
      isHistoryTrendOpen: store.isHistoryTrendOpen,
      stockHistoryItems: store.stockHistoryItems,
      stockHistoryTotal: store.stockHistoryTotal,
      stockHistoryHasMore: store.stockHistoryHasMore,
      isLoadingStockHistory: store.isLoadingStockHistory,
      isLoadingMoreStockHistory: store.isLoadingMoreStockHistory,
      stockHistoryError: store.stockHistoryError,
      stockHistoryFilters: store.stockHistoryFilters,
      markdownDrawerOpen: store.markdownDrawerOpen,
      notify: store.notify,
      clearError: store.clearError,
      loadMarketReviewHistory: store.loadMarketReviewHistory,
      refreshMarketReviewHistory: store.refreshMarketReviewHistory,
      loadMoreMarketReviewHistory: store.loadMoreMarketReviewHistory,
      selectHistoryItem: store.selectHistoryItem,
      retrySelectedRecord: store.retrySelectedRecord,
      clearSelectedRecord: store.clearSelectedRecord,
      toggleMarketReviewHistorySelection: store.toggleMarketReviewHistorySelection,
      toggleSelectAllVisibleMarketReviewHistory: store.toggleSelectAllVisibleMarketReviewHistory,
      deleteSelectedMarketReviewHistory: store.deleteSelectedMarketReviewHistory,
      setNotify: store.setNotify,
      openMarkdownDrawer: store.openMarkdownDrawer,
      closeMarkdownDrawer: store.closeMarkdownDrawer,
      openHistoryTrend: store.openHistoryTrend,
      closeHistoryTrend: store.closeHistoryTrend,
      setStockHistoryRange: store.setStockHistoryRange,
      loadMoreStockHistory: store.loadMoreStockHistory,
    })),
  );

  const selectedIds = useMemo(
    () => new Set(state.selectedMarketReviewHistoryIds),
    [state.selectedMarketReviewHistoryIds],
  );

  return { ...state, selectedIds };
}

export default useMarketReviewState;
