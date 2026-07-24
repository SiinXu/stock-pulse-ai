import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Menu } from 'lucide-react';
import { Outlet } from 'react-router-dom';
import { Drawer } from '../common/Drawer';
import { IconButton } from '../common/IconButton';
import { CommandPalette, useCommandPaletteShortcut } from '../command-palette';
import { NotificationBell } from '../notifications';
import { SidebarNav } from './SidebarNav';
import { SidebarProfile } from './SidebarProfile';
import { cn } from '../../utils/cn';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { APP_ROUTE_PATHS } from '../../routing/routes';

type ShellProps = {
  children?: React.ReactNode;
};

type ProfilePresentation = 'mobile' | 'desktop' | 'drawer';

const SIDEBAR_COLLAPSED_STORAGE_KEY = 'dsa-sidebar-collapsed';
const DESKTOP_SIDEBAR_QUERY = '(min-width: 1024px)';
const COMPACT_SIDEBAR_QUERY = '(min-width: 1024px) and (max-width: 1279px)';

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => (
    typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia(query).matches
  ));

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const mediaQuery = window.matchMedia(query);
    const update = () => setMatches(mediaQuery.matches);
    update();
    mediaQuery.addEventListener('change', update);
    return () => mediaQuery.removeEventListener('change', update);
  }, [query]);

  return matches;
}

