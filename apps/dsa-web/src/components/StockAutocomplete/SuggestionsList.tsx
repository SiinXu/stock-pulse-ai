/**
 * Stock search suggestion list.
 */

import type { CSSProperties } from 'react';
import type { StockSuggestion } from '../../types/stockIndex';
import { Badge } from '../common';
import { cn } from '../../utils/cn';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { STOCK_SEARCH_TEXT } from '../../locales/stockSearch';
import { getOverlayStyle } from '../common/overlayZ';

export interface SuggestionsListProps {
  /** Suggestion list */
  suggestions: StockSuggestion[];
  /** Highlighted index */
  highlightedIndex: number;
  /** Selection callback */
  onSelect: (suggestion: StockSuggestion) => void;
  /** Mouse hover callback */
  onMouseEnter: (index: number) => void;
  /** Custom style (for Portal fixed positioning) */
  style?: CSSProperties;
}

export function SuggestionsList({
  suggestions,
  highlightedIndex,
  onSelect,
  onMouseEnter,
  style,
}: SuggestionsListProps) {
  if (suggestions.length === 0) {
    return null;
  }

  return (
    <ul
      id="suggestions-list"
      data-dialog-popup="true"
      className="max-h-60 overflow-auto rounded-b-lg rounded-t-none border-x border-b shadow-xl"
      style={getOverlayStyle('popover', {
        ...style,
        backgroundColor: 'hsl(var(--card))',
        borderColor: 'hsl(var(--border))',
      })}
      role="listbox"
    >
      {suggestions.map((suggestion, index) => (
        <li
          key={suggestion.canonicalCode}
          role="option"
          aria-selected={index === highlightedIndex}
          className={cn(
            'px-4 py-2 cursor-pointer flex items-center justify-between',
            'hover:bg-muted',
            index === highlightedIndex && 'bg-muted',
          )}
          onClick={() => onSelect(suggestion)}
          onMouseEnter={() => onMouseEnter(index)}
        >
          <div className="flex items-center gap-3">
            <MarketBadge market={suggestion.market} />

            <div className="flex flex-col">
              <span className="text-sm font-medium text-primary-text">
                {suggestion.nameZh}
              </span>
              <span className="text-sm text-secondary-text">
                {suggestion.displayCode}
              </span>
            </div>
          </div>

          <MatchTypeBadge matchType={suggestion.matchType} />
        </li>
      ))}
    </ul>
  );
}

const MARKET_BADGE_CONFIG = {
  CN: { labelKey: 'marketCN', className: 'border-danger/25 bg-danger/10 text-danger' },
  HK: { labelKey: 'marketHK', className: 'border-success/25 bg-success/10 text-success' },
  US: { labelKey: 'marketUS', className: 'border-primary/25 bg-primary/10 text-primary' },
  JP: { labelKey: 'marketJP', className: 'border-indigo-500/25 bg-indigo-500/10 text-indigo-500' },
  KR: { labelKey: 'marketKR', className: 'border-rose-500/25 bg-rose-500/10 text-rose-500' },
  INDEX: { labelKey: 'marketIndex', className: 'border-secondary-text/25 bg-secondary-text/10 text-secondary-text' },
  ETF: { labelKey: null, className: 'border-warning/25 bg-warning/10 text-warning' },
  BSE: { labelKey: 'marketBSE', className: 'border-orange-500/25 bg-orange-500/10 text-orange-500' },
} as const;

function MarketBadge({ market }: { market: string }) {
  const { language } = useUiLanguage();
  const config = MARKET_BADGE_CONFIG[market as keyof typeof MARKET_BADGE_CONFIG];

  if (!config) {
    throw new Error(`Unsupported market in stock suggestion: ${market}`);
  }

  return (
    <Badge variant="default" size="sm" className={cn('min-w-[3rem] justify-center shadow-none', config.className)}>
      {config.labelKey ? STOCK_SEARCH_TEXT[language][config.labelKey] : 'ETF'}
    </Badge>
  );
}

function MatchTypeBadge({ matchType }: { matchType: string }) {
  const { language } = useUiLanguage();
  const text = STOCK_SEARCH_TEXT[language];
  const configMap = {
    exact: { label: text.matchExact, className: 'border-primary/25 bg-primary/10 text-primary' },
    prefix: { label: text.matchPrefix, className: 'border-secondary-text/25 bg-secondary-text/10 text-secondary-text' },
    contains: { label: text.matchContains, className: 'border-warning/25 bg-warning/10 text-warning' },
    fuzzy: { label: text.matchFuzzy, className: 'border-border/55 bg-elevated/75 text-muted-text' },
  };

  const config = configMap[matchType as keyof typeof configMap] || configMap.fuzzy;

  return (
    <Badge variant="default" size="sm" className={cn('shrink-0 shadow-none', config.className)}>
      {config.label}
    </Badge>
  );
}

export default SuggestionsList;
