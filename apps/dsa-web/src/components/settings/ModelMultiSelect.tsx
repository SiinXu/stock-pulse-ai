// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, X } from 'lucide-react';
import { Checkbox, Input, Pressable } from '../common';
import { useFixedPopup } from '../common/useFixedPopup';
import { getOverlayStyle } from '../common/overlayZ';
import { formatUiText } from '../../i18n/uiText';
import { SETTINGS_CONTROLS_TEXT } from '../../locales/settingsControls';
import type { UiLang } from './settingsInformationArchitecture';

interface ModelMultiSelectProps {
  /** Candidate model ids (e.g. discovery results). */
  options: string[];
  isSelected: (model: string) => boolean;
  onToggle: (model: string) => void;
  disabled?: boolean;
  language?: UiLang;
  /** Optional display label for route-valued options. */
  getOptionLabel?: (model: string) => string;
  /** Accessible name for contexts such as the fallback selector. */
  ariaLabel?: string;
}

/**
 * A collapsed searchable multi-select. Discovery results stay behind a trigger
 * until requested, keeping large model catalogs out of the normal form flow.
 * Selection remains explicit and per-model; discovery never selects for users.
 */
export const ModelMultiSelect: React.FC<ModelMultiSelectProps> = ({
  options,
  isSelected,
  onToggle,
  disabled = false,
  language = 'zh',
  getOptionLabel = (model) => model,
  ariaLabel,
}) => {
  const reactId = useId();
  const listboxId = `${reactId}-listbox`;
  const searchId = `${reactId}-search`;
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const text = SETTINGS_CONTROLS_TEXT[language];
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? options.filter((model) => model.toLowerCase().includes(q)) : options;
  }, [options, query]);
  const selectedModels = options.filter(isSelected);
  const popupContentVersion = useMemo(
    () => [filtered.length, query] as const,
    [filtered.length, query],
  );
  const { portalHost, popupStyle, prepareForOpen, resetPosition } = useFixedPopup({
    isOpen,
    triggerRef,
    popupRef,
    contentVersion: popupContentVersion,
    constrainWidthToViewport: true,
    matchTriggerWidth: true,
  });

  const close = useCallback((restoreFocus: boolean) => {
    setIsOpen(false);
    setQuery('');
    resetPosition();
    if (restoreFocus) {
      triggerRef.current?.focus();
    }
  }, [resetPosition]);

  const open = useCallback(() => {
    prepareForOpen();
    setIsOpen(true);
  }, [prepareForOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    searchRef.current?.focus();
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !popupRef.current?.contains(target)) {
        close(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [close, isOpen]);

  useEffect(() => {
    if (disabled && isOpen) {
      close(false);
    }
  }, [close, disabled, isOpen]);

  return (
    <div ref={rootRef} className="relative" data-testid="model-multi-select">
      <div className="flex min-h-11 w-full flex-wrap items-center gap-1.5 rounded-lg border border-border bg-transparent px-2 py-1 text-xs text-foreground transition-colors focus-within:border-muted-text">
        <Pressable
          ref={triggerRef}
          type="button"
          disabled={disabled}
          aria-label={ariaLabel ?? text.selectModels}
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          aria-controls={isOpen ? listboxId : undefined}
          onClick={() => (isOpen ? close(false) : open())}
          className="flex min-h-11 min-w-0 flex-1 items-center justify-between gap-2 rounded-lg px-1 text-left hover:bg-hover focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
        >
          <span className="shrink-0 text-muted-text">
            {formatUiText(text.selectedModels, { selected: selectedModels.length, total: options.length })}
          </span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-secondary-text" aria-hidden="true" />
        </Pressable>
        {selectedModels.slice(0, 2).map((model) => (
          <span key={model} className="inline-flex min-h-11 min-w-0 max-w-36 items-center gap-0.5 rounded-full border border-border pl-1.5">
            <span className="truncate">{getOptionLabel(model)}</span>
            <Pressable
              type="button"
              disabled={disabled}
              aria-label={formatUiText(text.removeModel, { model: getOptionLabel(model) })}
              onClick={() => onToggle(model)}
              className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted-text hover:text-danger focus:outline-none disabled:cursor-not-allowed"
            >
              <X className="h-3 w-3" aria-hidden="true" />
            </Pressable>
          </span>
        ))}
        {selectedModels.length > 2 ? <span className="shrink-0 text-muted-text">+{selectedModels.length - 2}</span> : null}
      </div>

      {isOpen && popupStyle && portalHost ? createPortal(
        <div
          ref={popupRef}
          data-dialog-popup="true"
          style={getOverlayStyle('dropdown', popupStyle)}
          className="fixed overflow-hidden rounded-xl border border-border bg-elevated shadow-lg"
        >
          <div className="border-b border-border p-2">
            <Input
              ref={searchRef}
              id={searchId}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Escape') {
                  event.preventDefault();
                  close(true);
                } else if (event.key === 'Tab') {
                  close(false);
                }
              }}
              aria-label={text.searchModels}
              placeholder={text.searchModelsPlaceholder}
              className="min-h-11"
            />
          </div>
          <ul
            id={listboxId}
            role="listbox"
            aria-label={text.availableModels}
            aria-multiselectable="true"
            className="max-h-48 space-y-0.5 overflow-y-auto p-1"
          >
            {filtered.length === 0 ? (
              <li role="presentation" className="px-3 py-2 text-xs text-muted-text">
                {text.noMatchingModels}
              </li>
            ) : filtered.map((model) => (
              <li
                key={model}
                role="option"
                aria-selected={isSelected(model)}
                className="rounded-md hover:bg-hover"
              >
                <Checkbox
                  checked={isSelected(model)}
                  onChange={() => onToggle(model)}
                  containerClassName="min-h-11 px-3 py-1.5 text-sm text-secondary-text"
                  label={<span className="min-w-0 truncate font-normal text-secondary-text">{getOptionLabel(model)}</span>}
                />
              </li>
            ))}
          </ul>
        </div>,
        portalHost,
      ) : null}
    </div>
  );
};
