import type React from 'react';
import { Trash2 } from 'lucide-react';
import { Badge, Button, IconButton } from '../common';
import type { StockBarItem as StockBarItemType } from '../../types/analysis';
import { getSentimentColor } from '../../types/analysis';
import { buildDecisionActionLabelMap, getDecisionActionLabel } from '../../utils/decisionAction';
import { formatDateTime } from '../../utils/format';
import { getMarketPhaseSummaryLabel, stripMarketPhaseSummaryPrefix } from '../../utils/marketPhase';
import { truncateStockName } from '../../utils/stockName';
import { useUiLanguage } from '../../contexts/UiLanguageContext';

interface StockBarItemProps {
  item: StockBarItemType;
  isViewing: boolean;
  onClick: (recordId: number) => void;
  onDelete?: (stockCode: string) => void;
  isDeleting?: boolean;
  isMarketReview?: boolean;
}

export const StockBarItemComponent: React.FC<StockBarItemProps> = ({
  item,
  isViewing,
  onClick,
  onDelete,
  isDeleting = false,
  isMarketReview = false,
}) => {
  const { language, t } = useUiLanguage();
  const sentimentScore = typeof item.sentimentScore === 'number' ? item.sentimentScore : null;
  const sentimentColor = sentimentScore !== null ? getSentimentColor(sentimentScore) : null;
  const stockName = item.stockName || item.stockCode;
  const actionLabels = buildDecisionActionLabelMap(t);
  const operationLabel = getDecisionActionLabel(
    item.action,
    item.actionLabel,
    item.operationAdvice,
    t('history.sentiment'),
    actionLabels,
  );
  const phaseLabel = stripMarketPhaseSummaryPrefix(
    getMarketPhaseSummaryLabel(item.marketPhaseSummary, language),
  );

  return (
    <div
      className={`history-item relative flex items-stretch group/item ${
        isViewing ? 'history-item-selected' : ''
      }`}
    >
      <Button
        type="button"
        variant="ghost"
        size="md"
        onClick={() => onClick(item.id)}
        aria-label={t('history.itemAria', { name: stockName, code: item.stockCode })}
        className="h-auto min-w-0 flex-1 justify-start border-0 p-1.5 text-left text-foreground shadow-none hover:bg-transparent hover:text-foreground"
      >
        <div className="relative z-10 flex w-full items-center gap-2">
          {isMarketReview ? null : sentimentColor ? (
            <div
              className="h-2 w-2 flex-shrink-0 rounded-full"
              style={{
                backgroundColor: sentimentColor,
              }}
            />
          ) : (
            <div className="h-2 w-2 flex-shrink-0 rounded-full bg-subtle" />
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <span className="block w-full truncate text-sm font-semibold text-foreground">
                  {truncateStockName(stockName)}
                </span>
              </div>
              <div className="flex items-center gap-1 shrink-0" data-testid="history-card-actions">
                {isMarketReview ? (
                  <Badge
                    variant="default"
                    size="sm"
                    className="shrink-0 border-warning/30 bg-warning/10 text-xs font-semibold leading-none text-warning shadow-none"
                  >
                    {t('stockBar.market')}
                  </Badge>
                ) : sentimentColor ? (
                  <Badge
                    variant="default"
                    size="sm"
                    className="history-sentiment-badge shrink-0 text-xs font-semibold leading-none shadow-none transition-opacity duration-200"
                    style={{
                      color: sentimentColor,
                      borderColor: `${sentimentColor}30`,
                      backgroundColor: `${sentimentColor}10`,
                    }}
                  >
                    {operationLabel} {sentimentScore}
                  </Badge>
                ) : null}
              </div>
            </div>
            <div className="mt-0.5 flex min-w-0 items-center gap-1" data-testid="history-card-meta">
              {item.lastAnalysisTime && (
                <span className="min-w-0 truncate text-[0.6875rem] text-muted-text">
                  {formatDateTime(item.lastAnalysisTime, language)}
                </span>
              )}
              {item.analysisCount > 1 && (
                <span className="shrink-0 whitespace-nowrap text-[0.6875rem] text-muted-text">
                  {t('history.analysisCount', { count: item.analysisCount })}
                </span>
              )}
              {phaseLabel ? (
                <Badge variant="default" size="sm" className="shrink-0 text-xs leading-none shadow-none">
                  {phaseLabel}
                </Badge>
              ) : null}
            </div>
          </div>
        </div>
      </Button>
      {onDelete && (
        <IconButton
          visualSize="xs"
          tone="danger"
          tooltip={false}
          onClick={(e) => {
            e.stopPropagation();
            onDelete(item.stockCode);
          }}
          disabled={isDeleting}
          className="absolute right-2 top-1/2 z-20 -translate-y-1/2 opacity-0 transition-opacity before:pointer-events-none before:absolute before:-inset-y-2 before:-left-8 before:right-0 before:bg-gradient-to-l before:from-elevated before:via-elevated/95 before:to-transparent before:content-[''] group-hover/item:opacity-100 focus-visible:opacity-100"
          visualClassName="!rounded-none group-hover:!bg-transparent"
          aria-label={t('history.deleteRecord', { name: item.stockName || item.stockCode })}
        >
          <Trash2 className="h-3.5 w-3.5 text-danger" aria-hidden="true" />
        </IconButton>
      )}
    </div>
  );
};
