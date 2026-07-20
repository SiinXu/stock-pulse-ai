// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable react-refresh/only-export-components -- this Vite-only fixture defines and mounts its test harness in one entry file */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import '@fontsource-variable/geist/index.css';
import '../src/index.css';
import '../src/App.css';
import {
  AdvancedFilterSheet,
  AppliedFilterChips,
  FilterBar,
  Input,
  Surface,
  useFilterQueryState,
  type AppliedFilterItem,
  type FilterQueryCodec,
} from '../src/components/common';
import { ThemeProvider } from '../src/components/theme/ThemeProvider';
import { UiLanguageProvider } from '../src/contexts/UiLanguageContext';

type FixtureFilters = {
  stock: string;
  market: string;
  status: string;
};

const DEFAULT_FILTERS: FixtureFilters = {
  stock: '',
  market: '',
  status: '',
};

const FILTER_CODEC: FilterQueryCodec<FixtureFilters> = {
  read: (params) => ({
    stock: params.get('stock')?.trim().toUpperCase() ?? '',
    market: ['cn', 'us', 'hk'].includes(params.get('market') ?? '')
      ? params.get('market') ?? ''
      : '',
    status: ['open', 'closed'].includes(params.get('status') ?? '')
      ? params.get('status') ?? ''
      : '',
  }),
  write: (params, filters) => {
    const entries = Object.entries(filters) as Array<[keyof FixtureFilters, string]>;
    entries.forEach(([key, value]) => {
      const normalized = key === 'stock' ? value.trim().toUpperCase() : value.trim();
      if (normalized) params.set(key, normalized);
      else params.delete(key);
    });
  },
};

const equalsFilters = (left: FixtureFilters, right: FixtureFilters) => (
  left.stock === right.stock
  && left.market === right.market
  && left.status === right.status
);

const countActiveFilters = (filters: FixtureFilters) => (
  Number(Boolean(filters.stock))
  + Number(Boolean(filters.market))
  + Number(Boolean(filters.status))
);

function FilterPatternFixture() {
  const filters = useFilterQueryState({
    codec: FILTER_CODEC,
    defaultValue: DEFAULT_FILTERS,
    equals: equalsFilters,
    getActiveCount: countActiveFilters,
    clearKeysOnApply: ['page'],
  });
  const advancedCount = Number(Boolean(filters.applied.market))
    + Number(Boolean(filters.applied.status));
  const advancedDraftCount = Number(Boolean(filters.draft.market))
    + Number(Boolean(filters.draft.status));
  const resultCount = Math.max(4, 24 - (filters.activeCount * 4));
  const draftResultCount = Math.max(4, 24 - (filters.draftActiveCount * 4));
  const appliedItems: AppliedFilterItem[] = [
    filters.applied.stock ? {
      id: 'stock',
      label: 'Stock',
      value: filters.applied.stock,
      removeLabel: 'Remove Stock filter',
      onRemove: () => filters.applyValue({ ...filters.applied, stock: '' }),
    } : null,
    filters.applied.market ? {
      id: 'market',
      label: 'Market',
      value: filters.applied.market.toUpperCase(),
      removeLabel: 'Remove Market filter',
      onRemove: () => filters.applyValue({ ...filters.applied, market: '' }),
    } : null,
    filters.applied.status ? {
      id: 'status',
      label: 'Status',
      value: filters.applied.status,
      removeLabel: 'Remove Status filter',
      onRemove: () => filters.applyValue({ ...filters.applied, status: '' }),
    } : null,
  ].filter((item): item is AppliedFilterItem => item !== null);

  return (
    <main className="min-h-dvh bg-background p-4 text-foreground sm:p-6">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="space-y-1">
          <p className="text-xs font-medium text-secondary-text">Signal workspace</p>
          <h1 className="text-2xl font-semibold text-foreground">Review decision signals</h1>
          <p className="max-w-2xl text-sm text-secondary-text">
            Narrow the current result set without losing report context or browser history.
          </p>
        </header>

        <Surface level="section" className="p-4 sm:p-5">
          <FilterBar
            aria-label="Decision signal filters"
            applyLabel="Apply filters"
            onApply={filters.applyDraft}
            applyDisabled={!filters.isDirty}
            advanced={(
              <AdvancedFilterSheet
                triggerLabel="More filters"
                triggerAriaLabel={advancedCount > 0
                  ? `More filters, ${advancedCount} active`
                  : 'More filters'}
                activeCount={advancedCount}
                title="More filters"
                description="Refine the signal set before applying changes."
                resetLabel="Reset"
                applyLabel={`View ${draftResultCount} results`}
                onReset={() => filters.setDraft((current) => ({
                  ...current,
                  market: '',
                  status: '',
                }))}
                onApply={filters.applyDraft}
                resetDisabled={advancedDraftCount === 0}
                applyDisabled={!filters.isDirty}
              >
                <Input
                  label="Market"
                  value={filters.draft.market}
                  placeholder="cn, us, or hk"
                  onChange={(event) => filters.setDraft((current) => ({
                    ...current,
                    market: event.target.value.toLowerCase(),
                  }))}
                />
                <Input
                  label="Status"
                  value={filters.draft.status}
                  placeholder="open or closed"
                  onChange={(event) => filters.setDraft((current) => ({
                    ...current,
                    status: event.target.value.toLowerCase(),
                  }))}
                />
              </AdvancedFilterSheet>
            )}
            applied={(
              <AppliedFilterChips
                aria-label="Applied filters"
                filters={appliedItems}
                clearAllLabel="Clear all"
                onClearAll={filters.resetApplied}
              />
            )}
          >
            <Input
              label="Stock code"
              value={filters.draft.stock}
              placeholder="AAPL"
              onChange={(event) => filters.setDraft((current) => ({
                ...current,
                stock: event.target.value.toUpperCase(),
              }))}
            />
          </FilterBar>
        </Surface>

        <section aria-labelledby="result-heading" className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border pb-3">
            <h2 id="result-heading" className="text-base font-semibold text-foreground">Signals</h2>
            <p className="text-sm text-secondary-text" aria-live="polite" data-testid="result-summary">
              {resultCount} results
              {filters.applied.stock ? ` for ${filters.applied.stock}` : ''}
            </p>
          </div>
          <div className="divide-y divide-border" role="list" aria-label="Signal results">
            {['Momentum strengthened', 'Risk threshold reached', 'Volume confirmed'].map((summary, index) => (
              <article key={summary} role="listitem" className="grid gap-1 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                <div className="min-w-0">
                  <h3 className="text-sm font-medium text-foreground">{summary}</h3>
                  <p className="text-xs text-secondary-text">Canonical signal sample {index + 1}</p>
                </div>
                <span className="text-xs text-secondary-text">Updated today</span>
              </article>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <UiLanguageProvider>
          <FilterPatternFixture />
        </UiLanguageProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
);
