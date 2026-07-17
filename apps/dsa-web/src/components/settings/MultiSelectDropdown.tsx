import type React from 'react';
import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, X } from 'lucide-react';
import { Input } from '../common';
import { formatUiText } from '../../i18n/uiText';
import type { UiLanguage } from '../../i18n/uiText';
import { SETTINGS_CONTROLS_TEXT } from '../../locales/settingsControls';
import { cn } from '../../utils/cn';

const SEARCH_THRESHOLD = 5;
const POPUP_GAP = 4;
const VIEWPORT_MARGIN = 8;

interface PopupPosition {
  top: number;
  left: number;
  maxHeight: number;
}

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
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [triggerRect, setTriggerRect] = useState<DOMRect | null>(null);
  const [portalHost, setPortalHost] = useState<HTMLElement | null>(null);
  const [popupPosition, setPopupPosition] = useState<PopupPosition | null>(null);
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
  const labelByValue = useMemo(
    () => new Map(entries.map((entry) => [entry.value, entry.label])),
    [entries],
  );
  const getLabel = (value: string) => labelByValue.get(value) ?? value;

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

  const open = useCallback(() => {
    if (disabled) {
      return;
    }
    setPopupPosition(null);
    setTriggerRect(triggerRef.current?.getBoundingClientRect() ?? null);
    setPortalHost(
      (triggerRef.current?.closest('[role="dialog"]') as HTMLElement | null) ?? document.body,
    );
    setIsOpen(true);
  }, [disabled]);

  const close = useCallback((restoreFocus: boolean) => {
    setIsOpen(false);
    setQuery('');
    setPopupPosition(null);
    if (restoreFocus) {
      triggerRef.current?.focus();
    }
  }, []);

  useLayoutEffect(() => {
    const popup = popupRef.current;
    if (!isOpen || !triggerRect || !popup) {
      return;
    }

    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const popupRect = popup.getBoundingClientRect();
    const maxHeight = Math.max(viewportHeight - (VIEWPORT_MARGIN * 2), 0);
    const popupHeight = Math.min(popupRect.height, maxHeight);
    const availableBelow = viewportHeight - triggerRect.bottom - POPUP_GAP - VIEWPORT_MARGIN;
    const availableAbove = triggerRect.top - POPUP_GAP - VIEWPORT_MARGIN;
    const openAbove = popupHeight > availableBelow && availableAbove > availableBelow;
    const preferredTop = openAbove
      ? triggerRect.top - POPUP_GAP - popupHeight
      : triggerRect.bottom + POPUP_GAP;
    const maxTop = Math.max(viewportHeight - VIEWPORT_MARGIN - popupHeight, VIEWPORT_MARGIN);
    const top = Math.min(Math.max(preferredTop, VIEWPORT_MARGIN), maxTop);
    const maxLeft = Math.max(viewportWidth - VIEWPORT_MARGIN - popupRect.width, VIEWPORT_MARGIN);
    const left = Math.min(Math.max(triggerRect.left, VIEWPORT_MARGIN), maxLeft);

    setPopupPosition({ top, left, maxHeight });
  }, [filtered.length, isOpen, ordered, portalHost, query, triggerRect]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    document.getElementById(searchId)?.focus();
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (rootRef.current?.contains(target) || popupRef.current?.contains(target)) {
        return;
      }
      close(false);
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [close, isOpen, searchId]);

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
          'flex min-h-11 w-full flex-wrap items-center gap-1.5 rounded-lg border bg-transparent px-2 py-1 text-xs text-foreground transition-colors focus-within:border-muted-text',
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
          className="flex min-h-11 min-w-0 flex-1 items-center justify-between gap-2 rounded-full px-1 text-left hover:bg-hover focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
        >
          <span className="shrink-0 text-muted-text">
            {formatUiText(text.selectedOptions, { selected: selected.length, total: entries.length })}
          </span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-secondary-text" aria-hidden="true" />
        </button>
        {selected.slice(0, 2).map((value) => (
          <span key={value} className="inline-flex min-h-11 min-w-0 max-w-36 items-center gap-0.5 rounded-full border border-border pl-1.5">
            <span className="truncate">
              {ordered ? `${positionOf(value)}. ${getLabel(value)}` : getLabel(value)}
            </span>
            <button
              type="button"
              disabled={disabled}
              aria-label={formatUiText(text.removeOption, { option: getLabel(value) })}
              onClick={() => toggle(value)}
              className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-muted-text hover:text-danger focus:outline-none disabled:cursor-not-allowed"
            >
              <X className="h-3 w-3" aria-hidden="true" />
            </button>
          </span>
        ))}
        {selected.length > 2 ? <span className="shrink-0 text-muted-text">+{selected.length - 2}</span> : null}
      </div>

      {isOpen && triggerRect && portalHost
        ? createPortal(
        <div
          ref={popupRef}
          data-dialog-popup="true"
          style={{
            top: popupPosition?.top ?? triggerRect.bottom + POPUP_GAP,
            left: popupPosition?.left ?? triggerRect.left,
            minWidth: triggerRect.width,
            maxWidth: `calc(100vw - ${VIEWPORT_MARGIN * 2}px)`,
            maxHeight: popupPosition?.maxHeight,
            visibility: popupPosition ? 'visible' : 'hidden',
          }}
          className="fixed z-50 flex w-max max-w-sm flex-col overflow-hidden rounded-xl border border-border bg-elevated shadow-lg"
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault();
              close(true);
            }
          }}
        >
          {showSearch ? (
            <div className="border-b border-border p-2">
              <Input
                id={searchId}
                value={query}
                disabled={disabled}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Tab') {
                    close(false);
                  }
                }}
                aria-label={text.searchOptions}
                placeholder={text.searchOptionsPlaceholder}
                className="min-h-11"
              />
            </div>
          ) : null}
          {ordered ? (
            <p className="border-b border-border px-3 py-2 text-xs text-muted-text">{text.orderedHint}</p>
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
                  <label className="flex min-h-11 cursor-pointer items-center gap-2 px-3 py-1.5 text-sm text-secondary-text">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      disabled={disabled}
                      onChange={() => toggle(entry.value)}
                      className="settings-input-checkbox h-4 w-4 rounded border-border/70 bg-base"
                    />
                    <span className="min-w-0 truncate">{entry.label}</span>
                    {ordered && isSelected ? (
                      <span className="ml-auto shrink-0 text-xs text-muted-text">
                        {formatUiText(text.priorityPosition, { position: positionOf(entry.value) })}
                      </span>
                    ) : null}
                  </label>
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
