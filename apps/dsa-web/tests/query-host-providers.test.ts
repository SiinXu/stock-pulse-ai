// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// @vitest-environment node
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { createAppQueryClient } from '../src/query/createAppQueryClient';

const webRoot = process.cwd();

function read(relativePath: string): string {
  return readFileSync(path.join(webRoot, relativePath), 'utf8');
}

describe('Query consumer hosts', () => {
  it('keeps production QueryClient defaults retry-free with focus refetch on', () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.retry).toBe(false);
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    expect(client.getDefaultOptions().mutations?.retry).toBe(false);
  });

  it('wraps every real useUnreadNotifications host with the production retry-free client', () => {
    expect(read('src/main.tsx')).toContain('<QueryProvider>');
    expect(read('e2e/application-shell-fixture.tsx')).toContain('<QueryProvider>');
    expect(read('src/App.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/layout/__tests__/RouteBoundary.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/playground/__tests__/scenarios.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useUnreadNotifications.test.tsx')).toContain('createAppQueryClient');
  });

  it('wraps NotificationCenterPage tests with the production retry-free client', () => {
    expect(read('src/pages/__tests__/NotificationCenterPage.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/pages/__tests__/NotificationCenterPage.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useNotificationCenterInbox.test.tsx')).toContain('createAppQueryClient');
  });

  it('wraps useSystemConfig hook tests with the production retry-free client', () => {
    expect(read('src/hooks/__tests__/useSystemConfig.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useSystemConfig.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useSystemConfigLoadQuery.test.tsx')).toContain('createAppQueryClient');
  });

  it('wraps EventCalendarWorkspace tests with the production retry-free client', () => {
    expect(read('src/components/event-calendar/__tests__/EventCalendarWorkspace.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/event-calendar/__tests__/EventCalendarWorkspace.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useEventCalendarQuery.test.tsx')).toContain('createAppQueryClient');
  });

  it('wraps TokenUsagePage tests with the production retry-free client', () => {
    expect(read('src/pages/__tests__/TokenUsagePage.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/pages/__tests__/TokenUsagePage.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useTokenUsageQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/pages/__tests__/SettingsPage.testHarness.tsx')).toContain('createAppQueryClient');
  });

  it('wraps FinancialCalculatorsPage tests with the production retry-free client', () => {
    expect(read('src/pages/__tests__/FinancialCalculatorsPage.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/pages/__tests__/FinancialCalculatorsPage.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useFinancialCalculatorsMutation.test.tsx')).toContain('createAppQueryClient');
  });

  it('wraps ReportVersionComparePage tests with the production retry-free client', () => {
    expect(read('src/pages/__tests__/ReportVersionComparePage.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/pages/__tests__/ReportVersionComparePage.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useReportVersionCompareQueries.test.tsx')).toContain('createAppQueryClient');
  });

  it('keeps report version-compare on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useReportVersionCompareQueries.ts');
    const barrelSource = read('src/hooks/index.ts');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(barrelSource).not.toContain('useReportVersionCompareQueries');
  });

  it('wraps useWatchlistScores tests with the production retry-free client', () => {
    expect(read('src/hooks/__tests__/useWatchlistScores.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useWatchlistScores.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps watchlist scores on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useWatchlistScores.ts');
    const barrelSource = read('src/hooks/index.ts');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(barrelSource).not.toContain('useWatchlistScores');
  });

  it('wraps useWatchlistAnalysisCoverage tests with the production retry-free client', () => {
    expect(read('src/hooks/__tests__/useWatchlistAnalysisCoverage.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useWatchlistAnalysisCoverage.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps watchlist coverage on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useWatchlistAnalysisCoverage.ts');
    const barrelSource = read('src/hooks/index.ts');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(barrelSource).not.toContain('useWatchlistAnalysisCoverage');
  });

  it('wraps SignalScorecardPanel tests with the production retry-free client', () => {
    expect(read('src/components/settings/__tests__/SignalScorecardPanel.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/SignalScorecardPanel.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useSignalScorecardQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useSignalScorecardQuery.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings signal scorecard on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useSignalScorecardQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(barrelSource).not.toContain('useSignalScorecardQuery');
  });

  it('wraps DataProviderRuntimeStatusPanel tests with the production retry-free client', () => {
    expect(read('src/components/settings/__tests__/DataProviderRuntimeStatusPanel.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/DataProviderRuntimeStatusPanel.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useDataProviderRuntimeStatusQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useDataProviderRuntimeStatusQuery.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings data-provider runtime status on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useDataProviderRuntimeStatusQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(barrelSource).not.toContain('useDataProviderRuntimeStatusQuery');
  });

  it('wraps KronosStatusPanel tests with the production retry-free client', () => {
    expect(read('src/components/settings/__tests__/KronosStatusPanel.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/KronosStatusPanel.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useKronosStatusQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useKronosStatusQuery.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings Kronos status on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useKronosStatusQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(barrelSource).not.toContain('useKronosStatusQuery');
  });
});
