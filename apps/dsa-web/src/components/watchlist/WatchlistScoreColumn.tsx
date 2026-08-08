// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useId, useState } from 'react';
import { ChevronDown, ChevronRight, Info } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import type { WatchlistScoreItem } from '../../types/watchlistScore';
import { getSentimentColor } from '../../types/analysis';
import { cn } from '../../utils/cn';
import { Badge, InlineAlert } from '../common';

export type WatchlistScoreColumnProps = {
  item: WatchlistScoreItem;
  /** Controlled expand state; when omitted the column manages its own open state. */
  expanded?: boolean;
  onToggleExpand?: () => void;
  /** Show non-investment-advice disclaimer under the drill-down. Default true when expanded. */
  showDisclaimer?: boolean;
  className?: string;
};

function freshnessLabel(
  item: WatchlistScoreItem,
  t: (key: UiTextKey, params?: Record<string, string | number>) => string,
): string {
  if (item.status === 'unanalyzed' || item.asOf == null) {
    return t('watchlistScore.freshnessNone');
  }
  if (item.ageDays === 0) {
    return t('watchlistScore.freshnessToday');
  }
  if (typeof item.ageDays === 'number' && item.ageDays > 0) {
    return t('watchlistScore.freshnessAge', { days: item.ageDays });
  }
  return t('watchlistScore.freshnessUnknown');
}

/**
 * Independent score cell for a watchlist row (Issue #147 / T25).
 *
 * Mount via props after T23 merges — does not own watchlist layout or drag order.
 * Default sort remains manual; this column only renders a score / unanalyzed state.
 */
export const WatchlistScoreColumn: React.FC<WatchlistScoreColumnProps> = ({
  item,
  expanded: expandedProp,
  onToggleExpand,
  showDisclaimer = true,
  className,
}) => {
  const { t } = useUiLanguage();
  const panelId = useId();
  const [internalExpanded, setInternalExpanded] = useState(false);
  const expanded = expandedProp ?? internalExpanded;

  const toggle = () => {
    if (onToggleExpand) {
      onToggleExpand();
      return;
    }
    setInternalExpanded((value) => !value);
  };

  if (item.status === 'unanalyzed' || item.score === null) {
    return (
      <div
        className={cn('watchlist-score-column flex min-w-0 flex-col gap-1', className)}
        data-testid="watchlist-score-column"
        data-status="unanalyzed"
      >
        <Badge
          variant="default"
          size="sm"
          className="w-fit shadow-none font-medium text-muted-text"
          data-testid="watchlist-score-unanalyzed"
        >
          {t('watchlistScore.unanalyzed')}
        </Badge>
        <span className="text-[11px] text-muted-text">{t('watchlistScore.unanalyzedHint')}</span>
      </div>
    );
  }

  const color = getSentimentColor(item.score);
  const Chevron = expanded ? ChevronDown : ChevronRight;

  return (
    <div
      className={cn('watchlist-score-column flex min-w-0 flex-col gap-1', className)}
      data-testid="watchlist-score-column"
      data-status="scored"
    >
      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
        <button
          type="button"
          className="inline-flex min-h-8 items-center gap-1 rounded-md border border-transparent px-0.5 text-left hover:border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={toggle}
          aria-expanded={expanded}
          aria-controls={panelId}
          data-testid="watchlist-score-toggle"
        >
          <Chevron className="size-3.5 shrink-0 text-muted-text" aria-hidden />
          <Badge
            variant="default"
            size="sm"
            className="shadow-none font-semibold leading-none"
            style={{
              color,
              borderColor: `${color}30`,
              backgroundColor: `${color}10`,
            }}
            data-testid="watchlist-score-value"
          >
            {t('watchlistScore.scoreLabel', { score: item.score })}
          </Badge>
        </button>
        <span
          className="inline-flex items-center gap-0.5 text-[11px] text-muted-text"
          data-testid="watchlist-score-freshness"
          title={item.asOf ?? undefined}
        >
          <Info className="size-3 shrink-0" aria-hidden />
          {freshnessLabel(item, t)}
        </span>
      </div>

      {expanded ? (
        <div
          id={panelId}
          className="rounded-md border border-border/70 bg-muted/30 px-2.5 py-2 text-xs"
          data-testid="watchlist-score-factors"
        >
          <p className="mb-1.5 font-medium text-foreground">{t('watchlistScore.factorsTitle')}</p>
          {item.factors.length === 0 ? (
            <p className="text-muted-text">{t('watchlistScore.noFactors')}</p>
          ) : (
            <ul className="grid gap-1.5">
              {item.factors.map((factor) => (
                <li key={factor.key} className="min-w-0">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
                    <span className="text-muted-text">{factor.label}</span>
                    <span className="font-medium text-foreground">{String(factor.value)}</span>
                  </div>
                  {factor.detail ? (
                    <p className="mt-0.5 text-[11px] text-muted-text">{factor.detail}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          {item.asOf ? (
            <p className="mt-2 text-[11px] text-muted-text">
              {t('watchlistScore.asOf', { date: item.asOf })}
            </p>
          ) : null}
          {showDisclaimer ? (
            <InlineAlert
              variant="info"
              className="mt-2"
              title={t('watchlistScore.disclaimerTitle')}
              message={t('watchlistScore.disclaimer')}
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
};

export default WatchlistScoreColumn;
