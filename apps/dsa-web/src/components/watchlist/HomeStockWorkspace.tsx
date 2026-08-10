import type React from 'react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import {
  ArrowDownWideNarrow,
  CalendarDays,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Funnel,
  Play,
  Plus,
  Star,
  Trash2,
} from 'lucide-react';
import { watchlistScoresApi } from '../../api/watchlistScores';
import { Badge, Button, IconButton, InlineAlert, Input, ScrollArea, SearchInput, Select, StatusDot, Surface } from '../common';
import { DashboardPanelHeader, DashboardStateBlock } from '../dashboard';
import { StockBar } from '../history';
import type { StockBarItem, TaskInfo } from '../../types/analysis';
import type { HomeWatchlistRow } from '../../types/watchlist';
import { getSentimentColor } from '../../types/analysis';
import type { WatchlistScoreItem, WatchlistScoreSortMode } from '../../types/watchlistScore';
import { buildDecisionActionLabelMap, getDecisionActionLabel } from '../../utils/decisionAction';
import { formatDateTime } from '../../utils/format';
import { truncateStockName } from '../../utils/stockName';
import { orderWatchlistByScore } from '../../utils/watchlistScoreOrder';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey, UiTextParams } from '../../i18n/uiText';
import { HOME_WORKSPACE_VALUES, type HomeWorkspaceValue } from '../../routing/routes';
import { Spinner } from '../common/Spinner';
import { WatchlistGroupsPanel } from './WatchlistGroupsPanel';
import { WatchlistScoreColumn } from './WatchlistScoreColumn';
import type { WatchlistGroup } from '../../types/watchlist';

export type HomeWorkspaceTab = HomeWorkspaceValue;
export type WatchlistAnalyzeMode = 'all' | 'pending';

export type { HomeWatchlistRow } from '../../types/watchlist';

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
  watchlistLoadError?: boolean;
  watchlistMessage: string | null;
  onAddToWatchlist: (code: string) => Promise<boolean | void>;
  onRemoveFromWatchlist: (code: string) => Promise<boolean | void>;
  onRefreshWatchlist: () => Promise<boolean | void>;
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
  /** Optional grouped organization layer (T23). When omitted, flat list only. */
  watchlistGroups?: WatchlistGroup[];
  watchlistGroupsLoading?: boolean;
  watchlistGroupsActioning?: boolean;
  watchlistGroupsError?: string | null;
  onCreateWatchlistGroup?: (name: string) => Promise<boolean> | boolean;
  onDeleteWatchlistGroup?: (groupId: string) => Promise<boolean> | boolean;
  onReorderWatchlistGroups?: (orderedIds: string[]) => Promise<boolean> | boolean;
  onReorderWatchlistGroupMembers?: (groupId: string, orderedCodes: string[]) => Promise<boolean> | boolean;
  onMoveWatchlistGroupMember?: (params: {
    stockCode: string;
    sourceGroupId: string;
    targetGroupId: string;
    targetIndex?: number;
  }) => Promise<boolean> | boolean;
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


function unanalyzedScoreItem(code: string): WatchlistScoreItem {
  return {
    stockCode: code,
    status: 'unanalyzed',
    score: null,
    asOf: null,
    ageDays: null,
    analysisId: null,
    operationAdvice: null,
    factors: [],
    freshness: 'none',
    degradedReasons: [],
  };
}

