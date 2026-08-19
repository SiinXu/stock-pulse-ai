// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { createParsedApiError } from '../../api/error';
import { ANALYSIS_WORKBENCH_SEGMENT_VALUES } from '../../routing/routes';
import type { TaskInfo } from '../../types/analysis';
import { useAnalysisWorkbenchErrorContract } from '../useAnalysisWorkbenchErrorContract';

const runningTask: TaskInfo = {
  taskId: 'task-live',
  stockCode: 'AAPL',
  status: 'processing',
  progress: 40,
  reportType: 'brief',
  createdAt: '2026-08-19T00:00:00.000Z',
};

describe('useAnalysisWorkbenchErrorContract', () => {
  it('blocks launch and attaches the existing task from the shared assistant', () => {
    const openTaskRunFlow = vi.fn();
    const selectSegment = vi.fn();
    const { result } = renderHook(() => useAnalysisWorkbenchErrorContract({
      duplicateError: null,
      duplicateTask: null,
      error: createParsedApiError({
        title: 'busy',
        message: 'busy',
        code: 'duplicate_task',
        status: 409,
        params: { existing_task_id: 'task-live' },
      }),
      analysisTasks: [runningTask],
      openTaskRunFlow,
      selectSegment,
    }));

    expect(result.current.launchBlockedByBusy).toBe(true);
    expect(result.current.errorRecovery.kind).toBe('attach_or_view_tasks');
    result.current.openBusyTasks();
    expect(openTaskRunFlow).toHaveBeenCalledWith(runningTask);
    expect(selectSegment).not.toHaveBeenCalled();
  });

  it('blocks scheduler_busy without treating it as an attachable task', () => {
    const { result } = renderHook(() => useAnalysisWorkbenchErrorContract({
      duplicateError: null,
      duplicateTask: null,
      error: createParsedApiError({
        title: 'busy',
        message: 'busy',
        code: 'scheduler_busy',
        status: 409,
      }),
      analysisTasks: [runningTask],
      openTaskRunFlow: vi.fn(),
      selectSegment: vi.fn(),
    }));

    expect(result.current.launchBlockedByBusy).toBe(true);
    expect(result.current.errorRecovery.kind).toBe('wait_and_dismiss');
    expect(result.current.errorRecovery.existingTaskId).toBeNull();
  });

  it('does not block a non-busy validation error', () => {
    const { result } = renderHook(() => useAnalysisWorkbenchErrorContract({
      duplicateError: null,
      duplicateTask: null,
      error: createParsedApiError({
        title: 'invalid',
        message: 'invalid',
        code: 'validation_error',
        status: 422,
      }),
      analysisTasks: [],
      openTaskRunFlow: vi.fn(),
      selectSegment: vi.fn(),
    }));

    expect(result.current.launchBlockedByBusy).toBe(false);
    expect(result.current.errorRecovery.kind).toBe('none');
    result.current.openBusyTasks();
    expect(result.current.errorRecovery.existingTaskId).toBeNull();
  });

  it('falls back to the tasks segment when the attachable id is not loaded', () => {
    const selectSegment = vi.fn();
    const { result } = renderHook(() => useAnalysisWorkbenchErrorContract({
      duplicateError: createParsedApiError({
        title: 'busy',
        message: 'busy',
        code: 'duplicate_task',
        status: 409,
      }),
      duplicateTask: { stockCode: 'AAPL', existingTaskId: 'missing' },
      error: null,
      analysisTasks: [runningTask],
      openTaskRunFlow: vi.fn(),
      selectSegment,
    }));

    result.current.openBusyTasks();
    expect(selectSegment).toHaveBeenCalledWith(ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks);
  });
});
