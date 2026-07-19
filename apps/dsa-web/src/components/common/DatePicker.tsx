import type React from 'react';
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { cn } from '../../utils/cn';
import { getUiLocale } from '../../utils/uiLocale';
import { IconButton } from './IconButton';
import { useFixedPopup } from './useFixedPopup';

interface DatePickerProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  label?: string;
  ariaLabel?: string;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  min?: string;
  max?: string;
  error?: string;
  ariaDescribedBy?: string;
  className?: string;
  triggerClassName?: string;
  'data-testid'?: string;
}

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function parseIsoDate(value: string): Date | null {
  if (!ISO_DATE_PATTERN.test(value)) return null;
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year
    && date.getMonth() === month - 1
    && date.getDate() === day
    ? date
    : null;
}

function toIsoDate(date: Date): string {
  const year = String(date.getFullYear()).padStart(4, '0');
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export const DatePicker = ({
  id,
  value,
  onChange,
  label,
  ariaLabel,
  placeholder,
  disabled = false,
  required = false,
  min,
  max,
  error,
  ariaDescribedBy,
  className,
  triggerClassName,
  'data-testid': testId,
}: DatePickerProps) => {
  const { language, t } = useUiLanguage();
  const generatedId = useId();
  const resolvedId = id ?? generatedId;
  const triggerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const calendarButtonRef = useRef<HTMLButtonElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const selectedDate = parseIsoDate(value);
  const today = useMemo(() => new Date(), []);
  const [visibleMonth, setVisibleMonth] = useState(() => {
    const initialDate = selectedDate ?? today;
    return new Date(initialDate.getFullYear(), initialDate.getMonth(), 1);
  });
  const [focusedDateIso, setFocusedDateIso] = useState(() => toIsoDate(selectedDate ?? today));
  const { portalHost, popupStyle, prepareForOpen, resetPosition } = useFixedPopup({
    isOpen,
    triggerRef,
    popupRef,
    contentVersion: `${visibleMonth.getFullYear()}-${visibleMonth.getMonth()}`,
    constrainWidthToViewport: true,
  });

  const monthFormatter = useMemo(() => new Intl.DateTimeFormat(getUiLocale(language), {
    year: 'numeric',
    month: 'long',
  }), [language]);
  const dayLabelFormatter = useMemo(() => new Intl.DateTimeFormat(getUiLocale(language), {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }), [language]);
  const weekdayFormatter = useMemo(() => new Intl.DateTimeFormat(getUiLocale(language), {
    weekday: 'short',
  }), [language]);

  const openPicker = useCallback(() => {
    if (disabled) return;
    const initialDate = parseIsoDate(value) ?? today;
    let initialIso = toIsoDate(initialDate);
    if (min && initialIso < min) initialIso = min;
    if (max && initialIso > max) initialIso = max;
    const focusDate = parseIsoDate(initialIso) ?? initialDate;
    setVisibleMonth(new Date(focusDate.getFullYear(), focusDate.getMonth(), 1));
    setFocusedDateIso(initialIso);
    prepareForOpen();
    setIsOpen(true);
  }, [disabled, max, min, prepareForOpen, today, value]);

  const closePicker = useCallback((restoreFocus = false) => {
    setIsOpen(false);
    resetPosition();
    if (restoreFocus) {
      requestAnimationFrame(() => {
        calendarButtonRef.current?.focus();
      });
    }
  }, [resetPosition]);

  useEffect(() => {
    if (!isOpen) return;
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || popupRef.current?.contains(target)) return;
      closePicker();
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [closePicker, isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const frame = requestAnimationFrame(() => {
      popupRef.current
        ?.querySelector<HTMLButtonElement>(`[data-date="${focusedDateIso}"]`)
        ?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [focusedDateIso, isOpen, visibleMonth]);

  const weekdays = useMemo(() => Array.from({ length: 7 }, (_, index) => {
    const monday = new Date(2024, 0, 1 + index);
    return weekdayFormatter.format(monday);
  }), [weekdayFormatter]);

  const calendarDays = useMemo(() => {
    const year = visibleMonth.getFullYear();
    const month = visibleMonth.getMonth();
    const firstWeekday = (new Date(year, month, 1).getDay() + 6) % 7;
    return Array.from({ length: 42 }, (_, index) => {
      const date = new Date(year, month, index - firstWeekday + 1);
      return date.getMonth() === month ? date : null;
    });
  }, [visibleMonth]);

  const resolvedAriaLabel = ariaLabel ?? label;
  const resolvedPlaceholder = placeholder ?? t('common.selectPlaceholder');
  const errorId = error ? `${resolvedId}-error` : undefined;
  const describedBy = [ariaDescribedBy, errorId].filter(Boolean).join(' ') || undefined;
  const isValueInvalid = value !== '' && (
    !selectedDate
    || Boolean(min && value < min)
    || Boolean(max && value > max)
  );

  useEffect(() => {
    inputRef.current?.setCustomValidity(isValueInvalid ? (error ?? 'YYYY-MM-DD') : '');
  }, [error, isValueInvalid]);

  const focusCalendarDate = (date: Date) => {
    let isoDate = toIsoDate(date);
    if (min && isoDate < min) isoDate = min;
    if (max && isoDate > max) isoDate = max;
    const nextDate = parseIsoDate(isoDate);
    if (!nextDate) return;
    setVisibleMonth(new Date(nextDate.getFullYear(), nextDate.getMonth(), 1));
    setFocusedDateIso(isoDate);
  };

  const handleDayKeyDown = (date: Date, event: React.KeyboardEvent<HTMLButtonElement>) => {
    const nextDate = new Date(date);
    switch (event.key) {
      case 'ArrowLeft':
        nextDate.setDate(nextDate.getDate() - 1);
        break;
      case 'ArrowRight':
        nextDate.setDate(nextDate.getDate() + 1);
        break;
      case 'ArrowUp':
        nextDate.setDate(nextDate.getDate() - 7);
        break;
      case 'ArrowDown':
        nextDate.setDate(nextDate.getDate() + 7);
        break;
      case 'Home':
        nextDate.setDate(nextDate.getDate() - ((nextDate.getDay() + 6) % 7));
        break;
      case 'End':
        nextDate.setDate(nextDate.getDate() + (6 - ((nextDate.getDay() + 6) % 7)));
        break;
      case 'PageUp':
      case 'PageDown': {
        const direction = event.key === 'PageUp' ? -1 : 1;
        const targetDay = nextDate.getDate();
        nextDate.setDate(1);
        nextDate.setMonth(nextDate.getMonth() + direction);
        const monthEnd = new Date(nextDate.getFullYear(), nextDate.getMonth() + 1, 0).getDate();
        nextDate.setDate(Math.min(targetDay, monthEnd));
        break;
      }
      default:
        return;
    }
    event.preventDefault();
    focusCalendarDate(nextDate);
  };

  return (
    <div className={cn('flex w-fit flex-col', className)}>
      {label ? (
        <label htmlFor={resolvedId} className="mb-1.5 text-xs font-medium text-secondary-text">
          {label}
        </label>
      ) : null}
      <div
        ref={triggerRef}
        className={cn(
          'flex h-11 min-h-11 min-w-11 w-full cursor-text items-center justify-between gap-2 rounded-lg border border-border bg-transparent px-3 text-xs text-foreground',
          'transition-colors duration-200 hover:bg-hover focus:outline-none focus-visible:border-muted-text disabled:cursor-not-allowed disabled:opacity-60',
          triggerClassName,
        )}
      >
        <input
          ref={inputRef}
          id={resolvedId}
          type="text"
          inputMode="numeric"
          data-testid={testId}
          data-value={value}
          value={value}
          disabled={disabled}
          required={required}
          pattern="\d{4}-\d{2}-\d{2}"
          aria-label={resolvedAriaLabel}
          aria-invalid={Boolean(error || isValueInvalid) || undefined}
          aria-describedby={describedBy}
          aria-haspopup="dialog"
          aria-expanded={isOpen}
          placeholder={resolvedPlaceholder}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Escape' && isOpen) {
              event.preventDefault();
              closePicker();
            } else if (event.altKey && event.key === 'ArrowDown') {
              event.preventDefault();
              openPicker();
            }
          }}
          className="h-full min-w-0 flex-1 bg-transparent text-base text-foreground outline-none placeholder:text-muted-text tabular-nums sm:text-xs"
        />
        <button
          ref={calendarButtonRef}
          type="button"
          disabled={disabled}
          aria-label={formatUiText(t('common.openCalendar'), { field: resolvedAriaLabel ?? resolvedPlaceholder })}
          aria-haspopup="dialog"
          aria-expanded={isOpen}
          onClick={() => (isOpen ? closePicker() : openPicker())}
          className="flex h-11 w-11 shrink-0 items-center justify-center gap-1 rounded-lg text-secondary-text transition-colors hover:bg-hover hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-foreground/20 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <CalendarDays className="h-4 w-4" aria-hidden="true" />
          <ChevronDown className={cn('h-3.5 w-3.5 transition-transform duration-200', isOpen && 'rotate-180')} aria-hidden="true" />
        </button>
      </div>

      {isOpen && portalHost ? createPortal(
        <div
          ref={popupRef}
          role="dialog"
          aria-label={resolvedAriaLabel}
          style={popupStyle}
          className="fixed z-[100] w-72 overflow-hidden rounded-xl border border-border bg-elevated p-3 shadow-lg"
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault();
              closePicker(true);
            }
          }}
        >
          <div className="mb-2 flex h-9 items-center justify-between gap-2">
            <IconButton
              variant="ghost"
              size="default"
              aria-label={t('common.prevPage')}
              onClick={() => setVisibleMonth((current) => new Date(current.getFullYear(), current.getMonth() - 1, 1))}
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            </IconButton>
            <p className="text-sm font-semibold text-foreground">{monthFormatter.format(visibleMonth)}</p>
            <IconButton
              variant="ghost"
              size="default"
              aria-label={t('common.nextPage')}
              onClick={() => setVisibleMonth((current) => new Date(current.getFullYear(), current.getMonth() + 1, 1))}
            >
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </IconButton>
          </div>
          <div className="grid grid-cols-7" aria-hidden="true">
            {weekdays.map((weekday, index) => (
              <span key={`${weekday}-${index}`} className="flex h-8 items-center justify-center text-xs font-medium text-muted-text">
                {weekday}
              </span>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-0.5">
            {calendarDays.map((date, index) => {
              if (!date) return <span key={`empty-${index}`} className="h-9 w-9" aria-hidden="true" />;
              const isoDate = toIsoDate(date);
              const isSelected = isoDate === value;
              const isToday = isoDate === toIsoDate(today);
              const isDisabled = Boolean((min && isoDate < min) || (max && isoDate > max));
              return (
                <button
                  key={isoDate}
                  type="button"
                  data-calendar-day="true"
                  data-date={isoDate}
                  disabled={isDisabled}
                  aria-label={dayLabelFormatter.format(date)}
                  aria-pressed={isSelected}
                  tabIndex={isoDate === focusedDateIso ? 0 : -1}
                  onFocus={() => setFocusedDateIso(isoDate)}
                  onKeyDown={(event) => handleDayKeyDown(date, event)}
                  onClick={() => {
                    onChange(isoDate);
                    closePicker(true);
                  }}
                  className={cn(
                    'flex h-9 w-9 items-center justify-center rounded-lg text-xs tabular-nums transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-foreground/20',
                    isSelected ? 'bg-foreground font-semibold text-background' : 'text-foreground hover:bg-hover',
                    isToday && !isSelected && 'ring-1 ring-border',
                    isDisabled && 'cursor-not-allowed opacity-30',
                  )}
                >
                  {date.getDate()}
                </button>
              );
            })}
          </div>
        </div>,
        portalHost,
      ) : null}
      {error ? <p id={errorId} role="alert" className="mt-2 text-xs text-danger">{error}</p> : null}
    </div>
  );
};
