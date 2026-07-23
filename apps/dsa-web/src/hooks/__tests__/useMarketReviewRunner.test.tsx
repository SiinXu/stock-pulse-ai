// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { analysisApi } from '../../api/analysis';
import type { HistoryListResponse } from '../../types/analysis';
import {
  MARKET_REVIEW_POLL_INTERVAL_MS,
  MARKET_REVIEW_POLL_MAX_ATTEMPTS,
  useMarketReviewRunner,
} from '../useMarketReviewRunner';

vi.mock('../../api/analysis', async () => {
  const actual = await vi.importActual<typeof import('../../api/analysis')>('../../api/analysis');
  return {
    ...actual,
    analysisApi: {
      ...actual.analysisApi,
      triggerMarketReview: vi.fn(),
      getStatus: vi.fn(),
    },
  };
});

const emptyHistory: HistoryListResponse = {
  total: 0,
  page: 1,
  limit: 10,
  items: [],
};

const persistedHistory: HistoryListResponse = {
  total: 1,
  page: 1,
  limit: 10,
  items: [{
    id: 42,
    queryId: 'market-task',
    stockCode: 'MARKET',
    stockName: '大盘复盘',
    reportType: 'market_review',
    createdAt: '2026-07-22T08:00:00Z',
  }],
};

