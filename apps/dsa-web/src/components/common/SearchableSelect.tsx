import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '../../utils/cn';

export interface SearchableSelectOption {
  /** Stable value stored on selection (e.g. a canonical model route). */
  value: string;
  /** Primary display line (e.g. model display name). */
  label: string;
  /** Secondary display line (e.g. "OpenAI · 生产连接"). */
  sublabel?: string;
  /** Optional group header the option is listed under. */
  group?: string;
  disabled?: boolean;
  /** Extra search facets beyond label/sublabel/value. */
  keywords?: string[];
}

interface SearchableSelectProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  options: SearchableSelectOption[];
  placeholder?: string;
  disabled?: boolean;
  ariaLabel?: string;
  className?: string;
  error?: boolean;
  emptyText?: string;
  searchPlaceholder?: string;
  /**
   * Marker rendered when the current value is not in the options list. The
   * value is kept (never silently cleared) so a stale-but-persisted config
   * stays visible until the user actively replaces it.
   */
  staleValueLabel?: string;
  /** When true a clear affordance is rendered next to the trigger. */
  clearable?: boolean;
}

/**
 * A strict searchable select: the user can only pick from the provided
 * options (no free-text values). A persisted value missing from the list is
 * surfaced as "unavailable" instead of being dropped.
 */
