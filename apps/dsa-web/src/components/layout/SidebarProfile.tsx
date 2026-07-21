import type React from 'react';
import { useId } from 'react';
import { ChevronUp, UserRound } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { Popover } from '../common/Popover';
import { Tooltip } from '../common/Tooltip';
import { UiLanguageToggle } from '../i18n/UiLanguageToggle';
import { ThemeToggle } from '../theme/ThemeToggle';

interface SidebarProfileProps {
  collapsed?: boolean;
  placement?: 'top' | 'bottom';
  align?: 'start' | 'end';
  rootClassName?: string;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  triggerRef?: React.Ref<HTMLButtonElement>;
  presentation?: 'mobile' | 'desktop' | 'drawer';
}

export const SidebarProfile: React.FC<SidebarProfileProps> = ({
  collapsed = false,
  placement = 'top',
  align = 'start',
  rootClassName,
  open,
  onOpenChange,
  triggerRef,
  presentation,
}) => {
  const { t } = useUiLanguage();
  const panelId = useId();
  const titleId = useId();
  const menuRowClass = 'flex h-11 w-full items-center gap-2 rounded-lg border border-transparent px-3 text-sm font-normal tracking-normal text-secondary-text transition-colors hover:bg-base hover:text-foreground dark:hover:bg-card';

  return (
    <Popover
      open={open}
      onOpenChange={onOpenChange}
      rootClassName={cn(
        placement === 'top' && 'mt-2',
        collapsed ? 'self-center' : 'w-full',
        rootClassName,
      )}
      contentRole="dialog"
      contentId={panelId}
      ariaLabelledBy={titleId}
      placement={placement}
      align={align}
      contentClassName={cn(
        'flex w-60 flex-col gap-2 bg-card px-1 pb-3 pt-1 shadow-soft-card-strong dark:bg-base',
      )}
      trigger={({ open, toggle }) => {
        const trigger = (
          <button
            ref={triggerRef}
            type="button"
            aria-haspopup="dialog"
            aria-expanded={open}
            aria-controls={open ? panelId : undefined}
            aria-label={t('layout.appFallbackTitle')}
            data-shell-profile-trigger={presentation}
            data-state={open ? 'open' : 'closed'}
            className={cn(
              'flex items-center rounded-lg border border-transparent text-secondary-text transition-colors hover:bg-[var(--nav-hover-bg)] hover:text-foreground',
              'data-[state=open]:border-[var(--nav-active-border)] data-[state=open]:bg-[var(--nav-active-bg)] data-[state=open]:text-foreground',
              collapsed ? 'h-11 w-11 justify-center' : 'h-12 w-full gap-2 px-2',
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
        );
        return collapsed ? (
          <Tooltip content={t('layout.appFallbackTitle')} side={placement}>
            {trigger}
          </Tooltip>
        ) : trigger;
      }}
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
