import type React from 'react';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, Clock3 } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { Button } from './Button';
import { getOverlayStyle } from './overlayZ';
import { useFixedPopup } from './useFixedPopup';

interface TimePickerProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  label?: string;
  ariaLabel?: string;
  placeholder?: string;
  disabled?: boolean;
  autoOpen?: boolean;
  onOpenChange?: (isOpen: boolean) => void;
  className?: string;
  triggerClassName?: string;
  'aria-invalid'?: React.AriaAttributes['aria-invalid'];
  'aria-describedby'?: string;
  'data-testid'?: string;
}

const TIME_PATTERN = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const HOURS = Array.from({ length: 24 }, (_, index) => String(index).padStart(2, '0'));
const MINUTES = Array.from({ length: 60 }, (_, index) => String(index).padStart(2, '0'));

export const TimePicker = ({
  id,
  value,
  onChange,
  label,
  ariaLabel,
  placeholder,
  disabled = false,
  autoOpen = false,
  onOpenChange,
  className,
  triggerClassName,
  'aria-invalid': ariaInvalid,
  'aria-describedby': ariaDescribedBy,
  'data-testid': testId,
}: TimePickerProps) => {
  const { t } = useUiLanguage();
  const generatedId = useId();
  const resolvedId = id ?? generatedId;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const autoOpenedRef = useRef(false);
  const selectedHourRef = useRef<HTMLButtonElement>(null);
  const selectedMinuteRef = useRef<HTMLButtonElement>(null);
  const hourListRef = useRef<HTMLDivElement>(null);
  const minuteListRef = useRef<HTMLDivElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [draftValue, setDraftValue] = useState(TIME_PATTERN.test(value) ? value : '00:00');
  const [draftHour, draftMinute] = draftValue.split(':');
  const { portalHost, popupStyle, prepareForOpen, resetPosition } = useFixedPopup({
    isOpen,
    triggerRef,
    popupRef,
    contentVersion: draftValue,
    constrainWidthToViewport: true,
  });

  const openPicker = useCallback(() => {
    if (disabled) return;
    setDraftValue(TIME_PATTERN.test(value) ? value : '00:00');
    prepareForOpen();
    setIsOpen(true);
    onOpenChange?.(true);
  }, [disabled, onOpenChange, prepareForOpen, value]);

  const closePicker = useCallback((restoreFocus = false) => {
    setIsOpen(false);
    resetPosition();
    onOpenChange?.(false);
    if (restoreFocus) requestAnimationFrame(() => triggerRef.current?.focus());
  }, [onOpenChange, resetPosition]);

  useEffect(() => {
    if (!autoOpen || autoOpenedRef.current || disabled) return;
    autoOpenedRef.current = true;
    const frame = requestAnimationFrame(openPicker);
    return () => cancelAnimationFrame(frame);
  }, [autoOpen, disabled, openPicker]);

  useEffect(() => {
    if (!isOpen) return;
    requestAnimationFrame(() => {
      selectedHourRef.current?.scrollIntoView?.({ block: 'center' });
      selectedMinuteRef.current?.scrollIntoView?.({ block: 'center' });
      hourListRef.current?.focus();
    });
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || popupRef.current?.contains(target)) return;
      closePicker();
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [closePicker, isOpen]);

  const resolvedAriaLabel = ariaLabel ?? label;
  const displayValue = TIME_PATTERN.test(value) ? value : (placeholder ?? t('common.selectPlaceholder'));
  const columnClassName = 'h-44 min-w-0 flex-1 space-y-0.5 overflow-y-auto rounded-lg bg-background/60 p-1';
  const optionClassName = 'flex h-9 w-full items-center justify-center rounded-md text-xs tabular-nums transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-foreground/20';
  const handleColumnKeyDown = (
    column: 'hour' | 'minute',
    event: React.KeyboardEvent<HTMLDivElement>,
  ) => {
    const values = column === 'hour' ? HOURS : MINUTES;
    const currentValue = column === 'hour' ? draftHour : draftMinute;
    const currentIndex = Math.max(values.indexOf(currentValue), 0);
    let nextIndex: number | null = null;
    switch (event.key) {
      case 'ArrowDown':
      case 'ArrowRight':
        nextIndex = Math.min(currentIndex + 1, values.length - 1);
        break;
      case 'ArrowUp':
      case 'ArrowLeft':
        nextIndex = Math.max(currentIndex - 1, 0);
        break;
      case 'PageDown':
        nextIndex = Math.min(currentIndex + 5, values.length - 1);
        break;
      case 'PageUp':
        nextIndex = Math.max(currentIndex - 5, 0);
        break;
      case 'Home':
        nextIndex = 0;
        break;
      case 'End':
        nextIndex = values.length - 1;
        break;
      default:
        break;
    }
    if (nextIndex === null) return;
    event.preventDefault();
    const nextValue = values[nextIndex];
    setDraftValue(column === 'hour'
      ? `${nextValue}:${draftMinute}`
      : `${draftHour}:${nextValue}`);
  };

  return (
    <div className={cn('flex w-fit flex-col', className)}>
      {label ? (
        <label htmlFor={resolvedId} className="mb-1.5 text-xs font-medium text-secondary-text">
          {label}
        </label>
      ) : null}
      <button
        ref={triggerRef}
        id={resolvedId}
        type="button"
        data-testid={testId}
        data-value={value}
        disabled={disabled}
        aria-label={resolvedAriaLabel}
        aria-invalid={ariaInvalid}
        aria-describedby={ariaDescribedBy}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        onClick={() => (isOpen ? closePicker() : openPicker())}
        className={cn(
          'flex h-11 min-h-11 min-w-11 w-full items-center justify-between gap-2 rounded-lg border border-border bg-transparent px-3 text-xs text-foreground',
          'transition-colors duration-200 hover:bg-hover focus:outline-none focus-visible:border-muted-text disabled:cursor-not-allowed disabled:opacity-60',
          ariaInvalid && 'border-danger/40 focus-visible:border-danger',
          triggerClassName,
        )}
      >
        <span className={cn('truncate tabular-nums', !TIME_PATTERN.test(value) && 'text-muted-text')}>{displayValue}</span>
        <span className="flex shrink-0 items-center gap-1 text-secondary-text">
          <Clock3 className="h-4 w-4" aria-hidden="true" />
          <ChevronDown className={cn('h-3.5 w-3.5 transition-transform duration-200', isOpen && 'rotate-180')} aria-hidden="true" />
        </span>
      </button>

      {isOpen && portalHost ? createPortal(
        <div
          ref={popupRef}
          role="dialog"
          aria-label={resolvedAriaLabel}
          style={getOverlayStyle('dropdown', popupStyle)}
          className="fixed w-56 overflow-hidden rounded-xl border border-border bg-elevated p-3 shadow-lg"
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault();
              closePicker(true);
            }
          }}
        >
          <div className="mb-2 grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-center text-xs font-semibold text-secondary-text" aria-hidden="true">
            <span>{draftHour}</span>
            <span>:</span>
            <span>{draftMinute}</span>
          </div>
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
            <div
              ref={hourListRef}
              role="listbox"
              tabIndex={0}
              aria-label={t('common.hours')}
              aria-activedescendant={`${resolvedId}-hour-${draftHour}`}
              className={columnClassName}
              onKeyDown={(event) => handleColumnKeyDown('hour', event)}
            >
              {HOURS.map((hour) => {
                const selected = hour === draftHour;
                return (
                  <button
                    key={hour}
                    ref={selected ? selectedHourRef : undefined}
                    type="button"
                    id={`${resolvedId}-hour-${hour}`}
                    role="option"
                    data-time-hour={hour}
                    aria-selected={selected}
                    tabIndex={-1}
                    onClick={() => {
                      setDraftValue(`${hour}:${draftMinute}`);
                      hourListRef.current?.focus();
                    }}
                    className={cn(optionClassName, selected ? 'bg-foreground font-semibold text-background' : 'text-foreground hover:bg-hover')}
                  >
                    {hour}
                  </button>
                );
              })}
            </div>
            <span className="font-semibold text-muted-text" aria-hidden="true">:</span>
            <div
              ref={minuteListRef}
              role="listbox"
              tabIndex={0}
              aria-label={t('common.minutes')}
              aria-activedescendant={`${resolvedId}-minute-${draftMinute}`}
              className={columnClassName}
              onKeyDown={(event) => handleColumnKeyDown('minute', event)}
            >
              {MINUTES.map((minute) => {
                const selected = minute === draftMinute;
                return (
                  <button
                    key={minute}
                    ref={selected ? selectedMinuteRef : undefined}
                    type="button"
                    id={`${resolvedId}-minute-${minute}`}
                    role="option"
                    data-time-minute={minute}
                    aria-selected={selected}
                    tabIndex={-1}
                    onClick={() => {
                      setDraftValue(`${draftHour}:${minute}`);
                      minuteListRef.current?.focus();
                    }}
                    className={cn(optionClassName, selected ? 'bg-foreground font-semibold text-background' : 'text-foreground hover:bg-hover')}
                  >
                    {minute}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="mt-3 flex justify-end gap-2 border-t border-border pt-3">
            <Button variant="ghost" size="sm" onClick={() => closePicker(true)}>{t('common.cancel')}</Button>
            <Button size="sm" onClick={() => {
              onChange(draftValue);
              closePicker(true);
            }}>{t('common.confirm')}</Button>
          </div>
        </div>,
        portalHost,
      ) : null}
    </div>
  );
};
