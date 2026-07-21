import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { useFixedPopup } from './useFixedPopup';

export interface SelectOption {
  value: string;
  label: string;
  swatch?: {
    start: 'success' | 'danger' | 'warning' | 'info' | 'neutral';
    end?: 'success' | 'danger' | 'warning' | 'info' | 'neutral';
  };
}

export type SelectSize = 'default' | 'comfortable' | 'primary';

export interface SelectProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  label?: string;
  ariaLabel?: string;
  ariaDescribedBy?: string;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  triggerClassName?: string;
  error?: boolean;
  menuAlign?: 'start' | 'end';
  menuPlacement?: 'auto' | 'bottom' | 'top';
  size?: SelectSize;
}

// min-h-11 keeps the 44px mobile touch target; sm:* restores compact desktop heights.
const SELECT_SIZE_STYLES: Record<SelectSize, string> = {
  default: 'min-h-11 sm:h-8 sm:min-h-8',
  comfortable: 'min-h-11 sm:h-9 sm:min-h-9',
  primary: 'min-h-11 sm:h-10 sm:min-h-10',
};

const SELECT_SWATCH_STYLES = {
  success: 'bg-success',
  danger: 'bg-danger',
  warning: 'bg-warning',
  info: 'bg-info',
  neutral: 'bg-muted-text',
} as const;

const SelectOptionContent = ({ option }: { option: SelectOption }) => (
  <span className="flex min-w-0 items-center gap-2">
    {option.swatch ? (
      <span
        data-select-swatch="true"
        aria-hidden="true"
        className="flex h-4 w-4 shrink-0 overflow-hidden rounded-full border border-border"
      >
        <span className={cn('h-full flex-1', SELECT_SWATCH_STYLES[option.swatch.start])} />
        {option.swatch.end ? (
          <span className={cn('h-full flex-1', SELECT_SWATCH_STYLES[option.swatch.end])} />
        ) : null}
      </span>
    ) : null}
    <span className="truncate">{option.label}</span>
  </span>
);

/**
 * Custom select with a compact trigger and a styled listbox popover
 * (native <select> popups cannot be styled consistently across platforms).
 */
export const Select: React.FC<SelectProps> = ({
  id,
  value,
  onChange,
  options,
  label,
  ariaLabel,
  ariaDescribedBy,
  placeholder,
  disabled = false,
  className = '',
  triggerClassName = '',
  error = false,
  menuAlign = 'start',
  menuPlacement = 'auto',
  size = 'comfortable',
}) => {
  const { t } = useUiLanguage();
  const selectId = useId();
  const resolvedId = id ?? selectId;
  const listboxId = `${resolvedId}-listbox`;
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const selectedIndex = options.findIndex((option) => option.value === value);
  const [activeIndex, setActiveIndex] = useState(selectedIndex);
  const selectedOption = selectedIndex >= 0 ? options[selectedIndex] : undefined;
  const resolvedPlaceholder = placeholder ?? t('common.selectPlaceholder');
  const { portalHost, popupStyle, prepareForOpen, resetPosition } = useFixedPopup({
    isOpen,
    triggerRef,
    popupRef: listRef,
    contentVersion: `${activeIndex}:${options.length}:${value}`,
    constrainWidthToViewport: true,
    placement: menuPlacement,
    align: menuAlign,
  });

  const openList = useCallback(() => {
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : 0);
    prepareForOpen();
    setIsOpen(true);
  }, [prepareForOpen, selectedIndex]);

  const closeList = useCallback(() => {
    setIsOpen(false);
    resetPosition();
  }, [resetPosition]);

  const commitOption = useCallback((index: number) => {
    const option = options[index];
    if (option) onChange(option.value);
    closeList();
  }, [closeList, options, onChange]);

  useEffect(() => {
    if (!isOpen) return;
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (containerRef.current?.contains(target) || listRef.current?.contains(target)) return;
      closeList();
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [closeList, isOpen]);

  useEffect(() => {
    if (!isOpen || !listRef.current) return;
    const activeItem = listRef.current.children[activeIndex] as HTMLElement | undefined;
    activeItem?.scrollIntoView?.({ block: 'nearest' });
  }, [isOpen, activeIndex]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    if (!isOpen) {
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) {
        event.preventDefault();
        openList();
      }
      return;
    }
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        setActiveIndex((index) => Math.min(index + 1, options.length - 1));
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
        setActiveIndex(options.length - 1);
        break;
      case 'Enter':
      case ' ':
        event.preventDefault();
        commitOption(activeIndex);
        break;
      case 'Escape':
        event.preventDefault();
        closeList();
        break;
      case 'Tab':
        closeList();
        break;
      default:
        break;
    }
  };

  return (
    <div className={cn('flex w-fit flex-col', className)}>
      {label ? <label htmlFor={resolvedId} className="mb-1.5 text-xs font-medium text-secondary-text">{label}</label> : null}
      <div ref={containerRef}>
        <button
          type="button"
          ref={triggerRef}
          id={resolvedId}
          role="combobox"
          disabled={disabled}
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          aria-controls={isOpen ? listboxId : undefined}
          aria-label={ariaLabel}
          aria-invalid={error || undefined}
          aria-describedby={ariaDescribedBy}
          aria-activedescendant={isOpen ? `${resolvedId}-option-${activeIndex}` : undefined}
          data-value={value}
          data-control="select"
          data-size={size}
          onClick={() => (isOpen ? closeList() : openList())}
          onKeyDown={handleKeyDown}
          className={cn(
            'flex w-full items-center justify-between gap-2 rounded-lg border bg-transparent px-3 text-xs text-foreground',
            'transition-colors duration-200 hover:bg-hover focus:outline-none focus-visible:border-muted-text',
            SELECT_SIZE_STYLES[size],
            error ? 'border-danger' : 'border-border',
            disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
            triggerClassName,
          )}
        >
          <span className={cn('min-w-0 truncate', !selectedOption && 'text-muted-text')}>
            {selectedOption ? <SelectOptionContent option={selectedOption} /> : resolvedPlaceholder}
          </span>
          <ChevronDown
            className={cn('h-3.5 w-3.5 shrink-0 text-secondary-text transition-transform duration-200', isOpen && 'rotate-180')}
            aria-hidden="true"
          />
        </button>

        {isOpen && portalHost ? createPortal(
          <ul
            id={listboxId}
            ref={listRef}
            role="listbox"
            aria-labelledby={label ? resolvedId : undefined}
            aria-label={!label ? ariaLabel : undefined}
            data-dialog-popup="true"
            style={popupStyle}
            className="fixed max-h-60 w-max overflow-auto rounded-xl border border-border bg-elevated p-1 shadow-lg"
          >
            {options.map((option, index) => (
              <li
                key={option.value}
                id={`${resolvedId}-option-${index}`}
                role="option"
                aria-selected={option.value === value}
                data-value={option.value}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => commitOption(index)}
                className={cn(
                  'flex min-h-11 cursor-pointer items-center justify-between gap-3 rounded-md px-3 py-1.5 text-xs text-foreground sm:min-h-9',
                  index === activeIndex && 'bg-hover',
                )}
              >
                <SelectOptionContent option={option} />
                {option.value === value && (
                  <Check className="h-3.5 w-3.5 shrink-0 text-foreground" aria-hidden="true" />
                )}
              </li>
            ))}
          </ul>,
          portalHost,
        ) : null}
      </div>
    </div>
  );
};
