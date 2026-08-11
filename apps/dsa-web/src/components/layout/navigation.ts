import type { MouseEvent as ReactMouseEvent } from 'react';
import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  BarChart3,
  BriefcaseBusiness,
  Calculator,
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

// Keep the five primary domains stable while secondary routes remain discoverable
// in collapsible expanded groups and the compact flyout.
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
      // Order follows Research IA: Market → Discover → Analysis → Backtest → Skill outcomes.
      { kind: 'link', key: 'research-market', labelKey: 'layout.nav.marketReview', to: APP_ROUTE_PATHS.researchMarket, icon: BarChart3 },
      { kind: 'link', key: 'research-discover', labelKey: 'layout.nav.discover', to: APP_ROUTE_PATHS.researchDiscover, icon: Search },
      { kind: 'link', key: 'research-analysis', labelKey: 'layout.nav.analysis', to: APP_ROUTE_PATHS.researchAnalysis, icon: FlaskConical },
      { kind: 'link', key: 'research-backtest', labelKey: 'layout.nav.backtest', to: APP_ROUTE_PATHS.researchBacktest, icon: Activity },
      { kind: 'link', key: 'research-calculators', labelKey: 'layout.nav.calculators', to: APP_ROUTE_PATHS.calculators, icon: Calculator },
      { kind: 'link', key: 'research-skill-outcomes', labelKey: 'layout.nav.skillOutcomes', to: APP_ROUTE_PATHS.researchSkillOutcomes, icon: Gauge },
    ],
  },
  { kind: 'link', key: 'portfolio', labelKey: 'layout.nav.portfolio', to: APP_ROUTE_PATHS.portfolio, icon: BriefcaseBusiness },
  { kind: 'link', key: 'agent', labelKey: 'layout.nav.agent', to: APP_ROUTE_PATHS.agent, icon: MessageSquareQuote, badge: 'completion' },
  { kind: 'link', key: 'settings', labelKey: 'layout.nav.settings', to: APP_ROUTE_PATHS.settings, icon: Settings2 },
];
