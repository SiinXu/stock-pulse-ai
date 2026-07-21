import { PLAYGROUND_CATALOG } from '../catalog';
import type { PlaygroundScenarioRenderer } from '../types';
import { ALERT_HISTORY_SCENARIOS } from './alertHistoryScenarios';
import { COMMON_SCENARIOS } from './commonScenarios';
import { DECISION_REPORT_RUN_FLOW_SCENARIOS } from './decisionReportRunFlowScenarios';
import { LAYOUT_DASHBOARD_SCENARIOS } from './layoutDashboardScenarios';
import { SETTINGS_SCENARIOS } from './settingsScenarios';
import { WORKSPACE_SCENARIOS } from './workspaceScenarios';

const RENDERERS: Record<string, PlaygroundScenarioRenderer> = {
  ...COMMON_SCENARIOS,
  ...LAYOUT_DASHBOARD_SCENARIOS,
  ...ALERT_HISTORY_SCENARIOS,
  ...DECISION_REPORT_RUN_FLOW_SCENARIOS,
  ...WORKSPACE_SCENARIOS,
  ...SETTINGS_SCENARIOS,
};

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
  return PLAYGROUND_CATALOG
    .filter((entry) => !RENDERERS[entry.id])
    .map((entry) => entry.id);
}
import { createElement, type ReactNode } from 'react';
