// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import {
  ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS,
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  REPORT_ROUTE_QUERY_KEYS,
  RUN_FLOW_ROUTE_QUERY_VALUES,
  type AnalysisWorkbenchSegment,
} from './routes';

export type AnalysisWorkbenchRouteState = {
  segment: AnalysisWorkbenchSegment;
  recordId: number | null;
  runFlow: 'history' | 'task' | null;
  runFlowRecordId: number | null;
  runFlowTaskId: string | null;
};

export type ParsedAnalysisWorkbenchRouteState = {
  state: AnalysisWorkbenchRouteState;
  normalizedParams: URLSearchParams;
  invalidKeys: string[];
};

export const DEFAULT_ANALYSIS_WORKBENCH_ROUTE_STATE: AnalysisWorkbenchRouteState = {
  segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch,
  recordId: null,
  runFlow: null,
  runFlowRecordId: null,
  runFlowTaskId: null,
};

const SEGMENTS = new Set<AnalysisWorkbenchSegment>(
  Object.values(ANALYSIS_WORKBENCH_SEGMENT_VALUES),
);

function toSearchParams(search: string | URLSearchParams): URLSearchParams {
  return typeof search === 'string' ? new URLSearchParams(search) : new URLSearchParams(search);
}

function parsePositiveInt(raw: string | null): number | null {
  if (raw === null) return null;
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || !Number.isInteger(value) || value <= 0) return null;
  return value;
}

function replaceOwnedParams(
  source: URLSearchParams,
  state: AnalysisWorkbenchRouteState,
): URLSearchParams {
  const ownedKeys = new Set<string>(Object.values(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS));
  const next = new URLSearchParams();
  source.forEach((value, key) => {
    if (!ownedKeys.has(key)) next.append(key, value);
  });
  if (
    state.segment !== DEFAULT_ANALYSIS_WORKBENCH_ROUTE_STATE.segment
    || source.has(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment)
  ) {
    next.set(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment, state.segment);
  }
  if (state.recordId !== null) {
    next.set(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId, String(state.recordId));
  }
  if (state.runFlow) {
    next.set(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow, state.runFlow);
    if (state.runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.history && state.runFlowRecordId !== null) {
      next.set(
        ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId,
        String(state.runFlowRecordId),
      );
    }
    if (state.runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.task && state.runFlowTaskId) {
      next.set(
        ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowTaskId,
        state.runFlowTaskId,
      );
    }
  }
  return next;
}

export function parseAnalysisWorkbenchRouteState(
  search: string | URLSearchParams,
): ParsedAnalysisWorkbenchRouteState {
  const source = toSearchParams(search);
  const invalidKeys: string[] = [];

  const rawSegment = source.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment);
  let segment: AnalysisWorkbenchSegment;
  if (rawSegment === null) {
    segment = DEFAULT_ANALYSIS_WORKBENCH_ROUTE_STATE.segment;
  } else if (SEGMENTS.has(rawSegment as AnalysisWorkbenchSegment)) {
    segment = rawSegment as AnalysisWorkbenchSegment;
  } else {
    segment = DEFAULT_ANALYSIS_WORKBENCH_ROUTE_STATE.segment;
    invalidKeys.push(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment);
  }

  const rawRecordId = source.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId);
  const recordId = parsePositiveInt(rawRecordId);
  if (rawRecordId !== null && recordId === null) {
    invalidKeys.push(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId);
  }

  const rawRunFlow = source.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow);
  let runFlow: 'history' | 'task' | null = null;
  if (rawRunFlow === RUN_FLOW_ROUTE_QUERY_VALUES.history || rawRunFlow === RUN_FLOW_ROUTE_QUERY_VALUES.task) {
    runFlow = rawRunFlow;
  } else if (rawRunFlow !== null) {
    invalidKeys.push(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow);
  }

  const rawRunFlowRecordId = source.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId);
  let runFlowRecordId = parsePositiveInt(rawRunFlowRecordId);
  if (rawRunFlowRecordId !== null && runFlowRecordId === null) {
    invalidKeys.push(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId);
  }

  const rawRunFlowTaskId = source.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowTaskId);
  let runFlowTaskId = rawRunFlowTaskId?.trim() || null;

  if (runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.history) {
    runFlowTaskId = null;
  } else if (runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.task) {
    runFlowRecordId = null;
  } else {
    runFlowRecordId = null;
    runFlowTaskId = null;
  }

  // Coerce segment when the URL implies a specific view but leaves segment unspecified:
  // recordId or runFlow=history land users on the history segment; runFlow=task lands on tasks.
  if (rawSegment === null) {
    if (runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.task) {
      segment = ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks;
    } else if (recordId !== null || runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.history) {
      segment = ANALYSIS_WORKBENCH_SEGMENT_VALUES.history;
    }
  }

  const state: AnalysisWorkbenchRouteState = {
    segment,
    recordId,
    runFlow,
    runFlowRecordId,
    runFlowTaskId,
  };
  return {
    state,
    normalizedParams: replaceOwnedParams(source, state),
    invalidKeys,
  };
}

