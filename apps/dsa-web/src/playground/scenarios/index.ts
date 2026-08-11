import { createElement, lazy, Suspense, type ReactNode } from 'react';
import { PLAYGROUND_CATALOG } from '../catalog';
import type { PlaygroundScenarioRenderer } from '../types';
import { ALERT_HISTORY_SCENARIOS } from './alertHistoryScenarios';
import { COMMON_SCENARIOS } from './commonScenarios';
import { DECISION_REPORT_RUN_FLOW_SCENARIOS } from './decisionReportRunFlowScenarios';
import { LAYOUT_DASHBOARD_SCENARIOS } from './layoutDashboardScenarios';
import { SETTINGS_SCENARIOS } from './settingsScenarios';
import { SKILL_OUTCOME_SCENARIOS } from './skillOutcomeScenarios';
import { WORKSPACE_SCENARIOS } from './workspaceScenarios';
import { SCREENING_SCENARIOS } from './screeningScenarios';

type ChartScenarioId = 'kline-chart' | 'risk-heatmap';
type ValuationScenarioId = 'dcf-sensitivity-panel';

function createLazyScenario(loadRenderer: () => Promise<PlaygroundScenarioRenderer>): PlaygroundScenarioRenderer {
  const LazyRenderer = lazy(async () => {
    const renderer = await loadRenderer();
    return { default: renderer };
  });
  return () => createElement(Suspense, { fallback: null }, createElement(LazyRenderer));
}

const LAZY_CHART_SCENARIOS: Record<ChartScenarioId, PlaygroundScenarioRenderer> = {
  'kline-chart': createLazyScenario(async () => (
    (await import('./chartScenarios')).CHART_SCENARIOS['kline-chart']
  )),
  'risk-heatmap': createLazyScenario(async () => (
    (await import('./chartScenarios')).CHART_SCENARIOS['risk-heatmap']
  )),
};

const LAZY_REPORT_VERSION_COMPARE_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'report-version-compare-view': createLazyScenario(async () => (
    (await import('./reportVersionCompareScenarios')).REPORT_VERSION_COMPARE_SCENARIOS['report-version-compare-view']
  )),
};

const LAZY_WORKBENCH_HISTORY_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'workbench-history-popover': createLazyScenario(async () => (
    (await import('./workbenchHistoryPopoverScenario')).default
  )),
};

const LAZY_RISK_GATE_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'report-decision-card': createLazyScenario(async () => (
    (await import('./riskGate')).default[0]
  )),
  'report-risk-gate-banner': createLazyScenario(async () => (
    (await import('./riskGate')).default[1]
  )),
  'report-details': createLazyScenario(async () => (
    (await import('./riskGate')).default[2]
  )),
  'report-diagnostics': createLazyScenario(async () => (
    (await import('./riskGate')).default[3]
  )),
};

const LAZY_REPORT_MARKDOWN_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'report-markdown': createLazyScenario(async () => (
    (await import('./reportMarkdown')).default[0]
  )),
  'report-markdown-body': createLazyScenario(async () => (
    (await import('./reportMarkdown')).default[1]
  )),
  'report-markdown-drawer': createLazyScenario(async () => (
    (await import('./reportMarkdown')).default[2]
  )),
  'report-markdown-panel': createLazyScenario(async () => (
    (await import('./reportMarkdown')).default[3]
  )),
};

const LAZY_VALUATION_SCENARIOS: Record<ValuationScenarioId, PlaygroundScenarioRenderer> = {
  'dcf-sensitivity-panel': createLazyScenario(async () => (
    (await import('./valuationScenarios')).VALUATION_SCENARIOS['dcf-sensitivity-panel']
  )),
};

type WatchlistWorkspaceScenarioId = 'home-stock-workspace' | 'watchlist-score-column';

// Lazy-load watchlist workspace stories so score-column product wiring does not
// inflate the PlaygroundRenderPage entry chunk (same pattern as charts/valuation).
const LAZY_WATCHLIST_WORKSPACE_SCENARIOS: Record<WatchlistWorkspaceScenarioId, PlaygroundScenarioRenderer> = {
  'home-stock-workspace': createLazyScenario(async () => (
    (await import('./watchlistWorkspaceScenarios')).WATCHLIST_WORKSPACE_SCENARIOS['home-stock-workspace']
  )),
  'watchlist-score-column': createLazyScenario(async () => (
    (await import('./watchlistWorkspaceScenarios')).WATCHLIST_WORKSPACE_SCENARIOS['watchlist-score-column']
  )),
};

const RENDERERS: Record<string, PlaygroundScenarioRenderer> = {
  ...COMMON_SCENARIOS,
  ...LAYOUT_DASHBOARD_SCENARIOS,
  'notification-inbox-list': createLazyScenario(async () => (
    (await import('./inbox')).default
  )),
  ...ALERT_HISTORY_SCENARIOS,
  ...LAZY_WORKBENCH_HISTORY_SCENARIOS,
  ...DECISION_REPORT_RUN_FLOW_SCENARIOS,
  ...LAZY_RISK_GATE_SCENARIOS,
  ...LAZY_REPORT_MARKDOWN_SCENARIOS,
  ...SKILL_OUTCOME_SCENARIOS,
  ...WORKSPACE_SCENARIOS,
  ...SETTINGS_SCENARIOS,
  ...SCREENING_SCENARIOS,
  ...LAZY_CHART_SCENARIOS,
  ...LAZY_VALUATION_SCENARIOS,
  ...LAZY_REPORT_VERSION_COMPARE_SCENARIOS,
  ...LAZY_WATCHLIST_WORKSPACE_SCENARIOS,
};

/**
 * Pure missing-renderer check shared by runtime and contract tests.
 * A catalog id is missing when the runtime registry has no entry for it.
 */
export function listMissingPlaygroundRendererIds(
  catalog: readonly { readonly id: string }[],
  registry: Readonly<Record<string, unknown>>,
): string[] {
  return catalog.filter((entry) => !registry[entry.id]).map((entry) => entry.id);
}

export function getPlaygroundRenderer(componentId: string): PlaygroundScenarioRenderer | undefined {
  return RENDERERS[componentId];
}

export function hasPlaygroundRenderer(componentId: string): boolean {
  return Boolean(RENDERERS[componentId]);
}

export function renderPlaygroundScenario(componentId: string): ReactNode {
  const Renderer = RENDERERS[componentId];
  return Renderer ? createElement(Renderer) : null;
}

export function getMissingPlaygroundRendererIds(): string[] {
  return listMissingPlaygroundRendererIds(PLAYGROUND_CATALOG, RENDERERS);
}
