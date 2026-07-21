// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { analysisApi } from '../../api/analysis';
import { agentApi } from '../../api/agent';
import { historyApi } from '../../api/history';
import { systemConfigApi } from '../../api/systemConfig';
import { useStockPoolStore } from '../../stores/stockPoolStore';
import type { UseTaskStreamOptions } from '../../hooks/useTaskStream';
import type { AnalysisReport } from '../../types/analysis';
import type { RunFlowSnapshot } from '../../types/runFlow';
import HomePage from '../HomePage';

vi.mock('../../api/history', () => ({
  historyApi: {
    getList: vi.fn(),
    getDetail: vi.fn(),
    getNews: vi.fn().mockResolvedValue({ total: 0, items: [] }),
    getMarkdown: vi.fn().mockResolvedValue('# report'),
    getDiagnostics: vi.fn(),
    getRecordFlow: vi.fn(),
    getStockBarList: vi.fn(),
    deleteByCode: vi.fn(),
  },
}));

vi.mock('../../api/analysis', async () => {
  const actual = await vi.importActual<typeof import('../../api/analysis')>('../../api/analysis');
  return {
    ...actual,
    analysisApi: {
      analyzeAsync: vi.fn(),
      triggerMarketReview: vi.fn(),
      getStatus: vi.fn(),
      getTasks: vi.fn(),
      getTaskFlow: vi.fn(),
    },
  };
});

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getSetupStatus: vi.fn(),
    getWatchlist: vi.fn(),
  },
}));

vi.mock('../../api/agent', () => ({
  agentApi: {
    getSkills: vi.fn(),
  },
}));

const taskStreamHarness = vi.hoisted(() => ({
  dashboardOptions: null as UseTaskStreamOptions | null,
}));

vi.mock('../../hooks/useTaskStream', () => ({
  useTaskStream: vi.fn((options: UseTaskStreamOptions) => {
    if (options.onTaskCreated) {
      taskStreamHarness.dashboardOptions = options;
    }
    return {
      isConnected: true,
      reconnect: vi.fn(),
      disconnect: vi.fn(),
    };
  }),
}));

const historyItems = [
  {
    id: 1,
    queryId: 'q-1',
    stockCode: '600519',
    stockName: '贵州茅台',
    reportType: 'detailed' as const,
    sentimentScore: 78,
    operationAdvice: '观察',
    createdAt: '2026-03-18T08:00:00Z',
  },
  {
    id: 2,
    queryId: 'q-2',
    stockCode: 'AAPL',
    stockName: 'Apple',
    reportType: 'detailed' as const,
    sentimentScore: 72,
    operationAdvice: '持有',
    createdAt: '2026-03-19T08:00:00Z',
  },
];

const completedHistoryItem = {
  ...historyItems[0],
  id: 3,
  queryId: 'q-3',
  createdAt: '2026-03-20T08:00:00Z',
};

let currentHistoryItems = [...historyItems];
const defaultRefreshHistoryForCompletedTask = useStockPoolStore.getState().refreshHistoryForCompletedTask;

const reports: Record<number, AnalysisReport> = {
  1: {
    meta: {
      id: 1,
      queryId: 'q-1',
      stockCode: '600519',
      stockName: '贵州茅台',
      reportType: 'detailed',
      reportLanguage: 'zh',
      createdAt: '2026-03-18T08:00:00Z',
    },
    summary: {
      analysisSummary: '报告一摘要',
      operationAdvice: '继续观察',
      trendPrediction: '震荡',
      sentimentScore: 78,
    },
  },
  2: {
    meta: {
      id: 2,
      queryId: 'q-2',
      stockCode: 'AAPL',
      stockName: 'Apple',
      reportType: 'detailed',
      reportLanguage: 'zh',
      createdAt: '2026-03-19T08:00:00Z',
    },
    summary: {
      analysisSummary: '报告二摘要',
      operationAdvice: '继续持有',
      trendPrediction: '偏强',
      sentimentScore: 72,
    },
  },
  3: {
    meta: {
      id: 3,
      queryId: 'q-3',
      stockCode: '600519',
      stockName: '贵州茅台',
      reportType: 'detailed',
      reportLanguage: 'zh',
      createdAt: '2026-03-20T08:00:00Z',
    },
    summary: {
      analysisSummary: '任务完成后的新报告',
      operationAdvice: '继续观察',
      trendPrediction: '偏强',
      sentimentScore: 81,
    },
  },
  4: {
    meta: {
      id: 4,
      queryId: 'q-4',
      stockCode: '600519',
      stockName: '贵州茅台',
      reportType: 'detailed',
      reportLanguage: 'zh',
      createdAt: '2025-01-10T08:00:00Z',
    },
    summary: {
      analysisSummary: '未加载的旧报告',
      operationAdvice: '观察',
      trendPrediction: '震荡',
      sentimentScore: 70,
    },
  },
};

const runFlowSnapshot: RunFlowSnapshot = {
  taskId: 'task-2',
  traceId: 'trace-2',
  stockCode: 'AAPL',
  stockName: 'Apple',
  status: 'running',
  generatedAt: '2026-06-08T08:00:00Z',
  summary: {
    elapsedMs: 100,
    failedAttempts: 0,
    fallbackCount: 0,
    dataSourceCount: 0,
    eventCount: 0,
  },
  lanes: [{ id: 'entry', label: '入口', order: 1 }],
  nodes: [{ id: 'request', lane: 'entry', kind: 'entry', label: '请求', status: 'running' }],
  edges: [],
  events: [],
};

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, reject, resolve };
}

function renderHome(initialEntry: string, strictMode = false) {
  const router = createMemoryRouter(
    [
      { path: '/', element: <HomePage /> },
      { path: '/other', element: <h1>Other route</h1> },
    ],
    { initialEntries: [initialEntry] },
  );
  const content = <RouterProvider router={router} />;
  render(strictMode ? <StrictMode>{content}</StrictMode> : content);
  return router;
}

