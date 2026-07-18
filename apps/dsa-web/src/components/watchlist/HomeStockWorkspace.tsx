import type React from 'react';
import { useId, useMemo, useState } from 'react';
import {
  ArrowDownWideNarrow,
  CalendarDays,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Filter,
  Loader2,
  Play,
  Plus,
  Search,
  Star,
  Trash2,
} from 'lucide-react';
import { Badge, Button, Input, ScrollArea, StatusDot } from '../common';
import { DashboardPanelHeader, DashboardStateBlock } from '../dashboard';
import { StockBar } from '../history';
import type { StockBarItem, TaskInfo } from '../../types/analysis';
import { getSentimentColor } from '../../types/analysis';
import { buildDecisionActionLabelMap, getDecisionActionLabel } from '../../utils/decisionAction';
import { formatDateTime } from '../../utils/format';
import { truncateStockName } from '../../utils/stockName';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey, UiTextParams } from '../../i18n/uiText';

export type HomeWorkspaceTab = 'watchlist' | 'today' | 'history';
export type WatchlistAnalyzeMode = 'all' | 'pending';

export interface HomeWatchlistRow {
  code: string;
  latestItem?: StockBarItem;
  analyzedToday: boolean;
  isTodayStatusLoading?: boolean;
  isTodayStatusUnknown?: boolean;
  activeTask?: TaskInfo;
}

interface BatchStatus {
  variant: 'success' | 'warning' | 'danger';
  message: string;
}

interface HomeStockWorkspaceProps {
  activeTab: HomeWorkspaceTab;
  onTabChange: (tab: HomeWorkspaceTab) => void;
  watchlistRows: HomeWatchlistRow[];
  watchlistLoading: boolean;
  watchlistActioning: boolean;
  watchlistMessage: string | null;
  onAddToWatchlist: (code: string) => Promise<void>;
  onRemoveFromWatchlist: (code: string) => Promise<void>;
  onRefreshWatchlist: () => Promise<void>;
  onAnalyzeWatchlist: (mode: WatchlistAnalyzeMode) => Promise<void>;
  isBatchAnalyzing: boolean;
  batchStatus: BatchStatus | null;
  todayItems: StockBarItem[];
  isLoadingTodayItems: boolean;
  todayLoadError: boolean;
  watchlistAnalyzedTodayCount: number;
  historyItems: StockBarItem[];
  isLoadingHistory: boolean;
  selectedStockCode?: string;
  selectedRecordId?: number;
  onHistoryItemClick: (recordId: number) => void;
  onDeleteStock?: (stockCode: string) => Promise<void> | void;
  isDeleting?: boolean;
  className?: string;
}

function getTaskStatusLabel(task: TaskInfo | undefined, t: (key: UiTextKey, params?: UiTextParams) => string) {
  if (!task) return '';
  if (task.status === 'processing') return t('taskPanel.processing');
  if (task.status === 'pending') return t('taskPanel.pending');
  if (task.status === 'cancel_requested') return t('taskPanel.cancelRequested');
  return task.status;
}

const ScoreBadge: React.FC<{ item?: StockBarItem }> = ({ item }) => {
  const { t } = useUiLanguage();
  const score = typeof item?.sentimentScore === 'number' ? item.sentimentScore : null;
  const color = score !== null ? getSentimentColor(score) : null;
  if (score === null || !color) {
    return <span className="text-xs text-muted-text">{t('common.noData')}</span>;
  }

  const actionLabels = buildDecisionActionLabelMap(t);
  const operationLabel = getDecisionActionLabel(
    item?.action,
    item?.actionLabel,
    item?.operationAdvice,
    t('history.sentiment'),
    actionLabels,
  );

  return (
    <Badge
      variant="default"
      size="sm"
      className="shrink-0 shadow-none font-semibold leading-none"
      style={{
        color,
        borderColor: `${color}30`,
        backgroundColor: `${color}10`,
      }}
    >
      {operationLabel} {score}
    </Badge>
  );
};

