import React, { useEffect, useState } from 'react';
import { Activity, BarChart3, Bell, BriefcaseBusiness, Gauge, Home, LogOut, MessageSquareQuote, PanelLeft, PanelRight, Search, Settings2 } from 'lucide-react';
import { NavLink, useNavigate } from 'react-router-dom';
import { ALPHASIFT_CONFIG_CHANGED_EVENT, SYSTEM_CONFIG_CHANGED_EVENT, alphasiftApi } from '../../api/alphasift';
import { useAuth } from '../../contexts/AuthContext';
import { useAgentChatStore } from '../../stores/agentChatStore';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import { cn } from '../../utils/cn';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { StatusDot } from '../common/StatusDot';
import { UiLanguageToggle } from '../i18n/UiLanguageToggle';
import { ThemeToggle } from '../theme/ThemeToggle';

type SidebarNavProps = {
  collapsed?: boolean;
  onNavigate?: () => void;
  onToggleCollapse?: () => void;
  variant?: 'default' | 'rail';
};

type NavItem = {
  key: string;
  labelKey: UiTextKey;
  to: string;
  icon: React.ComponentType<{ className?: string }>;
  exact?: boolean;
  badge?: 'completion';
};

const NAV_ITEMS: NavItem[] = [
  { key: 'home', labelKey: 'layout.nav.home', to: '/', icon: Home, exact: true },
  { key: 'chat', labelKey: 'layout.nav.chat', to: '/chat', icon: MessageSquareQuote, badge: 'completion' },
  { key: 'screening', labelKey: 'layout.nav.screening', to: '/screening', icon: Search },
  { key: 'portfolio', labelKey: 'layout.nav.portfolio', to: '/portfolio', icon: BriefcaseBusiness },
  { key: 'decision-signals', labelKey: 'layout.nav.decisionSignals', to: '/decision-signals', icon: Activity },
  { key: 'backtest', labelKey: 'layout.nav.backtest', to: '/backtest', icon: BarChart3 },
  { key: 'alerts', labelKey: 'layout.nav.alerts', to: '/alerts', icon: Bell },
  { key: 'usage', labelKey: 'layout.nav.usage', to: '/usage', icon: Gauge },
  { key: 'settings', labelKey: 'layout.nav.settings', to: '/settings', icon: Settings2 },
];