export function setAnalysisWorkbenchRouteState(
  search: string | URLSearchParams,
  state: AnalysisWorkbenchRouteState,
): URLSearchParams {
  return replaceOwnedParams(toSearchParams(search), state);
}

function replaceSearchParams(target: URLSearchParams, source: URLSearchParams): void {
  for (const key of [...target.keys()]) target.delete(key);
  source.forEach((value, key) => target.append(key, value));
}

/**
 * Legacy home compatibility: map old HomePage analysis-scoped params
 * (recordId, runFlow, runFlowRecordId, runFlowTaskId — see REPORT_ROUTE_QUERY_KEYS)
 * to the Analysis Workbench route contract with an explicit segment.
 */
export function mapLegacyHomeAnalysisSearchParams(searchParams: URLSearchParams): void {
  const rawRecordId = searchParams.get(REPORT_ROUTE_QUERY_KEYS.recordId);
  const rawRunFlow = searchParams.get(REPORT_ROUTE_QUERY_KEYS.runFlow);
  const rawRunFlowRecordId = searchParams.get(REPORT_ROUTE_QUERY_KEYS.runFlowRecordId);
  const rawRunFlowTaskId = searchParams.get(REPORT_ROUTE_QUERY_KEYS.runFlowTaskId);

  const recordId = parsePositiveInt(rawRecordId);
  const runFlow: 'history' | 'task' | null =
    rawRunFlow === RUN_FLOW_ROUTE_QUERY_VALUES.history
      ? RUN_FLOW_ROUTE_QUERY_VALUES.history
      : rawRunFlow === RUN_FLOW_ROUTE_QUERY_VALUES.task
        ? RUN_FLOW_ROUTE_QUERY_VALUES.task
        : null;
  const runFlowRecordId = runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.history
    ? parsePositiveInt(rawRunFlowRecordId)
    : null;
  const runFlowTaskId = runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.task
    ? (rawRunFlowTaskId?.trim() || null)
    : null;

  // Drop the legacy home-scoped analysis params from the copy we hand to the workbench parser.
  searchParams.delete(REPORT_ROUTE_QUERY_KEYS.recordId);
  searchParams.delete(REPORT_ROUTE_QUERY_KEYS.runFlow);
  searchParams.delete(REPORT_ROUTE_QUERY_KEYS.runFlowRecordId);
  searchParams.delete(REPORT_ROUTE_QUERY_KEYS.runFlowTaskId);

  const segment: AnalysisWorkbenchSegment = runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.task
    ? ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks
    : recordId !== null || runFlow === RUN_FLOW_ROUTE_QUERY_VALUES.history
      ? ANALYSIS_WORKBENCH_SEGMENT_VALUES.history
      : DEFAULT_ANALYSIS_WORKBENCH_ROUTE_STATE.segment;

  const state: AnalysisWorkbenchRouteState = {
    segment,
    recordId,
    runFlow,
    runFlowRecordId,
    runFlowTaskId,
  };
  const normalized = setAnalysisWorkbenchRouteState(searchParams, state);
  replaceSearchParams(searchParams, normalized);
}
