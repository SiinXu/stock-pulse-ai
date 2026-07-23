// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';

import {
  ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS,
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  APP_ROUTE_PATHS,
  REPORT_ROUTE_QUERY_KEYS,
  RUN_FLOW_ROUTE_QUERY_VALUES,
  buildAnalysisWorkbenchHref,
} from '../routes';
import {
  DEFAULT_ANALYSIS_WORKBENCH_ROUTE_STATE,
  mapLegacyHomeAnalysisSearchParams,
  parseAnalysisWorkbenchRouteState,
  setAnalysisWorkbenchRouteState,
} from '../analysisWorkbenchRouteState';

describe('parseAnalysisWorkbenchRouteState', () => {
  it('returns the launch default when the search is empty', () => {
    const parsed = parseAnalysisWorkbenchRouteState('');
    expect(parsed.state).toEqual(DEFAULT_ANALYSIS_WORKBENCH_ROUTE_STATE);
    expect(parsed.invalidKeys).toEqual([]);
    expect(parsed.normalizedParams.toString()).toBe('');
  });

  it('accepts each explicit segment value', () => {
    for (const segment of Object.values(ANALYSIS_WORKBENCH_SEGMENT_VALUES)) {
      const parsed = parseAnalysisWorkbenchRouteState(`segment=${segment}`);
      expect(parsed.state.segment).toBe(segment);
      expect(parsed.invalidKeys).toEqual([]);
    }
  });

  it('falls back to the launch default and records an invalid key for an unknown segment', () => {
    const parsed = parseAnalysisWorkbenchRouteState('segment=nope');
    expect(parsed.state.segment).toBe(DEFAULT_ANALYSIS_WORKBENCH_ROUTE_STATE.segment);
    expect(parsed.invalidKeys).toContain(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment);
  });

  it('lands on the history segment when only recordId is provided', () => {
    const parsed = parseAnalysisWorkbenchRouteState('recordId=42');
    expect(parsed.state.segment).toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.history);
    expect(parsed.state.recordId).toBe(42);
    expect(parsed.invalidKeys).toEqual([]);
  });

  it('lands on the history segment when runFlow=history is provided without a segment', () => {
    const parsed = parseAnalysisWorkbenchRouteState(
      'runFlow=history&runFlowRecordId=7',
    );
    expect(parsed.state.segment).toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.history);
    expect(parsed.state.runFlow).toBe(RUN_FLOW_ROUTE_QUERY_VALUES.history);
    expect(parsed.state.runFlowRecordId).toBe(7);
    expect(parsed.state.runFlowTaskId).toBeNull();
  });

  it('lands on the tasks segment when runFlow=task is provided without a segment', () => {
    const parsed = parseAnalysisWorkbenchRouteState(
      'runFlow=task&runFlowTaskId=abc',
    );
    expect(parsed.state.segment).toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks);
    expect(parsed.state.runFlow).toBe(RUN_FLOW_ROUTE_QUERY_VALUES.task);
    expect(parsed.state.runFlowRecordId).toBeNull();
    expect(parsed.state.runFlowTaskId).toBe('abc');
  });

  it('respects an explicit segment override even when recordId is present', () => {
    const parsed = parseAnalysisWorkbenchRouteState('segment=launch&recordId=9');
    expect(parsed.state.segment).toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch);
    expect(parsed.state.recordId).toBe(9);
  });

  it('rejects non-positive-integer recordId values', () => {
    for (const bad of ['-1', '0', 'abc', '3.5', '  ']) {
      const parsed = parseAnalysisWorkbenchRouteState(`recordId=${bad}`);
      expect(parsed.state.recordId).toBeNull();
      expect(parsed.invalidKeys).toContain(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId);
    }
  });

  it('rejects an unrecognized runFlow value', () => {
    const parsed = parseAnalysisWorkbenchRouteState('runFlow=other');
    expect(parsed.state.runFlow).toBeNull();
    expect(parsed.invalidKeys).toContain(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow);
  });

  it('drops runFlowTaskId when runFlow is history and drops runFlowRecordId when runFlow is task', () => {
    const parsedHistory = parseAnalysisWorkbenchRouteState(
      'runFlow=history&runFlowRecordId=3&runFlowTaskId=leftover',
    );
    expect(parsedHistory.state.runFlowRecordId).toBe(3);
    expect(parsedHistory.state.runFlowTaskId).toBeNull();

    const parsedTask = parseAnalysisWorkbenchRouteState(
      'runFlow=task&runFlowTaskId=xyz&runFlowRecordId=99',
    );
    expect(parsedTask.state.runFlowRecordId).toBeNull();
    expect(parsedTask.state.runFlowTaskId).toBe('xyz');
  });

  it('preserves foreign search params in the normalized copy', () => {
    const parsed = parseAnalysisWorkbenchRouteState(
      'utm=source&segment=tasks',
    );
    expect(parsed.normalizedParams.get('utm')).toBe('source');
    expect(parsed.normalizedParams.get(
      ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment,
    )).toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks);
  });
});