export const SidebarNav: React.FC<SidebarNavProps> = ({ collapsed = false, onNavigate, onToggleCollapse, variant = 'default' }) => {
  const { authEnabled, logout } = useAuth();
  const { t } = useUiLanguage();
  const navigate = useNavigate();

  const openSearch = () => {
    navigate('/');
    onNavigate?.();
  };
  const completionBadge = useAgentChatStore((state) => state.completionBadge);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const [showAlphaSiftNav, setShowAlphaSiftNav] = useState(false);

  useEffect(() => {
    let active = true;

    const refreshAlphaSiftStatus = async () => {
      try {
        const status = await alphasiftApi.getStatus();
        if (active) {
          setShowAlphaSiftNav(status.enabled);
        }
      } catch {
        if (active) {
          setShowAlphaSiftNav(false);
        }
      }
    };

    void refreshAlphaSiftStatus();
    window.addEventListener(ALPHASIFT_CONFIG_CHANGED_EVENT, refreshAlphaSiftStatus);
    window.addEventListener(SYSTEM_CONFIG_CHANGED_EVENT, refreshAlphaSiftStatus);

    return () => {
      active = false;
      window.removeEventListener(ALPHASIFT_CONFIG_CHANGED_EVENT, refreshAlphaSiftStatus);
      window.removeEventListener(SYSTEM_CONFIG_CHANGED_EVENT, refreshAlphaSiftStatus);
    };
  }, []);

  const navItems = showAlphaSiftNav ? NAV_ITEMS : NAV_ITEMS.filter((item) => item.key !== 'screening');
  const isRail = variant === 'rail';
  const itemBaseClass = cn(
    'group relative flex h-[var(--nav-item-height)] w-full items-center overflow-hidden rounded-full border border-transparent text-sm leading-none text-secondary-text transition-all',
    isRail
      ? 'justify-center gap-2.5 px-2'
      : collapsed
        ? 'justify-center px-0'
        : 'gap-3 px-[var(--nav-item-padding-x)]'
  );
  const itemInteractiveClass = cn(
    itemBaseClass,
    'hover:bg-[var(--nav-hover-bg)] hover:text-foreground'
  );
  const itemActiveClass = 'border-[var(--nav-active-border)] bg-[var(--nav-active-bg)] font-medium text-foreground shadow-[0_1px_2px_var(--nav-active-shadow)]';
  const itemIconClass = cn('h-5 w-5', 'shrink-0');
  const itemLabelClass = cn('truncate', isRail ? 'text-center' : '');

  return (
    <>
      {collapsed ? (
        <div className="mb-4 flex justify-center">
          <div className="group relative h-11 w-11">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-primary text-primary-foreground transition-opacity group-hover:opacity-0">
              <BarChart3 className="size-4.5" />
            </div>
            {onToggleCollapse ? (
              <button
                type="button"
                onClick={onToggleCollapse}
                aria-label={t('layout.expandSidebar')}
                className="absolute inset-0 flex h-11 w-11 items-center justify-center rounded-full border border-border bg-card text-secondary-text opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100"
              >
                <PanelRight className="size-4.5" />
              </button>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="mb-4 flex items-center gap-2 px-1">
          <div className="flex h-8 w-8 items-center justify-center rounded-sm bg-primary text-primary-foreground">
            <BarChart3 className="size-4.5" />
          </div>
          <p className="min-w-0 flex-1 truncate text-xl font-bold tracking-tight text-foreground">StockPulse</p>
          {onToggleCollapse ? (
            <button
              type="button"
              onClick={onToggleCollapse}
              aria-label={t('layout.collapseSidebar')}
              className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-transparent text-secondary-text transition-colors hover:bg-[var(--nav-hover-bg)] hover:text-foreground"
            >
              <PanelLeft className="size-4.5" />
            </button>
          ) : null}
        </div>
      )}

      {collapsed ? (
        <button
          type="button"
          onClick={openSearch}
          aria-label={t('layout.search')}
          className="mb-3 flex h-11 w-11 items-center justify-center self-center rounded-full border border-border bg-card text-muted-text transition-colors hover:bg-hover hover:text-foreground"
        >
          <Search className="h-4 w-4" />
        </button>
      ) : (
        <>
          <button
            type="button"
            onClick={openSearch}
            aria-label={t('layout.search')}
            className="mb-3 flex min-h-11 w-full items-center justify-between rounded-full border border-border bg-card px-2.5 py-2 text-left shadow-soft-card transition-colors hover:bg-hover"
          >
            <span className="flex items-center gap-2 text-xs text-muted-text">
              <Search className="h-4 w-4" />
              {t('layout.search')}
            </span>
            <kbd className="flex h-5 w-5 items-center justify-center rounded bg-muted text-xs font-medium text-secondary-text">/</kbd>
          </button>
          <div className="mb-3 border-t border-dashed border-border" />
        </>
      )}

      <nav className={cn('flex flex-col gap-1', isRail ? '' : 'flex-1')} aria-label={t('layout.mainNav')}>
        {navItems.map(({ key, labelKey, to, icon: Icon, exact, badge }) => {
          const label = t(labelKey);
          return (
          <NavLink
            key={key}
            to={to}
            end={exact}
            onClick={onNavigate}
            aria-label={label}
            className={({ isActive }) =>
              cn(
                itemInteractiveClass,
                isActive ? itemActiveClass : ''
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon className={cn(itemIconClass, isActive ? 'text-[var(--nav-icon-active)]' : 'text-current')} />
                {!collapsed ? <span className={itemLabelClass}>{label}</span> : null}
                {badge === 'completion' && completionBadge ? (
                  <StatusDot
                    tone="info"
                    data-testid="chat-completion-badge"
                    className={cn(
                      'absolute right-3 border-2 border-background shadow-soft-card',
                      collapsed ? 'right-2 top-2' : ''
                    )}
                    aria-label={t('layout.newChatMessage')}
                  />
                ) : null}
              </>
            )}
          </NavLink>
        );
        })}

      </nav>

      <div className={cn('mt-2 flex gap-1', collapsed ? 'flex-col items-center' : 'items-center')}>
        <ThemeToggle
          variant="nav"
          collapsed
          wrapperClassName={collapsed ? '' : 'flex-1'}
          triggerClassName={cn('inline-flex h-11 items-center justify-center rounded-full border border-transparent text-secondary-text transition-colors hover:bg-[var(--nav-hover-bg)] hover:text-foreground', collapsed ? 'w-11' : 'w-full')}
          triggerActiveClassName={itemActiveClass}
          iconClassName="size-4.5 shrink-0"
        />
        <UiLanguageToggle
          variant="nav"
          collapsed
          wrapperClassName={collapsed ? '' : 'flex-1'}
          triggerClassName={cn('inline-flex h-11 items-center justify-center rounded-full border border-transparent text-secondary-text transition-colors hover:bg-[var(--nav-hover-bg)] hover:text-foreground', collapsed ? 'w-11' : 'w-full')}
          triggerActiveClassName={itemActiveClass}
          iconClassName="size-4.5 shrink-0"
        />
      </div>

      {authEnabled ? (
        <button
          type="button"
          onClick={() => setShowLogoutConfirm(true)}
          className={cn(
            itemInteractiveClass,
            isRail ? 'mt-1.5' : 'mt-5'
          )}
        >
          <LogOut className={itemIconClass} />
          {!collapsed ? <span className={itemLabelClass}>{t('layout.logout')}</span> : null}
        </button>
      ) : null}

      <ConfirmDialog
        isOpen={showLogoutConfirm}
        title={t('layout.logoutTitle')}
        message={t('layout.logoutMessage')}
        confirmText={t('layout.logoutConfirm')}
        cancelText={t('common.cancel')}
        isDanger
        onConfirm={() => {
          setShowLogoutConfirm(false);
          onNavigate?.();
          void logout();
        }}
        onCancel={() => setShowLogoutConfirm(false)}
      />
    </>
  );
};
