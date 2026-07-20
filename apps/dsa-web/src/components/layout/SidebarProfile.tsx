import type React from 'react';
import { useId } from 'react';
import { ChevronUp, UserRound } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { Popover } from '../common/Popover';
import { UiLanguageToggle } from '../i18n/UiLanguageToggle';
import { ThemeToggle } from '../theme/ThemeToggle';

interface SidebarProfileProps {
  collapsed?: boolean;
}

export const SidebarProfile: React.FC<SidebarProfileProps> = ({ collapsed = false }) => {
  const { t } = useUiLanguage();
  const panelId = useId();
  const titleId = useId();
  const menuRowClass = 'flex h-8 w-full items-center gap-2 rounded-lg border border-transparent px-3 text-sm font-normal tracking-normal text-secondary-text transition-colors hover:bg-base hover:text-foreground dark:hover:bg-card';

  return (
    <Popover
      rootClassName={cn('mt-2', collapsed ? 'self-center' : 'w-full')}
      contentRole="dialog"
      contentId={panelId}
      ariaLabelledBy={titleId}
      placement="top"
      align="start"
      contentClassName={cn(
        'flex w-57 flex-col gap-2 bg-card px-1 pb-3 pt-1 shadow-soft-card-strong dark:bg-base',
      )}
      trigger={({ open, toggle }) => (
        <button
          type="button"
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls={open ? panelId : undefined}
          aria-label={t('layout.appFallbackTitle')}
          data-state={open ? 'open' : 'closed'}
          className={cn(
            'flex items-center rounded-lg border border-transparent text-secondary-text transition-colors hover:bg-[var(--nav-hover-bg)] hover:text-foreground',
            'data-[state=open]:border-[var(--nav-active-border)] data-[state=open]:bg-[var(--nav-active-bg)] data-[state=open]:text-foreground',
            collapsed ? 'h-10 w-10 justify-center' : 'h-12 w-full gap-2 px-2',
          )}
          onClick={toggle}
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground text-background">
            <UserRound className="h-4 w-4" aria-hidden="true" />
          </span>
          {!collapsed ? (
            <>
              <span className="min-w-0 flex-1 truncate text-left text-sm font-medium tracking-normal text-foreground">
                {t('layout.appFallbackTitle')}
              </span>
              <ChevronUp className={cn('h-4 w-4 shrink-0 transition-transform', open ? '' : 'rotate-180')} aria-hidden="true" />
            </>
          ) : null}
        </button>
      )}
    >
      <>
        <div className="flex items-center gap-2 rounded-lg p-2">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground text-background">
            <UserRound className="h-4 w-4" aria-hidden="true" />
          </span>
          <span id={titleId} className="min-w-0 truncate text-sm font-medium leading-[1.4] tracking-normal text-foreground">
            {t('layout.appFallbackTitle')}
          </span>
        </div>
        <div className="mx-2 border-t border-border" />
        <ThemeToggle
          menuLayout="horizontal"
          wrapperClassName="w-full"
          triggerClassName={menuRowClass}
          iconClassName="h-4 w-4 shrink-0"
        />
        <UiLanguageToggle
          popover
          wrapperClassName="w-full"
          triggerClassName={menuRowClass}
          iconClassName="h-4 w-4 shrink-0"
        />
      </>
    </Popover>
  );
};
