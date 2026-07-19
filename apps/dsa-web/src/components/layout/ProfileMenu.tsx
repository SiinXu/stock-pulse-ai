// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { ChevronUp, UserRound } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { IconButton } from '../common/IconButton';
import { Popover } from '../common/Popover';
import { Pressable } from '../common/Pressable';
import { UiLanguageToggle } from '../i18n/UiLanguageToggle';
import { ThemeToggle } from '../theme/ThemeToggle';

export type ProfileMenuVariant = 'sidebar' | 'collapsed' | 'mobile';

export interface ProfileMenuProps {
  variant?: ProfileMenuVariant;
  className?: string;
}

export const ProfileMenu: React.FC<ProfileMenuProps> = ({
  variant = 'sidebar',
  className,
}) => {
  const { t } = useUiLanguage();
  const isCollapsed = variant === 'collapsed';
  const isMobile = variant === 'mobile';
  const menuRowClass = 'flex h-8 w-full items-center gap-2 rounded-lg border border-transparent px-3 text-sm font-normal tracking-normal text-secondary-text transition-colors hover:bg-base hover:text-foreground dark:hover:bg-card';

  return (
    <Popover
      rootClassName={cn(
        isMobile ? '' : 'mt-2',
        isCollapsed ? 'self-center' : isMobile ? '' : 'w-full',
        className,
      )}
      contentRole="dialog"
      ariaLabel={t('layout.appFallbackTitle')}
      layer="tooltip"
      contentClassName={cn(
        'flex w-57 flex-col gap-2 overflow-visible bg-card px-1 pb-3 pt-1 shadow-soft-card-strong dark:bg-base',
        isMobile
          ? 'right-0 top-full mt-2'
          : isCollapsed
            ? 'bottom-0 left-full ml-2'
            : 'bottom-full left-0 mb-2',
      )}
      trigger={({ open, toggle }) => isMobile ? (
        <IconButton
          type="button"
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-label={t('layout.appFallbackTitle')}
          data-state={open ? 'open' : 'closed'}
          onClick={toggle}
          tooltip={false}
          visualClassName="rounded-full bg-foreground text-background shadow-soft-card"
        >
          <UserRound className="h-4 w-4" aria-hidden="true" />
        </IconButton>
      ) : (
        <Pressable
          type="button"
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-label={t('layout.appFallbackTitle')}
          data-state={open ? 'open' : 'closed'}
          className={cn(
            'flex items-center rounded-lg border border-transparent text-secondary-text transition-colors hover:bg-[var(--nav-hover-bg)] hover:text-foreground',
            'data-[state=open]:border-[var(--nav-active-border)] data-[state=open]:bg-[var(--nav-active-bg)] data-[state=open]:text-foreground',
            isCollapsed ? 'h-10 w-10 justify-center' : 'h-12 w-full gap-2 px-2',
          )}
          onClick={toggle}
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground text-background">
            <UserRound className="h-4 w-4" aria-hidden="true" />
          </span>
          {!isCollapsed ? (
            <>
              <span className="min-w-0 flex-1 truncate text-left text-sm font-medium tracking-normal text-foreground">
                {t('layout.appFallbackTitle')}
              </span>
              <ChevronUp className={cn('h-4 w-4 shrink-0 transition-transform', open ? '' : 'rotate-180')} aria-hidden="true" />
            </>
          ) : null}
        </Pressable>
      )}
    >
      <>
        <div className="flex items-center gap-2 rounded-lg p-2">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground text-background">
            <UserRound className="h-4 w-4" aria-hidden="true" />
          </span>
          <span className="min-w-0 truncate text-sm font-medium leading-[1.4] tracking-normal text-foreground">
            {t('layout.appFallbackTitle')}
          </span>
        </div>
        <div className="mx-2 border-t border-border" />
        <ThemeToggle
          menuLayout={isMobile ? 'vertical' : 'horizontal'}
          wrapperClassName="w-full"
          triggerClassName={menuRowClass}
          iconClassName="h-4 w-4 shrink-0"
        />
        <UiLanguageToggle
          popover
          popoverPlacement={isMobile ? 'bottom' : 'top'}
          wrapperClassName="w-full"
          triggerClassName={menuRowClass}
          iconClassName="h-4 w-4 shrink-0"
        />
      </>
    </Popover>
  );
};