describe('useMarketReviewRunner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it('polls serially and selects only the matching persisted report', async () => {
    vi.mocked(analysisApi.triggerMarketReview).mockResolvedValue({
      status: 'accepted',
      sendNotification: true,
      message: '大盘复盘任务已提交',
      taskId: 'market-task',
    });
    vi.mocked(analysisApi.getStatus)
      .mockResolvedValueOnce({
        taskId: 'market-task',
        status: 'processing',
        progress: 60,
      })
      .mockResolvedValueOnce({
        taskId: 'market-task',
        status: 'completed',
        marketReviewReport: 'RAW_TASK_OUTPUT_MUST_NOT_RENDER',
      });
    const refreshMarketReviewHistory = vi.fn().mockResolvedValue(persistedHistory);
    const onPersistedReport = vi.fn();
    const onFeedback = vi.fn();
    const { result } = renderHook(() => useMarketReviewRunner({
      notify: true,
      refreshMarketReviewHistory,
      onPersistedReport,
      onFeedback,
    }));

    await act(async () => {
      await result.current.triggerMarketReview();
    });
    expect(analysisApi.triggerMarketReview).toHaveBeenCalledWith({ sendNotification: true });
    expect(analysisApi.getStatus).toHaveBeenCalledTimes(1);
    expect(result.current.notice?.title).toBe('大盘复盘进行中');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(MARKET_REVIEW_POLL_INTERVAL_MS);
    });

    expect(analysisApi.getStatus).toHaveBeenCalledTimes(2);
    expect(refreshMarketReviewHistory).toHaveBeenCalledWith(true);
    expect(onPersistedReport).toHaveBeenCalledWith(42);
    expect(result.current.notice).toEqual({
      variant: 'success',
      title: '大盘复盘已完成',
      message: '大盘复盘任务已完成，结果如下：',
    });
    expect(JSON.stringify(result.current)).not.toContain('RAW_TASK_OUTPUT_MUST_NOT_RENDER');
    expect(onFeedback).toHaveBeenCalled();
  });

  it('reports completion without selecting raw task output when persistence is delayed', async () => {
    vi.mocked(analysisApi.triggerMarketReview).mockResolvedValue({
      status: 'accepted',
      sendNotification: false,
      message: 'Accepted',
      taskId: 'market-task',
    });
    vi.mocked(analysisApi.getStatus).mockResolvedValue({
      taskId: 'market-task',
      status: 'completed',
      marketReviewReport: 'RAW_TASK_OUTPUT_MUST_NOT_RENDER',
    });
    const onPersistedReport = vi.fn();
    const { result } = renderHook(() => useMarketReviewRunner({
      notify: false,
      refreshMarketReviewHistory: vi.fn().mockResolvedValue(emptyHistory),
      onPersistedReport,
    }));

    await act(async () => {
      await result.current.triggerMarketReview();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.notice?.title).toBe('大盘复盘已完成');
    expect(onPersistedReport).not.toHaveBeenCalled();
    expect(result.current.notice?.message).toBe(
      '大盘复盘任务已完成，结果已生成并按配置推送。',
    );
    expect(JSON.stringify(result.current)).not.toContain('RAW_TASK_OUTPUT_MUST_NOT_RENDER');
  });

  it('surfaces a terminal task failure and stops polling', async () => {
    vi.mocked(analysisApi.triggerMarketReview).mockResolvedValue({
      status: 'accepted',
      sendNotification: true,
      message: 'Accepted',
      taskId: 'market-task',
    });
    vi.mocked(analysisApi.getStatus).mockResolvedValue({
      taskId: 'market-task',
      status: 'failed',
      error: 'Provider unavailable',
    });
    const onFeedback = vi.fn();
    const { result } = renderHook(() => useMarketReviewRunner({
      notify: true,
      refreshMarketReviewHistory: vi.fn().mockResolvedValue(emptyHistory),
      onPersistedReport: vi.fn(),
      onFeedback,
    }));

    await act(async () => {
      await result.current.triggerMarketReview();
      await Promise.resolve();
    });

    expect(result.current.error).toMatchObject({
      code: 'market_review_failed',
      status: 500,
      rawMessage: 'Provider unavailable',
    });
    expect(result.current.notice).toBeNull();
    expect(analysisApi.getStatus).toHaveBeenCalledTimes(1);
    expect(onFeedback).toHaveBeenCalled();
  });

  it('reports a bounded timeout after the maximum polling attempts', async () => {
    vi.mocked(analysisApi.triggerMarketReview).mockResolvedValue({
      status: 'accepted',
      sendNotification: false,
      message: 'Accepted',
      taskId: 'market-task',
    });
    vi.mocked(analysisApi.getStatus).mockResolvedValue({
      taskId: 'market-task',
      status: 'processing',
      progress: 25,
    });
    const { result } = renderHook(() => useMarketReviewRunner({
      notify: false,
      refreshMarketReviewHistory: vi.fn().mockResolvedValue(emptyHistory),
      onPersistedReport: vi.fn(),
    }));

    await act(async () => {
      await result.current.triggerMarketReview();
      await vi.advanceTimersByTimeAsync(
        MARKET_REVIEW_POLL_INTERVAL_MS * MARKET_REVIEW_POLL_MAX_ATTEMPTS,
      );
    });

    expect(analysisApi.getStatus).toHaveBeenCalledTimes(MARKET_REVIEW_POLL_MAX_ATTEMPTS);
    expect(result.current.notice).toEqual({
      variant: 'danger',
      title: '大盘复盘已超时',
      message: '任务长时间未返回最终结果，请在任务列表/历史中查看。',
    });
    expect(result.current.error).toBeNull();
  });

  it('surfaces a trigger failure without starting status polling', async () => {
    vi.mocked(analysisApi.triggerMarketReview).mockRejectedValue({
      response: {
        status: 503,
        data: { error: 'market_review_unavailable', message: 'Service unavailable' },
      },
    });
    const { result } = renderHook(() => useMarketReviewRunner({
      notify: true,
      refreshMarketReviewHistory: vi.fn().mockResolvedValue(emptyHistory),
      onPersistedReport: vi.fn(),
    }));

    await act(async () => {
      await result.current.triggerMarketReview();
    });

    expect(result.current.error).toMatchObject({
      code: 'market_review_unavailable',
      status: 503,
      rawMessage: 'Service unavailable',
    });
    expect(result.current.notice).toBeNull();
    expect(analysisApi.getStatus).not.toHaveBeenCalled();
  });

  it('ignores a superseded poll result after a newer run completes', async () => {
    vi.mocked(analysisApi.triggerMarketReview)
      .mockResolvedValueOnce({
        status: 'accepted',
        sendNotification: true,
        message: 'Old accepted',
        taskId: 'old-task',
      })
      .mockResolvedValueOnce({
        status: 'accepted',
        sendNotification: true,
        message: 'New accepted',
        taskId: 'market-task',
      });
    let resolveOldStatus!: (value: Awaited<ReturnType<typeof analysisApi.getStatus>>) => void;
    const oldStatus = new Promise<Awaited<ReturnType<typeof analysisApi.getStatus>>>((resolve) => {
      resolveOldStatus = resolve;
    });
    vi.mocked(analysisApi.getStatus).mockImplementation((taskId) => (
      taskId === 'old-task'
        ? oldStatus
        : Promise.resolve({ taskId, status: 'completed' })
    ));
    const refreshMarketReviewHistory = vi.fn().mockResolvedValue(persistedHistory);
    const onPersistedReport = vi.fn();
    const { result } = renderHook(() => useMarketReviewRunner({
      notify: true,
      refreshMarketReviewHistory,
      onPersistedReport,
    }));

    await act(async () => {
      await result.current.triggerMarketReview();
      await result.current.triggerMarketReview();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(onPersistedReport).toHaveBeenCalledWith(42);

    await act(async () => {
      resolveOldStatus({ taskId: 'old-task', status: 'completed' });
      await oldStatus;
    });

    expect(refreshMarketReviewHistory).toHaveBeenCalledTimes(1);
    expect(onPersistedReport).toHaveBeenCalledTimes(1);
    expect(result.current.notice?.title).toBe('大盘复盘已完成');
  });

  it('ignores an in-flight poll result after unmount', async () => {
    vi.mocked(analysisApi.triggerMarketReview).mockResolvedValue({
      status: 'accepted',
      sendNotification: true,
      message: 'Accepted',
      taskId: 'market-task',
    });
    let resolveStatus!: (value: Awaited<ReturnType<typeof analysisApi.getStatus>>) => void;
    const status = new Promise<Awaited<ReturnType<typeof analysisApi.getStatus>>>((resolve) => {
      resolveStatus = resolve;
    });
    vi.mocked(analysisApi.getStatus).mockReturnValue(status);
    const refreshMarketReviewHistory = vi.fn().mockResolvedValue(persistedHistory);
    const onPersistedReport = vi.fn();
    const { result, unmount } = renderHook(() => useMarketReviewRunner({
      notify: true,
      refreshMarketReviewHistory,
      onPersistedReport,
    }));

    await act(async () => {
      await result.current.triggerMarketReview();
    });
    unmount();
    await act(async () => {
      resolveStatus({ taskId: 'market-task', status: 'completed' });
      await status;
    });

    expect(refreshMarketReviewHistory).not.toHaveBeenCalled();
    expect(onPersistedReport).not.toHaveBeenCalled();
  });
});
