import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '../../utils/cn';

export interface ComboboxOption {
  /** Stable value stored on selection (e.g. a canonical model route). */
  value: string;
  /** User-facing display name. */
  label: string;
  /** Optional group header the option is listed under. */
  group?: string;
  /** Optional secondary hint shown to the right (e.g. capability/status). */
  hint?: string;
  disabled?: boolean;
}

interface CreatableComboboxProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  options: ComboboxOption[];
  placeholder?: string;
  disabled?: boolean;
  /** When true (default) the user may type a value that is not in the list. */
  allowCustom?: boolean;
  ariaLabel?: string;
  className?: string;
  error?: boolean;
  emptyText?: string;
  /** Label for the "use this custom value" row, e.g. (v) => `自定义: ${v}`. */
  customLabel?: (input: string) => string;
  /** Label shown when the current value is not in the options list. */
  unavailableLabel?: string;
}

/**
 * A searchable, creatable combobox: one shared control for fields that have a
 * candidate set (models, providers, enums with recommendations) but may still
 * accept a custom value. Supports keyboard navigation, search, custom input,
 * clearing, group headers, and marks a value that is not in the current list as
 * "custom / unavailable" instead of silently dropping it.
 */
export const CreatableCombobox: React.FC<CreatableComboboxProps> = ({
  id,
  value,
  onChange,
  options,
  placeholder,
  disabled = false,
  allowCustom = true,
  ariaLabel,
  className = '',
  error = false,
  emptyText,
  customLabel,
  unavailableLabel,
}) => {
  const reactId = useId();
  const resolvedId = id ?? reactId;
  const listboxId = `${resolvedId}-listbox`;
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [triggerRect, setTriggerRect] = useState<DOMRect | null>(null);

  const selectedOption = useMemo(
    () => options.find((option) => option.value === value),
    [options, value],
  );
  const valueIsCustom = Boolean(value) && !selectedOption;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return options;
    }
    // Search covers display name, stored value (e.g. model route), group header
    // (e.g. connection name) and hint (e.g. provider) so users can filter model
    // options by any of the facets they actually know.
    return options.filter(
      (option) =>
        option.label.toLowerCase().includes(q)
        || option.value.toLowerCase().includes(q)
        || (option.group ?? '').toLowerCase().includes(q)
        || (option.hint ?? '').toLowerCase().includes(q),
    );
  }, [options, query]);

  const trimmedQuery = query.trim();
  const showCustomRow = allowCustom
    && trimmedQuery.length > 0
    && !options.some((option) => option.value === trimmedQuery);
  // Flat list used for keyboard navigation (headers are not navigable). Each
  // item precomputes whether it starts a new group so the render never mutates
  // an outer variable.
  interface NavItem {
    value: string;
    label: string;
    disabled?: boolean;
    custom?: boolean;
    group?: string;
    hint?: string;
    showHeader: boolean;
  }
  const navItems = useMemo<NavItem[]>(() => {
    const base: Array<Omit<NavItem, 'showHeader'>> = filtered.map((option) => ({
      value: option.value,
      label: option.label,
      disabled: option.disabled,
      group: option.group,
      hint: option.hint,
      custom: false,
    }));
    if (showCustomRow) {
      base.push({ value: trimmedQuery, label: customLabel ? customLabel(trimmedQuery) : trimmedQuery, custom: true });
    }
    return base.map((item, index) => {
      const previous = base[index - 1];
      const previousGroup = previous && !previous.custom ? previous.group : undefined;
      const showHeader = !item.custom && Boolean(item.group) && item.group !== previousGroup;
      return { ...item, showHeader };
    });
  }, [filtered, showCustomRow, trimmedQuery, customLabel]);

  const open = useCallback(() => {
    setTriggerRect(inputRef.current?.getBoundingClientRect() ?? null);
    setActiveIndex(0);
    setIsOpen(true);
  }, []);

  const commit = useCallback((next: string) => {
    onChange(next);
    setQuery('');
    setIsOpen(false);
  }, [onChange]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (containerRef.current?.contains(target) || listRef.current?.contains(target)) {
        return;
      }
      setIsOpen(false);
      setQuery('');
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const updateRect = () => setTriggerRect(inputRef.current?.getBoundingClientRect() ?? null);
    window.addEventListener('scroll', updateRect, true);
    window.addEventListener('resize', updateRect);
    return () => {
      window.removeEventListener('scroll', updateRect, true);
      window.removeEventListener('resize', updateRect);
    };
  }, [isOpen]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (disabled) {
      return;
    }
    if (!isOpen && ['ArrowDown', 'ArrowUp'].includes(event.key)) {
      event.preventDefault();
      open();
      return;
    }
    if (!isOpen) {
      return;
    }
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        setActiveIndex((index) => Math.min(index + 1, navItems.length - 1));
        break;
      case 'ArrowUp':
        event.preventDefault();
        setActiveIndex((index) => Math.max(index - 1, 0));
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
        setIsOpen(false);
        setQuery('');
        break;
      case 'Tab':
        setIsOpen(false);
        break;
      default:
        break;
    }
  };

  const displayText = isOpen ? query : (selectedOption ? selectedOption.label : value);

  return (
    <div className={cn('relative flex w-full flex-col', className)} ref={containerRef}>
      <div className="relative">
        <input
          ref={inputRef}
          id={resolvedId}
          role="combobox"
          type="text"
          autoComplete="off"
          disabled={disabled}
          aria-label={ariaLabel}
          aria-expanded={isOpen}
          aria-controls={isOpen ? listboxId : undefined}
          aria-autocomplete="list"
          aria-activedescendant={isOpen && navItems[activeIndex] ? `${resolvedId}-option-${activeIndex}` : undefined}
          data-value={value}
          value={displayText}
          placeholder={placeholder}
          onFocus={open}
          onClick={open}
          onChange={(event) => {
            setQuery(event.target.value);
            setActiveIndex(0);
            if (!isOpen) {
              open();
            }
          }}
          onKeyDown={handleKeyDown}
          className={cn(
            'h-8 w-full rounded-[10px] border bg-transparent px-3 pr-8 text-xs text-foreground',
            'transition-colors duration-200 hover:bg-hover focus:outline-none',
            error ? 'border-danger focus-visible:border-danger' : 'border-border focus-visible:border-muted-text',
            disabled ? 'cursor-not-allowed opacity-50' : '',
          )}
        />
        {value && !disabled ? (
          <button
            type="button"
            aria-label={ariaLabel ? `${ariaLabel} clear` : 'clear'}
            onClick={() => commit('')}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-secondary-text hover:text-foreground"
          >
            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        ) : null}
      </div>

      {valueIsCustom && !isOpen ? (
        <span className="mt-1 text-[11px] text-warning">
          {unavailableLabel ?? (customLabel ? customLabel(value) : `自定义值：${value}`)}
        </span>
      ) : null}

      {isOpen && triggerRect
        ? createPortal(
          <ul
            id={listboxId}
            ref={listRef}
            role="listbox"
            style={{ top: triggerRect.bottom + 4, left: triggerRect.left, minWidth: triggerRect.width }}
            className="fixed z-50 max-h-60 w-max overflow-auto rounded-xl border border-border bg-elevated p-1 shadow-lg"
          >
            {navItems.length === 0 ? (
              <li role="presentation" className="px-3 py-1.5 text-xs text-muted-text">
                {emptyText ?? '无匹配项'}
              </li>
            ) : null}
            {navItems.map((item, index) => (
              <React.Fragment key={`${item.value}-${index}`}>
                {item.showHeader ? (
                  <li role="presentation" className="px-3 pb-0.5 pt-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-text">
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
                    'flex cursor-pointer items-center justify-between gap-3 rounded-[6px] px-3 py-1.5 text-xs text-foreground',
                    index === activeIndex && 'bg-hover',
                    item.disabled && 'cursor-not-allowed opacity-50',
                  )}
                >
                  <span className="truncate">{item.label}</span>
                  {item.hint ? (
                    <span className="shrink-0 text-[10px] text-muted-text">{item.hint}</span>
                  ) : null}
                </li>
              </React.Fragment>
            ))}
          </ul>,
          document.body,
        )
        : null}
    </div>
  );
};
