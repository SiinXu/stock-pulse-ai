import type React from 'react';
import { useMemo, useState } from 'react';
import { Input } from '../common';
import type { UiLang } from './settingsInformationArchitecture';

interface ModelMultiSelectProps {
  /** Candidate model ids (e.g. discovery results). */
  options: string[];
  isSelected: (model: string) => boolean;
  onToggle: (model: string) => void;
  disabled?: boolean;
  language?: UiLang;
}

/**
 * Searchable multi-select for confirming which models to enable. Discovery can
 * return hundreds of models, so a bare checkbox list is not enough: this adds a
 * filter box and a selected counter while keeping explicit per-model opt-in
 * (never auto-select-all).
 */
export const ModelMultiSelect: React.FC<ModelMultiSelectProps> = ({
  options,
  isSelected,
  onToggle,
  disabled = false,
  language = 'zh',
}) => {
  const [query, setQuery] = useState('');
  const tx = (zh: string, en: string) => (language === 'en' ? en : zh);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? options.filter((model) => model.toLowerCase().includes(q)) : options;
  }, [options, query]);
  const selectedCount = options.filter(isSelected).length;

  return (
    <div className="space-y-2" data-testid="model-multi-select">
      <div className="flex items-center gap-2">
        <Input
          value={query}
          disabled={disabled}
          onChange={(event) => setQuery(event.target.value)}
          aria-label={tx('搜索模型', 'Search models')}
          placeholder={tx('搜索模型…', 'Search models…')}
        />
        <span className="shrink-0 text-xs text-muted-text">
          {tx(`已选 ${selectedCount} / ${options.length}`, `${selectedCount} of ${options.length} selected`)}
        </span>
      </div>
      <div className="max-h-48 space-y-2 overflow-y-auto rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] p-3">
        {filtered.length === 0 ? (
          <p className="text-xs text-muted-text">{tx('无匹配模型', 'No matching models')}</p>
        ) : (
          filtered.map((model) => (
            <label key={model} className="flex items-center gap-2 text-sm text-secondary-text">
              <input
                type="checkbox"
                checked={isSelected(model)}
                disabled={disabled}
                onChange={() => onToggle(model)}
                className="settings-input-checkbox h-4 w-4 rounded border-border/70 bg-base"
              />
              <span className="min-w-0 truncate">{model}</span>
            </label>
          ))
        )}
      </div>
    </div>
  );
};
