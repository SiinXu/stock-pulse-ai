import { createElement, type ReactNode } from 'react';
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
import { VALUATION_SCENARIOS } from './valuationScenarios';
import { REPORT_VERSION_COMPARE_SCENARIOS } from './reportVersionCompareScenarios';

const RENDERERS: Record<string, PlaygroundScenarioRenderer> = {
  ...COMMON_SCENARIOS,
  ...LAYOUT_DASHBOARD_SCENARIOS,
  ...ALERT_HISTORY_SCENARIOS,
  ...DECISION_REPORT_RUN_FLOW_SCENARIOS,
  ...SKILL_OUTCOME_SCENARIOS,
  ...WORKSPACE_SCENARIOS,
  ...SETTINGS_SCENARIOS,
  ...SCREENING_SCENARIOS,
  ...VALUATION_SCENARIOS,
  ...REPORT_VERSION_COMPARE_SCENARIOS,
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
