import React, { useCallback, useEffect, useRef, useState } from 'react';
import { BarChart3, ChevronRight, LogOut, PanelLeft, PanelRight, Search } from 'lucide-react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useAgentChatStore } from '../../stores/agentChatStore';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { resolveContextAwareNavigationTarget } from '../../utils/sessionContinuity';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { Popover } from '../common/Popover';
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

const SIDEBAR_GROUP_CLOSE_DELAY_MS = 120;

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
  const location = useLocation();
  const currentHref = `${location.pathname}${location.search}${location.hash}`;

  const openSearch = () => {
    navigate(resolveContextAwareNavigationTarget(APP_ROUTE_PATHS.home, currentHref), {
      state: { focusStockSearch: true, focusToken: Date.now() },
    });
    onNavigate?.();
  };
  const completionBadge = useAgentChatStore((state) => state.completionBadge);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const [openGroupKey, setOpenGroupKey] = useState<string | null>(null);
  const [focusFlyoutGroupKey, setFocusFlyoutGroupKey] = useState<string | null>(null);
  const groupCloseTimerRef = useRef<number | null>(null);
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
  const cancelGroupClose = useCallback(() => {
    if (groupCloseTimerRef.current !== null) {
      window.clearTimeout(groupCloseTimerRef.current);
      groupCloseTimerRef.current = null;
    }
  }, []);
  const openGroup = useCallback((key: string, focusContent: boolean) => {
    cancelGroupClose();
    setFocusFlyoutGroupKey(focusContent ? key : null);
    setOpenGroupKey(key);
  }, [cancelGroupClose]);
  const closeGroup = useCallback(() => {
    cancelGroupClose();
    setOpenGroupKey(null);
    setFocusFlyoutGroupKey(null);
  }, [cancelGroupClose]);
  const scheduleGroupClose = useCallback(() => {
    cancelGroupClose();
    groupCloseTimerRef.current = window.setTimeout(
      closeGroup,
      SIDEBAR_GROUP_CLOSE_DELAY_MS,
    );
  }, [cancelGroupClose, closeGroup]);
  useEffect(() => cancelGroupClose, [cancelGroupClose]);

  const isRouteActive = useCallback((to: string, exact = false) => (
    exact
      ? location.pathname === to
      : location.pathname === to || location.pathname.startsWith(`${to}/`)
  ), [location.pathname]);
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
        {navItems.map((item) => {
          const { key, labelKey, to, icon: Icon, exact, badge, children } = item;
          const label = t(labelKey);
          const navigationTarget = resolveContextAwareNavigationTarget(to, currentHref);
          const groupActive = isRouteActive(to, exact)
            || children?.some((child) => isRouteActive(child.to, child.exact))
            || false;
          const link = (
            <NavLink
              to={navigationTarget}
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
                  isActive || groupActive ? itemActiveClass : ''
                )
              }
            >
              {({ isActive }) => {
                const active = isActive || groupActive;
                return (
                <>
                  <Icon className={cn(itemIconClass, active ? 'text-[var(--nav-icon-active)]' : 'text-current')} />
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
                );
              }}
            </NavLink>
          );

          if (children && collapsed) {
            const contentId = `${focusKeyPrefix}-${key}-flyout`;
            const triggerFocusKey = `${focusKeyPrefix}:${key}`;
            return (
              <Popover
                key={key}
                open={openGroupKey === key}
                onOpenChange={(open) => {
                  if (open) openGroup(key, true);
                  else closeGroup();
                }}
                rootClassName="w-full shrink-0"
                contentRole="menu"
                contentId={contentId}
                ariaLabel={label}
                placement="right"
                autoFocusContent={focusFlyoutGroupKey === key}
                contentClassName="w-56 p-1.5"
                onContentMouseEnter={cancelGroupClose}
                onContentMouseLeave={scheduleGroupClose}
                onContentKeyDown={(event) => {
                  if (event.key === 'Tab') {
                    closeGroup();
                    return;
                  }
                  if (event.key !== 'ArrowLeft') return;
                  event.preventDefault();
                  closeGroup();
                  window.requestAnimationFrame(() => {
                    document.querySelector<HTMLElement>(
                      `[data-route-focus-key="${triggerFocusKey}"]`,
                    )?.focus();
                  });
                }}
                trigger={({ open }) => (
                  <NavLink
                    to={navigationTarget}
                    end={exact}
                    aria-label={label}
                    aria-haspopup="menu"
                    aria-expanded={open}
                    aria-controls={open ? contentId : undefined}
                    data-route-focus-key={triggerFocusKey}
                    data-route-focus-return-key={returnFocusKey}
                    onMouseEnter={() => openGroup(key, false)}
                    onMouseLeave={scheduleGroupClose}
                    onKeyDown={(event) => {
                      if (event.key !== 'ArrowRight') return;
                      event.preventDefault();
                      openGroup(key, true);
                    }}
                    onClick={(event) => {
                      if (shouldDelegateCurrentDocumentNavigation(event)) {
                        closeGroup();
                        onNavigate?.();
                      }
                    }}
                    className={cn(itemInteractiveClass, groupActive ? itemActiveClass : '')}
                  >
                    <Icon className={cn(itemIconClass, groupActive ? 'text-[var(--nav-icon-active)]' : 'text-current')} />
                    <ChevronRight
                      className="absolute bottom-1.5 right-1.5 h-3 w-3 text-muted-text"
                      aria-hidden="true"
                    />
                  </NavLink>
                )}
              >
                {() => (
                  <div>
                    <div className="px-2.5 pb-1.5 pt-1 text-xs font-medium text-muted-text">
                      {label}
                    </div>
                    {children.map((child) => {
                      const ChildIcon = child.icon;
                      const childLabel = t(child.labelKey);
                      const childActive = isRouteActive(child.to, child.exact);
                      return (
                        <Link
                          key={child.key}
                          role="menuitem"
                          tabIndex={-1}
                          to={resolveContextAwareNavigationTarget(child.to, currentHref)}
                          aria-label={childLabel}
                          aria-current={childActive && child.to !== to ? 'page' : undefined}
                          data-route-focus-key={`${focusKeyPrefix}:${child.key}`}
                          data-route-focus-return-key={triggerFocusKey}
                          onClick={(event) => {
                            if (shouldDelegateCurrentDocumentNavigation(event)) {
                              closeGroup();
                              onNavigate?.();
                            }
                          }}
                          className={cn(
                            'flex min-h-11 items-center gap-2.5 rounded-lg px-2.5 text-sm text-secondary-text transition-colors hover:bg-[var(--nav-hover-bg)] hover:text-foreground motion-reduce:transition-none',
                            childActive ? itemActiveClass : '',
                          )}
                        >
                          <ChildIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
                          <span className="truncate">{childLabel}</span>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </Popover>
            );
          }

          if (children) {
            return (
              <div key={key} className="flex shrink-0 flex-col gap-1">
                {link}
                <div className="ml-4 flex flex-col gap-1 border-l border-border pl-3">
                  {children.map((child) => {
                    const ChildIcon = child.icon;
                    const childLabel = t(child.labelKey);
                    return (
                      <Link
                        key={child.key}
                        to={resolveContextAwareNavigationTarget(child.to, currentHref)}
                        onClick={(event) => {
                          if (shouldDelegateCurrentDocumentNavigation(event)) {
                            onNavigate?.();
                          }
                        }}
                        aria-label={childLabel}
                        aria-current={isRouteActive(child.to, child.exact) && child.to !== to
                          ? 'page'
                          : undefined}
                        data-route-focus-key={`${focusKeyPrefix}:${child.key}`}
                        data-route-focus-return-key={returnFocusKey}
                        className={cn(
                          itemInteractiveClass,
                          'min-h-10 gap-2.5 px-2.5 text-xs',
                          isRouteActive(child.to, child.exact) ? itemActiveClass : '',
                        )}
                      >
                        <ChildIcon className={cn(
                          'h-4 w-4 shrink-0',
                          isRouteActive(child.to, child.exact)
                            ? 'text-[var(--nav-icon-active)]'
                            : 'text-current',
                        )} />
                        <span className="truncate">{childLabel}</span>
                      </Link>
                    );
                  })}
                </div>
              </div>
            );
          }

          return (
            <React.Fragment key={key}>
              {collapsed ? (
                <Tooltip content={label} className="w-full shrink-0">
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
