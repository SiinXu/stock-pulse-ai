// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { MouseEvent as ReactMouseEvent } from 'react';
import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  BarChart3,
  BellRing,
  BriefcaseBusiness,
  Calculator,
  CalendarDays,
  ClipboardCheck,
  FlaskConical,
  Gauge,
  Home,
  MessageSquareQuote,
  Search,
  Settings2,
} from 'lucide-react';
import type { UiTextKey } from '../../i18n/uiText';
import { APP_ROUTE_PATHS } from '../../routing/routes';

type ApplicationNavigationBaseItem = {
  key: string;
  labelKey: UiTextKey;
  icon: LucideIcon;
  badge?: 'completion';
};

export type ApplicationNavigationLink = ApplicationNavigationBaseItem & {
  kind: 'link';
  to: string;
  exact?: boolean;
  children?: never;
};

export type ApplicationNavigationGroup = ApplicationNavigationBaseItem & {
  kind: 'group';
  to: string;
  exact?: boolean;
  overviewLabelKey: UiTextKey;
  children: readonly ApplicationNavigationLink[];
};

export type ApplicationNavigationItem =
  | ApplicationNavigationLink
  | ApplicationNavigationGroup;

export type CommandPalettePageDescriptor = {
  id: string;
  labelKey: UiTextKey;
  href: string;
  icon: LucideIcon;
};

export function shouldDelegateCurrentDocumentNavigation(
  event: ReactMouseEvent<HTMLAnchorElement>,
): boolean {
  const target = event.currentTarget.getAttribute('target');
  return (
    !event.defaultPrevented
    && event.button === 0
    && !event.metaKey
    && !event.ctrlKey
    && !event.shiftKey
    && !event.altKey
    && (!target || target === '_self')
    && !event.currentTarget.hasAttribute('download')
  );
}

/**
 * Primary sidebar / mobile drawer graph for the core experience spine:
 * Today → Research → Agent → Signals → Portfolio → Settings.
 *
 * Paths come only from `routes.ts` (`APP_ROUTE_PATHS`). Command palette pages
 * must be derived via `listCommandPalettePages` so membership cannot drift.
 */
export const APPLICATION_NAVIGATION_ITEMS: readonly ApplicationNavigationItem[] = [
  {
    kind: 'link',
    key: 'home',
    labelKey: 'layout.nav.home',
    to: APP_ROUTE_PATHS.home,
    icon: Home,
    exact: true,
  },
  {
    kind: 'group',
    key: 'research',
    labelKey: 'layout.nav.research',
    to: APP_ROUTE_PATHS.research,
    exact: true,
    overviewLabelKey: 'researchOverview.overviewLabel',
    icon: Search,
    children: [
      // Order follows Research IA: Market → Discover → Analysis → Backtest → Event calendar → Calculators → Skill outcomes.
      { kind: 'link', key: 'research-market', labelKey: 'layout.nav.marketReview', to: APP_ROUTE_PATHS.researchMarket, icon: BarChart3 },
      { kind: 'link', key: 'research-discover', labelKey: 'layout.nav.discover', to: APP_ROUTE_PATHS.researchDiscover, icon: Search },
      { kind: 'link', key: 'research-analysis', labelKey: 'layout.nav.analysis', to: APP_ROUTE_PATHS.researchAnalysis, icon: FlaskConical },
      { kind: 'link', key: 'research-backtest', labelKey: 'layout.nav.backtest', to: APP_ROUTE_PATHS.researchBacktest, icon: Activity },
      { kind: 'link', key: 'research-event-calendar', labelKey: 'layout.nav.eventCalendar', to: APP_ROUTE_PATHS.eventCalendar, icon: CalendarDays },
      { kind: 'link', key: 'research-calculators', labelKey: 'layout.nav.calculators', to: APP_ROUTE_PATHS.calculators, icon: Calculator },
      { kind: 'link', key: 'research-skill-outcomes', labelKey: 'layout.nav.skillOutcomes', to: APP_ROUTE_PATHS.researchSkillOutcomes, icon: Gauge },
    ],
  },
  {
    kind: 'link',
    key: 'agent',
    labelKey: 'layout.nav.agent',
    to: APP_ROUTE_PATHS.agent,
    icon: MessageSquareQuote,
    badge: 'completion',
  },
  {
    kind: 'link',
    key: 'signals',
    labelKey: 'layout.nav.decisionSignals',
    to: APP_ROUTE_PATHS.signals,
    icon: BellRing,
  },
  { kind: 'link', key: 'portfolio', labelKey: 'layout.nav.portfolio', to: APP_ROUTE_PATHS.portfolio, icon: BriefcaseBusiness },
  { kind: 'link', key: 'settings', labelKey: 'layout.nav.settings', to: APP_ROUTE_PATHS.settings, icon: Settings2 },
];

/**
 * Reachable product pages indexed by Cmd+K but intentionally outside primary sidebar.
 * Approvals stay a conditional Home/palette entry because administrator auth owns access.
 */
export const COMMAND_PALETTE_SECONDARY_PAGES: readonly ApplicationNavigationLink[] = [
  {
    kind: 'link',
    key: 'approvals',
    labelKey: 'layout.nav.approvals',
    to: APP_ROUTE_PATHS.approvals,
    icon: ClipboardCheck,
  },
];

function resolvePaletteHref(
  item: ApplicationNavigationLink | ApplicationNavigationGroup,
  analysisHref: string,
): string {
  if (item.key === 'research-analysis' || item.to === APP_ROUTE_PATHS.researchAnalysis) {
    return analysisHref;
  }
  return item.to;
}

/**
 * Single flattened page list for the command palette.
 * Primary items expand Research children; secondary pages append after Settings.
 */
export function listCommandPalettePages(
  options: { analysisHref?: string } = {},
): readonly CommandPalettePageDescriptor[] {
  const analysisHref = options.analysisHref ?? APP_ROUTE_PATHS.researchAnalysis;
  const pages: CommandPalettePageDescriptor[] = [];

  for (const item of APPLICATION_NAVIGATION_ITEMS) {
    pages.push({
      id: item.key,
      labelKey: item.labelKey,
      href: resolvePaletteHref(item, analysisHref),
      icon: item.icon,
    });
    if (item.kind === 'group') {
      for (const child of item.children) {
        pages.push({
          id: child.key,
          labelKey: child.labelKey,
          href: resolvePaletteHref(child, analysisHref),
          icon: child.icon,
        });
      }
    }
  }

  for (const item of COMMAND_PALETTE_SECONDARY_PAGES) {
    pages.push({
      id: item.key,
      labelKey: item.labelKey,
      href: resolvePaletteHref(item, analysisHref),
      icon: item.icon,
    });
  }

  return pages;
}
