// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import {
  Activity,
  BarChart3,
  BellRing,
  BriefcaseBusiness,
  Calculator,
  ClipboardCheck,
  FileText,
  FlaskConical,
  Gauge,
  Home,
  LineChart,
  MessageSquareQuote,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import { NOTIFICATIONS_TEXT } from '../../locales/notifications';
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  APP_ROUTE_PATHS,
  RESEARCH_MARKET_ACTION_VALUES,
  SIGNAL_CENTER_SCOPE_VALUES,
  SIGNAL_CENTER_TAB_VALUES,
  buildAnalysisWorkbenchHref,
  buildResearchMarketHref,
  buildSignalCenterHref,
} from '../../routing/routes';
import { cn } from '../../utils/cn';
import { formatDateTime, formatReportType } from '../../utils/format';
import { Modal } from '../common/Modal';
import { SearchInput } from '../common/SearchInput';
import { Spinner } from '../common/Spinner';
import { useCommandPaletteSearch } from './useCommandPaletteSearch';
import type { LucideIcon } from 'lucide-react';

type CommandItem = {
  id: string;
  href: string;
  icon: LucideIcon;
} & (
  | { labelKey: UiTextKey; label?: never }
  | { label: string; labelKey?: never }
);

type PaletteResult = {
  id: string;
  href: string;
  icon: LucideIcon;
  label: string;
  description?: string;
  meta?: string;
};

type PaletteGroup = {
  id: string;
  label: string;
  items: PaletteResult[];
};

export type CommandPaletteProps = {
  isOpen: boolean;
  onClose: () => void;
  analysisHref?: string;
  onNavigate?: (href: string) => void;
};

