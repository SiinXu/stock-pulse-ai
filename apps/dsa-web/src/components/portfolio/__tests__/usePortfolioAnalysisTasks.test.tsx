// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApiError, createParsedApiError } from '../../../api/error';
import {
  PORTFOLIO_ANALYSIS_TASK_QUERY_KEY,
  PORTFOLIO_ANALYSIS_TASK_SESSION_KEY,
  persistPortfolioAnalysisTasks,
} from '../portfolioAnalysisTaskState';
import { usePortfolioAnalysisTasks } from '../usePortfolioAnalysisTasks';

const getStatus = vi.fn();
const getTasks = vi.fn();

vi.mock('../../../api/analysis', () => ({
  analysisApi: {
    getStatus: (...args: unknown[]) => getStatus(...args),
    getTasks: (...args: unknown[]) => getTasks(...args),
    getTaskStreamUrl: () => '/api/v1/analysis/tasks/stream',
  },
}));

vi.mock('../../../hooks/useTaskStream', () => ({
  useTaskStream: () => ({
    isConnected: false,
    reconnect: () => undefined,
    disconnect: () => undefined,
  }),
}));

function notFoundError(taskId: string) {
  return createApiError(
    createParsedApiError({
      title: '未找到',
      message: `任务 ${taskId} 不存在或已过期`,
      status: 404,
      category: 'http_error',
      code: 'not_found',
    }),
  );
}

function timeoutError() {
  return createApiError(
    createParsedApiError({
      title: '上游服务响应超时',
      message: '请稍后重试，或检查网络和代理设置。',
      status: 504,
      category: 'upstream_timeout',
      code: 'upstream_timeout',
    }),
  );
}

