// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Pressable, type SearchableSelectOption } from '../common';
import type { UiLang } from './settingsInformationArchitecture';
import { ModelMultiSelect } from './ModelMultiSelect';
import { formatUiText } from '../../i18n/uiText';
import { SETTINGS_CONTROLS_TEXT } from '../../locales/settingsControls';
import { decodeModelRef } from '../../utils/modelRef';

interface ModelFallbackEditorProps {
  /** Comma-separated list of fallback model routes. */
  value: string;
  onChange: (value: string) => void;
  /** Available model routes (grouped) offered when adding a fallback. */
  options: SearchableSelectOption[];
  /** The primary model route — excluded from the add list (it's the primary). */
  primaryRoute?: string;
  /** Resolve a persisted legacy runtime route to a unique Connection ModelRef. */
  resolveConfiguredModelRef?: (value: string) => string;
  language: UiLang;
  disabled?: boolean;
}

function splitRoutes(value: string): string[] {
  return value.split(',').map((entry) => entry.trim()).filter(Boolean);
}

/**
 * Ordered, multi-value editor for the model fallback list: removable tokens plus
 * a model selector to append. Never requires the user to hand-type a
 * comma-separated string of provider/model routes.
 */
export const ModelFallbackEditor: React.FC<ModelFallbackEditorProps> = ({
  value,
  onChange,
  options,
  primaryRoute,
  resolveConfiguredModelRef,
  language,
  disabled = false,
}) => {
  const text = SETTINGS_CONTROLS_TEXT[language];
  const routes = splitRoutes(value);
  const resolveRoute = (route: string) => (
    resolveConfiguredModelRef?.(route) ?? route.trim()
  );
  const labelFor = (route: string) => {
    const option = options.find((candidate) => candidate.value === resolveRoute(route));
    if (!option) {
      return route;
    }
    return option.sublabel ? `${option.label} · ${option.sublabel}` : option.label;
  };
  // A configured route that is no longer in the available catalog is kept (never
  // silently cleared) and marked as unavailable so the user can decide.
  const isStale = (route: string) => (
    !options.some((option) => option.value === resolveRoute(route))
  );

  const setRoutes = (next: string[]) => onChange(next.join(','));
  const canonicalizeRoutes = (next: string[]) => {
    const seen = new Set<string>();
    return next
      .map(resolveRoute)
      .filter((route) => {
        if (!route || seen.has(route)) {
          return false;
        }
        seen.add(route);
        return true;
      });
  };
  const removeAt = (index: number) => setRoutes(routes.filter((_, position) => position !== index));
  const moveUp = (index: number) => {
    if (index <= 0) {
      return;
    }
    const next = [...routes];
    [next[index - 1], next[index]] = [next[index], next[index - 1]];
    setRoutes(next);
  };
  const moveDown = (index: number) => {
    if (index >= routes.length - 1) {
      return;
    }
    const next = [...routes];
    [next[index], next[index + 1]] = [next[index + 1], next[index]];
    setRoutes(next);
  };
  const selectableOptions = options.filter((option) => option.value !== primaryRoute);
  const optionLabelByRoute = new Map(selectableOptions.map((option) => [
    option.value,
    option.sublabel ? `${option.label} · ${option.sublabel}` : option.label,
  ]));
  const toggleRoute = (route: string) => {
    if (routes.some((entry) => resolveRoute(entry) === route)) {
      setRoutes(routes.filter((entry) => resolveRoute(entry) !== route));
      return;
    }
    const selectedModelRef = decodeModelRef(route);
    const nextRoutes = selectedModelRef
      ? routes.filter((entry) => (
        decodeModelRef(entry) !== null || entry !== selectedModelRef.runtimeRoute
      ))
      : routes;
    setRoutes(canonicalizeRoutes([...nextRoutes, route]));
  };

  return (
    <div className="space-y-2" data-testid="model-fallback-editor">
      {routes.length === 0 ? (
        <p className="text-xs text-muted-text">
          {text.noFallbacks}
        </p>
      ) : (
        <ul className="space-y-1.5">
          {routes.map((route, index) => (
            <li
              key={`${route}-${index}`}
              className="flex items-center justify-between gap-2 rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] px-3 py-1.5 text-xs"
            >
              <span className="flex min-w-0 items-center gap-2">
                <span className="text-muted-text">{index + 1}.</span>
                <span className="truncate font-medium text-foreground">{labelFor(route)}</span>
                {isStale(route) ? (
                  <span className="shrink-0 text-xs text-warning">
                    {text.unavailable}
                  </span>
                ) : null}
              </span>
              <span className="flex shrink-0 items-center gap-1">
                <Pressable
                  type="button"
                  disabled={disabled || index === 0}
                  aria-label={formatUiText(text.moveUp, { model: labelFor(route) })}
                  onClick={() => moveUp(index)}
                  className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-secondary-text hover:text-foreground disabled:opacity-40"
                >
                  ↑
                </Pressable>
                <Pressable
                  type="button"
                  disabled={disabled || index === routes.length - 1}
                  aria-label={formatUiText(text.moveDown, { model: labelFor(route) })}
                  onClick={() => moveDown(index)}
                  className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-secondary-text hover:text-foreground disabled:opacity-40"
                >
                  ↓
                </Pressable>
                <Pressable
                  type="button"
                  disabled={disabled}
                  aria-label={formatUiText(text.removeFallback, { model: labelFor(route) })}
                  onClick={() => removeAt(index)}
                  className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-secondary-text hover:text-danger"
                >
                  ✕
                </Pressable>
              </span>
            </li>
          ))}
        </ul>
      )}
      <ModelMultiSelect
        options={selectableOptions.map((option) => option.value)}
        isSelected={(route) => routes.some((entry) => resolveRoute(entry) === route)}
        onToggle={toggleRoute}
        disabled={disabled}
        language={language}
        getOptionLabel={(route) => optionLabelByRoute.get(route) ?? route}
        ariaLabel={text.selectFallbacks}
      />
    </div>
  );
};