function optionId(result: PaletteResult): string {
  return `command-palette-option-${result.id.replace(/[^A-Za-z0-9_-]/g, '-')}`;
}

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
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(-1);
  const search = useCommandPaletteSearch(query, isOpen);

  const pages = useMemo<CommandItem[]>(() => [
    { id: 'home', labelKey: 'layout.nav.home', href: APP_ROUTE_PATHS.home, icon: Home },
    { id: 'signals', labelKey: 'layout.nav.decisionSignals', href: APP_ROUTE_PATHS.signals, icon: BellRing },
    { id: 'research', labelKey: 'layout.nav.research', href: APP_ROUTE_PATHS.research, icon: Search },
    { id: 'market', labelKey: 'layout.nav.marketReview', href: APP_ROUTE_PATHS.researchMarket, icon: BarChart3 },
    { id: 'discover', labelKey: 'layout.nav.discover', href: APP_ROUTE_PATHS.researchDiscover, icon: Search },
    { id: 'analysis', labelKey: 'layout.nav.analysis', href: analysisHref, icon: FlaskConical },
    { id: 'backtest', labelKey: 'layout.nav.backtest', href: APP_ROUTE_PATHS.researchBacktest, icon: Activity },
    { id: 'calculators', labelKey: 'layout.nav.calculators', href: APP_ROUTE_PATHS.calculators, icon: Calculator },
    { id: 'skill-outcomes', labelKey: 'layout.nav.skillOutcomes', href: APP_ROUTE_PATHS.researchSkillOutcomes, icon: Gauge },
    { id: 'portfolio', labelKey: 'layout.nav.portfolio', href: APP_ROUTE_PATHS.portfolio, icon: BriefcaseBusiness },
    { id: 'agent', labelKey: 'layout.nav.agent', href: APP_ROUTE_PATHS.agent, icon: MessageSquareQuote },
    { id: 'approvals', labelKey: 'layout.nav.approvals', href: APP_ROUTE_PATHS.approvals, icon: ClipboardCheck },
    { id: 'settings', labelKey: 'layout.nav.settings', href: APP_ROUTE_PATHS.settings, icon: Settings2 },
  ], [analysisHref]);
  const actions = useMemo<CommandItem[]>(() => [
    { id: 'run-analysis', labelKey: 'home.startAnalysisTitle', href: analysisHref, icon: Sparkles },
    { id: 'create-rule', labelKey: 'decisionSignals.createFirstRule', href: buildSignalCenterHref({ createRule: true }), icon: ShieldCheck },
    { id: 'scope-all', labelKey: 'decisionSignals.scopeAllSignals', href: buildSignalCenterHref({ scope: SIGNAL_CENTER_SCOPE_VALUES.all }), icon: Activity },
    { id: 'scope-holdings', labelKey: 'decisionSignals.scopeHoldings', href: buildSignalCenterHref({ scope: SIGNAL_CENTER_SCOPE_VALUES.holdings }), icon: BriefcaseBusiness },
    { id: 'scope-watchlist', labelKey: 'decisionSignals.scopeWatchlist', href: buildSignalCenterHref({ scope: SIGNAL_CENTER_SCOPE_VALUES.watchlist }), icon: ClipboardCheck },
    { id: 'run-market-review', label: text.runMarketReview, href: buildResearchMarketHref({ action: RESEARCH_MARKET_ACTION_VALUES.run }), icon: BarChart3 },
    { id: 'review-signals', labelKey: 'decisionSignals.tab.review', href: buildSignalCenterHref({ tab: SIGNAL_CENTER_TAB_VALUES.review }), icon: Activity },
  ], [analysisHref, text.runMarketReview]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const frame = window.requestAnimationFrame(() => {
      setQuery('');
      setActiveIndex(-1);
      searchRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [isOpen]);

  const normalizedQuery = query.trim().toLocaleLowerCase();
  const commandResult = (item: CommandItem, resultType: 'page' | 'action'): PaletteResult => ({
    id: `${resultType}-${item.id}`,
    href: item.href,
    icon: item.icon,
    label: item.label ?? t(item.labelKey),
  });
  const matchesQuery = (item: CommandItem) => {
    const label = item.label ?? t(item.labelKey);
    return normalizedQuery.length === 0 || label.toLocaleLowerCase().includes(normalizedQuery);
  };
  const stockResults = search.stocks.map<PaletteResult>((stock) => ({
    id: `stock-${stock.canonicalCode}`,
    href: APP_ROUTE_PATHS.stockDetails.replace(
      ':stockCode',
      encodeURIComponent(stock.canonicalCode),
    ),
    icon: LineChart,
    label: stock.nameZh || stock.displayCode,
    description: stock.displayCode,
    meta: stock.market,
  }));
  const reportResults = search.reports.map<PaletteResult>((report) => ({
    id: `report-${report.id}`,
    href: buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      recordId: report.id,
      stock: report.stockCode,
    }),
    icon: FileText,
    label: report.stockName
      ? `${report.stockName} (${report.stockCode})`
      : report.stockCode,
    description: report.summary ?? formatReportType(report.reportType, language),
    meta: `${formatReportType(report.reportType, language)} · ${formatDateTime(report.createdAt, language)}`,
  }));
  const groups: PaletteGroup[] = [
    { id: 'stocks', label: text.stocksGroup, items: stockResults },
    { id: 'reports', label: text.reportsGroup, items: reportResults },
    {
      id: 'pages',
      label: text.pagesGroup,
      items: pages.filter(matchesQuery).map((item) => commandResult(item, 'page')),
    },
    {
      id: 'actions',
      label: text.actionsGroup,
      items: actions.filter(matchesQuery).map((item) => commandResult(item, 'action')),
    },
  ].filter((group) => group.items.length > 0);
  const visibleResults = groups.flatMap((group) => group.items);
  const safeActiveIndex = activeIndex < visibleResults.length ? activeIndex : -1;
  const activeResult = safeActiveIndex >= 0 ? visibleResults[safeActiveIndex] : undefined;

  const selectHref = (href: string) => {
    onClose();
    if (onNavigate) onNavigate(href);
    else navigate(href);
  };

  const moveActive = (direction: 1 | -1) => {
    if (visibleResults.length === 0) return;
    setActiveIndex((current) => {
      if (current < 0 || current >= visibleResults.length) {
        return direction === 1 ? 0 : visibleResults.length - 1;
      }
      return (current + direction + visibleResults.length) % visibleResults.length;
    });
  };

  const handleSearchKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      moveActive(1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      moveActive(-1);
    } else if (event.key === 'Home' && visibleResults.length > 0) {
      event.preventDefault();
      setActiveIndex(0);
    } else if (event.key === 'End' && visibleResults.length > 0) {
      event.preventDefault();
      setActiveIndex(visibleResults.length - 1);
    } else if (event.key === 'Enter' && activeResult) {
      event.preventDefault();
      selectHref(activeResult.href);
    }
  };

  let resultOffset = 0;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={text.paletteTitle}
      description={text.paletteDescription}
      size="wide"
    >
      <div className="space-y-4">
        <SearchInput
          ref={searchRef}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActiveIndex(-1);
          }}
          onKeyDown={handleSearchKeyDown}
          placeholder={text.searchPlaceholder}
          aria-label={text.searchPlaceholder}
          role="combobox"
          aria-autocomplete="list"
          aria-controls="command-palette-results"
          aria-expanded={visibleResults.length > 0}
          aria-activedescendant={activeResult ? optionId(activeResult) : undefined}
          autoComplete="off"
          wrapperClassName="h-10 sm:h-10"
        />

        <div
          id="command-palette-results"
          role="listbox"
          aria-label={text.paletteDescription}
          aria-busy={search.isLoading}
          className="max-h-[55dvh] space-y-4 overflow-y-auto pr-1"
        >
          {groups.map((group) => {
            const groupOffset = resultOffset;
            resultOffset += group.items.length;
            const labelId = `command-palette-${group.id}-label`;
            return (
              <section key={group.id} role="group" aria-labelledby={labelId}>
                <h3 id={labelId} className="mb-1 px-2 text-xs font-medium uppercase text-muted-text">
                  {group.label}
                </h3>
                <div className="space-y-1">
                  {group.items.map((result, itemIndex) => {
                    const resultIndex = groupOffset + itemIndex;
                    const Icon = result.icon;
                    const selected = resultIndex === safeActiveIndex;
                    return (
                      <button
                        key={result.id}
                        id={optionId(result)}
                        type="button"
                        role="option"
                        aria-selected={selected}
                        tabIndex={-1}
                        onClick={() => selectHref(result.href)}
                        onMouseMove={() => setActiveIndex(resultIndex)}
                        className={cn(
                          'flex min-h-11 w-full items-center gap-3 rounded-md px-2 text-left text-sm text-foreground',
                          'hover:bg-hover focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/25',
                          selected && 'bg-hover ring-2 ring-primary/20',
                        )}
                      >
                        <Icon className="size-4 shrink-0 text-secondary-text" aria-hidden="true" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium">{result.label}</span>
                          {result.description ? (
                            <span className="block truncate text-xs text-secondary-text">
                              {result.description}
                            </span>
                          ) : null}
                        </span>
                        {result.meta ? (
                          <span className="shrink-0 text-xs text-muted-text">{result.meta}</span>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              </section>
            );
          })}

          {search.isLoading ? (
            <div role="status" className="flex items-center justify-center gap-2 px-2 py-4 text-sm text-secondary-text">
              <Spinner size="sm" />
              <span>{t('common.loading')}</span>
            </div>
          ) : null}
          {search.hasError ? (
            <p role="alert" className="px-2 py-3 text-center text-sm text-danger">
              {text.searchUnavailable}
            </p>
          ) : null}
          {normalizedQuery.length > 0
            && !search.isLoading
            && !search.hasError
            && visibleResults.length === 0 ? (
              <p role="status" className="px-2 py-4 text-center text-sm text-secondary-text">
                {text.noResults}
              </p>
            ) : null}
        </div>
      </div>
    </Modal>
  );
}
