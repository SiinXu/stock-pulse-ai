// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import {
  parseAnalysisWorkbenchRouteState,
  setAnalysisWorkbenchRouteState,
} from './analysisWorkbenchRouteState';
import {
  ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS,
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  APP_ROUTE_PATHS,
  HOME_ROUTE_QUERY_KEYS,
  HOME_WORKSPACE_VALUES,
  REPORT_ROUTE_QUERY_KEYS,
} from './routes';

type LegacyHomeLocation = {
  search: string;
  hash: string;
};

const LEGACY_ANALYSIS_QUERY_KEYS = new Set<string>([
  ...Object.values(REPORT_ROUTE_QUERY_KEYS),
  HOME_ROUTE_QUERY_KEYS.stock,
]);
const LEGACY_HOME_WORKSPACES = new Set<string>(Object.values(HOME_WORKSPACE_VALUES));

export function resolveLegacyHomeAnalysisRedirect(
  location: LegacyHomeLocation,
): { pathname: string; search: string; hash: string } | null {
  const source = new URLSearchParams(location.search);
  const rawWorkspace = source.get(HOME_ROUTE_QUERY_KEYS.workspace);
  const hasAnalysisIntent = [...source.keys()].some((key) => LEGACY_ANALYSIS_QUERY_KEYS.has(key))
    || (rawWorkspace !== null && LEGACY_HOME_WORKSPACES.has(rawWorkspace));
  if (!hasAnalysisIntent) return null;

  const parsed = parseAnalysisWorkbenchRouteState(source);
  let normalized = parsed.normalizedParams;
  if (
    !source.has(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment)
    && !source.has(REPORT_ROUTE_QUERY_KEYS.recordId)
    && !source.has(REPORT_ROUTE_QUERY_KEYS.runFlow)
    && (rawWorkspace === HOME_WORKSPACE_VALUES.history || rawWorkspace === HOME_WORKSPACE_VALUES.today)
  ) {
    normalized = setAnalysisWorkbenchRouteState(normalized, {
      ...parsed.state,
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
    });
  }
  normalized.delete(HOME_ROUTE_QUERY_KEYS.workspace);

  const search = normalized.toString();
  return {
    pathname: APP_ROUTE_PATHS.researchAnalysis,
    search: search ? `?${search}` : '',
    hash: location.hash,
  };
}
