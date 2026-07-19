// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  clearHomeRunFlow,
  parseHomeUrlState,
  setHomeHistoryRunFlow,
  setHomeRecord,
  setHomeTaskRunFlow,
} from '../homeUrlState';

describe('homeUrlState', () => {
  it('parses a canonical report and history Run Flow deep link', () => {
    expect(parseHomeUrlState('?recordId=42&runFlow=history&runFlowRecordId=42')).toMatchObject({
      recordId: 42,
      runFlow: { type: 'history', recordId: 42 },
      normalizedSearch: '?recordId=42&runFlow=history&runFlowRecordId=42',
      needsNormalization: false,
    });
  });

  it('parses a stable task Run Flow identity without treating display text as state', () => {
    expect(parseHomeUrlState('?runFlow=task&runFlowTaskId=task_01%3Aus-east.2')).toMatchObject({
      recordId: null,
      runFlow: { type: 'task', taskId: 'task_01:us-east.2' },
      needsNormalization: false,
    });
  });

  it('removes invalid core identities while preserving unrelated query parameters', () => {
    const parsed = parseHomeUrlState(
      '?keep=one&recordId=0&runFlow=task&runFlowTaskId=%20&runFlowRecordId=9&keep=two',
    );

    expect(parsed.recordId).toBeNull();
    expect(parsed.runFlow).toBeNull();
    expect(parsed.invalidRecordId).toBe(true);
    expect(parsed.invalidRunFlow).toBe(true);
    expect(parsed.needsNormalization).toBe(true);
    expect(parsed.normalizedSearch).toBe('?keep=one&keep=two');
  });

  it('normalizes duplicate and cross-kind Run Flow parameters to one source', () => {
    const parsed = parseHomeUrlState(
      '?runFlow=history&runFlowRecordId=07&runFlowRecordId=8&runFlowTaskId=task-1&x=1',
    );

    expect(parsed.runFlow).toEqual({ type: 'history', recordId: 7 });
    expect(parsed.normalizedSearch).toBe('?runFlow=history&runFlowRecordId=7&x=1');
    expect(parsed.needsNormalization).toBe(true);
  });

  it('updates only the report identity and preserves Run Flow plus unrelated state', () => {
    expect(setHomeRecord('?tab=history&runFlow=task&runFlowTaskId=task-1', 9)).toBe(
      '?tab=history&runFlow=task&runFlowTaskId=task-1&recordId=9',
    );
  });

  it('switches between task and history Run Flow without retaining stale identities', () => {
    const taskSearch = setHomeTaskRunFlow('?recordId=3&filter=open', 'task-2');
    expect(taskSearch).toBe('?recordId=3&filter=open&runFlow=task&runFlowTaskId=task-2');

    const historySearch = setHomeHistoryRunFlow(taskSearch, 3);
    expect(historySearch).toBe('?recordId=3&filter=open&runFlow=history&runFlowRecordId=3');
  });

  it('closes Run Flow without clearing the report or unrelated parameters', () => {
    expect(
      clearHomeRunFlow('?recordId=3&runFlow=history&runFlowRecordId=3&filter=open'),
    ).toBe('?recordId=3&filter=open');
  });
});
