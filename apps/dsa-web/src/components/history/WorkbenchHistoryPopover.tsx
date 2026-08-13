// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { History, X } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { HistoryItem } from '../../types/analysis';
import { IconButton, Popover } from '../common';
import { HistoryList } from './HistoryList';

interface WorkbenchHistoryPopoverProps {
  items: HistoryItem[];
  isLoading: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  selectedId?: number;
  selectedIds: ReadonlySet<number>;
  isDeleting: boolean;
  onItemClick: (recordId: number) => void;
  onLoadMore: () => void;
  onToggleItemSelection: (recordId: number) => void;
  onToggleSelectAll: () => void;
  onDeleteSelected: () => void;
  onCompareSelected?: (items: readonly [HistoryItem, HistoryItem]) => void;
}

/** Compact, focus-managed history selector for the Analysis Workbench. */
export const WorkbenchHistoryPopover: React.FC<WorkbenchHistoryPopoverProps> = ({
  items,
  isLoading,
  isLoadingMore,
  hasMore,
  selectedId,
  selectedIds,
  isDeleting,
  onItemClick,
  onLoadMore,
  onToggleItemSelection,
  onToggleSelectAll,
  onDeleteSelected,
  onCompareSelected,
}) => {
  const { t } = useUiLanguage();

  return (
    <Popover
      rootClassName="ml-2 shrink-0"
      contentRole="dialog"
      contentId="analysis-workbench-history-panel"
      ariaLabel={t('analysisWorkbench.history')}
      placement="bottom"
      align="start"
      contentClassName="w-80 max-w-[calc(100vw-2rem)] rounded-2xl border-border/80 shadow-elevation-popper"
      trigger={({ open, toggle }) => (
        <IconButton
          type="button"
          variant="ghost"
          size="default"
          onClick={toggle}
          aria-label={t('analysisWorkbench.history')}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls={open ? 'analysis-workbench-history-panel' : undefined}
        >
          <History aria-hidden="true" />
        </IconButton>
      )}
    >
      {({ close }) => (
        <div data-testid="analysis-history-popover">
          <IconButton
            type="button"
            variant="bare"
            size="compact"
            tooltip={false}
            onClick={close}
            aria-label={t('common.close')}
            className="absolute right-3 top-3 z-10"
          >
            <X aria-hidden="true" />
          </IconButton>
          <HistoryList
            className="[&>aside]:max-h-[min(22rem,calc(100dvh-14rem))] [&>aside]:rounded-2xl [&>aside]:border-0 [&>aside]:bg-transparent [&_[data-testid=home-history-list-scroll]]:!p-3 [&_[data-testid=home-history-list-scroll]_.text-center.py-5]:hidden [&_[data-testid=history-card-meta]]:flex-nowrap [&_[data-testid=history-card-meta]]:gap-1 [&_[data-testid=history-card-meta]>span]:whitespace-nowrap"
            items={items}
            isLoading={isLoading}
            isLoadingMore={isLoadingMore}
            hasMore={hasMore}
            selectedId={selectedId}
            selectedIds={new Set(selectedIds)}
            isDeleting={isDeleting}
            onItemClick={(recordId) => {
              onItemClick(recordId);
              close();
            }}
            onLoadMore={onLoadMore}
            onToggleItemSelection={onToggleItemSelection}
            onToggleSelectAll={onToggleSelectAll}
            onDeleteSelected={onDeleteSelected}
            onCompareSelected={onCompareSelected}
          />
        </div>
      )}
    </Popover>
  );
};