export const SearchableSelect: React.FC<SearchableSelectProps> = ({
  id,
  value,
  onChange,
  options,
  placeholder,
  disabled = false,
  ariaLabel,
  className = '',
  error = false,
  emptyText,
  searchPlaceholder,
  staleValueLabel,
  clearable = false,
}) => {
  const reactId = useId();
  const resolvedId = id ?? reactId;
  const listboxId = `${resolvedId}-listbox`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [triggerRect, setTriggerRect] = useState<DOMRect | null>(null);
  const [portalHost, setPortalHost] = useState<HTMLElement | null>(null);

  const selectedOption = useMemo(
    () => options.find((option) => option.value === value),
    [options, value],
  );
  const valueIsStale = Boolean(value) && !selectedOption;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return options;
    }
    return options.filter((option) => {
      const haystack = [option.label, option.sublabel ?? '', option.value, option.group ?? '', ...(option.keywords ?? [])];
      return haystack.some((text) => text.toLowerCase().includes(q));
    });
  }, [options, query]);

  interface NavItem extends SearchableSelectOption {
    showHeader: boolean;
  }
  const navItems = useMemo<NavItem[]>(
    () =>
      filtered.map((option, index) => {
        const previousGroup = filtered[index - 1]?.group;
        return { ...option, showHeader: Boolean(option.group) && option.group !== previousGroup };
      }),
    [filtered],
  );

  const open = useCallback(() => {
    if (disabled) {
      return;
    }
    setTriggerRect(triggerRef.current?.getBoundingClientRect() ?? null);
    setPortalHost(
      (triggerRef.current?.closest('[role="dialog"]') as HTMLElement | null) ?? document.body,
    );
    setQuery('');
    setActiveIndex(0);
    setIsOpen(true);
  }, [disabled]);

  const close = useCallback((refocus: boolean) => {
    setIsOpen(false);
    setQuery('');
    if (refocus) {
      triggerRef.current?.focus();
    }
  }, []);

  const commit = useCallback(
    (next: string) => {
      onChange(next);
      close(true);
    },
    [onChange, close],
  );

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    searchRef.current?.focus();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || popoverRef.current?.contains(target)) {
        return;
      }
      close(false);
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [isOpen, close]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const updateRect = () => setTriggerRect(triggerRef.current?.getBoundingClientRect() ?? null);
    window.addEventListener('scroll', updateRect, true);
    window.addEventListener('resize', updateRect);
    return () => {
      window.removeEventListener('scroll', updateRect, true);
      window.removeEventListener('resize', updateRect);
    };
  }, [isOpen]);

  const handleTriggerKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) {
      return;
    }
    if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key) && !isOpen) {
      event.preventDefault();
      open();
    }
  };

  const handleSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        setActiveIndex((index) => Math.min(index + 1, Math.max(navItems.length - 1, 0)));
        break;
      case 'ArrowUp':
        event.preventDefault();
        setActiveIndex((index) => Math.max(index - 1, 0));
        break;
      case 'Home':
        event.preventDefault();
        setActiveIndex(0);
        break;
      case 'End':
        event.preventDefault();
        setActiveIndex(Math.max(navItems.length - 1, 0));
        break;
      case 'Enter': {
        event.preventDefault();
        const item = navItems[activeIndex];
        if (item && !item.disabled) {
          commit(item.value);
        }
        break;
      }
      case 'Escape':
        event.preventDefault();
        close(true);
        break;
      case 'Tab':
        close(false);
        break;
      default:
        break;
    }
  };

  const triggerText = selectedOption ? selectedOption.label : (value || '');

  return (
    <div className={cn('relative flex w-full flex-col', className)}>
      <div className="relative">
        <button
          ref={triggerRef}
          id={resolvedId}
          type="button"
          disabled={disabled}
          aria-label={ariaLabel}
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          aria-controls={isOpen ? listboxId : undefined}
          aria-invalid={error || undefined}
          data-value={value}
          onClick={() => (isOpen ? close(false) : open())}
          onKeyDown={handleTriggerKeyDown}
          className={cn(
            'flex h-8 w-full items-center justify-between gap-2 rounded-lg border bg-transparent px-3 text-left text-xs text-foreground',
            'transition-colors duration-200 hover:bg-hover focus:outline-none focus-visible:border-muted-text',
            error ? 'border-danger' : 'border-border',
            disabled ? 'cursor-not-allowed opacity-50' : '',
          )}
        >
          {triggerText ? (
            <span className="flex min-w-0 items-baseline gap-2">
              <span className="truncate">{triggerText}</span>
              {selectedOption?.sublabel ? (
                <span className="shrink-0 truncate text-xs text-muted-text">{selectedOption.sublabel}</span>
              ) : null}
            </span>
          ) : (
            <span className="truncate text-muted-text">{placeholder ?? '请选择'}</span>
          )}
          <svg className="h-3.5 w-3.5 shrink-0 text-secondary-text" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        {clearable && value && !disabled ? (
          <button
            type="button"
            aria-label={ariaLabel ? `${ariaLabel} clear` : 'clear'}
            onClick={() => onChange('')}
            className="absolute right-8 top-1/2 inline-flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-full text-secondary-text hover:text-foreground"
          >
            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        ) : null}
      </div>

      {valueIsStale ? (
        <span className="mt-1 text-xs text-warning">{staleValueLabel ?? '当前配置不可用'}</span>
      ) : null}

      {isOpen && triggerRect && portalHost
        ? createPortal(
          <div
            ref={popoverRef}
            data-dialog-popup="true"
            style={{ top: triggerRect.bottom + 4, left: triggerRect.left, minWidth: triggerRect.width }}
            className="fixed z-50 flex w-max max-w-sm flex-col overflow-hidden rounded-xl border border-border bg-elevated shadow-lg"
          >
            <div className="border-b border-border p-1.5">
              <input
                ref={searchRef}
                type="text"
                role="combobox"
                autoComplete="off"
                aria-expanded
                aria-controls={listboxId}
                aria-autocomplete="list"
                aria-activedescendant={navItems[activeIndex] ? `${resolvedId}-option-${activeIndex}` : undefined}
                aria-label={ariaLabel ? `${ariaLabel} 搜索` : '搜索选项'}
                value={query}
                placeholder={searchPlaceholder ?? '搜索…'}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setActiveIndex(0);
                }}
                onKeyDown={handleSearchKeyDown}
                className="h-7 w-full rounded-md bg-transparent px-2 text-xs text-foreground focus:outline-none"
              />
            </div>
            <ul id={listboxId} role="listbox" aria-label={ariaLabel} className="max-h-60 overflow-auto p-1">
              {navItems.length === 0 ? (
                <li role="presentation" className="px-3 py-1.5 text-xs text-muted-text">
                  {emptyText ?? '无匹配项'}
                </li>
              ) : null}
              {navItems.map((item, index) => (
                <React.Fragment key={`${item.value}-${index}`}>
                  {item.showHeader ? (
                    <li role="presentation" className="px-3 pb-0.5 pt-1.5 text-xs font-medium uppercase tracking-wide text-muted-text">
                      {item.group}
                    </li>
                  ) : null}
                  <li
                    id={`${resolvedId}-option-${index}`}
                    role="option"
                    aria-selected={item.value === value}
                    aria-disabled={item.disabled || undefined}
                    data-value={item.value}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => !item.disabled && commit(item.value)}
                    className={cn(
                      'flex cursor-pointer flex-col gap-0.5 rounded-md px-3 py-1.5 text-xs text-foreground',
                      index === activeIndex && 'bg-hover',
                      item.value === value && 'font-medium',
                      item.disabled && 'cursor-not-allowed opacity-50',
                    )}
                  >
                    <span className="truncate">{item.label}</span>
                    {item.sublabel ? (
                      <span className="truncate text-xs text-muted-text">{item.sublabel}</span>
                    ) : null}
                  </li>
                </React.Fragment>
              ))}
            </ul>
          </div>,
          portalHost,
        )
        : null}
    </div>
  );
};
