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

  it('wraps OutboundActivityPanel tests with the production retry-free client', () => {
    expect(read('src/components/settings/__tests__/OutboundActivityPanel.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/OutboundActivityPanel.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useOutboundActivityQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useOutboundActivityQuery.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings outbound activity on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useOutboundActivityQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(barrelSource).not.toContain('useOutboundActivityQuery');
  });

  it('wraps SecurityAuditPanel tests with the production retry-free client', () => {
    expect(read('src/components/settings/__tests__/SecurityAuditPanel.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/SecurityAuditPanel.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useSecurityAuditQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useSecurityAuditQuery.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings security-audit list on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useSecurityAuditQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(barrelSource).not.toContain('useSecurityAuditQuery');
  });

  it('wraps RuntimeCapabilitiesPanel tests with the production retry-free client', () => {
    expect(read('src/components/settings/__tests__/RuntimeCapabilitiesPanel.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/RuntimeCapabilitiesPanel.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useRuntimeCapabilitiesQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useRuntimeCapabilitiesQuery.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings runtime capabilities on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useRuntimeCapabilitiesQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(barrelSource).not.toContain('useRuntimeCapabilitiesQuery');
  });

  it('wraps SchedulerSettingsCard tests with the production retry-free client', () => {
    expect(read('src/components/settings/__tests__/SchedulerSettingsCard.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/SchedulerSettingsCard.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useSchedulerStatusQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useSchedulerStatusQuery.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useScheduledTasksOverlapQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useScheduledTasksOverlapQuery.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings scheduler status on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useSchedulerStatusQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(barrelSource).not.toContain('useSchedulerStatusQuery');
  });

  it('wraps LoadedExtensionsPanel tests with the production retry-free client', () => {
    expect(read('src/components/settings/__tests__/LoadedExtensionsPanel.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/LoadedExtensionsPanel.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useLoadedExtensionsQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useLoadedExtensionsQuery.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings loaded-extensions list on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useLoadedExtensionsQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    const panelSource = read('src/components/settings/LoadedExtensionsPanel.tsx');
    const sectionSource = read('src/components/settings/sections/SystemSecuritySection.tsx');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(hookSource).not.toContain('updateLifecycle');
    expect(hookSource).not.toContain('getSettings');
    expect(hookSource).not.toContain('updateSettings');
    expect(barrelSource).not.toContain('useLoadedExtensionsQuery');
    expect(panelSource).toContain('useLoadedExtensionsQuery');
    expect(sectionSource).toContain("lazy(() => import('../LoadedExtensionsPanel'))");
    expect(sectionSource).not.toContain('useLoadedExtensionsQuery');
  });

  it('wraps ScheduledTasksPanel tests with the production retry-free client', () => {
    expect(read('src/components/settings/__tests__/ScheduledTasksPanel.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/ScheduledTasksPanel.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useScheduledTasksListQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useScheduledTasksListQuery.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings scheduled-tasks list on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useScheduledTasksListQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    const panelSource = read('src/components/settings/ScheduledTasksPanel.tsx');
    const sectionSource = read('src/components/settings/sections/SystemSecuritySection.tsx');
    const settingsPageSource = read('src/pages/SettingsPage.tsx');
    const schedulerCardSource = read('src/components/settings/SchedulerSettingsCard.tsx');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(hookSource).toContain("['scheduled-tasks', 'list']");
    expect(hookSource).toContain('list({ limit: 200 })');
    expect(hookSource).not.toContain('getStatus');
    expect(hookSource).not.toContain('listRuns');
    expect(hookSource).not.toContain('.create(');
    expect(hookSource).not.toContain('.enable(');
    expect(hookSource).not.toContain('.disable(');
    expect(barrelSource).not.toContain('useScheduledTasksListQuery');
    expect(panelSource).toContain('useScheduledTasksListQuery');
    expect(sectionSource).toContain("lazy(() => import('../ScheduledTasksPanel'))");
    expect(sectionSource).toContain('Suspense');
    expect(sectionSource).not.toContain('useScheduledTasksListQuery');
    expect(settingsPageSource).not.toContain('useScheduledTasksListQuery');
    expect(schedulerCardSource).not.toContain('useScheduledTasksListQuery');
    expect(schedulerCardSource).not.toContain('list({ enabled: true, limit: 1 })');
  });

  it('wraps ConfigPresetsPanel tests with the production retry-free client', () => {
    expect(read('src/components/settings/__tests__/ConfigPresetsPanel.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/ConfigPresetsPanel.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useConfigPresetsListQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useConfigPresetsListQuery.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings config-presets list on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useConfigPresetsListQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    const panelSource = read('src/components/settings/ConfigPresetsPanel.tsx');
    const settingsPageSource = read('src/pages/SettingsPage.tsx');
    const backupCardSource = read('src/components/settings/ConfigBackupCard.tsx');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(hookSource).toContain("['config-presets', 'list']");
    expect(hookSource).toContain('listPresets()');
    expect(hookSource).not.toContain('previewPreset');
    expect(hookSource).not.toContain('applyPreset');
    expect(hookSource).not.toContain('exportProfile');
    expect(hookSource).not.toContain('previewImport');
    expect(hookSource).not.toContain('applyImport');
    expect(barrelSource).not.toContain('useConfigPresetsListQuery');
    expect(panelSource).toContain('useConfigPresetsListQuery');
    expect(settingsPageSource).toContain("lazy(() => import('../components/settings/ConfigPresetsPanel'))");
    expect(settingsPageSource).toContain('Suspense');
    expect(settingsPageSource).not.toContain('useConfigPresetsListQuery');
    expect(backupCardSource).not.toContain('useConfigPresetsListQuery');
    expect(backupCardSource).not.toContain('ConfigPresetsPanel');
  });

  it('wraps InvestmentFrameworkSettingsCard tests with the production retry-free client', () => {
    expect(read('src/components/settings/__tests__/InvestmentFrameworkSettingsCard.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/InvestmentFrameworkSettingsCard.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useInvestmentFrameworkQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useInvestmentFrameworkQuery.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings investment-framework current GET on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useInvestmentFrameworkQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    const cardSource = read('src/components/settings/InvestmentFrameworkSettingsCard.tsx');
    const settingsPageSource = read('src/pages/SettingsPage.tsx');
    const harnessSource = read('src/pages/__tests__/SettingsPage.testHarness.tsx');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(hookSource).toContain("['investment-framework', 'current']");
    expect(hookSource).toContain('investmentFrameworkApi.get()');
    expect(hookSource).not.toContain('.create(');
    expect(hookSource).not.toContain('.update(');
    expect(hookSource).not.toContain('.deactivate(');
    expect(hookSource).not.toContain('.remove(');
    expect(hookSource).not.toContain('.history(');
    expect(barrelSource).not.toContain('useInvestmentFrameworkQuery');
    expect(cardSource).toContain('useInvestmentFrameworkQuery');
    expect(settingsPageSource).toContain("lazy(() => import('../components/settings/InvestmentFrameworkSettingsCard'))");
    expect(settingsPageSource).toContain('Suspense');
    expect(settingsPageSource).not.toContain('useInvestmentFrameworkQuery');
    expect(harnessSource).toContain("vi.mock('../../components/settings/InvestmentFrameworkSettingsCard'");
  });

  it('wraps LocalModelsPanel tests with the production retry-free client', () => {
    expect(read('src/components/settings/__tests__/LocalModelsPanel.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/LocalModelsPanel.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/components/settings/__tests__/LocalModelsPanel.dualMount.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/LocalModelsPanel.dualMount.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useLocalModelsCatalogQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useLocalModelsCatalogQuery.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings local-models catalog GET on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useLocalModelsCatalogQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    const panelSource = read('src/components/settings/LocalModelsPanel.tsx');
    const withKronosSource = read('src/components/settings/LocalModelsWithKronos.tsx');
    const wizardSource = read('src/components/settings/FirstRunWizard.tsx');
    const settingsPageSource = read('src/pages/SettingsPage.tsx');
    const onboardingSource = read('src/components/onboarding/SettingsOnboardingHosts.tsx');
    const harnessSource = read('src/pages/__tests__/SettingsPage.testHarness.tsx');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(hookSource).toContain("['local-models', 'catalog']");
    expect(hookSource).toContain('getCatalog()');
    expect(hookSource).not.toContain('getRuntime(');
    expect(hookSource).not.toContain('startPull');
    expect(hookSource).not.toContain('.assign(');
    expect(hookSource).not.toContain('deleteModel');
    expect(hookSource).not.toContain('importPack');
    expect(barrelSource).not.toContain('useLocalModelsCatalogQuery');
    expect(panelSource).toContain('useLocalModelsCatalogQuery');
    expect(withKronosSource).toContain("lazy(() => import('./LocalModelsPanel'))");
    expect(withKronosSource).toContain('Suspense');
    expect(withKronosSource).not.toContain('useLocalModelsCatalogQuery');
    expect(wizardSource).toContain("lazy(() => import('./LocalModelsPanel'))");
    expect(wizardSource).toContain('Suspense');
    expect(wizardSource).not.toContain('useLocalModelsCatalogQuery');
    expect(settingsPageSource).not.toContain('useLocalModelsCatalogQuery');
    expect(onboardingSource).toContain('FirstRunWizard');
    expect(onboardingSource).not.toContain('useLocalModelsCatalogQuery');
    expect(harnessSource).toContain('local-models-with-kronos');
    expect(harnessSource).toContain('FirstRunWizard');
  });

  it('wraps GenerationBackendStatusPanel tests with the production retry-free client', () => {
    expect(read('src/components/settings/__tests__/GenerationBackendStatusPanel.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/GenerationBackendStatusPanel.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useGenerationBackendStatusQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useGenerationBackendStatusQuery.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings generation-backend saved GET and draft preview POST on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useGenerationBackendStatusQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    const panelSource = read('src/components/settings/GenerationBackendStatusPanel.tsx');
    const settingsPageSource = read('src/pages/SettingsPage.tsx');
    const editorSource = read('src/components/settings/LLMChannelEditor.tsx');
    const harnessSource = read('src/pages/__tests__/SettingsPage.testHarness.tsx');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(hookSource).toContain("['generation-backend', 'status', 'saved']");
    expect(hookSource).toContain('buildGenerationBackendPreviewStatusQueryKey');
    expect(hookSource).toContain('getGenerationBackendStatus');
    expect(hookSource).toContain('previewGenerationBackendStatus');
    expect(hookSource).not.toContain('testGenerationBackend');
    expect(barrelSource).not.toContain('useGenerationBackendStatusQuery');
    expect(panelSource).toContain('useGenerationBackendStatusQuery');
    expect(settingsPageSource).toContain("lazy(() => import('../components/settings/GenerationBackendStatusPanel'))");
    expect(settingsPageSource).toContain('Suspense');
    expect(settingsPageSource).not.toContain('useGenerationBackendStatusQuery');
    expect(editorSource).toContain('getGenerationBackendStatus()');
    expect(harnessSource).toContain('GenerationBackendStatusPanel');
  });

  it('wraps IntelligenceSourcesPanel tests with the production retry-free client', () => {
    expect(read('src/components/settings/__tests__/IntelligenceSourcesPanel.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/IntelligenceSourcesPanel.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useIntelligenceSourcesQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useIntelligenceSourcesQuery.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings intelligence sources list GET and templates list GET on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useIntelligenceSourcesQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    const panelSource = read('src/components/settings/IntelligenceSourcesPanel.tsx');
    const settingsPageSource = read('src/pages/SettingsPage.tsx');
    const settingsBarrelSource = read('src/components/settings/index.ts');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(hookSource).toContain("['intelligence', 'sources', 'list']");
    expect(hookSource).toContain("['intelligence', 'templates', 'list']");
    expect(hookSource).toContain('listSources');
    expect(hookSource).toContain('listTemplates');
    expect(hookSource).not.toContain('listItems');
    expect(hookSource).not.toContain('createSource');
    expect(hookSource).not.toContain('testSource');
    expect(hookSource).not.toContain('fetchSource');
    expect(barrelSource).not.toContain('useIntelligenceSourcesQuery');
    expect(panelSource).toContain('useIntelligenceSourcesQuery');
    expect(settingsPageSource).toContain("lazy(() => import('../components/settings/IntelligenceSourcesPanel'))");
    expect(settingsPageSource).toContain('Suspense');
    expect(settingsPageSource).not.toContain('useIntelligenceSourcesQuery');
    expect(settingsBarrelSource).not.toContain('IntelligenceSourcesPanel');
  });

  it('wraps NotificationChannelsPanel tests with the production retry-free client', () => {
    expect(read('src/components/settings/__tests__/NotificationChannelsPanel.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/NotificationChannelsPanel.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useNotificationChannelPluginsQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useNotificationChannelPluginsQuery.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings notification-channel plugin roster GET on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useNotificationChannelPluginsQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    const panelSource = read('src/components/settings/NotificationChannelsPanel.tsx');
    const activeConfigSource = read('src/components/settings/SettingsActiveConfigPanel.tsx');
    const settingsPageSource = read('src/pages/SettingsPage.tsx');
    const settingsBarrelSource = read('src/components/settings/index.ts');
    const harnessSource = read('src/pages/__tests__/SettingsPage.testHarness.tsx');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(hookSource).toContain("['plugins', 'notification-channels']");
    expect(hookSource).toContain('pluginsApi.list');
    expect(hookSource).not.toContain('updateLifecycle');
    expect(hookSource).not.toContain('getSettings');
    expect(hookSource).not.toContain('updateSettings');
    expect(hookSource).not.toMatch(/\['plugins',\s*'list'\]/);
    expect(barrelSource).not.toContain('useNotificationChannelPluginsQuery');
    expect(panelSource).toContain('useNotificationChannelPluginsQuery');
    expect(activeConfigSource).toContain("lazy(() => import('./NotificationChannelsPanel'))");
    expect(activeConfigSource).toContain('Suspense');
    expect(activeConfigSource).not.toContain('useNotificationChannelPluginsQuery');
    expect(settingsPageSource).not.toContain('useNotificationChannelPluginsQuery');
    expect(settingsBarrelSource).toContain('NotificationChannelsPanel');
    expect(harnessSource).toContain('NotificationChannelsPanel');
    expect(harnessSource).toContain("source.includes('NotificationChannelsPanel')");
  });

  it('wraps scheduled-task run history hook tests with the production retry-free client', () => {
    expect(read('src/components/settings/__tests__/ScheduledTasksPanel.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/ScheduledTasksPanel.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/hooks/__tests__/useScheduledTaskRunHistoryQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useScheduledTaskRunHistoryQuery.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings scheduled-task run history GET on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useScheduledTaskRunHistoryQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    const historySource = read('src/components/settings/ScheduledTaskRunHistory.tsx');
    const panelSource = read('src/components/settings/ScheduledTasksPanel.tsx');
    const sectionSource = read('src/components/settings/sections/SystemSecuritySection.tsx');
    const settingsPageSource = read('src/pages/SettingsPage.tsx');
    const editorSource = read('src/components/settings/LLMChannelEditor.tsx');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(hookSource).toContain("['scheduled-tasks', 'runs'");
    expect(hookSource).toContain('listRuns');
    expect(hookSource).not.toContain("['scheduled-tasks', 'list']");
    expect(hookSource).not.toContain('getStatus');
    expect(hookSource).not.toContain('.create(');
    expect(hookSource).not.toContain('.enable(');
    expect(hookSource).not.toContain('.disable(');
    expect(barrelSource).not.toContain('useScheduledTaskRunHistoryQuery');
    expect(historySource).toContain('useScheduledTaskRunHistoryQuery');
    expect(panelSource).not.toContain('useScheduledTaskRunHistoryQuery');
    expect(sectionSource).toContain("lazy(() => import('../ScheduledTasksPanel'))");
    expect(sectionSource).toContain('Suspense');
    expect(sectionSource).not.toContain('useScheduledTaskRunHistoryQuery');
    expect(settingsPageSource).not.toContain('useScheduledTaskRunHistoryQuery');
    expect(editorSource).toContain('getGenerationBackendStatus()');
  });

  it('wraps Settings scheduler overlap probe tests with the production retry-free client', () => {
    expect(read('src/hooks/__tests__/useScheduledTasksOverlapQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useScheduledTasksOverlapQuery.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/components/settings/__tests__/SchedulerSettingsCard.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/SchedulerSettingsCard.test.tsx')).toContain('QueryClientProvider');
  });

  it('wraps Settings scheduled-task getStatus fan-out tests with the production retry-free client', () => {
    expect(read('src/hooks/__tests__/useScheduledTaskLatestRunsQuery.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/hooks/__tests__/useScheduledTaskLatestRunsQuery.test.tsx')).toContain('QueryClientProvider');
    expect(read('src/components/settings/__tests__/ScheduledTasksPanel.test.tsx')).toContain('createAppQueryClient');
    expect(read('src/components/settings/__tests__/ScheduledTasksPanel.test.tsx')).toContain('QueryClientProvider');
  });

  it('keeps Settings scheduler overlap probe on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useScheduledTasksOverlapQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    const cardSource = read('src/components/settings/SchedulerSettingsCard.tsx');
    const sectionSource = read('src/components/settings/sections/SystemSecuritySection.tsx');
    const settingsPageSource = read('src/pages/SettingsPage.tsx');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(hookSource).toContain("['scheduled-tasks', 'overlap']");
    expect(hookSource).toContain('list({ enabled: true, limit: 1 })');
    expect(hookSource).not.toContain('list({ limit: 200 })');
    expect(hookSource).not.toContain('listRuns');
    expect(hookSource).not.toContain('getStatus');
    expect(hookSource).not.toContain('.create(');
    expect(hookSource).not.toContain('.enable(');
    expect(hookSource).not.toContain('.disable(');
    expect(hookSource).not.toContain('getSchedulerStatus');
    expect(hookSource).not.toContain('runSchedulerNow');
    expect(barrelSource).not.toContain('useScheduledTasksOverlapQuery');
    expect(cardSource).toContain('useScheduledTasksOverlapQuery');
    expect(cardSource).not.toContain('list({ enabled: true, limit: 1 })');
    expect(sectionSource).toContain("lazy(() => import('../SchedulerSettingsCard'))");
    expect(sectionSource).toContain('Suspense');
    expect(sectionSource).not.toContain('useScheduledTasksOverlapQuery');
    expect(settingsPageSource).not.toContain('useScheduledTasksOverlapQuery');
  });

  it('keeps Settings scheduled-task getStatus fan-out on an imperative fetchQuery recipe without a barrel export', () => {
    const hookSource = read('src/hooks/useScheduledTaskLatestRunsQuery.ts');
    const barrelSource = read('src/hooks/index.ts');
    const panelSource = read('src/components/settings/ScheduledTasksPanel.tsx');
    const sectionSource = read('src/components/settings/sections/SystemSecuritySection.tsx');
    const settingsPageSource = read('src/pages/SettingsPage.tsx');
    const historySource = read('src/components/settings/ScheduledTaskRunHistory.tsx');
    const cardSource = read('src/components/settings/SchedulerSettingsCard.tsx');
    const editorSource = read('src/components/settings/LLMChannelEditor.tsx');
    expect(hookSource).toContain('fetchQuery');
    expect(hookSource).not.toMatch(/\buseQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseInfiniteQuery\s*\(/);
    expect(hookSource).not.toMatch(/\buseMutation\s*\(/);
    expect(hookSource).toContain("['scheduled-tasks', 'latest-runs']");
    expect(hookSource).toContain('getStatus');
    expect(hookSource).toContain('allSettled');
    expect(hookSource).not.toContain('list({ limit: 200 })');
    expect(hookSource).not.toContain('list({ enabled: true, limit: 1 })');
    expect(hookSource).not.toContain('listRuns');
    expect(hookSource).not.toContain('.create(');
    expect(hookSource).not.toContain('.enable(');
    expect(hookSource).not.toContain('.disable(');
    expect(hookSource).not.toContain('getSchedulerStatus');
    expect(barrelSource).not.toContain('useScheduledTaskLatestRunsQuery');
    expect(panelSource).toContain('useScheduledTaskLatestRunsQuery');
    expect(panelSource).not.toContain('scheduledTasksApi.getStatus');
    expect(sectionSource).toContain("lazy(() => import('../ScheduledTasksPanel'))");
    expect(sectionSource).toContain('Suspense');
    expect(sectionSource).not.toContain('useScheduledTaskLatestRunsQuery');
    expect(settingsPageSource).not.toContain('useScheduledTaskLatestRunsQuery');
    expect(historySource).not.toContain('useScheduledTaskLatestRunsQuery');
    expect(cardSource).not.toContain('useScheduledTaskLatestRunsQuery');
    expect(editorSource).toContain('getGenerationBackendStatus()');
  });
});
