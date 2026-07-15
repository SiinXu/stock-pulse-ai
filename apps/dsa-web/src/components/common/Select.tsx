import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
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
  error?: boolean;
  menuAlign?: 'start' | 'end';
}

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
  error = false,
  menuAlign = 'start',
}) => {
  const { t } = useUiLanguage();
  const selectId = useId();
  const resolvedId = id ?? selectId;
  const listboxId = `${resolvedId}-listbox`;
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [triggerRect, setTriggerRect] = useState<DOMRect | null>(null);
  const selectedIndex = options.findIndex((option) => option.value === value);
  const [activeIndex, setActiveIndex] = useState(selectedIndex);
  const selectedOption = selectedIndex >= 0 ? options[selectedIndex] : undefined;
  const resolvedPlaceholder = placeholder ?? t('common.selectPlaceholder');

  const openList = useCallback(() => {
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : 0);
    setTriggerRect(triggerRef.current?.getBoundingClientRect() ?? null);
    setIsOpen(true);
  }, [selectedIndex]);

  const commitOption = useCallback((index: number) => {
    const option = options[index];
    if (option) onChange(option.value);
    setIsOpen(false);
  }, [options, onChange]);

  useEffect(() => {
    if (!isOpen) return;
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (containerRef.current?.contains(target) || listRef.current?.contains(target)) return;
      setIsOpen(false);
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const updateRect = () => {
      setTriggerRect(triggerRef.current?.getBoundingClientRect() ?? null);
    };
    window.addEventListener('scroll', updateRect, true);
    window.addEventListener('resize', updateRect);
    return () => {
      window.removeEventListener('scroll', updateRect, true);
      window.removeEventListener('resize', updateRect);
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !listRef.current) return;
    const activeItem = listRef.current.children[activeIndex] as HTMLElement | undefined;
    activeItem?.scrollIntoView({ block: 'nearest' });
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
        setIsOpen(false);
        break;
      case 'Tab':
        setIsOpen(false);
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
          onClick={() => (isOpen ? setIsOpen(false) : openList())}
          onKeyDown={handleKeyDown}
          className={cn(
            'flex h-8 w-full items-center justify-between gap-2 rounded-lg border bg-transparent px-3 text-xs text-foreground',
            'transition-colors duration-200 hover:bg-hover focus:outline-none focus-visible:border-muted-text',
            error ? 'border-danger' : 'border-border',
            disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
          )}
        >
          <span className={cn('truncate', !selectedOption && 'text-muted-text')}>
            {selectedOption ? selectedOption.label : resolvedPlaceholder}
          </span>
          <svg
            className={cn('h-3.5 w-3.5 shrink-0 text-secondary-text transition-transform duration-200', isOpen && 'rotate-180')}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {isOpen && triggerRect && createPortal(
          <ul
            id={listboxId}
            ref={listRef}
            role="listbox"
            aria-labelledby={label ? resolvedId : undefined}
            style={{
              top: triggerRect.bottom + 4,
              minWidth: triggerRect.width,
              ...(menuAlign === 'end'
                ? { right: Math.max(document.documentElement.clientWidth - triggerRect.right, 0) }
                : { left: triggerRect.left }),
            }}
            className="fixed z-50 max-h-60 w-max overflow-auto rounded-xl border border-border bg-elevated p-1 shadow-lg"
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
                  'flex cursor-pointer items-center justify-between gap-3 rounded-md px-3 py-1.5 text-xs text-foreground',
                  index === activeIndex && 'bg-hover',
                )}
              >
                <span className="truncate">{option.label}</span>
                {option.value === value && (
                  <svg className="h-3.5 w-3.5 shrink-0 text-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </li>
            ))}
          </ul>,
          document.body,
        )}
      </div>
    </div>
  );
};
