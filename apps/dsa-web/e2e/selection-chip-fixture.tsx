// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable react-refresh/only-export-components -- this Vite-only fixture defines and mounts its test harness in one entry file */
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/geist/index.css';
import '../src/index.css';
import '../src/App.css';
import { SelectionChip } from '../src/components/common';
import { ThemeProvider } from '../src/components/theme/ThemeProvider';
import { UiLanguageProvider } from '../src/contexts/UiLanguageContext';

type Candidate = {
  id: string;
  code: string;
  name: string;
  market: string;
  disabled?: boolean;
  loading?: boolean;
};

const CANDIDATES: readonly Candidate[] = [
  { id: 'aapl', code: 'AAPL', name: 'Apple Incorporated', market: 'NASDAQ' },
  { id: 'msft', code: 'MSFT', name: 'Microsoft Corporation', market: 'NASDAQ' },
  {
    id: 'brkb',
    code: 'BRK.B',
    name: 'Berkshire Hathaway Incorporated Class B Common Stock',
    market: 'NYSE',
  },
  { id: '600519', code: '600519', name: 'Kweichow Moutai Company Limited', market: 'SSE' },
  { id: 'loading', code: 'SYNCING', name: 'Refreshing candidate data', market: 'GLOBAL', loading: true },
  { id: 'disabled', code: 'PRIVATE', name: 'Unavailable candidate', market: 'PRIVATE', disabled: true },
];

function SelectionChipFixture() {
  const [selectedId, setSelectedId] = useState('aapl');
  const [result, setResult] = useState('Selected AAPL');

  return (
    <main className="min-h-dvh bg-background p-4 text-foreground sm:p-6">
      <div className="mx-auto max-w-4xl space-y-5">
        <header className="space-y-1">
          <p className="text-xs font-medium text-secondary-text">Selection controls</p>
          <h1 className="text-2xl font-semibold text-foreground">Candidate stocks</h1>
          <p className="max-w-2xl text-sm text-secondary-text">
            Choose a recent stock while preserving long company names and compact command geometry.
          </p>
        </header>

        <div className="border-b border-border pb-3">
          <p className="text-sm font-medium text-foreground">Recent and popular</p>
          <p className="mt-1 text-sm text-secondary-text" data-testid="selection-result" aria-live="polite">
            {result}
          </p>
        </div>

        <div className="flex flex-wrap gap-2" role="group" aria-label="Candidate stocks">
          {CANDIDATES.map((candidate) => (
            <SelectionChip
              key={candidate.id}
              label={<span className="font-mono">{candidate.code}</span>}
              description={candidate.name}
              metadata={`/ ${candidate.market}`}
              selected={selectedId === candidate.id}
              disabled={candidate.disabled}
              isLoading={candidate.loading}
              onClick={() => {
                setSelectedId(candidate.id);
                setResult(`Selected ${candidate.code}`);
              }}
            />
          ))}
          <SelectionChip
            label="Open market leader"
            onClick={() => setResult('Opened market leader')}
          />
        </div>
      </div>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <UiLanguageProvider>
        <SelectionChipFixture />
      </UiLanguageProvider>
    </ThemeProvider>
  </StrictMode>,
);
