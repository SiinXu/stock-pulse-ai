// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, renderHook, waitFor } from '@testing-library/react';
import type { SetURLSearchParams } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApiError, createParsedApiError } from '../../../api/error';
import {
  PORTFOLIO_ANALYSIS_TASK_QUERY_KEY,
  PORTFOLIO_ANALYSIS_TASK_SESSION_KEY,
  persistPortfolioAnalysisTasks,
  readPersistedPortfolioAnalysisTasks,
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

function authorizationError(status: 401 | 403) {
  return createApiError(
    createParsedApiError({
      title: status === 401 ? '未登录' : '无权限',
      message: status === 401 ? '请先登录。' : '当前账号无权访问。',
      status,
      category: 'http_error',
      code: status === 401 ? 'unauthorized' : 'forbidden',
    }),
  );
}

function createSearchParamsHarness(initial: string) {
  let current = new URLSearchParams(initial);
  const setSearchParams: SetURLSearchParams = vi.fn((nextInit) => {
    const resolved = typeof nextInit === 'function' ? nextInit(current) : nextInit;
    current = new URLSearchParams(resolved);
  });
  return {
    setSearchParams,
    current: () => current,
  };
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
    getStatus.mockResolvedValue({
      taskId: 'task-restored',
      status: 'completed',
      progress: 100,
      result: {
        stockCode: 'HK00700',
        stockName: 'Tencent',
        createdAt: '2026-03-18T00:00:00.000Z',
        report: {
          meta: {
            id: 73,
            stockCode: 'HK00700',
            stockName: 'Tencent',
            reportType: 'detailed',
            createdAt: '2026-03-18T00:00:00.000Z',
          },
        },
      },
    });

    const setSearchParams = vi.fn();
    const { result } = renderHook(() => usePortfolioAnalysisTasks({
      searchParams: new URLSearchParams(),
      setSearchParams,
    }));

    await waitFor(() => {
      expect(result.current.tasks[0]).toMatchObject({
        taskId: 'task-restored',
        stockCode: 'HK00700',
        stockName: 'Tencent',
        status: 'completed',
        resultRecordId: 73,
      });
    });
    await waitFor(() => {
      expect(window.sessionStorage.getItem(PORTFOLIO_ANALYSIS_TASK_SESSION_KEY)).toContain(
        '"resultRecordId":73',
      );
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

    const search = createSearchParamsHarness(
      `${PORTFOLIO_ANALYSIS_TASK_QUERY_KEY}=dead-task&keep=yes`,
    );
    const { result } = renderHook(() => usePortfolioAnalysisTasks({
      searchParams: new URLSearchParams(`${PORTFOLIO_ANALYSIS_TASK_QUERY_KEY}=dead-task`),
      setSearchParams: search.setSearchParams,
    }));

    await waitFor(() => {
      expect(getStatus).toHaveBeenCalledWith('dead-task');
    });
    await waitFor(() => {
      expect(result.current.tasks).toHaveLength(0);
    });
    await waitFor(() => {
      expect(window.sessionStorage.getItem(PORTFOLIO_ANALYSIS_TASK_SESSION_KEY)).toBeNull();
      expect(search.setSearchParams).toHaveBeenCalled();
    });
    // URL ?task= cleared via applyPortfolioAnalysisTaskToSearch(..., null)
    expect(search.current().get(PORTFOLIO_ANALYSIS_TASK_QUERY_KEY)).toBeNull();
    expect(search.current().get('keep')).toBe('yes');
  });

  it.each([401, 403] as const)(
    'preserves task, stock, and result identity when restore returns %s',
    async (status) => {
      persistPortfolioAnalysisTasks([{
        taskId: 'protected-task',
        stockCode: 'AAPL',
        analysisPhase: 'postmarket',
        resultRecordId: 88,
      }]);
      getStatus.mockRejectedValue(authorizationError(status));
      const search = createSearchParamsHarness('task=protected-task&keep=yes');

      const { result } = renderHook(() => usePortfolioAnalysisTasks({
        searchParams: new URLSearchParams('task=protected-task&keep=yes'),
        setSearchParams: search.setSearchParams,
      }));

      await waitFor(() => {
        expect(result.current.tasks).toHaveLength(1);
      });
      expect(result.current.tasks[0]).toMatchObject({
        taskId: 'protected-task',
        stockCode: 'AAPL',
        analysisPhase: 'postmarket',
        resultRecordId: 88,
      });
      expect(readPersistedPortfolioAnalysisTasks()[0]).toMatchObject({
        taskId: 'protected-task',
        stockCode: 'AAPL',
        resultRecordId: 88,
      });
      expect(search.current().get(PORTFOLIO_ANALYSIS_TASK_QUERY_KEY)).toBe('protected-task');
      expect(search.current().get('keep')).toBe('yes');
    },
  );

  it('reacts to a task id introduced into the URL after hydration', async () => {
    getStatus.mockImplementation(async (taskId: string) => ({
      taskId,
      status: 'processing',
      progress: 35,
      originalQuery: 'MSFT',
    }));
    const setSearchParams = vi.fn();
    const { result, rerender } = renderHook(
      ({ search }: { search: string }) => usePortfolioAnalysisTasks({
        searchParams: new URLSearchParams(search),
        setSearchParams,
      }),
      { initialProps: { search: '' } },
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    rerender({ search: 'task=route-task&keep=yes' });

    await waitFor(() => {
      expect(getStatus).toHaveBeenCalledWith('route-task');
    });
    await waitFor(() => {
      expect(result.current.tasks[0]).toMatchObject({
        taskId: 'route-task',
        stockCode: 'MSFT',
        status: 'processing',
      });
    });
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
    await waitFor(() => {
      expect(window.sessionStorage.getItem(PORTFOLIO_ANALYSIS_TASK_SESSION_KEY)).toBeNull();
    });
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
