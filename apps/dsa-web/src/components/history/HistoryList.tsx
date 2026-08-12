import type React from 'react';
import { useRef, useCallback, useEffect, useId } from 'react';
import { GitCompareArrows, Trash2 } from 'lucide-react';
import type { HistoryItem } from '../../types/analysis';
import { Badge, Button, Checkbox, IconButton, ScrollArea, Surface } from '../common';
import { Spinner } from '../common/Spinner';
import { DashboardPanelHeader, DashboardStateBlock } from '../dashboard';
import { HistoryListItem } from './HistoryListItem';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { REPORT_VERSION_COMPARE_TEXT } from '../../locales/reportVersionCompare';
import { useVirtualWindow } from '../../hooks/useVirtualWindow';
import {
  HISTORY_LIST_ESTIMATED_ROW_HEIGHT_PX,
  HISTORY_LIST_OVERSCAN,
  HISTORY_LIST_VIRTUALIZE_THRESHOLD,
} from '../../performance/runtimeBudgets';

interface HistoryListProps {
  items: HistoryItem[];
  isLoading: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  selectedId?: number;
  selectedIds: Set<number>;
  isDeleting?: boolean;
  onItemClick: (recordId: number) => void;
  onLoadMore: () => void;
  onToggleItemSelection: (recordId: number) => void;
  onToggleSelectAll: () => void;
  onDeleteSelected: () => void;
  onCompareSelected?: (items: readonly [HistoryItem, HistoryItem]) => void;
  title?: string;
  emptyTitle?: string;
  emptyDescription?: string;
  className?: string;
}

