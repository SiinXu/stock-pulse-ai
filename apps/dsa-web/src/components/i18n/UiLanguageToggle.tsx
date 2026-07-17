import type React from 'react';
import { Languages } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { UI_LANGUAGES, UI_LANGUAGE_METADATA, type UiLanguage } from '../../i18n/uiLanguages';
import { cn } from '../../utils/cn';

type UiLanguageToggleVariant = 'default' | 'nav' | 'rail';

interface UiLanguageToggleProps {
  variant?: UiLanguageToggleVariant;
  collapsed?: boolean;
  wrapperClassName?: string;
  triggerClassName?: string;
  triggerActiveClassName?: string;
  iconClassName?: string;
  labelClassName?: string;
}

export const UiLanguageToggle: React.FC<UiLanguageToggleProps> = ({
  variant = 'default',
  collapsed = false,
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

  return (
    <label className={cn('group relative block', isRailVariant ? 'w-full' : '', wrapperClassName)}>
      <span
        aria-hidden="true"
        className={cn(
          'group-focus-within:ring-2 group-focus-within:ring-primary group-focus-within:ring-offset-2 group-focus-within:ring-offset-background',
          triggerClassName
            ? triggerClassName
            : isRailVariant
              ? 'flex h-[var(--nav-item-height)] w-full items-center justify-center gap-2.5 rounded-full border border-transparent px-2 text-sm leading-none text-secondary-text transition-all hover:bg-[var(--nav-hover-bg)] hover:text-foreground'
              : isNavVariant
                ? 'group relative flex h-12 w-full select-none items-center gap-3 rounded-full border border-transparent px-4 text-sm text-secondary-text transition-all duration-300 hover:bg-hover hover:text-foreground'
                : 'inline-flex h-11 min-h-11 min-w-11 items-center justify-center gap-2 rounded-full border border-border/70 bg-card/80 px-3 text-sm text-secondary-text shadow-soft-card transition-colors hover:bg-hover hover:text-foreground',
          triggerActiveClassName,
          isNavVariant && collapsed ? 'justify-center px-2' : ''
        )}
      >
        <Languages className={iconClassName ?? cn('shrink-0', isRailVariant ? 'size-4.5' : isNavVariant ? 'h-5 w-5' : 'h-4 w-4')} />
        {isRailVariant ? (
          <span className={labelClassName}>{metadata.shortLabel}</span>
        ) : isNavVariant ? (
          collapsed ? null : <span className="truncate text-[1.02rem] font-medium">{metadata.nativeLabel}</span>
        ) : (
          <span className="hidden sm:inline">{metadata.nativeLabel}</span>
        )}
      </span>
      <select
        aria-label={t('language.toggle')}
        className="absolute inset-0 h-full w-full cursor-pointer opacity-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        data-testid="ui-language-selector"
        onChange={(event) => setLanguage(event.target.value as UiLanguage)}
        value={language}
      >
        {UI_LANGUAGES.map((option) => (
          <option key={option} value={option}>{UI_LANGUAGE_METADATA[option].nativeLabel}</option>
        ))}
      </select>
    </label>
  );
};
