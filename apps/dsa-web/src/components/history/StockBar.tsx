import type React from 'react';
import { useState, useCallback, useRef, useEffect, useId } from 'react';
import { Trash2 } from 'lucide-react';
import { Badge, Button, ConfirmDialog, InlineAlert, ScrollArea } from '../common';
import { DashboardPanelHeader, DashboardStateBlock } from '../dashboard';
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
 * 个股栏组件：以股票维度展示历史分析记录，每只股票只显示一条。
 * 大盘复盘可作为 MARKET 项参与展示，并按最近分析时间排序。
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
        testId="home-stock-bar-scroll"
      >
        <div className="mb-4 space-y-3">
          <DashboardPanelHeader
            className="mb-1"
            title={t('stockBar.title')}
            titleClassName="text-sm font-medium"
            leading={(
              <svg className="h-4 w-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
            )}
            headingClassName="items-center"
            actions={
              selectedCount > 0 ? (
                <Badge variant="info" size="sm" className="animate-in fade-in zoom-in duration-200">
                  {t('common.selectedCount', { count: selectedCount })}
                </Badge>
              ) : items.length > 0 ? (
                <span className="text-[11px] text-muted-text">{t('common.itemsCount', { count: items.length })}</span>
              ) : undefined
            }
          />

          {items.length > 0 && onDeleteStock && (
            <div className="flex items-center gap-2">
              <label
                className="flex flex-1 cursor-pointer items-center gap-2 rounded-lg py-1"
                htmlFor={selectAllId}
              >
                <input
                  id={selectAllId}
                  ref={selectAllRef}
                  type="checkbox"
                  checked={allVisibleSelected}
                  onChange={toggleSelectAll}
                  disabled={isDeleting}
                  aria-label={t('history.selectAllStockAria')}
                  className="chat-skill-checkbox cursor-pointer"
                />
                <span className="text-[11px] text-muted-text select-none">{t('common.selectAllCurrent')}</span>
              </label>
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
          <DashboardStateBlock
            loading
            compact
            title={t('stockBar.loading')}
          />
        ) : items.length === 0 ? (
          <DashboardStateBlock
            title={t('stockBar.emptyTitle')}
            description={t('stockBar.emptyDescription')}
            icon={(
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
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
                    <div className="pt-5">
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggleCode(code)}
                        disabled={isDeleting}
                        className="chat-skill-checkbox cursor-pointer"
                      />
                    </div>
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
