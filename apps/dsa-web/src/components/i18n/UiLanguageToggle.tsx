import type React from 'react';
import { Languages } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { UI_LANGUAGES, UI_LANGUAGE_METADATA, type UiLanguage } from '../../i18n/uiLanguages';
import { cn } from '../../utils/cn';
import { Select } from '../common';

type UiLanguageToggleVariant = 'default' | 'nav' | 'rail';

interface UiLanguageToggleProps {
  variant?: UiLanguageToggleVariant;
  collapsed?: boolean;
  popover?: boolean;
  popoverPlacement?: 'top' | 'bottom';
  wrapperClassName?: string;
  triggerClassName?: string;
  triggerActiveClassName?: string;
  iconClassName?: string;
  labelClassName?: string;
}

export const UiLanguageToggle: React.FC<UiLanguageToggleProps> = ({
  variant = 'default',
  collapsed = false,
  popover = false,
  popoverPlacement = 'top',
  wrapperClassName,
  triggerClassName,
  triggerActiveClassName,
  iconClassName,
  labelClassName,
}) => {
  const { language, setLanguage, t } = useUiLanguage();
  const isNavVariant = variant === 'nav';
  const isRailVariant = variant === 'rail';
  const metadata = UI_LANGUAGE_METADATA[language];

  if (popover) {
    return (
      <div
        data-testid="ui-language-selector"
        className={cn(
          triggerClassName ?? 'flex h-11 min-h-11 w-full items-center gap-2 rounded-lg px-3 text-sm text-secondary-text',
          triggerActiveClassName,
          wrapperClassName,
        )}
      >
        <Languages className={iconClassName ?? 'h-4 w-4 shrink-0'} />
        <Select
          value={language}
          onChange={(nextLanguage) => setLanguage(nextLanguage as UiLanguage)}
          options={UI_LANGUAGES.map((option) => ({
            value: option,
            label: UI_LANGUAGE_METADATA[option].nativeLabel,
          }))}
          ariaLabel={t('language.toggle')}
          className="min-w-0 flex-1 [&>div]:w-full [&_button]:h-full [&_button]:min-h-0 [&_button]:border-0 [&_button]:bg-transparent [&_button]:px-0 [&_button]:text-sm [&_button]:font-normal [&_button:hover]:bg-transparent"
          menuAlign="start"
          menuPlacement={popoverPlacement}
        />
      </div>
    );
  }

  const containerClassName = triggerClassName
    ? triggerClassName
    : isRailVariant
      ? 'flex h-[var(--nav-item-height)] w-full items-center justify-center gap-2.5 rounded-lg border border-transparent px-2 text-sm leading-none text-secondary-text transition-all hover:bg-[var(--nav-hover-bg)] hover:text-foreground'
      : isNavVariant
        ? 'group relative flex h-12 w-full select-none items-center gap-3 rounded-lg border border-transparent px-4 text-sm text-secondary-text transition-all duration-300 hover:bg-hover hover:text-foreground'
        : 'inline-flex h-11 min-h-11 min-w-11 items-center justify-center gap-2 rounded-lg border border-border/70 bg-card/80 px-3 text-sm text-secondary-text shadow-soft-card transition-colors hover:bg-hover hover:text-foreground';

  return (
    <div
      data-testid="ui-language-selector"
      className={cn(containerClassName, triggerActiveClassName, isNavVariant && collapsed ? 'justify-center px-2' : '', wrapperClassName)}
    >
        <Languages className={iconClassName ?? cn('shrink-0', isRailVariant ? 'size-4.5' : isNavVariant ? 'h-5 w-5' : 'h-4 w-4')} />
      <Select
        value={language}
        onChange={(nextLanguage) => setLanguage(nextLanguage as UiLanguage)}
        options={UI_LANGUAGES.map((option) => ({
          value: option,
          label: UI_LANGUAGE_METADATA[option].nativeLabel,
        }))}
        ariaLabel={t('language.toggle')}
        className={cn(
          'min-w-0 flex-1 [&>div]:w-full',
          isRailVariant || (isNavVariant && collapsed) ? 'hidden' : '',
        )}
        triggerClassName={cn(
          'h-full min-h-0 border-0 bg-transparent px-0 text-sm hover:bg-transparent focus-visible:border-transparent',
          isNavVariant ? 'text-[1.02rem] font-medium' : 'font-normal',
          labelClassName,
        )}
      />
      {isRailVariant || (isNavVariant && collapsed) ? (
        <span className={labelClassName}>{metadata.shortLabel}</span>
      ) : null}
    </div>
  );
};
