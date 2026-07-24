import type { MouseEvent as ReactMouseEvent } from 'react';
import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  BarChart3,
  BriefcaseBusiness,
  FlaskConical,
  Home,
  MessageSquareQuote,
  Search,
  Settings2,
} from 'lucide-react';
import type { UiTextKey } from '../../i18n/uiText';
import { APP_ROUTE_PATHS } from '../../routing/routes';

export type ApplicationNavigationItem = {
  key: string;
  labelKey: UiTextKey;
  to: string;
  icon: LucideIcon;
  exact?: boolean;
  badge?: 'completion';
  children?: readonly ApplicationNavigationItem[];
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

// Keep the five primary domains stable while secondary routes remain discoverable
// in collapsible expanded groups and the compact flyout.
export const APPLICATION_NAVIGATION_ITEMS: readonly ApplicationNavigationItem[] = [
  {
    key: 'home',
    labelKey: 'layout.nav.home',
    to: APP_ROUTE_PATHS.home,
    icon: Home,
    exact: true,
  },
  {
    key: 'research',
    labelKey: 'layout.nav.research',
    to: APP_ROUTE_PATHS.researchMarket,
    icon: Search,
    children: [
      { key: 'research-market', labelKey: 'home.marketReview', to: APP_ROUTE_PATHS.researchMarket, icon: BarChart3 },
      { key: 'research-discover', labelKey: 'layout.nav.discover', to: APP_ROUTE_PATHS.researchDiscover, icon: Search },
      { key: 'research-analysis', labelKey: 'analysisWorkbench.title', to: APP_ROUTE_PATHS.researchAnalysis, icon: FlaskConical },
      { key: 'research-backtest', labelKey: 'layout.nav.backtest', to: APP_ROUTE_PATHS.researchBacktest, icon: Activity },
    ],
  },
  { key: 'portfolio', labelKey: 'layout.nav.portfolio', to: APP_ROUTE_PATHS.portfolio, icon: BriefcaseBusiness },
  { key: 'agent', labelKey: 'layout.nav.agent', to: APP_ROUTE_PATHS.agent, icon: MessageSquareQuote, badge: 'completion' },
  { key: 'settings', labelKey: 'layout.nav.settings', to: APP_ROUTE_PATHS.settings, icon: Settings2 },
];
