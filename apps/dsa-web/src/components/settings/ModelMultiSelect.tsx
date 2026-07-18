// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { ChevronDown, X } from 'lucide-react';
import { Input } from '../common';
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
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const text = SETTINGS_CONTROLS_TEXT[language];
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? options.filter((model) => model.toLowerCase().includes(q)) : options;
  }, [options, query]);
  const selectedModels = options.filter(isSelected);

  const close = (restoreFocus: boolean) => {
    setIsOpen(false);
    setQuery('');
    if (restoreFocus) {
      triggerRef.current?.focus();
    }
  };

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    document.getElementById(searchId)?.focus();
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        close(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [isOpen, searchId]);

  useEffect(() => {
    if (disabled && isOpen) {
      close(false);
    }
  }, [disabled, isOpen]);

  return (
    <div ref={rootRef} className="relative" data-testid="model-multi-select">
      <div className="flex min-h-11 w-full flex-wrap items-center gap-1.5 rounded-lg border border-border bg-transparent px-2 py-1 text-xs text-foreground transition-colors focus-within:border-muted-text">
        <button
          ref={triggerRef}
          type="button"
          disabled={disabled}
          aria-label={ariaLabel ?? text.selectModels}
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          aria-controls={isOpen ? listboxId : undefined}
          onClick={() => (isOpen ? close(false) : setIsOpen(true))}
          className="flex min-h-11 min-w-0 flex-1 items-center justify-between gap-2 rounded-lg px-1 text-left hover:bg-hover focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
        >
          <span className="shrink-0 text-muted-text">
            {formatUiText(text.selectedModels, { selected: selectedModels.length, total: options.length })}
          </span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-secondary-text" aria-hidden="true" />
        </button>
        {selectedModels.slice(0, 2).map((model) => (
          <span key={model} className="inline-flex min-h-11 min-w-0 max-w-36 items-center gap-0.5 rounded-full border border-border pl-1.5">
            <span className="truncate">{getOptionLabel(model)}</span>
            <button
              type="button"
              disabled={disabled}
              aria-label={formatUiText(text.removeModel, { model: getOptionLabel(model) })}
              onClick={() => onToggle(model)}
              className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted-text hover:text-danger focus:outline-none disabled:cursor-not-allowed"
            >
              <X className="h-3 w-3" aria-hidden="true" />
            </button>
          </span>
        ))}
        {selectedModels.length > 2 ? <span className="shrink-0 text-muted-text">+{selectedModels.length - 2}</span> : null}
      </div>

      {isOpen ? (
        <div data-dialog-popup="true" className="absolute left-0 right-0 z-30 mt-1 overflow-hidden rounded-xl border border-border bg-elevated shadow-lg">
          <div className="border-b border-border p-2">
            <Input
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
                <label className="flex min-h-11 cursor-pointer items-center gap-2 px-3 py-1.5 text-sm text-secondary-text">
                  <input
                    type="checkbox"
                    checked={isSelected(model)}
                    onChange={() => onToggle(model)}
                    className="settings-input-checkbox h-4 w-4 rounded border-border/70 bg-base"
                  />
                  <span className="min-w-0 truncate">{getOptionLabel(model)}</span>
                </label>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
};