export const Shell: React.FC<ShellProps> = ({ children }) => {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const mobileOpenRef = useRef(false);
  const [profilePresentation, setProfilePresentation] = useState<ProfilePresentation | null>(null);
  const profilePresentationRef = useRef<ProfilePresentation | null>(null);
  const mobileProfileTriggerRef = useRef<HTMLButtonElement>(null);
  const desktopProfileTriggerRef = useRef<HTMLButtonElement>(null);
  const [collapsedPreference, setCollapsedPreference] = useState<boolean | null>(() => {
    if (typeof window === 'undefined') {
      return null;
    }
    const stored = window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY);
    return stored === null ? null : stored === '1';
  });
  const { t } = useUiLanguage();
  const desktopSidebar = useMediaQuery(DESKTOP_SIDEBAR_QUERY);
  const compactSidebar = useMediaQuery(COMPACT_SIDEBAR_QUERY);
  const sidebarCollapsed = collapsedPreference ?? compactSidebar;

  const openCommandPalette = useCallback(() => {
    setCommandPaletteOpen(true);
  }, []);

  useCommandPaletteShortcut(openCommandPalette);

  const setMobileNavigationOpen = useCallback((nextOpen: boolean) => {
    mobileOpenRef.current = nextOpen;
    setMobileOpen(nextOpen);
  }, []);

  const closeMobileNavigation = useCallback(() => {
    setMobileNavigationOpen(false);
  }, [setMobileNavigationOpen]);

  const updateProfilePresentation = useCallback((
    presentation: ProfilePresentation,
    open: boolean,
  ) => {
    const nextPresentation = open ? presentation : null;
    profilePresentationRef.current = nextPresentation;
    setProfilePresentation(nextPresentation);
  }, []);

  const toggleCollapsed = () => {
    setCollapsedPreference((preference) => {
      const next = !(preference ?? compactSidebar);
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, next ? '1' : '0');
      }
      return next;
    });
  };

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const mediaQuery = window.matchMedia(DESKTOP_SIDEBAR_QUERY);
    let focusFrame: number | undefined;
    const handlePresentationChange = (event: MediaQueryListEvent) => {
      const navigationWasOpen = event.matches && mobileOpenRef.current;
      const profileWasOpen = profilePresentationRef.current !== null;
      if (navigationWasOpen) setMobileNavigationOpen(false);
      if (profileWasOpen) {
        profilePresentationRef.current = null;
        setProfilePresentation(null);
      }
      if (!navigationWasOpen && !profileWasOpen) return;
      if (focusFrame !== undefined) window.cancelAnimationFrame(focusFrame);
      focusFrame = window.requestAnimationFrame(() => {
        if (profileWasOpen) {
          const visibleProfile = event.matches
            ? desktopProfileTriggerRef.current
            : mobileProfileTriggerRef.current;
          visibleProfile?.focus();
          return;
        }
        const sidebar = document.querySelector<HTMLElement>('[data-shell-sidebar]');
        const activeRoute = sidebar?.querySelector<HTMLElement>('a[aria-current="page"]');
        (activeRoute ?? sidebar)?.focus();
      });
    };
    mediaQuery.addEventListener('change', handlePresentationChange);
    return () => {
      mediaQuery.removeEventListener('change', handlePresentationChange);
      if (focusFrame !== undefined) window.cancelAnimationFrame(focusFrame);
    };
  }, [setMobileNavigationOpen]);

  return (
    <div className="h-dvh overflow-hidden bg-background text-foreground">
      <div
        data-shell-mobile-header="true"
        className="pointer-events-none fixed inset-x-0 top-3 z-40 flex min-w-0 items-center gap-3 px-3 lg:hidden"
      >
        <span className="pointer-events-auto">
          <IconButton
            variant="outline"
            size="navigation"
            onClick={() => setMobileNavigationOpen(true)}
            aria-label={t('layout.openNav')}
            data-route-focus-key="shell:mobile-navigation"
            className="bg-card shadow-soft-card"
          >
            <Menu aria-hidden="true" />
          </IconButton>
        </span>
        <span
          data-shell-mobile-brand="true"
          className="min-w-0 flex-1 truncate text-base font-semibold text-foreground"
        >
          {t('layout.appFallbackTitle')}
        </span>
        {!desktopSidebar ? (
          <NotificationBell className="pointer-events-auto" placement="bottom" />
        ) : null}
        <SidebarProfile
          collapsed
          placement="bottom"
          align="end"
          rootClassName="pointer-events-auto"
          open={profilePresentation === 'mobile'}
          onOpenChange={(open) => updateProfilePresentation('mobile', open)}
          triggerRef={mobileProfileTriggerRef}
          presentation="mobile"
        />
      </div>

      <div className="mx-auto flex h-dvh w-full overflow-hidden">
        <aside
          data-shell-sidebar="true"
          data-shell-sidebar-mode={sidebarCollapsed ? 'compact' : 'expanded'}
          tabIndex={-1}
          className={cn(
            'sticky top-0 z-40 hidden h-dvh shrink-0 self-start overflow-visible border-r border-border bg-background px-2 py-4 transition-[width] duration-300 ease-out motion-reduce:transition-none lg:flex lg:flex-col',
            sidebarCollapsed ? 'w-20' : 'w-60'
          )}
          aria-label={t('layout.desktopSidebar')}
        >
          <SidebarNav
            collapsed={sidebarCollapsed}
            onToggleCollapse={toggleCollapsed}
            onNavigate={() => setMobileNavigationOpen(false)}
            onOpenCommandPalette={openCommandPalette}
            globalActions={desktopSidebar ? <NotificationBell placement="right" /> : null}
            focusKeyPrefix="shell-nav-desktop"
            profileOpen={profilePresentation === 'desktop'}
            onProfileOpenChange={(open) => updateProfilePresentation('desktop', open)}
            profileTriggerRef={desktopProfileTriggerRef}
            profilePresentation="desktop"
          />
        </aside>

        <main
          data-shell-main="true"
          className="relative mt-14 mb-3 mx-3 flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto rounded-xl border border-border bg-card shadow-soft-card lg:mt-4 lg:mb-4 lg:ml-1 lg:mr-4"
        >
          {children ?? <Outlet />}
        </main>
      </div>

      <Drawer
        isOpen={mobileOpen}
        onClose={() => setMobileNavigationOpen(false)}
        title={t('layout.navMenu')}
        variant="navigation"
      >
        <div className="flex h-full flex-col">
          <SidebarNav
            onNavigate={closeMobileNavigation}
            onOpenCommandPalette={openCommandPalette}
            focusKeyPrefix="shell-nav-mobile"
            returnFocusKey="shell:mobile-navigation"
            profileOpen={profilePresentation === 'drawer'}
            onProfileOpenChange={(open) => updateProfilePresentation('drawer', open)}
            profilePresentation="drawer"
          />
        </div>
      </Drawer>

      <CommandPalette
        isOpen={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        analysisHref={APP_ROUTE_PATHS.researchAnalysis}
      />
    </div>
  );
};