describe('setAnalysisWorkbenchRouteState', () => {
  it('omits the segment key when it matches the default and was not previously set', () => {
    const next = setAnalysisWorkbenchRouteState('utm=abc', {
      ...DEFAULT_ANALYSIS_WORKBENCH_ROUTE_STATE,
    });
    expect(next.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment)).toBeNull();
    expect(next.get('utm')).toBe('abc');
  });

  it('writes segment/recordId/runFlow keys when the state carries them', () => {
    const next = setAnalysisWorkbenchRouteState('', {
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      recordId: 12,
      runFlow: RUN_FLOW_ROUTE_QUERY_VALUES.history,
      runFlowRecordId: 8,
      runFlowTaskId: null,
    });
    expect(next.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment))
      .toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.history);
    expect(next.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId)).toBe('12');
    expect(next.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow))
      .toBe(RUN_FLOW_ROUTE_QUERY_VALUES.history);
    expect(next.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId)).toBe('8');
    expect(next.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowTaskId)).toBeNull();
  });

  it('replaces existing owned params without duplicating them', () => {
    const next = setAnalysisWorkbenchRouteState(
      'segment=launch&recordId=1&runFlow=history&runFlowRecordId=2',
      {
        segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
        recordId: null,
        runFlow: RUN_FLOW_ROUTE_QUERY_VALUES.task,
        runFlowRecordId: null,
        runFlowTaskId: 't-9',
      },
    );
    expect(next.getAll(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment)).toEqual(['tasks']);
    expect(next.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId)).toBeNull();
    expect(next.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow))
      .toBe(RUN_FLOW_ROUTE_QUERY_VALUES.task);
    expect(next.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId)).toBeNull();
    expect(next.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowTaskId)).toBe('t-9');
  });
});

describe('mapLegacyHomeAnalysisSearchParams', () => {
  it('leaves a URL with no home analysis params unchanged besides removing owned keys', () => {
    const params = new URLSearchParams('utm=source');
    mapLegacyHomeAnalysisSearchParams(params);
    expect(params.get('utm')).toBe('source');
    // No segment param when default (launch) — foreign only.
    expect(params.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment)).toBeNull();
    expect(params.get(REPORT_ROUTE_QUERY_KEYS.recordId)).toBeNull();
  });

  it('maps a bare recordId onto segment=history + recordId (same key name as workbench)', () => {
    // The legacy home `recordId` and workbench `recordId` intentionally share the
    // same URL param name — the mapper only adds an explicit segment.
    const params = new URLSearchParams(`${REPORT_ROUTE_QUERY_KEYS.recordId}=17`);
    mapLegacyHomeAnalysisSearchParams(params);
    expect(params.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment))
      .toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.history);
    expect(params.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId)).toBe('17');
  });

  it('maps runFlow=history with a runFlowRecordId onto the history segment', () => {
    const params = new URLSearchParams(
      `${REPORT_ROUTE_QUERY_KEYS.runFlow}=history&${REPORT_ROUTE_QUERY_KEYS.runFlowRecordId}=88`,
    );
    mapLegacyHomeAnalysisSearchParams(params);
    expect(params.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment))
      .toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.history);
    expect(params.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow)).toBe('history');
    expect(params.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId)).toBe('88');
  });

  it('maps runFlow=task with a runFlowTaskId onto the tasks segment', () => {
    const params = new URLSearchParams(
      `${REPORT_ROUTE_QUERY_KEYS.runFlow}=task&${REPORT_ROUTE_QUERY_KEYS.runFlowTaskId}=t-4`,
    );
    mapLegacyHomeAnalysisSearchParams(params);
    expect(params.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment))
      .toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks);
    expect(params.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow)).toBe('task');
    expect(params.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowTaskId)).toBe('t-4');
  });

  it('preserves foreign params alongside the mapped state', () => {
    const params = new URLSearchParams(
      `utm=nav&${REPORT_ROUTE_QUERY_KEYS.recordId}=5`,
    );
    mapLegacyHomeAnalysisSearchParams(params);
    expect(params.get('utm')).toBe('nav');
    expect(params.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId)).toBe('5');
  });
});

describe('buildAnalysisWorkbenchHref', () => {
  it('returns the bare path when no options are provided', () => {
    expect(buildAnalysisWorkbenchHref()).toBe(APP_ROUTE_PATHS.researchAnalysis);
  });

  it('writes segment/recordId/runFlow options when supplied', () => {
    expect(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      recordId: 33,
    })).toBe(`${APP_ROUTE_PATHS.researchAnalysis}?segment=history&recordId=33`);
  });

  it('drops a nullish or non-positive recordId from the href', () => {
    expect(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      recordId: 0,
    })).toBe(`${APP_ROUTE_PATHS.researchAnalysis}?segment=history`);
  });

  it('serializes runFlow=task with runFlowTaskId', () => {
    expect(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
      runFlow: 'task',
      runFlowTaskId: 't-77',
    })).toBe(`${APP_ROUTE_PATHS.researchAnalysis}?segment=tasks&runFlow=task&runFlowTaskId=t-77`);
  });
});
