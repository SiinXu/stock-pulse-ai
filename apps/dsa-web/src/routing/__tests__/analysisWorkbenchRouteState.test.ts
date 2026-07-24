// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';

import {
  ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS,
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  APP_ROUTE_PATHS,
  HOME_ROUTE_QUERY_KEYS,
  RUN_FLOW_ROUTE_QUERY_VALUES,
  buildAnalysisWorkbenchHref,
} from '../routes';
import {
  DEFAULT_ANALYSIS_WORKBENCH_ROUTE_STATE,
  parseAnalysisWorkbenchRouteState,
  setAnalysisWorkbenchRouteState,
} from '../analysisWorkbenchRouteState';

function query(entries: Record<string, string>): string {
  return new URLSearchParams(entries).toString();
}

function expectedWorkbenchHref(entries: Record<string, string>): string {
  const search = query(entries);
  return search ? `${APP_ROUTE_PATHS.researchAnalysis}?${search}` : APP_ROUTE_PATHS.researchAnalysis;
}

describe('parseAnalysisWorkbenchRouteState', () => {
  it('returns the launch default when the search is empty', () => {
    const parsed = parseAnalysisWorkbenchRouteState('');
    expect(parsed.state).toEqual(DEFAULT_ANALYSIS_WORKBENCH_ROUTE_STATE);
    expect(parsed.invalidKeys).toEqual([]);
    expect(parsed.normalizedParams.toString()).toBe('');
  });

  it('accepts each explicit segment value', () => {
    for (const segment of Object.values(ANALYSIS_WORKBENCH_SEGMENT_VALUES)) {
      const parsed = parseAnalysisWorkbenchRouteState(query({
        [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: segment,
      }));
      expect(parsed.state.segment).toBe(segment);
      expect(parsed.invalidKeys).toEqual([]);
    }
  });

  it('normalizes an explicit launch segment to the single bare encoding', () => {
    const parsed = parseAnalysisWorkbenchRouteState(query({
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch,
    }));
    expect(parsed.state.segment).toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch);
    expect(parsed.normalizedParams.toString()).toBe('');
  });

  it('falls back to the launch default and records an invalid key for an unknown segment', () => {
    const parsed = parseAnalysisWorkbenchRouteState(query({
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: 'nope',
    }));
    expect(parsed.state.segment).toBe(DEFAULT_ANALYSIS_WORKBENCH_ROUTE_STATE.segment);
    expect(parsed.invalidKeys).toContain(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment);
  });

  it('lands on the history segment when only recordId is provided', () => {
    const parsed = parseAnalysisWorkbenchRouteState(query({
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId]: '42',
    }));
    expect(parsed.state.segment).toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.history);
    expect(parsed.state.recordId).toBe(42);
    expect(parsed.invalidKeys).toEqual([]);
  });

  it('lands on the history segment when a history RunFlow is provided without a segment', () => {
    const parsed = parseAnalysisWorkbenchRouteState(query({
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow]: RUN_FLOW_ROUTE_QUERY_VALUES.history,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId]: '7',
    }));
    expect(parsed.state.segment).toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.history);
    expect(parsed.state.runFlow).toBe(RUN_FLOW_ROUTE_QUERY_VALUES.history);
    expect(parsed.state.runFlowRecordId).toBe(7);
    expect(parsed.state.runFlowTaskId).toBeNull();
  });

  it('lands on the tasks segment when a task RunFlow is provided without a segment', () => {
    const parsed = parseAnalysisWorkbenchRouteState(query({
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow]: RUN_FLOW_ROUTE_QUERY_VALUES.task,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowTaskId]: 'abc',
    }));
    expect(parsed.state.segment).toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks);
    expect(parsed.state.runFlow).toBe(RUN_FLOW_ROUTE_QUERY_VALUES.task);
    expect(parsed.state.runFlowRecordId).toBeNull();
    expect(parsed.state.runFlowTaskId).toBe('abc');
  });

  it('strips a record intent that conflicts with the explicit launch segment', () => {
    const parsed = parseAnalysisWorkbenchRouteState(query({
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId]: '9',
    }));
    expect(parsed.state.segment).toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch);
    expect(parsed.state.recordId).toBeNull();
    expect(parsed.invalidKeys).toContain(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId);
    expect(parsed.normalizedParams.toString()).toBe('');
    expect(parseAnalysisWorkbenchRouteState(parsed.normalizedParams).state)
      .toEqual(parsed.state);
  });

  it('rejects non-positive-integer recordId values', () => {
    for (const bad of ['-1', '0', 'abc', '3.5', '1e3', '9007199254740992', '  ']) {
      const parsed = parseAnalysisWorkbenchRouteState(query({
        [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId]: bad,
      }));
      expect(parsed.state.recordId).toBeNull();
      expect(parsed.invalidKeys).toContain(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId);
    }
  });

  it('rejects an unrecognized runFlow value', () => {
    const parsed = parseAnalysisWorkbenchRouteState(query({
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow]: 'other',
    }));
    expect(parsed.state.runFlow).toBeNull();
    expect(parsed.invalidKeys).toContain(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow);
  });

  it('drops runFlowTaskId when runFlow is history and drops runFlowRecordId when runFlow is task', () => {
    const parsedHistory = parseAnalysisWorkbenchRouteState(query({
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow]: RUN_FLOW_ROUTE_QUERY_VALUES.history,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId]: '3',
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowTaskId]: 'leftover',
    }));
    expect(parsedHistory.state.runFlowRecordId).toBe(3);
    expect(parsedHistory.state.runFlowTaskId).toBeNull();

    const parsedTask = parseAnalysisWorkbenchRouteState(query({
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow]: RUN_FLOW_ROUTE_QUERY_VALUES.task,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowTaskId]: 'xyz',
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId]: '99',
    }));
    expect(parsedTask.state.runFlowRecordId).toBeNull();
    expect(parsedTask.state.runFlowTaskId).toBe('xyz');
  });

  it('rejects incomplete or unstable run-flow identities', () => {
    const missingHistoryId = parseAnalysisWorkbenchRouteState(query({
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow]: RUN_FLOW_ROUTE_QUERY_VALUES.history,
    }));
    expect(missingHistoryId.state.runFlow).toBeNull();
    expect(missingHistoryId.invalidKeys).toContain(
      ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId,
    );

    const unsafeTaskId = parseAnalysisWorkbenchRouteState(query({
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow]: RUN_FLOW_ROUTE_QUERY_VALUES.task,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowTaskId]: '<script>',
    }));
    expect(unsafeTaskId.state.runFlow).toBeNull();
    expect(unsafeTaskId.invalidKeys).toContain(
      ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowTaskId,
    );
  });

  it('rejects exponent and unsafe history RunFlow record identities', () => {
    for (const bad of ['1e3', '9007199254740992']) {
      const parsed = parseAnalysisWorkbenchRouteState(query({
        [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow]: RUN_FLOW_ROUTE_QUERY_VALUES.history,
        [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId]: bad,
      }));
      expect(parsed.state.runFlow).toBeNull();
      expect(parsed.invalidKeys).toContain(
        ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId,
      );
    }
  });

  it('preserves foreign search params in the normalized copy', () => {
    const parsed = parseAnalysisWorkbenchRouteState(query({
      utm: 'source',
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
    }));
    expect(parsed.normalizedParams.get('utm')).toBe('source');
    expect(parsed.normalizedParams.get(
      ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment,
    )).toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks);
    expect(parsed.ownedParams.toString()).toBe(query({
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
    }));
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
      query({
        [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch,
        [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId]: '1',
        [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow]: RUN_FLOW_ROUTE_QUERY_VALUES.history,
        [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId]: '2',
      }),
      {
        segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
        recordId: null,
        runFlow: RUN_FLOW_ROUTE_QUERY_VALUES.task,
        runFlowRecordId: null,
        runFlowTaskId: 't-9',
      },
    );
    expect(next.getAll(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment)).toEqual([
      ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
    ]);
    expect(next.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId)).toBeNull();
    expect(next.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow))
      .toBe(RUN_FLOW_ROUTE_QUERY_VALUES.task);
    expect(next.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId)).toBeNull();
    expect(next.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowTaskId)).toBe('t-9');
  });
});

