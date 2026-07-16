import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { analysisApi } from '../../api/analysis';
import { agentApi } from '../../api/agent';
import { historyApi } from '../../api/history';
import { systemConfigApi } from '../../api/systemConfig';
import { useStockPoolStore } from '../../stores';
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

vi.mock('../../hooks/useTaskStream', () => ({
  useTaskStream: vi.fn(() => ({
    isConnected: true,
    reconnect: vi.fn(),
    disconnect: vi.fn(),
  })),
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
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function renderHome(initialEntry: string) {
  const router = createMemoryRouter(
    [{ path: '/', element: <HomePage /> }],
    { initialEntries: [initialEntry] },
  );
  render(<RouterProvider router={router} />);
  return router;
}

describe('HomePage URL state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    useStockPoolStore.getState().resetDashboardState();
    vi.mocked(historyApi.getList).mockImplementation((params: { reportType?: string } = {}) => Promise.resolve({
      total: params.reportType === 'market_review' ? 0 : historyItems.length,
      page: 1,
      limit: params.reportType === 'market_review' ? 10 : 20,
      items: params.reportType === 'market_review' ? [] : historyItems,
    }));
    vi.mocked(historyApi.getStockBarList).mockResolvedValue({
      total: historyItems.length,
      items: historyItems.map((item) => ({
        ...item,
        analysisCount: 1,
        lastAnalysisTime: item.createdAt,
      })),
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
    const router = renderHome('/?recordId=2&keep=yes');

    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(historyApi.getDetail).toHaveBeenCalledWith(2);
    expect(router.state.location.search).toBe('?recordId=2&keep=yes');
  });

  it('pushes report clicks and restores reports with Back and Forward', async () => {
    const router = renderHome('/?keep=yes');

    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.search).toBe('?keep=yes&recordId=1'));

    fireEvent.click(screen.getByRole('button', { name: 'Apple AAPL 历史记录' }));
    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?keep=yes&recordId=2');

    await router.navigate(-1);
    expect(await screen.findByText('报告一摘要')).toBeInTheDocument();

    await router.navigate(1);
    expect(await screen.findByText('报告二摘要')).toBeInTheDocument();
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

  it('restores and closes a task Run Flow without clearing report or unrelated state', async () => {
    const router = renderHome('/?recordId=1&keep=yes&runFlow=task&runFlowTaskId=task-2');

    expect(await screen.findByTestId('run-flow-panel')).toBeInTheDocument();
    expect(analysisApi.getTaskFlow).toHaveBeenCalledWith('task-2');

    fireEvent.click(screen.getByRole('button', { name: '关闭抽屉' }));
    await waitFor(() => expect(screen.queryByTestId('run-flow-panel')).not.toBeInTheDocument());
    expect(router.state.location.search).toBe('?recordId=1&keep=yes');

    await router.navigate(-1);
    expect(await screen.findByTestId('run-flow-panel')).toBeInTheDocument();
  });

  it('restores and closes a history Run Flow from a shared deep link', async () => {
    const router = renderHome('/?recordId=2&runFlow=history&runFlowRecordId=2');

    expect(await screen.findByTestId('run-flow-panel')).toBeInTheDocument();
    expect(historyApi.getRecordFlow).toHaveBeenCalledWith(2);

    fireEvent.click(screen.getByRole('button', { name: '关闭抽屉' }));
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
    const router = renderHome('/?recordId=2&keep=yes');

    expect(await screen.findByText('需要登录')).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.search).toBe('?keep=yes'));
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
    const router = renderHome('/?recordId=2&keep=yes');

    expect(await screen.findByText('请求失败')).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.search).toBe('?keep=yes'));
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
    vi.mocked(historyApi.getRecordFlow).mockRejectedValue({
      response: {
        status: 404,
        data: {
          error: 'not_found',
          message: 'The requested Run Flow was not found.',
          params: {},
          details: null,
        },
      },
    });
    const router = renderHome('/?recordId=1&keep=yes&runFlow=history&runFlowRecordId=404');

    await waitFor(() => expect(router.state.location.search).toBe('?recordId=1&keep=yes'));
    expect(await screen.findByText('未找到请求的内容')).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '运行流' })).not.toBeInTheDocument();
  });
});
