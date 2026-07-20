// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable react-refresh/only-export-components -- this Vite-only fixture defines and mounts its test harness in one entry file */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/geist/index.css';
import '../src/index.css';
import '../src/App.css';
import { Surface } from '../src/components/common';
import { ThemeProvider } from '../src/components/theme/ThemeProvider';
import { UiLanguageProvider } from '../src/contexts/UiLanguageContext';

const LEVELS = [
  {
    level: 'canvas' as const,
    title: 'Canvas',
    description: 'Layout already provides the boundary.',
  },
  {
    level: 'section' as const,
    title: 'Section',
    description: 'A quiet tonal grouping without another border.',
  },
  {
    level: 'interactive' as const,
    title: 'Interactive',
    description: 'An independently actionable object with one border.',
  },
  {
    level: 'overlay' as const,
    title: 'Overlay',
    description: 'Elevated content above the document flow.',
  },
] as const;

function SurfaceContractFixture() {
  return (
    <main className="min-h-dvh bg-background p-4 text-foreground sm:p-6">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="space-y-1">
          <p className="text-xs font-medium text-secondary-text">Surface foundation</p>
          <h1 className="text-2xl font-semibold text-foreground">Semantic surface hierarchy</h1>
          <p className="max-w-2xl text-sm text-secondary-text">
            Four levels and theme-aware content tokens replace compatibility glass and raw white-alpha styles.
          </p>
        </header>

        <section aria-labelledby="levels-heading" className="space-y-3">
          <h2 id="levels-heading" className="text-base font-semibold text-foreground">Levels</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {LEVELS.map(({ level, title, description }) => (
              <Surface
                key={level}
                as="article"
                level={level}
                padding="md"
                data-testid={`surface-${level}`}
                aria-labelledby={`surface-${level}-title`}
              >
                <h3 id={`surface-${level}-title`} className="text-sm font-semibold text-foreground">
                  {title}
                </h3>
                <p className="mt-1 text-sm text-secondary-text">{description}</p>
              </Surface>
            ))}
          </div>
        </section>

        <section aria-labelledby="migration-heading" className="space-y-3">
          <h2 id="migration-heading" className="text-base font-semibold text-foreground">Panel migration</h2>
          <Surface
            as="article"
            level="interactive"
            padding="none"
            className="overflow-hidden"
            data-testid="migration-panel"
          >
            <header className="border-b border-subtle bg-subtle-soft px-4 py-3" data-testid="semantic-fill">
              <h3 className="text-sm font-semibold text-foreground">Research context</h3>
              <p className="mt-1 text-xs text-secondary-text">Token-owned fill and divider</p>
            </header>
            <div className="divide-y divide-border px-4" role="list" aria-label="Research context items">
              {['Source report', 'Analysis date', 'Return destination'].map((item) => (
                <div key={item} className="py-3 text-sm text-secondary-text" role="listitem">
                  {item}
                </div>
              ))}
            </div>
            <div className="m-4 rounded-lg p-3 ring-1 ring-subtle" data-testid="semantic-ring">
              <p className="text-sm text-secondary-text">Subtle emphasis without a raw white ring.</p>
            </div>
          </Surface>
        </section>
      </div>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <UiLanguageProvider>
        <SurfaceContractFixture />
      </UiLanguageProvider>
    </ThemeProvider>
  </StrictMode>,
);
