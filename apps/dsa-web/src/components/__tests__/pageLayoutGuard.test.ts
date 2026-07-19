// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
import { describe, expect, it } from 'vitest';

const pageSources = import.meta.glob('../../pages/*Page.tsx', {
  eager: true,
  import: 'default',
  query: '?raw',
}) as Record<string, string>;

const STANDARD_PAGE_FILES = [
  'AlertsPage.tsx',
  'BacktestPage.tsx',
  'DecisionSignalsPage.tsx',
  'PortfolioPage.tsx',
  'SettingsPage.tsx',
  'StockScreeningPage.tsx',
  'TokenUsagePage.tsx',
] as const;

function sourceFor(filename: string): string {
  const entry = Object.entries(pageSources).find(([path]) => path.endsWith(`/${filename}`));
  if (!entry) throw new Error(`Missing page source: ${filename}`);
  return entry[1];
}

describe('standard page layout guard', () => {
  it.each(STANDARD_PAGE_FILES)('%s uses the shared page width and title contracts', (filename) => {
    const source = sourceFor(filename);
    expect(source).toMatch(/<AppPage\b/);
    expect(source).toMatch(/<PageHeader\b/);
    expect(source).not.toMatch(/<AppPage\b[^>]*className=["'`][^"'`]*\bmax-w-/);
    expect(source).not.toMatch(/<AppPage\b[^>]*className=["'`][^"'`]*\bp-0\b/);
  });

  it('keeps the exceptions explicit and limited to specialized routes', () => {
    const standard = new Set<string>(STANDARD_PAGE_FILES);
    const allPageFiles = Object.keys(pageSources).map((path) => path.split('/').pop() as string);
    const exceptions = allPageFiles.filter((filename) => !standard.has(filename));

    expect(exceptions.sort()).toEqual([
      'ChatPage.tsx',
      'HomePage.tsx',
      'LoginPage.tsx',
      'NotFoundPage.tsx',
    ]);
  });
});
