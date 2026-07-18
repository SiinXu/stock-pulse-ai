// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, ListOrdered } from 'lucide-react';
import { Checkbox, Input } from '../common';
import { useFixedPopup } from '../common/useFixedPopup';
import { formatUiText } from '../../i18n/uiText';
import type { UiLanguage } from '../../i18n/uiText';
import { SETTINGS_CONTROLS_TEXT } from '../../locales/settingsControls';
import { cn } from '../../utils/cn';

const SEARCH_THRESHOLD = 5;

export interface MultiSelectOption {
  value: string;
  label: string;
}

interface MultiSelectDropdownProps {
  /** Trigger button id so an external <label htmlFor> can target the control. */
  id?: string;
  options: MultiSelectOption[];
  /** Currently selected values in stored order (may contain values outside options). */
  selected: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
  hasError?: boolean;
  ariaDescribedBy?: string;
  ariaLabel?: string;
  /** When true, selection order is meaningful: new picks append to the end. */
  ordered?: boolean;
  language?: UiLanguage;
  testId?: string;
}

/**
 * Generic collapsed multi-select for settings enums. Stored values outside the
 * catalog stay visible and deselectable so saving never silently drops them.
 */
export const MultiSelectDropdown: React.FC<MultiSelectDropdownProps> = ({
  id,
  options,
  selected,
  onChange,
  disabled = false,
  hasError = false,
  ariaDescribedBy,
  ariaLabel,
  ordered = false,
  language = 'zh',
  testId,
}) => {
  const reactId = useId();
  const listboxId = `${reactId}-listbox`;
  const searchId = `${reactId}-search`;
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const lastFocusedOptionValueRef = useRef<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const text = SETTINGS_CONTROLS_TEXT[language];

  const knownValues = useMemo(() => new Set(options.map((option) => option.value)), [options]);
  const unknownValues = useMemo(
    () => selected.filter((entry) => !knownValues.has(entry)),
    [selected, knownValues],
  );
  const entries = useMemo<MultiSelectOption[]>(
    () => [...options, ...unknownValues.map((entry) => ({ value: entry, label: entry }))],
    [options, unknownValues],
  );
  const showSearch = entries.length > SEARCH_THRESHOLD;
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return entries;
    }
    return entries.filter(
      (entry) => entry.value.toLowerCase().includes(q) || entry.label.toLowerCase().includes(q),
    );
  }, [entries, query]);
  const popupContentVersion = useMemo(
    () => [filtered.length, ordered, query] as const,
    [filtered.length, ordered, query],
  );
  const {
    portalHost,
    popupStyle,
    prepareForOpen,
    resetPosition,
  } = useFixedPopup({
    isOpen,
    triggerRef,
    popupRef,
    contentVersion: popupContentVersion,
    constrainWidthToViewport: true,
    matchTriggerWidth: true,
  });

  const open = useCallback(() => {
    if (disabled) {
      return;
    }
    lastFocusedOptionValueRef.current = null;
    prepareForOpen();
    setIsOpen(true);
  }, [disabled, prepareForOpen]);

  const close = useCallback((restoreFocus: boolean) => {
    setIsOpen(false);
    setQuery('');
    lastFocusedOptionValueRef.current = null;
    resetPosition();
    if (restoreFocus) {
      triggerRef.current?.focus();
    }
  }, [resetPosition]);

  useEffect(() => {
    if (!isOpen || disabled) {
      return;
    }
    const popup = popupRef.current;
    if (!popup || popup.contains(document.activeElement)) {
      return;
    }
    const enabledOptions = Array.from(
      popup.querySelectorAll<HTMLInputElement>('input[type="checkbox"]:not(:disabled)'),
    );
    const lastFocusedOptionValue = lastFocusedOptionValueRef.current;
    const focusTarget = lastFocusedOptionValue === null
      ? document.getElementById(searchId) ?? enabledOptions[0]
      : enabledOptions.find(
        (option) => option.dataset.optionValue === lastFocusedOptionValue,
      ) ?? enabledOptions[0];
    focusTarget?.focus();
  }, [disabled, isOpen, searchId]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (rootRef.current?.contains(target) || popupRef.current?.contains(target)) {
        return;
      }
      close(false);
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [close, isOpen]);

  const toggle = (target: string) => {
    const isSelected = selected.includes(target);
    if (ordered) {
      onChange(isSelected ? selected.filter((entry) => entry !== target) : [...selected, target]);
      return;
    }
    const nextSet = new Set(selected);
    if (isSelected) {
      nextSet.delete(target);
    } else {
      nextSet.add(target);
    }
    const orderedKnown = options.map((option) => option.value).filter((value) => nextSet.has(value));
    const keptUnknown = unknownValues.filter((entry) => nextSet.has(entry));
    onChange([...orderedKnown, ...keptUnknown]);
  };

  const positionOf = (value: string) => selected.indexOf(value) + 1;

  return (
    <div ref={rootRef} className="relative" data-testid={testId}>
      <div
        className={cn(
          'flex min-h-9 w-full items-center rounded-lg border bg-transparent px-0 py-0 text-xs text-foreground transition-colors focus-within:border-muted-text',
          hasError ? 'border-danger' : 'border-border',
        )}
      >
        <button
          ref={triggerRef}
          id={id}
          type="button"
          disabled={disabled}
          aria-label={ariaLabel}
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          aria-controls={isOpen ? listboxId : undefined}
          aria-invalid={hasError || undefined}
          aria-describedby={ariaDescribedBy}
          onClick={() => (isOpen ? close(false) : open())}
          className="flex min-h-9 min-w-0 flex-1 items-center justify-between gap-2 rounded-lg px-2 text-left hover:bg-hover focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
        >
          <span className="shrink-0 text-muted-text">
            {formatUiText(text.selectedOptions, { selected: selected.length, total: entries.length })}
          </span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-secondary-text" aria-hidden="true" />
        </button>
      </div>

      {isOpen && popupStyle && portalHost
        ? createPortal(
        <div
          ref={popupRef}
          data-dialog-popup="true"
          style={popupStyle}
          className="fixed z-50 flex flex-col overflow-hidden rounded-xl border border-border bg-elevated shadow-lg"
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault();
              close(true);
            }
          }}
        >
          {showSearch ? (
            <div className="p-2">
              <Input
                id={searchId}
                value={query}
                disabled={disabled}
                onChange={(event) => setQuery(event.target.value)}
                onFocus={() => {
                  lastFocusedOptionValueRef.current = null;
                }}
                onKeyDown={(event) => {
                  if (event.key !== 'Tab') {
                    return;
                  }
                  if (event.shiftKey) {
                    event.preventDefault();
                    close(true);
                    return;
                  }
                  const firstOption = popupRef.current?.querySelector<HTMLInputElement>(
                    'input[type="checkbox"]:not(:disabled)',
                  );
                  if (firstOption) {
                    event.preventDefault();
                    firstOption.focus();
                    return;
                  }
                  close(false);
                }}
                aria-label={text.searchOptions}
                placeholder={text.searchOptionsPlaceholder}
                className="min-h-9 rounded-lg"
              />
            </div>
          ) : null}
          {ordered ? (
            <p className="px-3 py-2 text-xs text-muted-text">{text.orderedHint}</p>
          ) : null}
          <ul
            id={listboxId}
            role="listbox"
            aria-label={ariaLabel ?? text.availableOptions}
            aria-multiselectable="true"
            className="min-h-0 max-h-48 space-y-0.5 overflow-y-auto p-1"
          >
            {filtered.length === 0 ? (
              <li role="presentation" className="px-3 py-2 text-xs text-muted-text">
                {text.noMatchingOptions}
              </li>
            ) : filtered.map((entry) => {
              const isSelected = selected.includes(entry.value);
              return (
                <li
                  key={entry.value}
                  role="option"
                  aria-selected={isSelected}
                  className="rounded-md hover:bg-hover"
                >
                  <Checkbox
                    data-option-value={entry.value}
                    checked={isSelected}
                    disabled={disabled}
                    onChange={() => toggle(entry.value)}
                    onFocus={() => {
                      lastFocusedOptionValueRef.current = entry.value;
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        toggle(entry.value);
                        return;
                      }
                      if (event.key === 'Tab') {
                        const enabledOptions = Array.from(
                          popupRef.current?.querySelectorAll<HTMLInputElement>(
                            'input[type="checkbox"]:not(:disabled)',
                          ) ?? [],
                        );
                        if (event.shiftKey && enabledOptions[0] === event.currentTarget) {
                          const search = document.getElementById(searchId);
                          event.preventDefault();
                          if (search) {
                            search.focus();
                          } else {
                            close(true);
                          }
                        } else if (!event.shiftKey && enabledOptions.at(-1) === event.currentTarget) {
                          event.preventDefault();
                          close(true);
                        }
                      }
                    }}
                    containerClassName="min-h-9 px-3 py-1.5 text-sm text-secondary-text"
                    label={(
                      <span className="flex min-w-0 flex-1 items-center gap-2 font-normal text-secondary-text">
                        <span className="min-w-0 truncate">
                          {ordered ? entry.label.replace(/\s*[（(][^）)]*[）)]\s*$/, '') : entry.label}
                        </span>
                        {ordered && isSelected ? (
                          <span
                            className="ml-auto inline-flex shrink-0 items-center gap-1 text-xs text-muted-text"
                          >
                            <ListOrdered className="h-3.5 w-3.5" aria-hidden="true" />
                            <span aria-hidden="true">{positionOf(entry.value)}</span>
                            <span className="sr-only">
                              {formatUiText(text.priorityPosition, { position: positionOf(entry.value) })}
                            </span>
                          </span>
                        ) : null}
                      </span>
                    )}
                  />
                </li>
              );
            })}
          </ul>
        </div>,
        portalHost,
      )
        : null}
    </div>
  );
};
