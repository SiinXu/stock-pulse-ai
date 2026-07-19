import type React from 'react';
import { useEffect, useState } from 'react';
import { Menu } from 'lucide-react';
import { Outlet } from 'react-router-dom';
import { Drawer } from '../common/Drawer';
import { IconButton } from '../common/IconButton';
import { getOverlayStyle, OVERLAY_Z } from '../common/overlayZ';
import { SidebarNav } from './SidebarNav';
import { cn } from '../../utils/cn';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { ProfileMenu } from './ProfileMenu';

type ShellProps = {
  children?: React.ReactNode;
};

const SIDEBAR_COLLAPSED_STORAGE_KEY = 'dsa-sidebar-collapsed';

export const Shell: React.FC<ShellProps> = ({ children }) => {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') {
      return false;
    }
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === '1';
  });
  const { t } = useUiLanguage();

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, next ? '1' : '0');
      }
      return next;
    });
  };

  useEffect(() => {
    if (!mobileOpen) {
      return undefined;
    }

    const handleResize = () => {
      if (window.innerWidth >= 1024) {
        setMobileOpen(false);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [mobileOpen]);

  return (
    <div className="h-dvh overflow-hidden bg-background text-foreground">
      <header
        className="pointer-events-none fixed inset-x-0 top-3 flex items-start justify-between px-3 lg:hidden"
        style={getOverlayStyle('pageDrawer')}
      >
        <IconButton
          onClick={() => setMobileOpen(true)}
          className="pointer-events-auto"
          visualClassName="border border-border/70 bg-card/85 shadow-soft-card backdrop-blur-sm"
          aria-label={t('layout.openNav')}
          tooltip={false}
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </IconButton>
        <div className="pointer-events-auto">
          <ProfileMenu variant="mobile" />
        </div>
      </header>

      <div className="mx-auto flex h-dvh w-full overflow-hidden">
        <aside
          className={cn(
            'sticky top-0 hidden h-dvh shrink-0 self-start overflow-visible bg-background pl-4 pr-2 py-5 transition-[width] duration-300 ease-out lg:flex lg:flex-col',
            collapsed ? 'w-19' : 'w-57'
          )}
          style={getOverlayStyle('pageDrawer')}
          aria-label={t('layout.desktopSidebar')}
        >
          <SidebarNav
            collapsed={collapsed}
            onToggleCollapse={toggleCollapsed}
            onNavigate={() => setMobileOpen(false)}
          />
        </aside>

        <main className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto overflow-x-hidden rounded-xl border border-border bg-card shadow-soft-card mt-14 mx-3 mb-3 lg:mt-4 lg:mb-4 lg:ml-1 lg:mr-4 touch-pan-y">
          {children ?? <Outlet />}
        </main>
      </div>

      <Drawer
        isOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
        title={t('layout.navMenu')}
        width="max-w-xs"
        zIndex={OVERLAY_Z.navigationDrawer}
        side="left"
      >
        <div className="flex h-full flex-col">
          <SidebarNav onNavigate={() => setMobileOpen(false)} />
        </div>
      </Drawer>
    </div>
  );
};