describe('HomePage URL state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    useStockPoolStore.getState().resetDashboardState();
    useStockPoolStore.setState({
      refreshHistoryForCompletedTask: defaultRefreshHistoryForCompletedTask,
    });
    taskStreamHarness.dashboardOptions = null;
    currentHistoryItems = [...historyItems];
    vi.mocked(historyApi.getList).mockImplementation((params: { reportType?: string } = {}) => Promise.resolve({
      total: params.reportType === 'market_review' ? 0 : currentHistoryItems.length,
      page: 1,
      limit: params.reportType === 'market_review' ? 10 : 20,
      items: params.reportType === 'market_review' ? [] : currentHistoryItems,
    }));
    vi.mocked(historyApi.getStockBarList).mockImplementation(() => Promise.resolve({
      total: currentHistoryItems.length,
      items: currentHistoryItems.map((item) => ({
        ...item,
        analysisCount: 1,
        lastAnalysisTime: item.createdAt,
      })),
    }));
    vi.mocked(historyApi.deleteByCode).mockImplementation((stockCode) => {
      currentHistoryItems = currentHistoryItems.filter((item) => item.stockCode !== stockCode);
      return Promise.resolve({ deleted: 1 });
    });
    vi.mocked(historyApi.getDetail).mockImplementation((recordId) => Promise.resolve(reports[recordId]));
    vi.mocked(historyApi.getDiagnostics).mockResolvedValue({
      status: 'unknown',
      statusLabel: '未知',
      reason: '暂无诊断',
      components: {},
      copyText: 'data_status: unknown',
    });
    vi.mocked(historyApi.getRecordFlow).mockResolvedValue(runFlowSnapshot);
    vi.mocked(analysisApi.getTaskFlow).mockResolvedValue(runFlowSnapshot);
    vi.mocked(analysisApi.getTasks).mockResolvedValue({
      total: 0,
      pending: 0,
      processing: 0,
      tasks: [],
    });
    vi.mocked(analysisApi.getStatus).mockRejectedValue(new Error('status not mocked'));
    vi.mocked(systemConfigApi.getWatchlist).mockResolvedValue([]);
    vi.mocked(systemConfigApi.getSetupStatus).mockResolvedValue({
      isComplete: true,
      readyForSmoke: true,
      requiredMissingKeys: [],
      nextStepKey: null,
      checks: [],
    });
    vi.mocked(agentApi.getSkills).mockResolvedValue({ skills: [], default_skill_id: '' });
  });

  it('restores a shared report deep link instead of auto-selecting the first record', async () => {
    const router = renderHome('/?recordId=2&keep=yes', true);

    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(vi.mocked(historyApi.getDetail).mock.calls.map(([recordId]) => recordId)).toEqual([2]);
    expect(router.state.location.search).toBe('?recordId=2&keep=yes');
  });

  it('refetches the URL-owned report after the mounted dashboard store resets', async () => {
    const router = renderHome('/?recordId=2&keep=yes');

    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(vi.mocked(historyApi.getDetail).mock.calls.map(([recordId]) => recordId)).toEqual([2]);

    act(() => {
      useStockPoolStore.getState().resetDashboardState();
    });

    await waitFor(() => expect(vi.mocked(historyApi.getDetail).mock.calls.map(([recordId]) => recordId))
      .toEqual([2, 2]));
    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?recordId=2&keep=yes');
  });

  it('reloads the current URL record when its selected report is absent', async () => {
    const router = renderHome('/?recordId=1&keep=yes');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    const locationKey = router.state.location.key;
    vi.mocked(historyApi.getDetail).mockClear();

    act(() => {
      useStockPoolStore.setState({
        selectedRecordId: 1,
        selectedReport: null,
      });
    });
    expect(screen.queryByText('报告一摘要')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '贵州茅台 600519 历史记录' }));

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    expect(historyApi.getDetail).toHaveBeenCalledWith(1);
    expect(router.state.location.search).toBe('?recordId=1&keep=yes');
    expect(router.state.location.key).toBe(locationKey);
  });

  it('keeps the canonical default URL and visible report aligned when detail loading can be retried', async () => {
    useStockPoolStore.setState({
      historyItems,
      selectedRecordId: 2,
      selectedReport: reports[2],
    });
    vi.mocked(historyApi.getDetail).mockRejectedValueOnce({
      response: {
        status: 500,
        data: {
          error: 'internal_error',
          message: 'The report detail is temporarily unavailable.',
          params: {},
          details: null,
        },
      },
    });
    const router = renderHome('/?keep=yes');

    await waitFor(() => expect(router.state.location.search).toBe('?keep=yes&recordId=1'));
    await waitFor(() => expect(useStockPoolStore.getState().reportDetailError).not.toBeNull());
    expect(screen.queryByText('报告二摘要')).not.toBeInTheDocument();

    vi.mocked(historyApi.getDetail).mockResolvedValueOnce(reports[1]);
    fireEvent.click(screen.getByRole('button', { name: '重试' }));

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=1');
  });

  it('keeps retry available after dismissing a transient report-detail error', async () => {
    vi.mocked(historyApi.getDetail)
      .mockRejectedValueOnce({
        response: {
          status: 500,
          data: {
            error: 'internal_error',
            message: 'The report detail is temporarily unavailable.',
            params: {},
            details: null,
          },
        },
      })
      .mockResolvedValueOnce(reports[1]);
    const router = renderHome('/?keep=yes&recordId=1');

    const reportAlert = await screen.findByRole('alert');
    fireEvent.click(within(reportAlert).getByRole('button', { name: '关闭' }));

    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(router.state.location.search).toBe('?keep=yes&recordId=1');
    fireEvent.click(screen.getByRole('button', { name: '重试' }));

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    expect(historyApi.getDetail).toHaveBeenCalledTimes(2);
    expect(router.state.location.search).toBe('?keep=yes&recordId=1');
  });

  it('closes the full-report drawer when switching to a different URL record', async () => {
    const secondReport = createDeferred<AnalysisReport>();
    vi.mocked(historyApi.getDetail).mockImplementation((recordId) => (
      recordId === 2 ? secondReport.promise : Promise.resolve(reports[recordId])
    ));
    vi.mocked(historyApi.getMarkdown).mockImplementation((recordId) => Promise.resolve(
      recordId === 1 ? '# Drawer report A' : '# Drawer report B',
    ));
    const router = renderHome('/?keep=yes&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '完整分析报告' }));
    await waitFor(() => expect(historyApi.getMarkdown).toHaveBeenCalledWith(1));
    expect(await screen.findByRole('heading', { name: 'Drawer report A' })).toBeInTheDocument();

    await act(async () => {
      await router.navigate('/?keep=yes&recordId=2');
    });

    await waitFor(() => expect(router.state.location.search).toBe('?keep=yes&recordId=2'));
    expect(screen.queryByRole('heading', { name: 'Drawer report A' })).not.toBeInTheDocument();
    expect(screen.getByText('加载报告中...')).toBeInTheDocument();

    await act(async () => {
      secondReport.resolve(reports[2]);
      await secondReport.promise;
    });

    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Drawer report B' })).not.toBeInTheDocument();
    expect(historyApi.getMarkdown).not.toHaveBeenCalledWith(2);
  });

  it('pushes report clicks and restores reports with Back and Forward', async () => {
    const router = renderHome('/?keep=yes', true);

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.search).toBe('?keep=yes&recordId=1'));

    fireEvent.click(screen.getByRole('button', { name: 'Apple AAPL 历史记录' }));
    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=2');

    fireEvent.click(screen.getByRole('button', { name: 'Apple AAPL 历史记录' }));
    expect(router.state.location.search).toBe('?keep=yes&recordId=2');

    await act(async () => {
      await router.navigate(-1);
    });
    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=1');

    await act(async () => {
      await router.navigate(1);
    });
    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=2');
  });

  it('keeps a valid report URL when a shared history error is permanent', async () => {
    const router = renderHome('/?keep=yes&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    vi.mocked(historyApi.getList).mockRejectedValueOnce({
      response: {
        status: 404,
        data: {
          error: 'not_found',
          message: 'The history refresh endpoint was not found.',
          params: {},
          details: null,
        },
      },
    });

    await act(async () => {
      await useStockPoolStore.getState().refreshHistory(true);
    });

    expect(await screen.findByText('未找到请求的内容')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=1');
    expect(screen.getByText('报告一摘要')).toBeInTheDocument();
  });

  it('keeps a valid report URL when a shared analysis error is permanent', async () => {
    const router = renderHome('/?keep=yes&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    vi.mocked(analysisApi.analyzeAsync).mockRejectedValueOnce({
      response: {
        status: 403,
        data: {
          error: 'forbidden',
          message: 'The analysis request is forbidden.',
          params: {},
          details: null,
        },
      },
    });

    await act(async () => {
      await useStockPoolStore.getState().submitAnalysis({ stockCode: '600519' });
    });

    expect(await screen.findByText('请求失败')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=1');
    expect(screen.getByText('报告一摘要')).toBeInTheDocument();
  });

  it('keeps the newer URL report when an older request resolves last', async () => {
    const firstReport = createDeferred<AnalysisReport>();
    vi.mocked(historyApi.getDetail).mockImplementation((recordId) => (
      recordId === 1 ? firstReport.promise : Promise.resolve(reports[2])
    ));
    const router = renderHome('/?recordId=1');

    await waitFor(() => expect(historyApi.getDetail).toHaveBeenCalledWith(1));
    fireEvent.click(await screen.findByRole('button', { name: 'Apple AAPL 历史记录' }));
    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?recordId=2');

    firstReport.resolve(reports[1]);
    await waitFor(() => expect(screen.queryByText('报告一摘要')).not.toBeInTheDocument());
    expect(screen.getByText('报告二摘要')).toBeInTheDocument();
  });

  it('opens a completed-task report through the Home URL owner', async () => {
    const router = renderHome('/?keep=yes&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    const navigationActions: string[] = [];
    const unsubscribe = router.subscribe((state) => {
      navigationActions.push(state.historyAction);
    });
    currentHistoryItems = [completedHistoryItem, ...historyItems];

    await act(async () => {
      taskStreamHarness.dashboardOptions?.onTaskCompleted?.({
        taskId: 'task-completed-3',
        stockCode: '600519',
        stockName: '贵州茅台',
        status: 'completed',
        progress: 100,
        reportType: 'detailed',
        createdAt: '2026-03-20T08:00:00Z',
        completedAt: '2026-03-20T08:01:00Z',
      });
    });

    expect(await screen.findByText('任务完成后的新报告')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=3');
    expect(historyApi.getDetail).toHaveBeenLastCalledWith(3);
    expect(navigationActions).toEqual(['REPLACE']);
    unsubscribe();
  });

  it('opens a persisted market review through URL history without rendering raw task output', async () => {
    const marketTaskId = 'market-task-5';
    const marketHistoryItem = {
      id: 5,
      queryId: marketTaskId,
      stockCode: 'MARKET',
      stockName: '大盘复盘',
      reportType: 'market_review' as const,
      createdAt: '2026-03-20T09:00:00Z',
    };
    const marketHistoryReport: AnalysisReport = {
      meta: {
        ...marketHistoryItem,
        reportLanguage: 'zh',
      },
      summary: {
        analysisSummary: '持久化大盘复盘摘要',
        operationAdvice: '查看复盘',
        trendPrediction: '大盘复盘',
        sentimentScore: 50,
      },
    };
    let marketRecordPersisted = false;
    vi.mocked(historyApi.getList).mockImplementation((params: { reportType?: string } = {}) => Promise.resolve({
      total: params.reportType === 'market_review'
        ? (marketRecordPersisted ? 1 : 0)
        : currentHistoryItems.length,
      page: 1,
      limit: params.reportType === 'market_review' ? 10 : 20,
      items: params.reportType === 'market_review'
        ? (marketRecordPersisted ? [marketHistoryItem] : [])
        : currentHistoryItems,
    }));
    vi.mocked(historyApi.getDetail).mockImplementation((recordId) => Promise.resolve(
      recordId === marketHistoryItem.id ? marketHistoryReport : reports[recordId],
    ));
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# 持久化大盘复盘正文');
    vi.mocked(analysisApi.triggerMarketReview).mockResolvedValue({
      status: 'accepted',
      sendNotification: true,
      message: '大盘复盘任务已提交',
      taskId: marketTaskId,
    });
    vi.mocked(analysisApi.getStatus).mockImplementation(async () => {
      marketRecordPersisted = true;
      return {
        taskId: marketTaskId,
        status: 'completed',
        marketReviewReport: 'RAW_TASK_OUTPUT_MUST_NOT_RENDER',
      };
    });
    const router = renderHome('/?keep=yes&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '大盘复盘' }));

    await waitFor(() => expect(router.state.location.search).toBe('?keep=yes&recordId=5'));
    expect(await screen.findByText('持久化大盘复盘摘要')).toBeInTheDocument();
    expect(screen.queryByText('RAW_TASK_OUTPUT_MUST_NOT_RENDER')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Apple AAPL 历史记录' }));
    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=2');

    await act(async () => {
      await router.navigate(-1);
    });
    expect(await screen.findByText('持久化大盘复盘摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=5');

    await act(async () => {
      await router.navigate(1);
    });
    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=2');
    expect(screen.queryByText('RAW_TASK_OUTPUT_MUST_NOT_RENDER')).not.toBeInTheDocument();
  });

  it('does not let a completed-task refresh replace a newer user URL selection', async () => {
    const completedRefresh = createDeferred<{
      total: number;
      page: number;
      limit: number;
      items: typeof currentHistoryItems;
    }>();
    const router = renderHome('/?keep=yes&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    currentHistoryItems = [completedHistoryItem, ...historyItems];
    vi.mocked(historyApi.getList).mockReturnValueOnce(completedRefresh.promise);

    act(() => {
      taskStreamHarness.dashboardOptions?.onTaskCompleted?.({
        taskId: 'task-completed-3',
        stockCode: '600519',
        stockName: '贵州茅台',
        status: 'completed',
        progress: 100,
        reportType: 'detailed',
        createdAt: '2026-03-20T08:00:00Z',
        completedAt: '2026-03-20T08:01:00Z',
      });
    });
    fireEvent.click(screen.getByRole('button', { name: 'Apple AAPL 历史记录' }));
    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();

    await act(async () => {
      completedRefresh.resolve({
        total: currentHistoryItems.length,
        page: 1,
        limit: 20,
        items: currentHistoryItems,
      });
      await completedRefresh.promise;
    });

    await waitFor(() => expect(router.state.location.search).toBe('?keep=yes&recordId=2'));
    expect(screen.getByText('报告二摘要')).toBeInTheDocument();
    expect(screen.queryByText('任务完成后的新报告')).not.toBeInTheDocument();
    expect(historyApi.getDetail).not.toHaveBeenCalledWith(3);
  });

  it('does not let a completed-task refresh navigate after Home unmounts', async () => {
    const completedRefresh = createDeferred<{
      total: number;
      page: number;
      limit: number;
      items: typeof currentHistoryItems;
    }>();
    const router = renderHome('/?keep=yes&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    currentHistoryItems = [completedHistoryItem, ...historyItems];
    vi.mocked(historyApi.getList).mockReturnValueOnce(completedRefresh.promise);
    act(() => {
      taskStreamHarness.dashboardOptions?.onTaskCompleted?.({
        taskId: 'task-completed-after-unmount',
        stockCode: '600519',
        stockName: '贵州茅台',
        status: 'completed',
        progress: 100,
        reportType: 'detailed',
        createdAt: '2026-03-20T08:00:00Z',
        completedAt: '2026-03-20T08:01:00Z',
      });
    });

    await act(async () => {
      await router.navigate('/other');
    });
    expect(await screen.findByRole('heading', { name: 'Other route' })).toBeInTheDocument();

    await act(async () => {
      completedRefresh.resolve({
        total: currentHistoryItems.length,
        page: 1,
        limit: 20,
        items: currentHistoryItems,
      });
      await completedRefresh.promise;
      await Promise.resolve();
    });

    expect(router.state.location.pathname).toBe('/other');
    expect(screen.getByRole('heading', { name: 'Other route' })).toBeInTheDocument();
    expect(historyApi.getDetail).not.toHaveBeenCalledWith(3);
  });

  it('waits for a superseding history refresh before opening a completed-task report', async () => {
    const staleSameStockItem = {
      ...historyItems[0],
      id: 4,
      queryId: 'q-4',
      createdAt: '2026-03-19T08:00:00Z',
    };
    const staleSameStockReport: AnalysisReport = {
      ...reports[1],
      meta: {
        ...reports[1].meta,
        id: 4,
        queryId: 'q-4',
        createdAt: '2026-03-19T08:00:00Z',
      },
      summary: {
        ...reports[1].summary,
        analysisSummary: '任务完成前的旧报告',
      },
    };
    currentHistoryItems = [staleSameStockItem, ...historyItems];
    vi.mocked(historyApi.getDetail).mockImplementation((recordId) => Promise.resolve(
      recordId === 4 ? staleSameStockReport : reports[recordId],
    ));
    const router = renderHome('/?keep=yes&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();

    const completedRefresh = createDeferred<{
      total: number;
      page: number;
      limit: number;
      items: typeof currentHistoryItems;
    }>();
    const supersedingRefresh = createDeferred<{
      total: number;
      page: number;
      limit: number;
      items: typeof currentHistoryItems;
    }>();
    let mainHistoryRequestCount = 0;
    vi.mocked(historyApi.getList).mockImplementation((params: { reportType?: string } = {}) => {
      if (params.reportType === 'market_review') {
        return Promise.resolve({ total: 0, page: 1, limit: 10, items: [] });
      }
      mainHistoryRequestCount += 1;
      if (mainHistoryRequestCount === 1) {
        return completedRefresh.promise;
      }
      if (mainHistoryRequestCount === 2) {
        return supersedingRefresh.promise;
      }
      return Promise.resolve({
        total: currentHistoryItems.length,
        page: 1,
        limit: 20,
        items: currentHistoryItems,
      });
    });

    act(() => {
      taskStreamHarness.dashboardOptions?.onTaskCompleted?.({
        taskId: 'task-completed-3',
        stockCode: '600519',
        stockName: '贵州茅台',
        status: 'completed',
        progress: 100,
        reportType: 'detailed',
        createdAt: '2026-03-20T08:00:00Z',
        completedAt: '2026-03-20T08:01:00Z',
      });
    });
    expect(mainHistoryRequestCount).toBe(1);

    let supersedingRefreshPromise!: Promise<unknown>;
    act(() => {
      supersedingRefreshPromise = useStockPoolStore.getState().refreshHistory(true);
    });
    expect(mainHistoryRequestCount).toBe(2);

    currentHistoryItems = [completedHistoryItem, staleSameStockItem, ...historyItems];
    await act(async () => {
      completedRefresh.resolve({
        total: currentHistoryItems.length,
        page: 1,
        limit: 20,
        items: currentHistoryItems,
      });
      await completedRefresh.promise;
      await Promise.resolve();
    });

    expect(router.state.location.search).toBe('?keep=yes&recordId=1');
    expect(screen.getByText('报告一摘要')).toBeInTheDocument();
    expect(historyApi.getDetail).not.toHaveBeenCalledWith(4);
    expect(historyApi.getDetail).not.toHaveBeenCalledWith(3);

    await act(async () => {
      supersedingRefresh.resolve({
        total: currentHistoryItems.length,
        page: 1,
        limit: 20,
        items: currentHistoryItems,
      });
      await supersedingRefreshPromise;
    });

    expect(await screen.findByText('任务完成后的新报告')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=3');
    expect(historyApi.getDetail).not.toHaveBeenCalledWith(4);
  });

  it('does not consume a paginated response after it supersedes a completed-task refresh', async () => {
    const staleSameStockItem = {
      ...historyItems[0],
      id: 4,
      queryId: 'q-4',
      createdAt: '2026-03-19T08:00:00Z',
    };
    const completedRefresh = createDeferred<{
      total: number;
      page: number;
      limit: number;
      items: typeof currentHistoryItems;
    }>();
    const pagination = createDeferred<{
      total: number;
      page: number;
      limit: number;
      items: typeof currentHistoryItems;
    }>();
    const completedTaskRefreshSettled = createDeferred<void>();
    useStockPoolStore.setState({
      refreshHistoryForCompletedTask: async (task) => {
        const candidate = await defaultRefreshHistoryForCompletedTask(task);
        completedTaskRefreshSettled.resolve();
        return candidate;
      },
    });
    const router = renderHome('/?keep=yes&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    vi.mocked(historyApi.getList)
      .mockReturnValueOnce(completedRefresh.promise)
      .mockReturnValueOnce(pagination.promise);

    act(() => {
      taskStreamHarness.dashboardOptions?.onTaskCompleted?.({
        taskId: 'task-completed-3',
        stockCode: '600519',
        stockName: '贵州茅台',
        status: 'completed',
        progress: 100,
        reportType: 'detailed',
        createdAt: '2026-03-20T08:00:00Z',
        completedAt: '2026-03-20T08:01:00Z',
      });
    });
    useStockPoolStore.setState({ hasMore: true });
    let paginationPromise!: Promise<void>;
    act(() => {
      paginationPromise = useStockPoolStore.getState().loadMoreHistory();
    });

    await act(async () => {
      completedRefresh.resolve({
        total: 3,
        page: 1,
        limit: 20,
        items: [completedHistoryItem, ...historyItems],
      });
      await completedRefresh.promise;
      pagination.resolve({
        total: 3,
        page: 2,
        limit: 20,
        items: [staleSameStockItem],
      });
      await paginationPromise;
    });
    await act(async () => {
      await completedTaskRefreshSettled.promise;
      await Promise.resolve();
    });

    expect(router.state.location.search).toBe('?keep=yes&recordId=1');
    expect(screen.getByText('报告一摘要')).toBeInTheDocument();
    expect(historyApi.getDetail).not.toHaveBeenCalledWith(3);
    expect(historyApi.getDetail).not.toHaveBeenCalledWith(4);
  });

  it('does not let a completed-task refresh overwrite newer query state for the same record', async () => {
    const completedRefresh = createDeferred<{
      total: number;
      page: number;
      limit: number;
      items: typeof currentHistoryItems;
    }>();
    const router = renderHome('/?keep=before&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    currentHistoryItems = [completedHistoryItem, ...historyItems];
    vi.mocked(historyApi.getList).mockReturnValueOnce(completedRefresh.promise);
    act(() => {
      taskStreamHarness.dashboardOptions?.onTaskCompleted?.({
        taskId: 'task-completed-3',
        stockCode: '600519',
        status: 'completed',
        progress: 100,
        reportType: 'detailed',
        createdAt: '2026-03-20T08:00:00Z',
      });
    });

    await router.navigate('/?keep=after&recordId=1');
    await act(async () => {
      completedRefresh.resolve({
        total: currentHistoryItems.length,
        page: 1,
        limit: 20,
        items: currentHistoryItems,
      });
      await completedRefresh.promise;
    });

    await waitFor(() => expect(router.state.location.search).toBe('?keep=after&recordId=1'));
    expect(screen.getByText('报告一摘要')).toBeInTheDocument();
    expect(historyApi.getDetail).not.toHaveBeenCalledWith(3);
  });

  it('keeps an explicit deep-link URL when a task completes before its report loads', async () => {
    const deepLinkReport = createDeferred<AnalysisReport>();
    vi.mocked(historyApi.getDetail).mockImplementation((recordId) => (
      recordId === 2 ? deepLinkReport.promise : Promise.resolve(reports[recordId])
    ));
    const router = renderHome('/?keep=yes&recordId=2');

    await waitFor(() => expect(historyApi.getDetail).toHaveBeenCalledWith(2));
    expect(taskStreamHarness.dashboardOptions?.onTaskCompleted).toBeTypeOf('function');
    const historyRequestCount = vi.mocked(historyApi.getList).mock.calls.length;
    currentHistoryItems = [completedHistoryItem, ...historyItems];
    act(() => {
      taskStreamHarness.dashboardOptions?.onTaskCompleted?.({
        taskId: 'task-completed-3',
        stockCode: '600519',
        stockName: '贵州茅台',
        status: 'completed',
        progress: 100,
        reportType: 'detailed',
        createdAt: '2026-03-20T08:00:00Z',
        completedAt: '2026-03-20T08:01:00Z',
      });
    });
    await waitFor(() => expect(vi.mocked(historyApi.getList).mock.calls.length).toBeGreaterThan(historyRequestCount));
    await act(async () => {
      await Promise.resolve();
    });

    expect(router.state.location.search).toBe('?keep=yes&recordId=2');
    expect(historyApi.getDetail).not.toHaveBeenCalledWith(3);

    await act(async () => {
      deepLinkReport.resolve(reports[2]);
      await deepLinkReport.promise;
    });
    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=2');
  });

  it('replaces a deleted current report with the next URL record without requesting the deleted id again', async () => {
    const router = renderHome('/?keep=yes&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    const navigationEvents: Array<{ action: string; search: string }> = [];
    const unsubscribe = router.subscribe((state) => {
      navigationEvents.push({ action: state.historyAction, search: state.location.search });
    });
    fireEvent.click(screen.getByRole('button', { name: '删除 贵州茅台 历史记录' }));
    const confirmDialog = screen.getByRole('dialog', { name: '删除历史记录' });
    fireEvent.click(within(confirmDialog).getByRole('button', { name: '删除' }));

    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=2');
    expect(vi.mocked(historyApi.getDetail).mock.calls.map(([recordId]) => recordId)).toEqual([1, 2]);
    expect(navigationEvents).toEqual([{ action: 'REPLACE', search: '?keep=yes&recordId=2' }]);
    unsubscribe();
  });

  it('does not let a completed deletion navigate after Home unmounts', async () => {
    const deletion = createDeferred<{ deleted: number }>();
    vi.mocked(historyApi.deleteByCode).mockImplementation((stockCode) => (
      deletion.promise.then((result) => {
        currentHistoryItems = currentHistoryItems.filter((item) => item.stockCode !== stockCode);
        return result;
      })
    ));
    const router = renderHome('/?keep=yes&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '删除 贵州茅台 历史记录' }));
    fireEvent.click(within(screen.getByRole('dialog', { name: '删除历史记录' }))
      .getByRole('button', { name: '删除' }));
    await waitFor(() => expect(historyApi.deleteByCode).toHaveBeenCalledWith('600519'));

    await act(async () => {
      await router.navigate('/other');
    });
    expect(await screen.findByRole('heading', { name: 'Other route' })).toBeInTheDocument();

    await act(async () => {
      deletion.resolve({ deleted: 1 });
      await deletion.promise;
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(router.state.location.pathname).toBe('/other');
    expect(screen.getByRole('heading', { name: 'Other route' })).toBeInTheDocument();
    expect(historyApi.getDetail).not.toHaveBeenCalledWith(2);
  });

  it('uses the final applied page-one refresh when deletion history is superseded', async () => {
    const deletionRefresh = createDeferred<{
      total: number;
      page: number;
      limit: number;
      items: typeof historyItems;
    }>();
    const supersedingRefresh = createDeferred<{
      total: number;
      page: number;
      limit: number;
      items: typeof historyItems;
    }>();
    const router = renderHome('/?keep=yes&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    const historyRequestCount = vi.mocked(historyApi.getList).mock.calls.length;
    vi.mocked(historyApi.getList)
      .mockReturnValueOnce(deletionRefresh.promise)
      .mockReturnValueOnce(supersedingRefresh.promise);

    fireEvent.click(screen.getByRole('button', { name: '删除 贵州茅台 历史记录' }));
    fireEvent.click(within(screen.getByRole('dialog', { name: '删除历史记录' }))
      .getByRole('button', { name: '删除' }));
    await waitFor(() => expect(vi.mocked(historyApi.getList).mock.calls.length)
      .toBe(historyRequestCount + 1));

    let latestRefresh!: Promise<unknown>;
    act(() => {
      latestRefresh = useStockPoolStore.getState().refreshHistory(true);
    });
    await waitFor(() => expect(vi.mocked(historyApi.getList).mock.calls.length)
      .toBe(historyRequestCount + 2));

    await act(async () => {
      supersedingRefresh.resolve({
        total: 1,
        page: 1,
        limit: 20,
        items: [historyItems[1]],
      });
      await latestRefresh;
    });
    await act(async () => {
      deletionRefresh.resolve({
        total: 1,
        page: 1,
        limit: 20,
        items: [historyItems[1]],
      });
      await deletionRefresh.promise;
    });

    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=2');
    expect(useStockPoolStore.getState().historyItems.map((item) => item.id)).toEqual([2]);
  });

  it('cancels a pending current report when its stock is deleted', async () => {
    const deletedReport = createDeferred<AnalysisReport>();
    vi.mocked(historyApi.getDetail).mockImplementation((recordId) => (
      recordId === 1 ? deletedReport.promise : Promise.resolve(reports[recordId])
    ));
    const router = renderHome('/?keep=yes&recordId=1');

    await waitFor(() => expect(historyApi.getDetail).toHaveBeenCalledWith(1));
    fireEvent.click(await screen.findByRole('button', { name: '删除 贵州茅台 历史记录' }));
    fireEvent.click(within(screen.getByRole('dialog', { name: '删除历史记录' }))
      .getByRole('button', { name: '删除' }));

    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=2');
    deletedReport.resolve(reports[1]);
    await act(async () => {
      await deletedReport.promise;
    });
    expect(screen.queryByText('报告一摘要')).not.toBeInTheDocument();
    expect(screen.getByText('报告二摘要')).toBeInTheDocument();
  });

  it('resolves an unloaded old deep link before deleting its stock and cancels the late detail', async () => {
    const oldDeepLinkReport = createDeferred<AnalysisReport>();
    let oldDeepLinkRequests = 0;
    vi.mocked(historyApi.getDetail).mockImplementation((recordId) => {
      if (recordId === 4) {
        oldDeepLinkRequests += 1;
        return oldDeepLinkRequests === 1
          ? oldDeepLinkReport.promise
          : Promise.resolve(reports[4]);
      }
      return Promise.resolve(reports[recordId]);
    });
    const router = renderHome('/?keep=yes&recordId=4');

    await waitFor(() => expect(historyApi.getDetail).toHaveBeenCalledWith(4));
    fireEvent.click(await screen.findByRole('button', { name: '删除 贵州茅台 历史记录' }));
    fireEvent.click(within(screen.getByRole('dialog', { name: '删除历史记录' }))
      .getByRole('button', { name: '删除' }));

    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=2');
    expect(oldDeepLinkRequests).toBe(2);

    oldDeepLinkReport.resolve(reports[4]);
    await act(async () => {
      await oldDeepLinkReport.promise;
    });
    expect(screen.queryByText('未加载的旧报告')).not.toBeInTheDocument();
    expect(screen.getByText('报告二摘要')).toBeInTheDocument();
  });

  it('replaces a same-stock URL when its post-delete identity probe is missing and cancels its late detail', async () => {
    const deletion = createDeferred<{ deleted: number }>();
    const driftedReport = createDeferred<AnalysisReport>();
    let driftedReportRequests = 0;
    vi.mocked(historyApi.deleteByCode).mockImplementation((stockCode) => (
      deletion.promise.then((result) => {
        currentHistoryItems = currentHistoryItems.filter((item) => item.stockCode !== stockCode);
        return result;
      })
    ));
    vi.mocked(historyApi.getDetail).mockImplementation((recordId) => {
      if (recordId === 4) {
        driftedReportRequests += 1;
        return driftedReportRequests === 1
          ? driftedReport.promise
          : Promise.reject({
            response: {
              status: 404,
              data: {
                error: 'not_found',
                message: 'The requested report was deleted.',
                params: {},
                details: null,
              },
            },
          });
      }
      return Promise.resolve(reports[recordId]);
    });
    const router = renderHome('/?keep=yes&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '删除 贵州茅台 历史记录' }));
    fireEvent.click(within(screen.getByRole('dialog', { name: '删除历史记录' }))
      .getByRole('button', { name: '删除' }));
    await waitFor(() => expect(historyApi.deleteByCode).toHaveBeenCalledWith('600519'));

    await act(async () => {
      await router.navigate('/?keep=yes&recordId=4');
    });
    await waitFor(() => expect(driftedReportRequests).toBe(1));
    await act(async () => {
      deletion.resolve({ deleted: 1 });
      await deletion.promise;
    });

    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=2');
    expect(driftedReportRequests).toBe(2);

    driftedReport.resolve(reports[4]);
    await act(async () => {
      await driftedReport.promise;
    });
    expect(screen.queryByText('未加载的旧报告')).not.toBeInTheDocument();
    expect(screen.getByText('报告二摘要')).toBeInTheDocument();
  });

  it('preserves a different-stock URL selected while deletion is in flight', async () => {
    const deletion = createDeferred<{ deleted: number }>();
    const differentStockReport = createDeferred<AnalysisReport>();
    vi.mocked(historyApi.deleteByCode).mockImplementation((stockCode) => (
      deletion.promise.then((result) => {
        currentHistoryItems = currentHistoryItems.filter((item) => item.stockCode !== stockCode);
        return result;
      })
    ));
    vi.mocked(historyApi.getDetail).mockImplementation((recordId) => (
      recordId === 2 ? differentStockReport.promise : Promise.resolve(reports[recordId])
    ));
    const router = renderHome('/?keep=yes&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '删除 贵州茅台 历史记录' }));
    fireEvent.click(within(screen.getByRole('dialog', { name: '删除历史记录' }))
      .getByRole('button', { name: '删除' }));
    await waitFor(() => expect(historyApi.deleteByCode).toHaveBeenCalledWith('600519'));

    await act(async () => {
      await router.navigate('/?keep=yes&recordId=2');
    });
    await waitFor(() => expect(historyApi.getDetail).toHaveBeenCalledWith(2));
    await act(async () => {
      deletion.resolve({ deleted: 1 });
      await deletion.promise;
    });

    expect(router.state.location.search).toBe('?keep=yes&recordId=2');
    expect(vi.mocked(historyApi.getDetail).mock.calls.filter(([recordId]) => recordId === 2)).toHaveLength(1);

    differentStockReport.resolve(reports[2]);
    await act(async () => {
      await differentStockReport.promise;
    });
    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=2');
  });

  it('validates the latest URL after two report changes during deletion probes', async () => {
    const deletion = createDeferred<{ deleted: number }>();
    const recordFourUrlDetail = createDeferred<AnalysisReport>();
    const recordFourProbe = createDeferred<AnalysisReport>();
    const recordFiveUrlDetail = createDeferred<AnalysisReport>();
    const recordFiveProbe = createDeferred<AnalysisReport>();
    const recordSixUrlDetail = createDeferred<AnalysisReport>();
    const recordFive = {
      ...reports[2],
      meta: { ...reports[2].meta, id: 5, queryId: 'q-5' },
    } as AnalysisReport;
    const recordSix = {
      ...reports[1],
      meta: { ...reports[1].meta, id: 6, queryId: 'q-6' },
    } as AnalysisReport;
    let recordFourRequests = 0;
    let recordFiveRequests = 0;
    let recordSixRequests = 0;
    vi.mocked(historyApi.deleteByCode).mockImplementation((stockCode) => (
      deletion.promise.then((result) => {
        currentHistoryItems = currentHistoryItems.filter((item) => item.stockCode !== stockCode);
        return result;
      })
    ));
    vi.mocked(historyApi.getDetail).mockImplementation((recordId) => {
      if (recordId === 4) {
        recordFourRequests += 1;
        return recordFourRequests === 1 ? recordFourUrlDetail.promise : recordFourProbe.promise;
      }
      if (recordId === 5) {
        recordFiveRequests += 1;
        return recordFiveRequests === 1 ? recordFiveUrlDetail.promise : recordFiveProbe.promise;
      }
      if (recordId === 6) {
        recordSixRequests += 1;
        return recordSixRequests === 1 ? recordSixUrlDetail.promise : Promise.resolve(recordSix);
      }
      return Promise.resolve(reports[recordId]);
    });
    const router = renderHome('/?keep=yes&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '删除 贵州茅台 历史记录' }));
    fireEvent.click(within(screen.getByRole('dialog', { name: '删除历史记录' }))
      .getByRole('button', { name: '删除' }));
    await waitFor(() => expect(historyApi.deleteByCode).toHaveBeenCalledWith('600519'));

    await act(async () => {
      await router.navigate('/?keep=yes&recordId=4');
    });
    await waitFor(() => expect(recordFourRequests).toBe(1));
    await act(async () => {
      deletion.resolve({ deleted: 1 });
      await deletion.promise;
    });
    await waitFor(() => expect(recordFourRequests).toBe(2));

    await act(async () => {
      await router.navigate('/?keep=yes&recordId=5');
    });
    await waitFor(() => expect(recordFiveRequests).toBe(1));
    await act(async () => {
      recordFourProbe.resolve(reports[4]);
      await recordFourProbe.promise;
    });
    await waitFor(() => expect(recordFiveRequests).toBe(2));

    await act(async () => {
      await router.navigate('/?keep=yes&recordId=6');
    });
    await waitFor(() => expect(recordSixRequests).toBe(1));
    await act(async () => {
      recordFiveProbe.resolve(recordFive);
      await recordFiveProbe.promise;
    });

    await waitFor(() => expect(recordSixRequests).toBe(2));
    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=2');
  });

  it('replaces a deleted last report with an empty URL state without requesting it again', async () => {
    currentHistoryItems = [historyItems[0]];
    const router = renderHome('/?keep=yes&recordId=1');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '删除 贵州茅台 历史记录' }));
    const confirmDialog = screen.getByRole('dialog', { name: '删除历史记录' });
    fireEvent.click(within(confirmDialog).getByRole('button', { name: '删除' }));

    expect(await screen.findByText('开始分析')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes');
    expect(screen.queryByText('报告一摘要')).not.toBeInTheDocument();
    expect(vi.mocked(historyApi.getDetail).mock.calls.map(([recordId]) => recordId)).toEqual([1]);
  });

  it('restores and closes a task Run Flow without clearing report or unrelated state', async () => {
    const router = renderHome('/?recordId=1&keep=yes&runFlow=task&runFlowTaskId=task-2');

    expect(await screen.findByTestId('run-flow-panel')).toBeInTheDocument();
    expect(analysisApi.getTaskFlow).toHaveBeenCalledWith('task-2');

    fireEvent.click(screen.getByRole('button', { name: '关闭' }));
    await waitFor(() => expect(screen.queryByTestId('run-flow-panel')).not.toBeInTheDocument());
    expect(router.state.location.search).toBe('?recordId=1&keep=yes');

    await router.navigate(-1);
    expect(await screen.findByTestId('run-flow-panel')).toBeInTheDocument();
  });

  it('restores and closes a history Run Flow from a shared deep link', async () => {
    const router = renderHome('/?recordId=2&runFlow=history&runFlowRecordId=2');

    expect(await screen.findByTestId('run-flow-panel')).toBeInTheDocument();
    expect(historyApi.getRecordFlow).toHaveBeenCalledWith(2);

    fireEvent.click(screen.getByRole('button', { name: '关闭' }));
    await waitFor(() => expect(router.state.location.search).toBe('?recordId=2'));
  });

  it('removes a missing report from the URL without showing the previous report as current', async () => {
    vi.mocked(historyApi.getDetail).mockRejectedValue({
      response: {
        status: 404,
        data: {
          error: 'not_found',
          message: 'The requested report was not found.',
          params: {},
          details: null,
        },
      },
    });
    const router = renderHome('/?recordId=404&keep=yes');

    expect(await screen.findByText('未找到请求的内容')).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.search).toBe('?keep=yes'));
    expect(screen.queryByText('报告一摘要')).not.toBeInTheDocument();
  });

  it('removes an unauthorized report identity without selecting a fallback report', async () => {
    vi.mocked(historyApi.getDetail).mockRejectedValue({
      response: {
        status: 401,
        data: {
          error: 'unauthorized',
          message: 'The session cannot access this report.',
          params: {},
          details: null,
        },
      },
    });
    const router = renderHome('/?recordId=2&keep=yes', true);

    expect(await screen.findByText('需要登录')).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.search).toBe('?keep=yes'));
    expect(vi.mocked(historyApi.getDetail).mock.calls.map(([recordId]) => recordId)).toEqual([2]);
    expect(screen.queryByText('报告一摘要')).not.toBeInTheDocument();
    expect(screen.queryByText('报告二摘要')).not.toBeInTheDocument();
  });

  it('removes a forbidden report identity without selecting a fallback report', async () => {
    vi.mocked(historyApi.getDetail).mockRejectedValue({
      response: {
        status: 403,
        data: {
          error: 'forbidden',
          message: 'The current account cannot access this report.',
          params: {},
          details: null,
        },
      },
    });
    const router = renderHome('/?recordId=2&keep=yes', true);

    expect(await screen.findByText('请求失败')).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.search).toBe('?keep=yes'));
    expect(vi.mocked(historyApi.getDetail).mock.calls.map(([recordId]) => recordId)).toEqual([2]);
    expect(screen.queryByText('报告一摘要')).not.toBeInTheDocument();
    expect(screen.queryByText('报告二摘要')).not.toBeInTheDocument();
  });

  it('shows a localized warning after normalizing an invalid report deep link', async () => {
    vi.mocked(historyApi.getList).mockResolvedValue({ total: 0, page: 1, limit: 20, items: [] });
    vi.mocked(historyApi.getStockBarList).mockResolvedValue({ total: 0, items: [] });
    const router = renderHome('/?recordId=invalid&keep=yes');

    expect(await screen.findByText('报告链接无效')).toBeInTheDocument();
    expect(screen.getByText('报告链接中的记录 ID 无效，已从地址中移除。')).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.search).toBe('?keep=yes'));
  });

  it('keeps a localized Run Flow error after removing a permanently unavailable source', async () => {
    const runFlowRequest = createDeferred<RunFlowSnapshot>();
    const runFlowError = {
      response: {
        status: 404,
        data: {
          error: 'not_found',
          message: 'The requested Run Flow was not found.',
          params: {},
          details: null,
        },
      },
    };
    vi.mocked(historyApi.getRecordFlow).mockReturnValue(runFlowRequest.promise);
    const router = renderHome('/?recordId=1&keep=yes&runFlow=history&runFlowRecordId=404');

    await waitFor(() => expect(historyApi.getRecordFlow).toHaveBeenCalledWith(404));
    await act(async () => {
      runFlowRequest.reject(runFlowError);
      await runFlowRequest.promise.catch(() => undefined);
    });

    expect(router.state.location.search).toBe('?recordId=1&keep=yes');
    expect(screen.queryByRole('dialog', { name: '运行流' })).not.toBeInTheDocument();
    expect(screen.getByText('未找到请求的内容')).toBeInTheDocument();
  });
});
