import type { MouseEvent as ReactMouseEvent } from 'react';
import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  BarChart3,
  Bell,
  BriefcaseBusiness,
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

// Current flat routes remain canonical until an approved IA tuple replaces them.
export const APPLICATION_NAVIGATION_ITEMS: readonly ApplicationNavigationItem[] = [
  { key: 'home', labelKey: 'layout.nav.home', to: '/', icon: Home, exact: true },
  { key: 'chat', labelKey: 'layout.nav.chat', to: '/chat', icon: MessageSquareQuote, badge: 'completion' },
  { key: 'screening', labelKey: 'layout.nav.screening', to: '/screening', icon: Search },
  { key: 'portfolio', labelKey: 'layout.nav.portfolio', to: '/portfolio', icon: BriefcaseBusiness },
  { key: 'decision-signals', labelKey: 'layout.nav.decisionSignals', to: '/decision-signals', icon: Activity },
  { key: 'backtest', labelKey: 'layout.nav.backtest', to: '/backtest', icon: BarChart3 },
  { key: 'alerts', labelKey: 'layout.nav.alerts', to: '/alerts', icon: Bell },
  { key: 'settings', labelKey: 'layout.nav.settings', to: APP_ROUTE_PATHS.settings, icon: Settings2 },
];