const WatchlistRowItem: React.FC<{
  row: HomeWatchlistRow;
  onRemove: (code: string) => Promise<void>;
  disabled: boolean;
}> = ({ row, onRemove, disabled }) => {
  const { language, t } = useUiLanguage();
  const taskLabel = getTaskStatusLabel(row.activeTask, t);
  const item = row.latestItem;
  const stockName = item?.stockName || row.code;

  return (
    <div className="home-subpanel grid min-w-0 gap-2 px-3 py-2.5">
      <div className="flex min-w-0 items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-sm font-semibold text-foreground">
              {truncateStockName(stockName)}
            </span>
            {row.isTodayStatusLoading ? (
              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-text" aria-label={t('watchlist.todayStatusLoading')} />
            ) : row.isTodayStatusUnknown ? (
              <CircleAlert className="h-3.5 w-3.5 shrink-0 text-warning" aria-label={t('watchlist.todayStatusUnavailable')} />
            ) : row.analyzedToday ? (
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-success" aria-label={t('watchlist.analyzedToday')} />
            ) : (
              <Clock3 className="h-3.5 w-3.5 shrink-0 text-muted-text" aria-label={t('watchlist.notAnalyzedToday')} />
            )}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-secondary-text">{row.code}</span>
            {item?.lastAnalysisTime ? (
              <>
                <span className="h-1 w-1 rounded-full bg-subtle-hover" />
                <span className="text-xs text-muted-text">{formatDateTime(item.lastAnalysisTime, language)}</span>
              </>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <ScoreBadge item={item} />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            disabled={disabled}
            aria-label={t('watchlist.removeAria', { code: row.code })}
            onClick={() => void onRemove(row.code)}
          >
            <Trash2 className="h-3.5 w-3.5 text-danger" aria-hidden="true" />
          </Button>
        </div>
      </div>
      {row.activeTask ? (
        <div className="flex min-w-0 items-center gap-2 text-xs text-muted-text">
          <StatusDot
            tone={row.activeTask.status === 'processing' ? 'info' : 'neutral'}
            pulse={row.activeTask.status === 'processing'}
            className="h-1.5 w-1.5"
          />
          <span className="truncate">{t('watchlist.taskRunning', { status: taskLabel })}</span>
        </div>
      ) : null}
    </div>
  );
};

const TodayItem: React.FC<{ item: StockBarItem; onClick: (recordId: number) => void }> = ({ item, onClick }) => {
  const stockName = item.stockName || item.stockCode;

  return (
    <button
      type="button"
      className="home-subpanel-button grid w-full min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-2 px-3 py-2.5 text-left"
      onClick={() => onClick(item.id)}
    >
      <div className="min-w-0">
        <span className="block truncate text-sm font-semibold text-foreground">
          {truncateStockName(stockName)}
        </span>
        <span className="mt-1 block truncate font-mono text-xs text-secondary-text">
          {item.stockCode}
        </span>
      </div>
      <ScoreBadge item={item} />
    </button>
  );
};

export const HomeStockWorkspace: React.FC<HomeStockWorkspaceProps> = ({
  activeTab,
  onTabChange,
  watchlistRows,
  watchlistLoading,
  watchlistActioning,
  watchlistMessage,
  onAddToWatchlist,
  onRemoveFromWatchlist,
  onRefreshWatchlist,
  onAnalyzeWatchlist,
  isBatchAnalyzing,
  batchStatus,
  todayItems,
  isLoadingTodayItems,
  todayLoadError,
  watchlistAnalyzedTodayCount,
  historyItems,
  isLoadingHistory,
  selectedStockCode,
  selectedRecordId,
  onHistoryItemClick,
  onDeleteStock,
  isDeleting = false,
  className = '',
}) => {
  const { t } = useUiLanguage();
  const reactId = useId();
  const [draftCode, setDraftCode] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const pendingWatchlistCount = watchlistRows
    .filter((row) => !row.analyzedToday && !row.isTodayStatusLoading && !row.isTodayStatusUnknown)
    .length;
  const isTodayStatusUnavailable = watchlistRows.some((row) => row.isTodayStatusLoading || row.isTodayStatusUnknown);
  const topTodayItem = todayItems[0];
  const tabs: Array<{ key: HomeWorkspaceTab; label: string }> = [
    { key: 'history', label: t('watchlist.tabHistory') },
    { key: 'watchlist', label: t('watchlist.tabWatchlist') },
    { key: 'today', label: t('watchlist.tabToday') },
  ];

  const statusClassName = useMemo(() => {
    if (!batchStatus) return '';
    if (batchStatus.variant === 'danger') return 'border-danger/30 bg-danger/10 text-danger';
    if (batchStatus.variant === 'warning') return 'border-warning/30 bg-warning/10 text-warning';
    return 'border-success/30 bg-success/10 text-success';
  }, [batchStatus]);
  const normalizedSearchQuery = searchQuery.trim().toLowerCase();
  const filteredWatchlistRows = useMemo(() => {
    if (!normalizedSearchQuery) return watchlistRows;
    return watchlistRows.filter((row) => {
      const stockName = row.latestItem?.stockName ?? '';
      return (
        row.code.toLowerCase().includes(normalizedSearchQuery) ||
        stockName.toLowerCase().includes(normalizedSearchQuery)
      );
    });
  }, [normalizedSearchQuery, watchlistRows]);
  const filteredTodayItems = useMemo(() => {
    if (!normalizedSearchQuery) return todayItems;
    return todayItems.filter((item) => (
      item.stockCode.toLowerCase().includes(normalizedSearchQuery) ||
      (item.stockName ?? '').toLowerCase().includes(normalizedSearchQuery)
    ));
  }, [normalizedSearchQuery, todayItems]);
  const filteredHistoryItems = useMemo(() => {
    if (!normalizedSearchQuery) return historyItems;
    return historyItems.filter((item) => (
      item.stockCode.toLowerCase().includes(normalizedSearchQuery) ||
      (item.stockName ?? '').toLowerCase().includes(normalizedSearchQuery)
    ));
  }, [historyItems, normalizedSearchQuery]);

  const handleAddSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const code = draftCode.trim();
    if (!code) return;
    void onAddToWatchlist(code).then(() => setDraftCode(''));
  };

  const tabId = (key: HomeWorkspaceTab) => `${reactId}-tab-${key}`;
  const panelId = `${reactId}-panel`;

  const handleTabListKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const currentIndex = tabs.findIndex((tab) => tab.key === activeTab);
    let nextIndex = -1;
    if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = tabs.length - 1;
    if (nextIndex < 0) return;
    event.preventDefault();
    const nextKey = tabs[nextIndex].key;
    onTabChange(nextKey);
    document.getElementById(tabId(nextKey))?.focus();
  };

  const renderTabs = (
    <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-2">
      <div
        role="tablist"
        aria-label={t('watchlist.tabsAria')}
        onKeyDown={handleTabListKeyDown}
        className="inline-flex h-11 items-center gap-1 rounded-lg border border-subtle bg-base/40 px-1"
      >
        <Filter className="ml-1 h-4 w-4 shrink-0 text-muted-text" aria-hidden="true" />
        {tabs.map((tab) => {
          const selected = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              id={tabId(tab.key)}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={panelId}
              tabIndex={selected ? 0 : -1}
              className={`h-9 rounded-md px-2 text-xs font-medium transition-colors ${
                selected ? 'bg-primary/15 text-primary shadow-inner' : 'text-secondary-text hover:bg-hover hover:text-foreground'
              }`}
              onClick={() => onTabChange(tab.key)}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div className="relative min-w-0">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 z-10 h-3.5 w-3.5 -translate-y-1/2 text-muted-text" aria-hidden="true" />
        <Input
          type="search"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder={t('common.searchPlaceholder')}
          aria-label={t('layout.search')}
          className="h-11 pl-8 pr-2"
        />
      </div>
    </div>
  );

  // Both branches share one skeleton so the tab bar keeps an identical
  // position/size when switching tabs; only the panel content changes.
  const workspaceShell = (content: React.ReactNode) => (
    <div className={`flex min-h-0 flex-1 flex-col gap-2 ${className}`}>
      {renderTabs}
      <div
        role="tabpanel"
        id={panelId}
        aria-labelledby={tabId(activeTab)}
        className="flex min-h-0 flex-1 flex-col overflow-hidden"
      >
        {content}
      </div>
    </div>
  );

  if (activeTab === 'history') {
    return workspaceShell(
      <StockBar
        items={filteredHistoryItems}
        isLoading={isLoadingHistory}
        selectedStockCode={selectedStockCode}
        selectedRecordId={selectedRecordId}
        onItemClick={onHistoryItemClick}
        onDeleteStock={onDeleteStock}
        isDeleting={isDeleting}
        className="flex-1 overflow-hidden"
      />,
    );
  }

  return workspaceShell(
    <aside className="glass-card flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="space-y-3 border-b border-subtle px-4 py-4">
        {activeTab === 'watchlist' ? (
          <>
            <DashboardPanelHeader
              className="mb-0"
              title={t('watchlist.title')}
              titleClassName="text-sm font-medium"
              leading={<Star className="h-4 w-4 text-primary" aria-hidden="true" />}
              actions={<span className="text-xs text-muted-text">{t('common.itemsCount', { count: watchlistRows.length })}</span>}
            />
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-xl border border-subtle bg-base/35 px-3 py-2">
                <p className="text-xs text-muted-text">{t('watchlist.todayCoverage')}</p>
                <p className="mt-1 text-sm font-semibold text-foreground">{watchlistAnalyzedTodayCount}/{watchlistRows.length}</p>
              </div>
              <div className="rounded-xl border border-subtle bg-base/35 px-3 py-2">
                <p className="text-xs text-muted-text">{t('watchlist.pendingToday')}</p>
                <p className="mt-1 text-sm font-semibold text-foreground">{pendingWatchlistCount}</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Button
                type="button"
                size="sm"
                variant="home-action-ai"
                className="whitespace-nowrap px-2 text-xs"
                disabled={watchlistRows.length === 0 || isBatchAnalyzing}
                isLoading={isBatchAnalyzing}
                loadingText={t('watchlist.submitting')}
                onClick={() => void onAnalyzeWatchlist('all')}
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                {t('watchlist.analyzeAll')}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="home-action-report"
                className="whitespace-nowrap px-2 text-xs"
                disabled={pendingWatchlistCount === 0 || isTodayStatusUnavailable || isBatchAnalyzing}
                onClick={() => void onAnalyzeWatchlist('pending')}
              >
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                {t('watchlist.analyzePending')}
              </Button>
            </div>
            <form className="grid grid-cols-[minmax(0,1fr)_auto] gap-2" onSubmit={handleAddSubmit}>
              <Input
                value={draftCode}
                onChange={(event) => setDraftCode(event.target.value)}
                placeholder={t('watchlist.addPlaceholder')}
                className="h-11 px-3 text-xs"
                disabled={watchlistActioning}
                aria-label={t('watchlist.addPlaceholder')}
              />
              <Button
                type="submit"
                size="icon"
                variant="secondary"
                disabled={!draftCode.trim() || watchlistActioning}
                isLoading={watchlistActioning}
                aria-label={t('watchlist.add')}
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
              </Button>
            </form>
            {batchStatus ? (
              <div className={`rounded-xl border px-3 py-2 text-xs ${statusClassName}`}>
                {batchStatus.message}
              </div>
            ) : null}
            {watchlistMessage ? (
              <div className="rounded-xl border border-subtle bg-base/35 px-3 py-2 text-xs text-secondary-text">
                {watchlistMessage}
              </div>
            ) : null}
          </>
        ) : (
          <>
            <DashboardPanelHeader
              className="mb-0"
              title={t('watchlist.todayTitle')}
              titleClassName="text-sm font-medium"
              leading={<CalendarDays className="h-4 w-4 text-success" aria-hidden="true" />}
              actions={<span className="text-xs text-muted-text">{t('common.itemsCount', { count: todayItems.length })}</span>}
            />
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-xl border border-subtle bg-base/35 px-3 py-2">
                <p className="text-xs text-muted-text">{t('watchlist.watchlistCoverage')}</p>
                <p className="mt-1 text-sm font-semibold text-foreground">{watchlistAnalyzedTodayCount}/{watchlistRows.length}</p>
              </div>
              <div className="rounded-xl border border-subtle bg-base/35 px-3 py-2">
                <p className="text-xs text-muted-text">{t('watchlist.topScore')}</p>
                <p className="mt-1 truncate text-sm font-semibold text-foreground">
                  {topTodayItem?.sentimentScore ?? '-'}
                </p>
              </div>
            </div>
          </>
        )}
      </div>

      <ScrollArea viewportClassName="p-4" className="min-h-0 flex-1">
        {activeTab === 'watchlist' ? (
          watchlistLoading ? (
            <DashboardStateBlock loading compact title={t('watchlist.loading')} />
          ) : watchlistRows.length === 0 ? (
            <DashboardStateBlock
              compact
              title={t('watchlist.emptyTitle')}
              description={t('watchlist.emptyDescription')}
            />
          ) : filteredWatchlistRows.length === 0 ? (
            <DashboardStateBlock compact title={t('common.noData')} />
          ) : (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs text-muted-text">
                <ArrowDownWideNarrow className="h-3.5 w-3.5" aria-hidden="true" />
                {t('watchlist.listHint')}
              </div>
              {filteredWatchlistRows.map((row) => (
                <WatchlistRowItem
                  key={row.code}
                  row={row}
                  onRemove={onRemoveFromWatchlist}
                  disabled={watchlistActioning}
                />
              ))}
            </div>
          )
        ) : isLoadingTodayItems ? (
          <DashboardStateBlock loading compact title={t('watchlist.loading')} />
        ) : todayLoadError ? (
          <DashboardStateBlock
            compact
            title={t('watchlist.todayLoadErrorTitle')}
            description={t('watchlist.todayLoadErrorDescription')}
          />
        ) : todayItems.length === 0 ? (
          <DashboardStateBlock
            compact
            title={t('watchlist.todayEmptyTitle')}
            description={t('watchlist.todayEmptyDescription')}
          />
        ) : filteredTodayItems.length === 0 ? (
          <DashboardStateBlock compact title={t('common.noData')} />
        ) : (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs text-muted-text">
              <ArrowDownWideNarrow className="h-3.5 w-3.5" aria-hidden="true" />
              {t('watchlist.todaySortHint')}
            </div>
            {filteredTodayItems.map((item) => (
              <TodayItem key={`${item.stockCode}-${item.id}`} item={item} onClick={onHistoryItemClick} />
            ))}
          </div>
        )}
      </ScrollArea>

      {activeTab === 'watchlist' ? (
        <div className="border-t border-subtle px-4 py-3">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="w-full"
            disabled={watchlistLoading}
            onClick={() => void onRefreshWatchlist()}
          >
            {t('watchlist.refresh')}
          </Button>
        </div>
      ) : null}
    </aside>,
  );
};

export default HomeStockWorkspace;
