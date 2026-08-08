// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
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
});
