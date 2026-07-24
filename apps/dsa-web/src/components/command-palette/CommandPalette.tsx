// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import {
  Activity,
  BarChart3,
  BellRing,
  BriefcaseBusiness,
  ChartNoAxesCombined,
  ClipboardCheck,
  FlaskConical,
  MessageSquareQuote,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { StockAutocomplete } from '../StockAutocomplete';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import { NOTIFICATIONS_TEXT } from '../../locales/notifications';
import {
  APP_ROUTE_PATHS,
  SIGNAL_CENTER_SCOPE_VALUES,
  SIGNAL_CENTER_TAB_VALUES,
  buildSignalCenterHref,
} from '../../routing/routes';
import { cn } from '../../utils/cn';
import { Modal } from '../common/Modal';
import { SearchInput } from '../common/SearchInput';
import type { LucideIcon } from 'lucide-react';

type CommandItem = {
  id: string;
  labelKey: UiTextKey;
  href: string;
  icon: LucideIcon;
};

export type CommandPaletteProps = {
  isOpen: boolean;
  onClose: () => void;
  analysisHref?: string;
  onNavigate?: (href: string) => void;
};

export function CommandPalette({
  isOpen,
  onClose,
  analysisHref = APP_ROUTE_PATHS.researchAnalysis,
  onNavigate,
}: CommandPaletteProps) {
  const { language, t } = useUiLanguage();
  const text = NOTIFICATIONS_TEXT[language];
  const navigate = useNavigate();
  const searchRef = useRef<HTMLInputElement>(null);
  const commandRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [query, setQuery] = useState('');
  const [stockQuery, setStockQuery] = useState('');

  const pages = useMemo<CommandItem[]>(() => [
    { id: 'analysis', labelKey: 'home.startAnalysisTitle', href: analysisHref, icon: ChartNoAxesCombined },
    { id: 'signals', labelKey: 'layout.nav.decisionSignals', href: APP_ROUTE_PATHS.signals, icon: BellRing },
    { id: 'market', labelKey: 'home.marketReview', href: APP_ROUTE_PATHS.researchMarket, icon: BarChart3 },
    { id: 'discover', labelKey: 'layout.nav.discover', href: APP_ROUTE_PATHS.researchDiscover, icon: Search },
    { id: 'backtest', labelKey: 'layout.nav.backtest', href: APP_ROUTE_PATHS.researchBacktest, icon: FlaskConical },
    { id: 'portfolio', labelKey: 'layout.nav.portfolio', href: APP_ROUTE_PATHS.portfolio, icon: BriefcaseBusiness },
    { id: 'agent', labelKey: 'layout.nav.agent', href: APP_ROUTE_PATHS.agent, icon: MessageSquareQuote },
    { id: 'settings', labelKey: 'layout.nav.settings', href: APP_ROUTE_PATHS.settings, icon: Settings2 },
  ], [analysisHref]);
  const actions = useMemo<CommandItem[]>(() => [
    { id: 'run-analysis', labelKey: 'home.analyze', href: analysisHref, icon: Sparkles },
    { id: 'create-rule', labelKey: 'decisionSignals.createFirstRule', href: buildSignalCenterHref({ createRule: true }), icon: ShieldCheck },
    { id: 'scope-all', labelKey: 'decisionSignals.scopeAllSignals', href: buildSignalCenterHref({ scope: SIGNAL_CENTER_SCOPE_VALUES.all }), icon: Activity },
    { id: 'scope-holdings', labelKey: 'decisionSignals.scopeHoldings', href: buildSignalCenterHref({ scope: SIGNAL_CENTER_SCOPE_VALUES.holdings }), icon: BriefcaseBusiness },
    { id: 'scope-watchlist', labelKey: 'decisionSignals.scopeWatchlist', href: buildSignalCenterHref({ scope: SIGNAL_CENTER_SCOPE_VALUES.watchlist }), icon: ClipboardCheck },
    { id: 'review-signals', labelKey: 'decisionSignals.tab.review', href: buildSignalCenterHref({ tab: SIGNAL_CENTER_TAB_VALUES.review }), icon: Activity },
  ], [analysisHref]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const frame = window.requestAnimationFrame(() => {
      setQuery('');
      setStockQuery('');
      searchRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [isOpen]);

  const normalizedQuery = query.trim().toLocaleLowerCase();
  const matchesQuery = (item: CommandItem) => (
    normalizedQuery.length === 0 || t(item.labelKey).toLocaleLowerCase().includes(normalizedQuery)
  );
  const visiblePages = pages.filter(matchesQuery);
  const visibleActions = actions.filter(matchesQuery);
  const visibleCommands = [...visiblePages, ...visibleActions];

  const selectHref = (href: string) => {
    onClose();
    if (onNavigate) onNavigate(href);
    else navigate(href);
  };

  const selectStock = (stockCode: string) => {
    const normalizedCode = stockCode.trim();
    if (!normalizedCode) return;
    selectHref(
      APP_ROUTE_PATHS.stockDetails.replace(':stockCode', encodeURIComponent(normalizedCode)),
    );
  };

  const focusCommand = (index: number) => {
    if (visibleCommands.length === 0) return;
    const normalizedIndex = (index + visibleCommands.length) % visibleCommands.length;
    commandRefs.current[normalizedIndex]?.focus();
  };

  const handleSearchKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      focusCommand(0);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      focusCommand(visibleCommands.length - 1);
    }
  };

  const renderGroup = (label: string, items: CommandItem[], offset: number) => {
    if (items.length === 0) return null;
    return (
      <section>
        <h3 className="mb-1 px-2 text-xs font-medium uppercase text-muted-text">{label}</h3>
        <div className="space-y-1">
          {items.map((item, itemIndex) => {
            const commandIndex = offset + itemIndex;
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                ref={(node) => { commandRefs.current[commandIndex] = node; }}
                type="button"
                onClick={() => selectHref(item.href)}
                onKeyDown={(event) => {
                  if (event.key === 'ArrowDown') {
                    event.preventDefault();
                    focusCommand(commandIndex + 1);
                  } else if (event.key === 'ArrowUp') {
                    event.preventDefault();
                    focusCommand(commandIndex - 1);
                  } else if (event.key === 'Home') {
                    event.preventDefault();
                    focusCommand(0);
                  } else if (event.key === 'End') {
                    event.preventDefault();
                    focusCommand(visibleCommands.length - 1);
                  }
                }}
                className={cn(
                  'flex min-h-10 w-full items-center gap-3 rounded-md px-2 text-left text-sm text-foreground',
                  'hover:bg-hover focus-visible:bg-hover focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/25',
                )}
              >
                <Icon className="size-4 shrink-0 text-secondary-text" aria-hidden="true" />
                <span className="truncate">{t(item.labelKey)}</span>
              </button>
            );
          })}
        </div>
      </section>
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={text.paletteTitle}
      description={text.paletteDescription}
      size="wide"
    >
      <div className="space-y-5">
        <SearchInput
          ref={searchRef}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={handleSearchKeyDown}
          placeholder={text.searchPlaceholder}
          aria-label={text.searchPlaceholder}
          wrapperClassName="h-10 sm:h-10"
        />

        <div className="max-h-[40dvh] space-y-4 overflow-y-auto pr-1">
          {renderGroup(text.pagesGroup, visiblePages, 0)}
          {renderGroup(text.actionsGroup, visibleActions, visiblePages.length)}
          {visibleCommands.length === 0 ? (
            <p className="px-2 py-4 text-center text-sm text-secondary-text">{text.noResults}</p>
          ) : null}
        </div>

        <section className="border-t border-border pt-4">
          <h3 className="mb-2 text-xs font-medium uppercase text-muted-text">{text.stocksGroup}</h3>
          <StockAutocomplete
            value={stockQuery}
            onChange={setStockQuery}
            onSubmit={selectStock}
            placeholder={t('common.searchPlaceholder')}
            ariaLabel={text.stocksGroup}
          />
        </section>
      </div>
    </Modal>
  );
}
