import type React from 'react';
import { CreatableCombobox, type ComboboxOption } from '../common';
import type { UiLang } from './settingsInformationArchitecture';

interface ModelFallbackEditorProps {
  /** Comma-separated list of fallback model routes. */
  value: string;
  onChange: (value: string) => void;
  /** Available model routes (grouped) offered when adding a fallback. */
  options: ComboboxOption[];
  /** The primary model route — excluded from the add list (it's the primary). */
  primaryRoute?: string;
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
  language,
  disabled = false,
}) => {
  const tx = (zh: string, en: string) => (language === 'en' ? en : zh);
  const routes = splitRoutes(value);
  const labelFor = (route: string) => options.find((option) => option.value === route)?.label ?? route;

  const setRoutes = (next: string[]) => onChange(next.join(','));
  const removeAt = (index: number) => setRoutes(routes.filter((_, position) => position !== index));
  const moveUp = (index: number) => {
    if (index <= 0) {
      return;
    }
    const next = [...routes];
    [next[index - 1], next[index]] = [next[index], next[index - 1]];
    setRoutes(next);
  };
  const addRoute = (route: string) => {
    if (route && !routes.includes(route)) {
      setRoutes([...routes, route]);
    }
  };

  // Only offer models that are not the primary and not already picked.
  const addOptions = options.filter(
    (option) => option.value !== primaryRoute && !routes.includes(option.value),
  );

  return (
    <div className="space-y-2" data-testid="model-fallback-editor">
      {routes.length === 0 ? (
        <p className="text-xs text-muted-text">
          {tx('未启用备用模型', 'No fallback models enabled')}
        </p>
      ) : (
        <ul className="space-y-1.5">
          {routes.map((route, index) => (
            <li
              key={route}
              className="flex items-center justify-between gap-2 rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] px-3 py-1.5 text-xs"
            >
              <span className="flex min-w-0 items-center gap-2">
                <span className="text-muted-text">{index + 1}.</span>
                <span className="truncate font-medium text-foreground">{labelFor(route)}</span>
              </span>
              <span className="flex shrink-0 items-center gap-1">
                <button
                  type="button"
                  disabled={disabled || index === 0}
                  aria-label={tx(`上移 ${labelFor(route)}`, `Move ${labelFor(route)} up`)}
                  onClick={() => moveUp(index)}
                  className="rounded px-1 text-secondary-text hover:text-foreground disabled:opacity-40"
                >
                  ↑
                </button>
                <button
                  type="button"
                  disabled={disabled}
                  aria-label={tx(`移除 ${labelFor(route)}`, `Remove ${labelFor(route)}`)}
                  onClick={() => removeAt(index)}
                  className="rounded px-1 text-secondary-text hover:text-danger"
                >
                  ✕
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
      <CreatableCombobox
        value=""
        onChange={addRoute}
        options={addOptions}
        disabled={disabled}
        ariaLabel={tx('添加备用模型', 'Add a fallback model')}
        placeholder={tx('添加备用模型…', 'Add a fallback model…')}
        emptyText={tx('暂无可添加的模型', 'No models to add')}
        customLabel={(val) => (language === 'en' ? `Custom: ${val}` : `自定义：${val}`)}
      />
    </div>
  );
};
