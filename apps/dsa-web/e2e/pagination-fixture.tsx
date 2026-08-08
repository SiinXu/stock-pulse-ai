// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable react-refresh/only-export-components -- this Vite-only fixture defines and mounts its test harness in one entry file */
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/geist/index.css';
import '../src/index.css';
import '../src/App.css';
import { Pagination } from '../src/components/common';
import { ThemeProvider } from '../src/components/theme/ThemeProvider';
import { UiLanguageProvider } from '../src/contexts/UiLanguageContext';

function readContainerWidth(): number {
  const raw = new URLSearchParams(window.location.search).get('width');
  const parsed = raw ? Number.parseInt(raw, 10) : 520;
  if (!Number.isFinite(parsed) || parsed < 200 || parsed > 2000) {
    return 520;
  }
  return parsed;
}

function readDensity(): 'auto' | 'compact' | 'full' {
  const raw = new URLSearchParams(window.location.search).get('density');
  if (raw === 'auto' || raw === 'compact' || raw === 'full') {
    return raw;
  }
  return 'full';
}

function PaginationFixture() {
  const containerWidth = readContainerWidth();
  const density = readDensity();
  const [page, setPage] = useState(10);

  return (
    <main className="min-h-dvh bg-background p-4 text-foreground">
      <div className="mx-auto max-w-5xl space-y-4">
        <header className="space-y-1">
          <p className="text-xs font-medium text-secondary-text">Pagination contract</p>
          <h1 className="text-2xl font-semibold text-foreground">Pagination reachability</h1>
          <p className="text-sm text-secondary-text">
            Real shared Pagination inside a width-controlled host for overflow reachability checks.
          </p>
        </header>

        <div
          data-testid="pagination-host"
          data-container-width={containerWidth}
          data-density={density}
          style={{ width: containerWidth, maxWidth: '100%' }}
          className="rounded-lg border border-border bg-elevated p-2"
        >
          <Pagination
            currentPage={page}
            totalPages={20}
            onPageChange={setPage}
            density={density}
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
        <PaginationFixture />
      </UiLanguageProvider>
    </ThemeProvider>
  </StrictMode>,
);
