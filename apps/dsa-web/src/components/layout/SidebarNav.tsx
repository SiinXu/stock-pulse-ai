import React, { useState } from 'react';
import { BarChart3, LogOut, PanelLeft, PanelRight, Search } from 'lucide-react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useAgentChatStore } from '../../stores/agentChatStore';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { StatusDot } from '../common/StatusDot';
import { Tooltip } from '../common/Tooltip';
import { SidebarProfile } from './SidebarProfile';
import {
  APPLICATION_NAVIGATION_ITEMS,
  shouldDelegateCurrentDocumentNavigation,
} from './navigation';

type SidebarNavProps = {
  collapsed?: boolean;
  onNavigate?: () => void;
  onToggleCollapse?: () => void;
  variant?: 'default' | 'rail';
  focusKeyPrefix?: string;
  returnFocusKey?: string;
  profileOpen?: boolean;
  onProfileOpenChange?: (open: boolean) => void;
  profileTriggerRef?: React.Ref<HTMLButtonElement>;
  profilePresentation?: 'mobile' | 'desktop' | 'drawer';
};

export const SidebarNav: React.FC<SidebarNavProps> = ({
  collapsed = false,
  onNavigate,
  onToggleCollapse,
  variant = 'default',
  focusKeyPrefix = 'shell-nav',
  returnFocusKey,
  profileOpen,
  onProfileOpenChange,
  profileTriggerRef,
  profilePresentation,
}) => {
  const { authEnabled, logout } = useAuth();
  const { t } = useUiLanguage();
  const navigate = useNavigate();

  const openSearch = () => {
    navigate('/', { state: { focusStockSearch: true, focusToken: Date.now() } });
    onNavigate?.();
  };
  const completionBadge = useAgentChatStore((state) => state.completionBadge);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const navItems = APPLICATION_NAVIGATION_ITEMS;
  const isRail = variant === 'rail';
  const itemBaseClass = cn(
    'group relative flex h-[var(--nav-item-height)] w-full shrink-0 items-center overflow-hidden rounded-md border border-transparent text-sm leading-none text-secondary-text transition-all motion-reduce:transition-none',
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
  const logoutButton = authEnabled ? (
    <button
      type="button"
      onClick={() => setShowLogoutConfirm(true)}
      aria-label={collapsed ? t('layout.logout') : undefined}
      className={cn(
        itemInteractiveClass,
        !collapsed && (isRail ? 'mt-1.5' : 'mt-5'),
      )}
    >
      <LogOut className={itemIconClass} />
      {!collapsed ? <span className={itemLabelClass}>{t('layout.logout')}</span> : null}
    </button>
  ) : null;

  return (
    <>
      {collapsed ? (
        <div className="mb-4 flex justify-center">
          <div
            className={cn('relative h-11 w-11', onToggleCollapse && 'group')}
            data-shell-brand-behavior={onToggleCollapse ? 'replaceable' : 'persistent'}
          >
            <div
              data-shell-brand-mark="true"
              className={cn(
                'flex h-11 w-11 items-center justify-center rounded-md bg-primary text-primary-foreground transition-opacity motion-reduce:transition-none',
                onToggleCollapse && 'group-hover:opacity-0',
              )}
            >
              <BarChart3 className="size-4.5" />
            </div>
            {onToggleCollapse ? (
              <Tooltip
                content={t('layout.expandSidebar')}
                className="absolute inset-0"
              >
                <button
                  type="button"
                  onClick={onToggleCollapse}
                  aria-label={t('layout.expandSidebar')}
                  className="flex h-11 w-11 items-center justify-center rounded-lg border border-border bg-card text-secondary-text opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100 focus-visible:opacity-100 motion-reduce:transition-none"
                >
                  <PanelRight className="size-4.5" />
                </button>
              </Tooltip>
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
            <Tooltip content={t('layout.collapseSidebar')}>
              <button
                type="button"
                onClick={onToggleCollapse}
                aria-label={t('layout.collapseSidebar')}
                className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-transparent text-secondary-text transition-colors hover:bg-[var(--nav-hover-bg)] hover:text-foreground motion-reduce:transition-none"
              >
                <PanelLeft className="size-4.5" />
              </button>
            </Tooltip>
          ) : null}
        </div>
      )}

      {collapsed ? (
        <Tooltip content={t('layout.search')} className="mb-3 self-center">
          <button
            type="button"
            onClick={openSearch}
            aria-label={t('layout.search')}
            data-route-focus-key={`${focusKeyPrefix}:search`}
            data-route-focus-return-key={returnFocusKey}
            className="flex h-11 w-11 items-center justify-center rounded-lg border border-border bg-card text-muted-text transition-colors hover:bg-hover hover:text-foreground motion-reduce:transition-none"
          >
            <Search className="h-4 w-4" />
          </button>
        </Tooltip>
      ) : (
        <>
          <button
            type="button"
            onClick={openSearch}
            aria-label={t('layout.search')}
            data-route-focus-key={`${focusKeyPrefix}:search`}
            data-route-focus-return-key={returnFocusKey}
            className="mb-3 flex min-h-11 w-full items-center rounded-lg border border-border bg-card px-2.5 py-2 text-left shadow-soft-card transition-colors hover:bg-hover"
          >
            <span className="flex items-center gap-2 text-xs text-muted-text">
              <Search className="h-4 w-4" />
              {t('layout.search')}
            </span>
          </button>
          <div className="mb-3 border-t border-dashed border-border" />
        </>
      )}

      <nav
        className={cn(
          'flex flex-col gap-1',
          isRail ? '' : 'min-h-0 flex-1 overflow-y-auto overscroll-contain',
        )}
        aria-label={t('layout.mainNav')}
      >
        {navItems.map(({ key, labelKey, to, icon: Icon, exact, badge }) => {
          const label = t(labelKey);
          const link = (
            <NavLink
              to={to}
              end={exact}
              onClick={(event) => {
                if (shouldDelegateCurrentDocumentNavigation(event)) {
                  onNavigate?.();
                }
              }}
              aria-label={label}
              data-route-focus-key={`${focusKeyPrefix}:${key}`}
              data-route-focus-return-key={returnFocusKey}
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
          return (
            <React.Fragment key={key}>
              {collapsed ? (
                <Tooltip content={label} className="w-full">
                  {link}
                </Tooltip>
              ) : link}
            </React.Fragment>
          );
        })}

      </nav>

      <SidebarProfile
        collapsed={collapsed}
        open={profileOpen}
        onOpenChange={onProfileOpenChange}
        triggerRef={profileTriggerRef}
        presentation={profilePresentation}
      />

      {collapsed && logoutButton ? (
          <Tooltip content={t('layout.logout')} className={cn('w-full', isRail ? 'mt-1.5' : 'mt-5')}>
            {logoutButton}
          </Tooltip>
      ) : logoutButton}

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
