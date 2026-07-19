import type React from 'react';
import { Check, Monitor, Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import { cn } from '../../utils/cn';
import { Popover } from '../common/Popover';
import { Pressable } from '../common/Pressable';

type ThemeOption = 'light' | 'dark' | 'system';
type ThemeToggleVariant = 'default' | 'nav' | 'rail';

const THEME_OPTIONS: Array<{
  value: ThemeOption;
  labelKey: UiTextKey;
  icon: typeof Sun;
}> = [
  { value: 'light', labelKey: 'theme.light', icon: Sun },
  { value: 'dark', labelKey: 'theme.dark', icon: Moon },
  { value: 'system', labelKey: 'theme.system', icon: Monitor },
];

function resolveThemeLabel(theme: string | undefined, t: (key: UiTextKey) => string) {
  switch (theme) {
    case 'light':
      return t('theme.light');
    case 'dark':
      return t('theme.dark');
    default:
      return t('theme.system');
  }
}

interface ThemeToggleProps {
  variant?: ThemeToggleVariant;
  collapsed?: boolean;
  menuLayout?: 'vertical' | 'horizontal';
  wrapperClassName?: string;
  triggerClassName?: string;
  triggerActiveClassName?: string;
  iconClassName?: string;
  labelClassName?: string;
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({
  variant = 'default',
  collapsed = false,
  menuLayout = 'vertical',
  wrapperClassName,
  triggerClassName,
  triggerActiveClassName,
  iconClassName,
  labelClassName,
}) => {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const { t } = useUiLanguage();

  const activeTheme = (theme as ThemeOption | undefined) ?? 'system';
  const visualTheme = resolvedTheme ?? 'dark';
  const TriggerIcon = visualTheme === 'light' ? Sun : Moon;
  const isNavVariant = variant === 'nav';
  const isRailVariant = variant === 'rail';
  const isHorizontalMenu = menuLayout === 'horizontal';

  return (
    <Popover
      rootClassName={cn(isRailVariant ? 'w-full' : '', wrapperClassName)}
      contentRole="menu"
      ariaLabel={t('theme.menu')}
      contentClassName={cn(
        'min-w-[8rem] rounded-2xl border-border/70 p-1.5 shadow-2xl backdrop-blur-sm',
        isHorizontalMenu
          ? 'bottom-0 left-full ml-2 flex min-w-[9rem] flex-col'
          : isNavVariant || isRailVariant
          ? 'bottom-full left-0 mb-2 w-max min-w-[9rem]'
          : 'right-0 top-full mt-2'
      )}
      trigger={({ open, toggle }) => (
        <Pressable
        type="button"
        onClick={toggle}
        data-state={open ? 'open' : 'closed'}
        className={cn(
          triggerClassName
            ? triggerClassName
            : isRailVariant
              ? 'flex h-[var(--nav-item-height)] w-full items-center justify-center gap-2.5 rounded-lg border border-transparent px-2 text-sm leading-none text-secondary-text transition-all hover:bg-[var(--nav-hover-bg)] hover:text-foreground data-[state=open]:border-[var(--nav-active-border)] data-[state=open]:bg-[var(--nav-active-bg)] data-[state=open]:text-[hsl(var(--primary))]'
              : isNavVariant
                ? 'group relative flex h-12 w-full select-none items-center gap-3 rounded-lg border border-transparent px-4 text-sm text-secondary-text transition-all duration-300 hover:bg-hover hover:text-foreground data-[state=open]:border-subtle data-[state=open]:bg-subtle data-[state=open]:text-foreground'
                : 'inline-flex h-11 min-h-11 min-w-11 items-center justify-center gap-2 rounded-lg border border-border/70 bg-card/80 px-3 text-sm text-secondary-text shadow-soft-card transition-colors hover:bg-hover hover:text-foreground',
          triggerClassName && open ? triggerActiveClassName : '',
          isNavVariant && collapsed ? 'justify-center px-2' : ''
        )}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('theme.toggle')}
      >
        <TriggerIcon className={iconClassName ?? cn('shrink-0', isRailVariant ? 'size-4.5' : isNavVariant ? 'h-5 w-5' : 'h-4 w-4')} />
        {isRailVariant ? (
          <span className={labelClassName}>{t('theme.theme')}</span>
        ) : isNavVariant ? (
          collapsed ? null : <span className="truncate text-[1.02rem] font-medium">{t('theme.theme')}</span>
        ) : (
          <span className="hidden sm:inline">{resolveThemeLabel(activeTheme, t)}</span>
        )}
        </Pressable>
      )}
    >
      {({ close }) => (
        <>
          {THEME_OPTIONS.map(({ value, labelKey, icon: Icon }) => {
            const isActive = activeTheme === value;
            return (
              <Pressable
                key={value}
                type="button"
                role="menuitemradio"
                aria-checked={isActive}
                onClick={() => {
                  setTheme(value);
                  close();
                }}
                className={cn(
                  'flex w-full items-center rounded-lg transition-colors',
                  isHorizontalMenu
                    ? 'relative min-h-11 min-w-0 justify-between gap-1 px-2 py-1 text-xs'
                    : 'min-h-11 justify-between px-3 py-2 text-sm',
                  isActive
                    ? 'bg-hover text-foreground'
                    : 'text-secondary-text hover:bg-hover hover:text-foreground'
                )}
              >
                <span className={cn('flex items-center', isHorizontalMenu ? 'gap-1.5 whitespace-nowrap' : 'gap-2')}>
                  <Icon className="h-4 w-4" />
                  {t(labelKey)}
                </span>
                {isActive ? (
                  <Check className={cn('text-foreground', isHorizontalMenu ? 'absolute right-1.5 top-1.5 h-3 w-3' : 'h-4 w-4')} />
                ) : null}
              </Pressable>
            );
          })}
        </>
      )}
    </Popover>
  );
};