/** History list with batch selection, incremental loading, and windowed rows. */
export const HistoryList: React.FC<HistoryListProps> = ({
  items,
  isLoading,
  isLoadingMore,
  hasMore,
  selectedId,
  selectedIds,
  isDeleting = false,
  onItemClick,
  onLoadMore,
  onToggleItemSelection,
  onToggleSelectAll,
  onDeleteSelected,
  onCompareSelected,
  title,
  emptyTitle,
  emptyDescription,
  className = '',
}) => {
  const { language, t } = useUiLanguage();
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const loadMoreTriggerRef = useRef<HTMLDivElement>(null);
  const selectAllRef = useRef<HTMLInputElement>(null);
  const selectAllId = useId();
  const virtualize = items.length >= HISTORY_LIST_VIRTUALIZE_THRESHOLD;
  const {
    range,
    onScroll: onVirtualScroll,
    setViewportHeight,
  } = useVirtualWindow({
    itemCount: items.length,
    estimatedItemHeight: HISTORY_LIST_ESTIMATED_ROW_HEIGHT_PX,
    overscan: HISTORY_LIST_OVERSCAN,
    enabled: virtualize,
  });

  const selectedCount = items.filter((item) => selectedIds.has(item.id)).length;
  const selectedItems = [...selectedIds]
    .map((id) => items.find((item) => item.id === id))
    .filter((item): item is HistoryItem => Boolean(item));
  const comparisonStockCode = selectedItems[0]?.stockCode.trim().toUpperCase();
  const comparisonItems = selectedItems.length === 2
    && Boolean(comparisonStockCode)
    && selectedItems.every(
      (item) => item.stockCode.trim().toUpperCase() === comparisonStockCode,
    )
    ? selectedItems as [HistoryItem, HistoryItem]
    : null;
  const allVisibleSelected = items.length > 0 && selectedCount === items.length;
  const someVisibleSelected = selectedCount > 0 && !allVisibleSelected;

  const handleObserver = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const target = entries[0];
      if (target.isIntersecting && hasMore && !isLoading && !isLoadingMore) {
        const container = scrollContainerRef.current;
        if (container && container.scrollHeight > container.clientHeight) {
          onLoadMore();
        }
      }
    },
    [hasMore, isLoading, isLoadingMore, onLoadMore]
  );

  useEffect(() => {
    const trigger = loadMoreTriggerRef.current;
    const container = scrollContainerRef.current;
    if (!trigger || !container) return;

    const observer = new IntersectionObserver(handleObserver, {
      root: container,
      rootMargin: '20px',
      threshold: 0.1,
    });

    observer.observe(trigger);
    return () => observer.disconnect();
  }, [handleObserver]);

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someVisibleSelected;
    }
  }, [someVisibleSelected]);

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container || !virtualize) {
      return;
    }

    const updateHeight = () => {
      setViewportHeight(container.clientHeight);
    };
    updateHeight();

    if (typeof ResizeObserver === 'undefined') {
      return;
    }
    const observer = new ResizeObserver(updateHeight);
    observer.observe(container);
    return () => observer.disconnect();
  }, [setViewportHeight, virtualize, items.length, isLoading]);

  const handleScroll = useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      if (virtualize) {
        onVirtualScroll(event);
      }
    },
    [onVirtualScroll, virtualize],
  );

  const visibleItems = virtualize
    ? items.slice(range.startIndex, range.endIndex + 1)
    : items;

  return (
    <div className={className}>
      <Surface as="aside" level="interactive" className="flex h-full flex-col overflow-hidden">
        <ScrollArea
        viewportRef={scrollContainerRef}
        viewportClassName="p-4"
        testId="home-history-list-scroll"
        onScroll={handleScroll}
      >
        <div className="mb-4 space-y-3">
          <DashboardPanelHeader
            className="mb-1"
            title={title ?? t('history.defaultTitle')}
            titleClassName="text-sm font-medium"
            leading={(
              <svg className="h-4 w-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            )}
            headingClassName="items-center"
            actions={
              selectedCount > 0 ? (
                <Badge variant="info" size="sm" className="history-selection-badge animate-in fade-in zoom-in duration-200">
                  {t('common.selectedCount', { count: selectedCount })}
                </Badge>
              ) : undefined
            }
          />

          {items.length > 0 && (
            <div className="flex items-center gap-2">
              <Checkbox
                id={selectAllId}
                ref={selectAllRef}
                checked={allVisibleSelected}
                onChange={onToggleSelectAll}
                disabled={isDeleting}
                aria-label={t('history.selectAllHistoryAria')}
                containerClassName="min-h-11 flex-1 rounded-lg py-1"
                label={<span className="text-xs font-normal text-muted-text">{t('common.selectAllCurrent')}</span>}
              />
              {onCompareSelected && comparisonItems ? (
                <Button
                  variant="secondary"
                  size="compact"
                  onClick={() => onCompareSelected(comparisonItems)}
                  disabled={isDeleting}
                  data-testid="history-compare-selected"
                >
                  <GitCompareArrows aria-hidden="true" />
                  {REPORT_VERSION_COMPARE_TEXT[language].compare}
                </Button>
              ) : null}
              <IconButton
                variant="danger"
                size="compact"
                onClick={onDeleteSelected}
                disabled={selectedCount === 0 || isDeleting}
                isLoading={isDeleting}
                aria-label={isDeleting ? t('common.deleting') : t('common.delete')}
              >
                <Trash2 aria-hidden="true" />
              </IconButton>
            </div>
          )}
        </div>

        {isLoading ? (
          <DashboardStateBlock
            loading
            compact
            title={t('history.loading')}
          />
        ) : items.length === 0 ? (
          <DashboardStateBlock
            title={emptyTitle ?? t('history.defaultEmptyTitle')}
            description={emptyDescription ?? t('history.defaultEmptyDescription')}
            icon={(
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            )}
          />
        ) : (
          <div
            className="space-y-2"
            data-testid="history-list-window"
            data-virtualized={virtualize ? 'true' : 'false'}
            data-mounted-count={visibleItems.length}
            data-total-count={items.length}
          >
            {virtualize && range.offsetTop > 0 ? (
              <div
                aria-hidden="true"
                data-testid="history-list-spacer-top"
                style={{ height: range.offsetTop }}
              />
            ) : null}
            {visibleItems.map((item) => (
              <HistoryListItem
                key={item.id}
                item={item}
                isViewing={selectedId === item.id}
                isChecked={selectedIds.has(item.id)}
                isDeleting={isDeleting}
                onToggleChecked={onToggleItemSelection}
                onClick={onItemClick}
              />
            ))}
            {virtualize && range.offsetBottom > 0 ? (
              <div
                aria-hidden="true"
                data-testid="history-list-spacer-bottom"
                style={{ height: range.offsetBottom }}
              />
            ) : null}

            <div ref={loadMoreTriggerRef} className="h-4" />

            {isLoadingMore && (
              <div className="flex justify-center py-4">
                <Spinner size="md" label={t('history.loading')} />
              </div>
            )}

            {!hasMore && items.length > 0 && (
              <div className="text-center py-5">
                <div className="h-px bg-subtle w-full mb-3" />
                <span className="text-xs text-secondary-text uppercase tracking-[0.2em]">{t('history.bottomReached')}</span>
              </div>
            )}
          </div>
        )}
        </ScrollArea>
      </Surface>
    </div>
  );
};
