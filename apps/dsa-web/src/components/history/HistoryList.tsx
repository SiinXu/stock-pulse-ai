import type React from 'react';
import { useRef, useCallback, useEffect, useId } from 'react';
import type { HistoryItem } from '../../types/analysis';
import { Badge, Button, Checkbox, ScrollArea, Surface } from '../common';
import { DashboardPanelHeader, DashboardStateBlock } from '../dashboard';
import { HistoryListItem } from './HistoryListItem';
import { useUiLanguage } from '../../contexts/UiLanguageContext';

interface HistoryListProps {
  items: HistoryItem[];
  isLoading: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  selectedId?: number;  // Currently selected history record ID.
  selectedIds: Set<number>;
  isDeleting?: boolean;
  onItemClick: (recordId: number) => void;
  onLoadMore: () => void;
  onToggleItemSelection: (recordId: number) => void;
  onToggleSelectAll: () => void;
  onDeleteSelected: () => void;
  title?: string;
  emptyTitle?: string;
  emptyDescription?: string;
  className?: string;
}

/** History list with batch selection and incremental loading. */
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
  title,
  emptyTitle,
  emptyDescription,
  className = '',
}) => {
  const { t } = useUiLanguage();
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const loadMoreTriggerRef = useRef<HTMLDivElement>(null);
  const selectAllRef = useRef<HTMLInputElement>(null);
  const selectAllId = useId();

  const selectedCount = items.filter((item) => selectedIds.has(item.id)).length;
  const allVisibleSelected = items.length > 0 && selectedCount === items.length;
  const someVisibleSelected = selectedCount > 0 && !allVisibleSelected;

  // Load the next page when the bottom sentinel enters the scroll viewport.
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

  return (
    <div className={className}>
      <Surface as="aside" level="interactive" className="flex h-full flex-col overflow-hidden">
        <ScrollArea
        viewportRef={scrollContainerRef}
        viewportClassName="p-4"
        testId="home-history-list-scroll"
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
              <Button
                variant="danger-subtle"
                size="default"
                onClick={onDeleteSelected}
                disabled={selectedCount === 0 || isDeleting}
                isLoading={isDeleting}
                className="disabled:!border-transparent disabled:!bg-transparent"
              >
                {isDeleting ? t('common.deleting') : t('common.delete')}
              </Button>
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
          <div className="space-y-2">
            {items.map((item) => (
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

            <div ref={loadMoreTriggerRef} className="h-4" />
            
            {isLoadingMore && (
              <div className="flex justify-center py-4">
                <div className="home-spinner h-5 w-5 animate-spin border-2" />
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
