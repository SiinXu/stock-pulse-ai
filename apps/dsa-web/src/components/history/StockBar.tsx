import type React from 'react';
import { useState, useCallback, useRef, useEffect, useId } from 'react';
import { Folder, History, Trash2 } from 'lucide-react';
import { Badge, Button, Checkbox, ConfirmDialog, InlineAlert, ScrollArea, StatePanel } from '../common';
import { DashboardPanelHeader } from '../dashboard';
import { StockBarItemComponent } from './StockBarItem';
import type { StockBarItem as StockBarItemType } from '../../types/analysis';
import { useUiLanguage } from '../../contexts/UiLanguageContext';

interface StockBarProps {
  items: StockBarItemType[];
  isLoading: boolean;
  selectedStockCode?: string;
  selectedRecordId?: number;
  onItemClick: (recordId: number) => void;
  onDeleteStock?: (stockCode: string) => Promise<void> | void;
  isDeleting?: boolean;
  className?: string;
}

/**
 * Shows the latest analysis record for each stock.
 * Market reviews participate as the MARKET item and use the same recency order.
 */
export const StockBar: React.FC<StockBarProps> = ({
  items,
  isLoading,
  selectedStockCode,
  selectedRecordId,
  onItemClick,
  onDeleteStock,
  isDeleting = false,
  className = '',
}) => {
  const { t } = useUiLanguage();
  const isMarketReview = (code: string) => code === 'MARKET';
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());
  const selectAllRef = useRef<HTMLInputElement>(null);
  const selectAllId = useId();

  const deletableItems = items;
  const selectedCount = [...selectedCodes].filter((code) => deletableItems.some((item) => item.stockCode === code)).length;
  const allVisibleSelected = deletableItems.length > 0 && selectedCount === deletableItems.length;
  const someVisibleSelected = selectedCount > 0 && !allVisibleSelected;

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someVisibleSelected;
    }
  }, [someVisibleSelected]);

  const toggleCode = useCallback((code: string) => {
    setSelectedCodes((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    setSelectedCodes((prev) => {
      if (prev.size === deletableItems.length) return new Set();
      return new Set(deletableItems.map((item) => item.stockCode));
    });
  }, [deletableItems]);

  const [confirmCodes, setConfirmCodes] = useState<string[] | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const requestDeleteSingle = useCallback((code: string) => {
    setDeleteError(null);
    setConfirmCodes([code]);
  }, []);

  const requestDeleteSelected = useCallback(() => {
    if (selectedCodes.size === 0) return;
    setDeleteError(null);
    setConfirmCodes([...selectedCodes]);
  }, [selectedCodes]);

  const handleConfirmDelete = useCallback(async () => {
    if (!onDeleteStock || !confirmCodes) return;
    const codes = confirmCodes;
    setConfirmCodes(null);
    try {
      for (const code of codes) {
        await onDeleteStock(code);
      }
      setSelectedCodes((prev) => {
        const next = new Set(prev);
        for (const code of codes) next.delete(code);
        return next;
      });
    } catch {
      setDeleteError(t('history.deleteFailed'));
    }
  }, [onDeleteStock, confirmCodes, t]);

  const confirmMessage = (() => {
    if (!confirmCodes) return '';
    if (confirmCodes.length === 1) {
      const target = items.find((item) => item.stockCode === confirmCodes[0]);
      return t('history.deleteConfirmSingle', { name: target?.stockName || confirmCodes[0] });
    }
    return t('history.deleteConfirmBatch', { count: confirmCodes.length });
  })();

  return (
    <aside className={`glass-card overflow-hidden flex flex-col ${className}`}>
      <ScrollArea
        viewportClassName="p-4"
        testId="history-stock-bar-scroll"
      >
        <div className="mb-4 space-y-3">
          <DashboardPanelHeader
            className="mb-1"
            title={t('stockBar.title')}
            titleClassName="text-sm font-medium"
            leading={(
              <Folder className="h-4 w-4 text-primary" aria-hidden="true" />
            )}
            headingClassName="items-center"
            actions={
              selectedCount > 0 ? (
                <Badge variant="info" size="sm" className="animate-in fade-in zoom-in duration-200">
                  {t('common.selectedCount', { count: selectedCount })}
                </Badge>
              ) : items.length > 0 ? (
                <span className="text-xs text-muted-text">{t('common.itemsCount', { count: items.length })}</span>
              ) : undefined
            }
          />

          {items.length > 0 && onDeleteStock && (
            <div className="flex items-center gap-2">
              <Checkbox
                id={selectAllId}
                ref={selectAllRef}
                checked={allVisibleSelected}
                onChange={toggleSelectAll}
                disabled={isDeleting}
                aria-label={t('history.selectAllStockAria')}
                containerClassName="min-h-11 flex-1 rounded-lg py-1"
                label={<span className="text-xs font-normal text-muted-text">{t('common.selectAllCurrent')}</span>}
              />
              <Button
                variant="danger-subtle"
                size="xsm"
                onClick={requestDeleteSelected}
                disabled={selectedCount === 0 || isDeleting}
                isLoading={isDeleting}
                loadingText=""
                aria-label={t('common.delete')}
                className="disabled:!border-transparent disabled:!bg-transparent"
              >
                <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}

          {deleteError && (
            <InlineAlert variant="danger" message={deleteError} />
          )}
        </div>

        {isLoading ? (
          <StatePanel status="loading"
            compact
            title={t('stockBar.loading')}
          />
        ) : items.length === 0 ? (
          <StatePanel status="empty"
            title={t('stockBar.emptyTitle')}
            description={t('stockBar.emptyDescription')}
            icon={(
              <History className="h-5 w-5" aria-hidden="true" />
            )}
          />
        ) : (
          <div className="space-y-1.5">
            {items.map((item) => {
              const code = item.stockCode || '';
              const isMarket = isMarketReview(code);
              const isSelected = selectedRecordId === item.id || selectedStockCode === code;
              const isChecked = selectedCodes.has(code);

              return (
                <div key={`${code}-${item.id}`} className="flex items-start gap-2 group">
                  {onDeleteStock && (
                    <Checkbox
                      checked={isChecked}
                      onChange={() => toggleCode(code)}
                      disabled={isDeleting}
                      aria-label={t('history.selectRecordAria', { name: item.stockName || code })}
                      containerClassName="h-11 w-11 shrink-0 justify-start self-center"
                    />
                  )}
                  <StockBarItemComponent
                    item={item}
                    isViewing={isSelected}
                    onClick={onItemClick}
                    onDelete={requestDeleteSingle}
                    isDeleting={isDeleting}
                    isMarketReview={isMarket}
                  />
                </div>
              );
            })}
          </div>
        )}
      </ScrollArea>

      <ConfirmDialog
        isOpen={confirmCodes !== null}
        title={t('history.deleteConfirmTitle')}
        message={confirmMessage}
        confirmText={t('common.delete')}
        isDanger
        onConfirm={() => void handleConfirmDelete()}
        onCancel={() => setConfirmCodes(null)}
      />
    </aside>
  );
};