const WatchlistRowItem: React.FC<{
  row: HomeWatchlistRow;
  scoreItem: WatchlistScoreItem;
  onRemove: (code: string) => Promise<boolean | void>;
  disabled: boolean;
}> = ({ row, scoreItem, onRemove, disabled }) => {
  const { language, t } = useUiLanguage();
  const taskLabel = getTaskStatusLabel(row.activeTask, t);
  const item = row.latestItem;
  const stockName = item?.stockName || row.code;

  return (
    <div className="home-subpanel grid min-w-0 gap-2 px-3 py-2.5" data-testid="watchlist-row">
      <div className="flex min-w-0 items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-sm font-semibold text-foreground">
              {truncateStockName(stockName)}
            </span>
            {row.isTodayStatusLoading ? (
              <>
                <Spinner
                  size="sm"
                  className="h-3.5 w-3.5 shrink-0 text-muted-text"
                />
                <span className="sr-only">{t('watchlist.todayStatusLoading')}</span>
              </>
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
        <div className="flex shrink-0 items-start gap-1.5">
          <WatchlistScoreColumn item={scoreItem} className="max-w-40" />
          <IconButton
            type="button"
            variant="danger"
            size="default"
            disabled={disabled}
            aria-label={t('watchlist.removeAria', { code: row.code })}
            onClick={() => void onRemove(row.code)}
          >
            <Trash2 className="h-3.5 w-3.5 text-danger" aria-hidden="true" />
          </IconButton>
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
  watchlistLoadError = false,
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
  watchlistGroups,
  watchlistGroupsLoading = false,
  watchlistGroupsActioning = false,
  watchlistGroupsError = null,
  onCreateWatchlistGroup,
  onDeleteWatchlistGroup,
  onReorderWatchlistGroups,
  onReorderWatchlistGroupMembers,
  onMoveWatchlistGroupMember,
}) => {
  const { t } = useUiLanguage();
  const reactId = useId();
  const [draftCode, setDraftCode] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [scoreSort, setScoreSort] = useState<WatchlistScoreSortMode>('manual');
  const [scoresByCode, setScoresByCode] = useState<ReadonlyMap<string, WatchlistScoreItem>>(
    () => new Map(),
  );
  const scoreRequestIdRef = useRef(0);
  const watchlistCodesKey = useMemo(
    () => watchlistRows.map((row) => row.code).join('\u0001'),
    [watchlistRows],
  );

  useEffect(() => {
    const codes = watchlistCodesKey ? watchlistCodesKey.split('\u0001').filter(Boolean) : [];
    if (codes.length === 0) {
      // Avoid setState-in-effect: empty lists fall back via resolvedScoresByCode.
      return;
    }
    const requestId = scoreRequestIdRef.current + 1;
    scoreRequestIdRef.current = requestId;
    const controller = new AbortController();
    void watchlistScoresApi.score({
      stockCodes: codes,
      sort: 'manual',
      signal: controller.signal,
    }).then((response) => {
      if (scoreRequestIdRef.current !== requestId) return;
      const next = new Map<string, WatchlistScoreItem>();
      for (const item of response.items) {
        next.set(item.stockCode, item);
      }
      setScoresByCode(next);
    }).catch(() => {
      if (scoreRequestIdRef.current !== requestId) return;
      // Keep last successful scores; rows fall back to unanalyzed placeholders.
    });
    return () => {
      controller.abort();
      scoreRequestIdRef.current += 1;
    };
  }, [watchlistCodesKey]);

  const resolvedScoresByCode = useMemo(() => {
    if (!watchlistCodesKey) {
      return new Map<string, WatchlistScoreItem>();
    }
    return scoresByCode;
  }, [scoresByCode, watchlistCodesKey]);

  const pendingWatchlistCount = watchlistRows
    .filter((row) => !row.analyzedToday && !row.isTodayStatusLoading && !row.isTodayStatusUnknown)
    .length;
  const isTodayStatusUnavailable = watchlistRows.some((row) => row.isTodayStatusLoading || row.isTodayStatusUnknown);
  const topTodayItem = todayItems[0];
  const tabs: Array<{ value: HomeWorkspaceTab; label: string }> = [
    { value: HOME_WORKSPACE_VALUES.history, label: t('watchlist.tabHistory') },
    { value: HOME_WORKSPACE_VALUES.watchlist, label: t('watchlist.tabWatchlist') },
    { value: HOME_WORKSPACE_VALUES.today, label: t('watchlist.tabToday') },
  ];
  const activeTabLabel = tabs.find((tab) => tab.value === activeTab)?.label ?? tabs[0].label;

  const normalizedSearchQuery = searchQuery.trim().toLowerCase();
  const filteredWatchlistRows = useMemo(() => {
    const searched = !normalizedSearchQuery
      ? watchlistRows
      : watchlistRows.filter((row) => {
        const stockName = row.latestItem?.stockName ?? '';
        return (
          row.code.toLowerCase().includes(normalizedSearchQuery) ||
          stockName.toLowerCase().includes(normalizedSearchQuery)
        );
      });
    return orderWatchlistByScore(searched, resolvedScoresByCode, scoreSort);
  }, [normalizedSearchQuery, scoreSort, resolvedScoresByCode, watchlistRows]);
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
    void onAddToWatchlist(code).then((success) => {
      if (success !== false) setDraftCode('');
    });
  };

  const panelId = `${reactId}-panel`;

  const renderTabs = (
    <div className="flex min-w-0 items-center gap-2">
      <SearchInput
        value={searchQuery}
        onChange={(event) => setSearchQuery(event.target.value)}
        placeholder={t('common.searchPlaceholder')}
        aria-label={t('layout.search')}
        wrapperClassName="min-w-0 flex-1"
      />
      <div className="relative w-11 shrink-0 sm:w-7">
        <Select
          value={activeTab}
          options={tabs}
          onChange={(value) => onTabChange(value as HomeWorkspaceTab)}
          ariaLabel={t('watchlist.tabsAria')}
          className="w-full"
          triggerClassName="h-11 min-h-11 px-0 sm:h-7 sm:min-h-7 [&>span]:sr-only [&>svg]:hidden"
          menuAlign="end"
        />
        <Funnel className="pointer-events-none absolute left-1/2 top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 text-secondary-text" aria-hidden="true" />
      </div>
    </div>
  );

  // Both branches share one skeleton so the controls keep an identical position.
  const workspaceShell = (content: React.ReactNode) => (
    <div className={`flex min-h-0 flex-1 flex-col gap-2 ${className}`}>
      {renderTabs}
      <div
        role="region"
        id={panelId}
        aria-label={activeTabLabel}
        className="flex min-h-0 flex-1 flex-col overflow-hidden"
      >
        {content}
      </div>
    </div>
  );

  if (activeTab === HOME_WORKSPACE_VALUES.history) {
    return workspaceShell(
      <StockBar
        items={filteredHistoryItems}
        isLoading={isLoadingHistory}
        selectedStockCode={selectedStockCode}
        selectedRecordId={selectedRecordId}
        onItemClick={onHistoryItemClick}
        onDeleteStock={onDeleteStock}
        isDeleting={isDeleting}
        className="min-h-0 flex-1 overflow-hidden"
      />,
    );
  }

  return workspaceShell(
    <Surface as="aside" level="interactive" className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="space-y-3 border-b border-subtle px-4 py-4">
        {activeTab === HOME_WORKSPACE_VALUES.watchlist ? (
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
                size="default"
                variant="secondary"
                className="whitespace-nowrap text-xs"
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
                size="default"
                variant="secondary"
                className="whitespace-nowrap text-xs"
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
                className="text-xs"
                disabled={watchlistActioning}
                aria-label={t('watchlist.addPlaceholder')}
              />
              <IconButton
                type="submit"
                size="comfortable"
                variant="outline"
                disabled={!draftCode.trim() || watchlistActioning}
                isLoading={watchlistActioning}
                aria-label={t('watchlist.add')}
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
              </IconButton>
            </form>
            {batchStatus ? (
              <InlineAlert variant={batchStatus.variant} size="compact" message={batchStatus.message} />
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
        {activeTab === HOME_WORKSPACE_VALUES.watchlist ? (
          watchlistLoading ? (
            <DashboardStateBlock loading compact title={t('watchlist.loading')} />
          ) : watchlistLoadError ? (
            <DashboardStateBlock
              compact
              title={t('chat.actionFailed')}
              action={(
                <Button type="button" size="default" variant="secondary" onClick={() => void onRefreshWatchlist()}>
                  {t('common.retry')}
                </Button>
              )}
            />
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
              {watchlistGroups && onCreateWatchlistGroup && onDeleteWatchlistGroup
                && onReorderWatchlistGroups && onReorderWatchlistGroupMembers
                && onMoveWatchlistGroupMember ? (
                <WatchlistGroupsPanel
                  groups={watchlistGroups}
                  watchlistRows={watchlistRows}
                  loading={watchlistGroupsLoading}
                  actioning={watchlistGroupsActioning || watchlistActioning}
                  errorMessage={watchlistGroupsError}
                  onCreateGroup={onCreateWatchlistGroup}
                  onDeleteGroup={onDeleteWatchlistGroup}
                  onReorderGroups={onReorderWatchlistGroups}
                  onReorderMembers={onReorderWatchlistGroupMembers}
                  onMoveMember={onMoveWatchlistGroupMember}
                  onRemoveFromWatchlist={onRemoveFromWatchlist}
                />
              ) : null}
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-text">
                <ArrowDownWideNarrow className="h-3.5 w-3.5" aria-hidden="true" />
                <span className="min-w-0 flex-1">{t('watchlist.listHint')}</span>
                <Select
                  value={scoreSort}
                  onChange={(value) => setScoreSort(value as WatchlistScoreSortMode)}
                  options={[
                    { value: 'manual', label: t('watchlistScore.sortManual') },
                    { value: 'score_desc', label: t('watchlistScore.sortScoreDesc') },
                    { value: 'score_asc', label: t('watchlistScore.sortScoreAsc') },
                  ]}
                  ariaLabel={t('watchlistScore.sortManual')}
                  className="min-w-36"
                  size="default"
                />
              </div>
              {filteredWatchlistRows.map((row) => (
                <WatchlistRowItem
                  key={row.code}
                  row={row}
                  scoreItem={resolvedScoresByCode.get(row.code) ?? unanalyzedScoreItem(row.code)}
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

      {activeTab === HOME_WORKSPACE_VALUES.watchlist ? (
        <div className="border-t border-subtle px-4 py-3">
          <Button
            type="button"
            size="default"
            variant="ghost"
            disabled={watchlistLoading}
            onClick={() => void onRefreshWatchlist()}
          >
            {t('watchlist.refresh')}
          </Button>
        </div>
      ) : null}
    </Surface>,
  );
};

export default HomeStockWorkspace;