describe('buildAnalysisWorkbenchHref', () => {
  it('returns the bare path when no options are provided', () => {
    expect(buildAnalysisWorkbenchHref()).toBe(APP_ROUTE_PATHS.researchAnalysis);
    expect(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch,
    })).toBe(APP_ROUTE_PATHS.researchAnalysis);
  });

  it('drops report context that conflicts with an explicit launch segment', () => {
    expect(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch,
      recordId: 9,
      runFlow: RUN_FLOW_ROUTE_QUERY_VALUES.history,
      runFlowRecordId: 9,
    })).toBe(APP_ROUTE_PATHS.researchAnalysis);
  });

  it('writes segment/recordId/runFlow options when supplied', () => {
    expect(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      recordId: 33,
    })).toBe(expectedWorkbenchHref({
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId]: '33',
    }));
  });

  it('drops a nullish or non-positive recordId from the href', () => {
    expect(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      recordId: 0,
    })).toBe(expectedWorkbenchHref({
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
    }));
  });

  it('serializes a task RunFlow with its task identity', () => {
    expect(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
      runFlow: RUN_FLOW_ROUTE_QUERY_VALUES.task,
      runFlowTaskId: 't-77',
    })).toBe(expectedWorkbenchHref({
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow]: RUN_FLOW_ROUTE_QUERY_VALUES.task,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowTaskId]: 't-77',
    }));
  });

  it('preserves stock context in a report deep link', () => {
    expect(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      recordId: 33,
      runFlow: RUN_FLOW_ROUTE_QUERY_VALUES.history,
      runFlowRecordId: 33,
      stock: ' AAPL ',
    })).toBe(expectedWorkbenchHref({
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment]: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId]: '33',
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow]: RUN_FLOW_ROUTE_QUERY_VALUES.history,
      [ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId]: '33',
      [HOME_ROUTE_QUERY_KEYS.stock]: 'AAPL',
    }));
  });

  it('uses the same canonical encoding as the parser and setter', () => {
    const href = buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch,
    });
    const url = new URL(href, 'http://stockpulse.local');
    const parsed = parseAnalysisWorkbenchRouteState(url.search);
    const serialized = setAnalysisWorkbenchRouteState('', parsed.state).toString();
    expect(serialized).toBe(url.searchParams.toString());
  });
});
