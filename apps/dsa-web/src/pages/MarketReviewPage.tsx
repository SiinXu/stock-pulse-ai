// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { BarChart3, X } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  ApiErrorAlert,
  AppPage,
  Button,
  Checkbox,
  EmptyState,
  IconButton,
  InlineAlert,
  Modal,
  PageHeader,
} from '../components/common';
import { DashboardStateBlock } from '../components/dashboard';
import { HistoryList, StockHistoryTrendDrawer } from '../components/history';
import { ReportMarkdownDrawer } from '../components/report/ReportMarkdownDrawer';
import { ReportSummary } from '../components/report/ReportSummary';
import { RunFlowPanel } from '../components/run-flow';
import {
  useHomeUrlState,
  useMarketReviewRunner,
  useMarketReviewState,
} from '../hooks';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { APP_ROUTE_PATHS } from '../routing/routes';
import type { RunFlowSnapshotSource } from '../types/runFlow';
import { normalizeReportLanguage } from '../utils/reportLanguage';

type RunFlowDialogState =
  | { open: false }
  | { open: true; source: RunFlowSnapshotSource; title: string };

const MarketReviewPage: React.FC = () => {
  const { t } = useUiLanguage();
  const location = useLocation();
  const navigate = useNavigate();
  const feedbackRef = useRef<HTMLDivElement | null>(null);
  const {
    error,
    reportDetailError,
    reportSelectionEpoch,
    marketReviewHistoryItems,
    selectedIds,
    isLoadingMarketReviewHistory,
    isLoadingMoreMarketReviewHistory,
    isDeletingMarketReviewHistory,
    marketReviewHistoryHasMore,
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
    markdownDrawerOpen,
    notify,
    clearError,
    loadMarketReviewHistory,
    refreshMarketReviewHistory,
    loadMoreMarketReviewHistory,
    selectHistoryItem,
    retrySelectedRecord,
    clearSelectedRecord,
    toggleMarketReviewHistorySelection,
    toggleSelectAllVisibleMarketReviewHistory,
    deleteSelectedMarketReviewHistory,
    setNotify,
    openMarkdownDrawer,
    closeMarkdownDrawer,
    openHistoryTrend,
    closeHistoryTrend,
    setStockHistoryRange,
    loadMoreStockHistory,
  } = useMarketReviewState();

  const urlState = useHomeUrlState({
    defaultRecordId: marketReviewHistoryItems[0]?.id ?? null,
    isHistoryLoading: isLoadingMarketReviewHistory,
    selectedRecordId,
    selectedReportId: selectedReport?.meta.id ?? null,
    isReportLoading: isLoadingReport,
    reportError: reportDetailError,
    reportSelectionEpoch,
    selectHistoryItem,
    clearSelectedRecord,
  });

  const scrollFeedbackIntoView = useCallback(() => {
    if (typeof feedbackRef.current?.scrollIntoView === 'function') {
      feedbackRef.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, []);
  const runner = useMarketReviewRunner({
    notify,
    refreshMarketReviewHistory,
    onPersistedReport: urlState.replaceRecord,
    onFeedback: scrollFeedbackIntoView,
  });

  useEffect(() => {
    document.title = t('home.marketReviewPageTitle');
  }, [t]);

  useEffect(() => {
    void loadMarketReviewHistory();
    const intervalId = window.setInterval(() => {
      void refreshMarketReviewHistory(true);
    }, 30_000);
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void refreshMarketReviewHistory(true);
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [loadMarketReviewHistory, refreshMarketReviewHistory]);

  useEffect(() => {
    if (
      urlState.recordId === null
      || selectedReport?.meta.id !== urlState.recordId
      || selectedReport.meta.reportType === 'market_review'
    ) {
      return;
    }
    navigate(
      {
        pathname: APP_ROUTE_PATHS.home,
        search: location.search,
        hash: location.hash,
      },
      { replace: true },
    );
  }, [location.hash, location.search, navigate, selectedReport, urlState.recordId]);

  const marketReport = selectedReport?.meta.reportType === 'market_review'
    ? selectedReport
    : null;
  const hasUnresolvedReportIntent = urlState.recordId !== null
    && selectedRecordId === urlState.recordId
    && marketReport?.meta.id !== urlState.recordId
    && !isLoadingReport;
  const isReportLoadFailure = Boolean(reportDetailError) && hasUnresolvedReportIntent;
  const visibleReportError = reportDetailError ?? error;
  const historyTrendUnavailable = !marketReport?.meta.stockCode;
  const reportLanguage = normalizeReportLanguage(marketReport?.meta.reportLanguage);
  const urlIssueTitle = urlState.urlIssue === 'invalid_record'
    ? t('home.invalidRecordLinkTitle')
    : urlState.urlIssue === 'invalid_run_flow'
      ? t('home.invalidRunFlowLinkTitle')
      : t('home.invalidDeepLinkTitle');
  const urlIssueMessage = urlState.urlIssue === 'invalid_record'
    ? t('home.invalidRecordLinkMessage')
    : urlState.urlIssue === 'invalid_run_flow'
      ? t('home.invalidRunFlowLinkMessage')
      : t('home.invalidDeepLinkMessage');

  useEffect(() => {
    if (historyTrendUnavailable && isHistoryTrendOpen) closeHistoryTrend();
  }, [closeHistoryTrend, historyTrendUnavailable, isHistoryTrendOpen]);

  const handleHistoryItemClick = useCallback((recordId: number) => {
    runner.clear();
    urlState.navigateToRecord(recordId);
  }, [runner, urlState]);

  const handleDeleteSelected = useCallback(async () => {
    const selectedRecordWasDeleted = selectedRecordId !== null && selectedIds.has(selectedRecordId);
    await deleteSelectedMarketReviewHistory();
    if (selectedRecordWasDeleted) {
      clearSelectedRecord();
      urlState.replaceRecord(null);
    }
  }, [clearSelectedRecord, deleteSelectedMarketReviewHistory, selectedIds, selectedRecordId, urlState]);

  const runFlowDialog = useMemo<RunFlowDialogState>(() => {
    const source = urlState.runFlowSource;
    if (!source) return { open: false };
    if (source.type === 'task') {
      return {
        open: true,
        source,
        title: t('runFlow.taskDrawerTitle', { stock: source.taskId }),
      };
    }
    const item = marketReviewHistoryItems.find(({ id }) => id === source.recordId);
    const stock = marketReport?.meta.id === source.recordId
      ? marketReport.meta.stockName || marketReport.meta.stockCode
      : item?.stockName || item?.stockCode;
    return {
      open: true,
      source,
      title: t('runFlow.historyDrawerTitle', {
        stock: stock || t('home.marketReview'),
      }),
    };
  }, [marketReport, marketReviewHistoryItems, t, urlState.runFlowSource]);

  return (
    <AppPage>
      <PageHeader
        eyebrow={t('layout.nav.research')}
        title={t('home.marketReview')}
        description={t('home.marketReviewHistoryEmptyDescription')}
        actions={(
          <>
            <Checkbox
              checked={notify}
              onChange={(event) => setNotify(event.target.checked)}
              label={t('home.notify')}
            />
            <Button
              type="button"
              variant="primary"
              isLoading={runner.isSubmitting}
              loadingText={t('home.submitMarketReview')}
              onClick={() => void runner.triggerMarketReview()}
            >
              <BarChart3 className="h-4 w-4" aria-hidden="true" />
              {t('home.marketReview')}
            </Button>
          </>
        )}
      />

      <div ref={feedbackRef} className="mt-4 space-y-3" aria-live="polite">
        {runner.notice ? (
          <InlineAlert
            variant={runner.notice.variant}
            size="compact"
            title={runner.notice.title}
            message={runner.notice.message}
          />
        ) : null}
        {runner.error ? (
          <ApiErrorAlert error={runner.error} onDismiss={runner.dismissError} />
        ) : null}
        {urlState.urlIssue ? (
          <InlineAlert
            variant="warning"
            title={urlIssueTitle}
            message={urlIssueMessage}
            action={(
              <IconButton
                type="button"
                variant="ghost"
                size="default"
                aria-label={t('common.close')}
                onClick={urlState.dismissUrlIssue}
              >
                <X aria-hidden="true" />
              </IconButton>
            )}
          />
        ) : null}
        {visibleReportError ? (
          <ApiErrorAlert
            error={visibleReportError}
            actionLabel={isReportLoadFailure ? t('common.retry') : undefined}
            onAction={isReportLoadFailure ? () => void retrySelectedRecord() : undefined}
            onDismiss={clearError}
          />
        ) : null}
      </div>

      <div className="mt-4 grid min-h-0 gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <HistoryList
          className="min-h-96"
          title={t('home.marketReviewHistoryTitle')}
          emptyTitle={t('home.marketReviewHistoryEmptyTitle')}
          emptyDescription={t('home.marketReviewHistoryEmptyDescription')}
          items={marketReviewHistoryItems}
          isLoading={isLoadingMarketReviewHistory}
          isLoadingMore={isLoadingMoreMarketReviewHistory}
          hasMore={marketReviewHistoryHasMore}
          selectedId={selectedRecordId ?? undefined}
          selectedIds={selectedIds}
          isDeleting={isDeletingMarketReviewHistory}
          onItemClick={handleHistoryItemClick}
          onLoadMore={() => void loadMoreMarketReviewHistory()}
          onToggleItemSelection={toggleMarketReviewHistorySelection}
          onToggleSelectAll={toggleSelectAllVisibleMarketReviewHistory}
          onDeleteSelected={() => void handleDeleteSelected()}
        />

        <section className="min-w-0" aria-label={t('home.marketReview')}>
          {isLoadingReport ? (
            <DashboardStateBlock title={t('home.loadingReport')} loading />
          ) : marketReport ? (
            <div className="space-y-4 pb-8">
              <div className="flex flex-wrap justify-end gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  isLoading={runner.isSubmitting}
                  disabled={runner.isSubmitting}
                  loadingText={t('home.submitMarketReview')}
                  onClick={() => void runner.triggerMarketReview()}
                >
                  <BarChart3 className="h-4 w-4" aria-hidden="true" />
                  {t('home.rerunMarketReview')}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={marketReport.meta.id === undefined || historyTrendUnavailable}
                  onClick={() => {
                    if (isHistoryTrendOpen) closeHistoryTrend();
                    else void openHistoryTrend();
                  }}
                >
                  <BarChart3 className="h-4 w-4" aria-hidden="true" />
                  {t('home.historyTrend')}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={marketReport.meta.id === undefined}
                  onClick={openMarkdownDrawer}
                >
                  {t('home.fullReport')}
                </Button>
              </div>
              {isHistoryTrendOpen ? (
                <StockHistoryTrendDrawer
                  key={`market-history-${marketReport.meta.id}`}
                  report={marketReport}
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
                  data={marketReport}
                  isHistory
                  onOpenRunFlow={urlState.openHistoryRunFlow}
                />
              )}
            </div>
          ) : hasUnresolvedReportIntent && !reportDetailError ? (
            <DashboardStateBlock
              title={t('home.loadingReport')}
              action={(
                <Button type="button" variant="secondary" onClick={() => void retrySelectedRecord()}>
                  {t('common.retry')}
                </Button>
              )}
            />
          ) : !isReportLoadFailure ? (
            <EmptyState
              title={t('home.marketReviewHistoryEmptyTitle')}
              description={t('home.marketReviewHistoryEmptyDescription')}
              icon={<BarChart3 className="h-6 w-6" aria-hidden="true" />}
              action={(
                <Button
                  type="button"
                  variant="primary"
                  isLoading={runner.isSubmitting}
                  onClick={() => void runner.triggerMarketReview()}
                >
                  {t('home.marketReview')}
                </Button>
              )}
            />
          ) : null}
        </section>
      </div>

      {markdownDrawerOpen
      && !isLoadingReport
      && marketReport?.meta.id
      && marketReport.meta.id === urlState.recordId ? (
        <ReportMarkdownDrawer
          key={marketReport.meta.id}
          recordId={marketReport.meta.id}
          stockName={marketReport.meta.stockName || t('home.marketReview')}
          stockCode={marketReport.meta.stockCode}
          reportLanguage={reportLanguage}
          onClose={closeMarkdownDrawer}
        />
      ) : null}

      {runFlowDialog.open ? (
        <Modal
          isOpen
          onClose={urlState.closeRunFlow}
          title={t('runFlow.drawerTitle')}
          size="fullscreen"
        >
          <RunFlowPanel
            key={`${runFlowDialog.source.type}-${runFlowDialog.source.type === 'task' ? runFlowDialog.source.taskId : runFlowDialog.source.recordId}`}
            source={runFlowDialog.source}
            title={runFlowDialog.title}
            onUnavailable={urlState.removeUnavailableRunFlow}
          />
        </Modal>
      ) : null}
    </AppPage>
  );
};

export default MarketReviewPage;