describe('usePortfolioAnalysisTasks', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    getStatus.mockReset();
    getTasks.mockReset();
    getTasks.mockResolvedValue({ total: 0, pending: 0, processing: 0, tasks: [] });
    getStatus.mockResolvedValue({
      taskId: 'task-restored',
      status: 'processing',
      progress: 40,
      message: 'running',
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('accepts a submitted task and tracks it in the panel state', async () => {
    const setSearchParams = vi.fn();
    const { result } = renderHook(() => usePortfolioAnalysisTasks({
      searchParams: new URLSearchParams(),
      setSearchParams,
    }));

    act(() => {
      result.current.acceptTask({
        taskId: 'task-new-1',
        status: 'pending',
        message: 'queued',
        analysisPhase: 'auto',
      }, 'AAPL', 'auto');
    });

    expect(result.current.tasks).toHaveLength(1);
    expect(result.current.tasks[0]).toMatchObject({
      taskId: 'task-new-1',
      stockCode: 'AAPL',
      status: 'pending',
    });
    expect(window.sessionStorage.getItem(PORTFOLIO_ANALYSIS_TASK_SESSION_KEY)).toContain('task-new-1');
    expect(setSearchParams).toHaveBeenCalled();
  });

  it('restores a successful task from session storage on mount', async () => {
    persistPortfolioAnalysisTasks([
      { taskId: 'task-restored', stockCode: 'HK00700', analysisPhase: 'auto' },
    ]);
    getTasks.mockResolvedValue({
      total: 1,
      pending: 0,
      processing: 0,
      tasks: [{
        taskId: 'task-restored',
        stockCode: 'HK00700',
        status: 'completed',
        progress: 100,
        reportType: 'detailed',
        createdAt: '2026-03-18T00:00:00.000Z',
      }],
    });

    const setSearchParams = vi.fn();
    const { result } = renderHook(() => usePortfolioAnalysisTasks({
      searchParams: new URLSearchParams(),
      setSearchParams,
    }));

    await waitFor(() => {
      expect(result.current.tasks).toHaveLength(1);
    });
    expect(result.current.tasks[0]).toMatchObject({
      taskId: 'task-restored',
      stockCode: 'HK00700',
      status: 'completed',
    });
  });

  it('dismisses a terminal task and clears tracking', async () => {
    const setSearchParams = vi.fn();
    const { result } = renderHook(() => usePortfolioAnalysisTasks({
      searchParams: new URLSearchParams(),
      setSearchParams,
    }));

    act(() => {
      result.current.acceptTask({
        taskId: 'task-dismiss',
        status: 'pending',
      }, 'MSFT', 'auto');
    });
    expect(result.current.tasks).toHaveLength(1);

    act(() => {
      result.current.dismissTask('task-dismiss');
    });
    expect(result.current.tasks).toHaveLength(0);
  });

  it('drops an unrecoverable 404 restore and clears session persistence', async () => {
    persistPortfolioAnalysisTasks([
      { taskId: 'dead-task', stockCode: 'AAPL' },
    ]);
    getTasks.mockResolvedValue({ total: 0, pending: 0, processing: 0, tasks: [] });
    getStatus.mockRejectedValue(notFoundError('dead-task'));

    const setSearchParams = vi.fn();
    const { result } = renderHook(() => usePortfolioAnalysisTasks({
      searchParams: new URLSearchParams(`${PORTFOLIO_ANALYSIS_TASK_QUERY_KEY}=dead-task`),
      setSearchParams,
    }));

    await waitFor(() => {
      expect(getStatus).toHaveBeenCalledWith('dead-task');
    });
    await waitFor(() => {
      expect(result.current.tasks).toHaveLength(0);
    });
    expect(window.sessionStorage.getItem(PORTFOLIO_ANALYSIS_TASK_SESSION_KEY)).toBeNull();
    // URL ?task= cleared via applyPortfolioAnalysisTaskToSearch(..., null)
    expect(setSearchParams).toHaveBeenCalled();
    const lastSearch = setSearchParams.mock.calls.at(-1)?.[0] as URLSearchParams;
    expect(lastSearch.get(PORTFOLIO_ANALYSIS_TASK_QUERY_KEY)).toBeNull();
  });

  it('keeps a recoverable getStatus failure tracked without clearing persistence', async () => {
    persistPortfolioAnalysisTasks([
      { taskId: 'flaky-task', stockCode: 'AAPL', analysisPhase: 'auto' },
    ]);
    getTasks.mockResolvedValue({ total: 0, pending: 0, processing: 0, tasks: [] });
    getStatus.mockRejectedValue(timeoutError());

    const setSearchParams = vi.fn();
    const { result } = renderHook(() => usePortfolioAnalysisTasks({
      searchParams: new URLSearchParams(),
      setSearchParams,
    }));

    await waitFor(() => {
      expect(result.current.tasks).toHaveLength(1);
    });
    expect(result.current.tasks[0]).toMatchObject({
      taskId: 'flaky-task',
      stockCode: 'AAPL',
      status: 'pending',
    });
    expect(window.sessionStorage.getItem(PORTFOLIO_ANALYSIS_TASK_SESSION_KEY)).toContain('flaky-task');
  });

  it('drops a task when getStatus resolves without taskId/status', async () => {
    persistPortfolioAnalysisTasks([
      { taskId: 'empty-body-task', stockCode: 'TSLA' },
    ]);
    getTasks.mockResolvedValue({ total: 0, pending: 0, processing: 0, tasks: [] });
    getStatus.mockResolvedValue({} as never);

    const { result } = renderHook(() => usePortfolioAnalysisTasks({
      searchParams: new URLSearchParams(),
      setSearchParams: vi.fn(),
    }));

    await waitFor(() => {
      expect(getStatus).toHaveBeenCalledWith('empty-body-task');
    });
    await waitFor(() => {
      expect(result.current.tasks).toHaveLength(0);
    });
    expect(window.sessionStorage.getItem(PORTFOLIO_ANALYSIS_TASK_SESSION_KEY)).toBeNull();
  });

  it('poll drops unrecoverable 404 and clears persistence; recoverable keeps last state', async () => {
    vi.useFakeTimers();
    getTasks.mockResolvedValue({ total: 0, pending: 0, processing: 0, tasks: [] });
    // Avoid hydration attach; accept the task after mount.
    getStatus.mockResolvedValue({
      taskId: 'poll-task',
      status: 'processing',
      progress: 25,
      message: 'running',
    });

    const setSearchParams = vi.fn();
    const { result } = renderHook(() => usePortfolioAnalysisTasks({
      searchParams: new URLSearchParams(),
      setSearchParams,
    }));

    // Empty hydration (async IIFE) under fake timers still resolves via microtasks.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    act(() => {
      result.current.acceptTask({
        taskId: 'poll-task',
        status: 'processing',
        message: 'running',
        analysisPhase: 'auto',
      }, 'NVDA', 'auto');
    });
    expect(result.current.tasks).toHaveLength(1);
    expect(window.sessionStorage.getItem(PORTFOLIO_ANALYSIS_TASK_SESSION_KEY)).toContain('poll-task');

    // Recoverable poll failure: keep last known state.
    getStatus.mockClear();
    getStatus.mockRejectedValue(timeoutError());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_100);
    });
    expect(getStatus).toHaveBeenCalledWith('poll-task');
    expect(result.current.tasks).toHaveLength(1);
    expect(result.current.tasks[0]?.taskId).toBe('poll-task');
    expect(window.sessionStorage.getItem(PORTFOLIO_ANALYSIS_TASK_SESSION_KEY)).toContain('poll-task');

    // Unrecoverable poll failure: drop task + persistence.
    getStatus.mockClear();
    getStatus.mockRejectedValue(notFoundError('poll-task'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_100);
    });
    expect(result.current.tasks).toHaveLength(0);
    expect(window.sessionStorage.getItem(PORTFOLIO_ANALYSIS_TASK_SESSION_KEY)).toBeNull();
  });
});
