// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { agentApi } from '../../api/agent';
import { analysisApi } from '../../api/analysis';
import { historyApi } from '../../api/history';
import { stocksApi } from '../../api/stocks';
import { systemConfigApi } from '../../api/systemConfig';
import { ToastProvider } from '../../components/common';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import {
  ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS,
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  APP_ROUTE_PATHS,
  RUN_FLOW_ROUTE_QUERY_VALUES,
  buildAnalysisWorkbenchHref,
} from '../../routing/routes';
import { useStockPoolStore } from '../../stores/stockPoolStore';
import type { AnalysisReport, HistoryItem, StockBarItem, TaskInfo } from '../../types/analysis';
import ResearchAnalysisWorkbenchPage from '../ResearchAnalysisWorkbenchPage';

type LifecycleOptions = Parameters<
  (typeof import('../../hooks/useDashboardLifecycle'))['useDashboardLifecycle']
>[0];

let lifecycleOptions: LifecycleOptions | null = null;
let watchlistCodes: string[] = [];

vi.mock('../../hooks/useDashboardLifecycle', () => ({
  useDashboardLifecycle: (options: LifecycleOptions) => {
    lifecycleOptions = options;
    return { isInitialStockBarLoadSettled: true };
  },
}));

vi.mock('../../api/agent', () => ({
  agentApi: {
    getSkills: vi.fn(),
  },
}));

vi.mock('../../api/analysis', async () => {
  const actual = await vi.importActual<typeof import('../../api/analysis')>('../../api/analysis');
  return {
    ...actual,
    analysisApi: {
      ...actual.analysisApi,
      analyzeAsync: vi.fn(),
    },
  };
});

vi.mock('../../api/history', () => ({
  historyApi: {
    getDetail: vi.fn(),
    deleteRecords: vi.fn(),
  },
}));

vi.mock('../../api/stocks', () => ({
  stocksApi: {
    extractFromImage: vi.fn(),
    parseImport: vi.fn(),
  },
}));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getSetupStatus: vi.fn(),
  },
}));

vi.mock('../../hooks/useStockIndex', () => ({
  useStockIndex: () => ({
    index: [],
    loading: false,
    error: null,
    fallback: false,
    loaded: true,
  }),
}));

vi.mock('../../hooks/useWatchlist', () => ({
  useWatchlist: () => ({
    watchlistCodes,
    isLoading: false,
    isActioning: false,
    loadError: null,
    actionMessage: null,
    isInWatchlist: vi.fn(() => false),
    toggleWatchlist: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock('../../components/report/ReportSummary', () => ({
  ReportSummary: ({
    data,
    onOpenRunFlow,
  }: {
    data: AnalysisReport;
    onOpenRunFlow?: (recordId: number) => void;
  }) => (
    <div data-testid="report-summary">
      <span>{data.meta.stockName}</span>
      <button type="button" onClick={() => onOpenRunFlow?.(data.meta.id!)}>
        Open report run flow
      </button>
    </div>
  ),
}));

vi.mock('../../components/run-flow', () => ({
  RunFlowPanel: ({ source }: { source: { type: string } }) => (
    <div data-testid="run-flow-panel">{source.type}</div>
  ),
}));

const historyItem: HistoryItem = {
  id: 12,
  queryId: 'query-12',
  stockCode: 'AAPL',
  stockName: 'Apple',
  reportType: 'detailed',
  createdAt: '2026-07-23T12:00:00Z',
};

const report: AnalysisReport = {
  meta: {
    id: historyItem.id,
    queryId: historyItem.queryId,
    stockCode: historyItem.stockCode,
    stockName: historyItem.stockName ?? 'Apple',
    reportType: 'detailed',
    createdAt: historyItem.createdAt,
    reportLanguage: 'en',
  },
  summary: {
    analysisSummary: 'Apple report',
    operationAdvice: 'Observe',
    trendPrediction: 'Neutral',
    sentimentScore: 55,
  },
};

const runningTask: TaskInfo = {
  taskId: 'task-7',
  stockCode: 'AAPL',
  stockName: 'Apple',
  status: 'processing',
  progress: 40,
  reportType: 'detailed',
  createdAt: '2026-07-23T12:00:00Z',
};

const stockBarItem = (
  id: number,
  stockCode: string,
  lastAnalysisTime: string,
): StockBarItem => ({
  id,
  stockCode,
  stockName: stockCode,
  reportType: 'detailed',
  sentimentScore: 50,
  analysisCount: 1,
  lastAnalysisTime,
});

function deferredPromise<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}${location.hash}`}</output>;
}

function renderWorkbench(initialEntry: string = APP_ROUTE_PATHS.researchAnalysis) {
  return render(
    <UiLanguageProvider initialLanguage="zh">
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <LocationProbe />
          <Routes>
            <Route
              path={APP_ROUTE_PATHS.researchAnalysis}
              element={<ResearchAnalysisWorkbenchPage />}
            />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </UiLanguageProvider>,
  );
}

function renderedSearch(): URLSearchParams {
  const location = screen.getByTestId('location').textContent ?? '';
  return new URL(location, 'http://stockpulse.local').searchParams;
}

describe('ResearchAnalysisWorkbenchPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    window.sessionStorage.clear();
    lifecycleOptions = null;
    watchlistCodes = [];
    useStockPoolStore.getState().resetDashboardState();
    vi.mocked(agentApi.getSkills).mockResolvedValue({ skills: [], default_skill_id: '' });
    vi.mocked(analysisApi.analyzeAsync).mockResolvedValue({
      taskId: 'task-new',
      status: 'pending',
    });
    vi.mocked(historyApi.getDetail).mockResolvedValue(report);
    vi.mocked(historyApi.deleteRecords).mockResolvedValue({ deleted: 1 });
    vi.mocked(stocksApi.extractFromImage).mockResolvedValue({ codes: ['AAPL', 'MSFT'] });
    vi.mocked(stocksApi.parseImport).mockResolvedValue({ codes: ['AAPL', 'MSFT'] });
    vi.mocked(systemConfigApi.getSetupStatus).mockResolvedValue({
      isComplete: true,
      readyForSmoke: true,
      requiredMissingKeys: [],
      nextStepKey: null,
      checks: [],
    });
  });

  it('renders one workbench with three URL-backed segments and launch actions', async () => {
    renderWorkbench();

    expect(await screen.findByRole('heading', { name: '分析工作台' })).toBeInTheDocument();
    expect(document.title).toBe('分析工作台 - StockPulse');
    const workbenchTabs = screen.getByRole('tablist', { name: '分析工作台分段' });
    expect(within(workbenchTabs).getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      '发起与批量',
      '运行中任务',
      '历史与对比',
    ]);
    expect(screen.getByRole('button', { name: '导入图表/文档到分析' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '分析全部' })).toBeInTheDocument();
  });

  it('switches segments without a reload and gives the empty tasks view a primary action', async () => {
    renderWorkbench();

    fireEvent.click(await screen.findByRole('tab', { name: '运行中任务' }));

    expect(screen.getByTestId('location')).toHaveTextContent(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
    }));
    expect(screen.getByText('暂无运行任务')).toBeInTheDocument();
    const launchAction = screen.getByRole('button', { name: '发起与批量' });
    expect(launchAction).toHaveAttribute('data-variant', 'primary');
    fireEvent.click(launchAction);
    expect(screen.getByTestId('location')).toHaveTextContent(APP_ROUTE_PATHS.researchAnalysis);
  });

  it('shows the running count and opens task RunFlow through canonical URL state', async () => {
    useStockPoolStore.setState({
      activeTasks: [
        {
          ...runningTask,
          taskId: 'market-task',
          stockCode: 'MARKET',
          stockName: 'Market review task',
          reportType: 'market_review',
        },
        runningTask,
      ],
    });
    renderWorkbench(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
    }));

    const tasksTab = await screen.findByRole('tab', { name: /运行中任务/u });
    expect(within(tasksTab).getByText('1')).toBeInTheDocument();
    expect(screen.getByText('Apple')).toBeInTheDocument();
    expect(screen.queryByText('Market review task')).not.toBeInTheDocument();
    const runFlowTrigger = screen.getByRole('button', { name: '查看 Apple 运行流' });
    runFlowTrigger.focus();
    fireEvent.click(runFlowTrigger);

    expect(await screen.findByTestId('run-flow-panel')).toHaveTextContent('task');
    const runFlowDrawer = screen.getByRole('dialog', { name: '运行流' });
    expect(runFlowDrawer).toHaveAttribute('data-drawer-variant', 'detail');
    expect(runFlowDrawer).toHaveAttribute('data-drawer-size', 'wide');
    const search = new URLSearchParams(screen.getByTestId('location').textContent?.split('?')[1]);
    expect(search.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow))
      .toBe(RUN_FLOW_ROUTE_QUERY_VALUES.task);
    expect(search.get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowTaskId)).toBe('task-7');

    fireEvent.keyDown(runFlowDrawer, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '运行流' })).not.toBeInTheDocument());
    expect(renderedSearch().get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow)).toBeNull();
    expect(runFlowTrigger).toHaveFocus();
  });

  it('loads a historical report from a recordId deep link and opens its RunFlow', async () => {
    useStockPoolStore.setState({ historyItems: [historyItem] });
    renderWorkbench(buildAnalysisWorkbenchHref({ recordId: 12 }));

    expect(await screen.findByTestId('report-summary')).toHaveTextContent('Apple');
    expect(historyApi.getDetail).toHaveBeenCalledWith(12);
    expect(screen.getByRole('tab', { name: '历史与对比' })).toHaveAttribute(
      'aria-selected',
      'true',
    );

    fireEvent.click(screen.getByRole('button', { name: 'Open report run flow' }));
    expect(await screen.findByTestId('run-flow-panel')).toHaveTextContent('history');
    expect(renderedSearch().get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlow))
      .toBe(RUN_FLOW_ROUTE_QUERY_VALUES.history);
    expect(renderedSearch().get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.runFlowRecordId)).toBe('12');
  });

  it('selects the newest report when the history segment has no recordId', async () => {
    useStockPoolStore.setState({ historyItems: [historyItem] });
    renderWorkbench(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
    }));

    await waitFor(() => {
      expect(renderedSearch().get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId)).toBe('12');
    });
    expect(await screen.findByTestId('report-summary')).toBeInTheDocument();
  });

  it('moves an accepted launch directly to the tasks segment', async () => {
    useStockPoolStore.setState({ query: 'AAPL' });
    renderWorkbench();

    const analyzeButtons = await screen.findAllByRole('button', { name: '分析' });
    fireEvent.click(analyzeButtons.at(-1)!);

    await waitFor(() => {
      expect(renderedSearch().get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment))
        .toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks);
    });
    expect((await screen.findAllByText('AAPL')).length).toBeGreaterThan(0);
    expect(analysisApi.analyzeAsync).toHaveBeenCalledWith(expect.objectContaining({
      stockCode: 'AAPL',
      reportType: 'detailed',
    }));
  });

  it('consumes stock context once and allows a different symbol to be submitted', async () => {
    renderWorkbench(buildAnalysisWorkbenchHref({ stock: 'AAPL' }));
    const stockInput = document.querySelector<HTMLInputElement>('#analysis-workbench-stock-search')!;
    await waitFor(() => expect(stockInput).toHaveValue('AAPL'));

    fireEvent.change(stockInput, { target: { value: 'MSFT' } });
    await waitFor(() => expect(stockInput).toHaveValue('MSFT'));
    const analyzeButton = (await screen.findAllByRole('button', { name: '分析' })).at(-1)!;
    await waitFor(() => expect(analyzeButton).toBeEnabled());
    fireEvent.click(analyzeButton);

    await waitFor(() => expect(analysisApi.analyzeAsync).toHaveBeenCalledWith(
      expect.objectContaining({ stockCode: 'MSFT' }),
    ));
    await waitFor(() => {
      expect(renderedSearch().get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment))
        .toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks);
    });
    expect(useStockPoolStore.getState().query).not.toBe('AAPL');
  });

  it('preserves the existing beginner default until setup is complete', async () => {
    vi.mocked(systemConfigApi.getSetupStatus).mockResolvedValue({
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['LLM_CHANNELS'],
      nextStepKey: 'LLM_CHANNELS',
      checks: [],
    });
    useStockPoolStore.setState({ query: 'AAPL' });
    renderWorkbench();

    const analyzeButton = (await screen.findAllByRole('button', { name: '快速分析' })).at(-1)!;
    await waitFor(() => expect(analyzeButton).toBeEnabled());
    fireEvent.click(analyzeButton);

    await waitFor(() => expect(analysisApi.analyzeAsync).toHaveBeenCalledWith(
      expect.objectContaining({ stockCode: 'AAPL', reportType: 'brief' }),
    ));
  });

  it('keeps a partial imported batch warning visible after switching to tasks', async () => {
    const { container } = renderWorkbench();
    const file = new File(['symbol'], 'stocks.csv', { type: 'text/csv' });
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;

    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByText('已识别 2 只股票，可批量提交分析。')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '分析已导入 (2)' }));

    await waitFor(() => {
      expect(analysisApi.analyzeAsync).toHaveBeenCalledWith(expect.objectContaining({
        stockCodes: ['AAPL', 'MSFT'],
      }));
    });
    await waitFor(() => {
      expect(renderedSearch().get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment))
        .toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks);
    });
    expect(await screen.findByText(/已确认提交 1 个任务.*另有 1 只未确认/u)).toBeInTheDocument();
  });

  it('removes the previous imported batch while a replacement file is parsing', async () => {
    const replacementImport = deferredPromise<{ codes: string[] }>();
    vi.mocked(stocksApi.parseImport)
      .mockResolvedValueOnce({ codes: ['AAPL'] })
      .mockReturnValueOnce(replacementImport.promise);
    const { container } = renderWorkbench();
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;

    fireEvent.change(input, {
      target: { files: [new File(['first'], 'first.csv', { type: 'text/csv' })] },
    });
    expect(await screen.findByRole('button', { name: '分析已导入 (1)' })).toBeInTheDocument();

    fireEvent.change(input, {
      target: { files: [new File(['second'], 'second.csv', { type: 'text/csv' })] },
    });
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /分析已导入/u })).not.toBeInTheDocument();
    });

    await act(async () => {
      replacementImport.resolve({ codes: ['MSFT', 'GOOG'] });
      await replacementImport.promise;
    });
    expect(await screen.findByRole('button', { name: '分析已导入 (2)' })).toBeInTheDocument();
  });

  it('submits only watchlist symbols not analyzed today', async () => {
    watchlistCodes = ['AAPL', 'MSFT'];
    useStockPoolStore.setState({
      stockBarItems: [
        stockBarItem(1, 'AAPL', new Date().toISOString()),
        stockBarItem(2, 'MSFT', '2020-01-01T00:00:00Z'),
      ],
      isLoadingStockBar: false,
      stockBarRefreshFailed: false,
    });
    renderWorkbench();

    const pendingButton = await screen.findByRole('button', { name: '仅未分析' });
    await waitFor(() => expect(pendingButton).toBeEnabled());
    fireEvent.click(pendingButton);

    await waitFor(() => expect(analysisApi.analyzeAsync).toHaveBeenCalledWith(
      expect.objectContaining({ stockCodes: ['MSFT'] }),
    ));
  });

  it('blocks pending-only submission while today coverage is unavailable', async () => {
    watchlistCodes = ['AAPL'];
    useStockPoolStore.setState({
      stockBarItems: [stockBarItem(1, 'AAPL', '2020-01-01T00:00:00Z')],
      isLoadingStockBar: false,
      stockBarRefreshFailed: true,
    });
    renderWorkbench();

    const pendingButton = await screen.findByRole('button', { name: '仅未分析' });
    expect(pendingButton).toBeDisabled();
    expect(pendingButton).toHaveAttribute(
      'title',
      '自选股今日状态仍有未知项，请刷新后再提交仅未分析。',
    );
    expect(analysisApi.analyzeAsync).not.toHaveBeenCalled();
  });

  it('offers a completion toast action that deep-links to the finished report', async () => {
    const refreshCompleted = vi.fn().mockResolvedValue(historyItem);
    useStockPoolStore.setState({ refreshHistoryForCompletedTask: refreshCompleted });
    renderWorkbench(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
    }));

    expect(lifecycleOptions).not.toBeNull();
    await act(async () => {
      await lifecycleOptions?.refreshHistoryForCompletedTask?.({
        ...runningTask,
        status: 'completed',
        progress: 100,
      });
      lifecycleOptions?.onCompletedTaskDataRefreshed?.({
        ...runningTask,
        status: 'completed',
        progress: 100,
      });
    });

    expect(await screen.findByText('分析已完成')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看报告' }));
    expect(renderedSearch().get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment))
      .toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.history);
    expect(renderedSearch().get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId)).toBe('12');
  });

  it('keeps the completion toast actionable while history persistence catches up', async () => {
    const refreshCompleted = vi.fn().mockResolvedValue(null);
    useStockPoolStore.setState({ refreshHistoryForCompletedTask: refreshCompleted });
    renderWorkbench(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
    }));

    await act(async () => {
      await lifecycleOptions?.refreshHistoryForCompletedTask?.({
        ...runningTask,
        status: 'completed',
        progress: 100,
      });
      lifecycleOptions?.onCompletedTaskDataRefreshed?.({
        ...runningTask,
        status: 'completed',
        progress: 100,
      });
    });

    fireEvent.click(await screen.findByRole('button', { name: '查看报告' }));
    expect(renderedSearch().get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment))
      .toBe(ANALYSIS_WORKBENCH_SEGMENT_VALUES.history);
  });

  it.each([
    { status: 401, code: 'unauthorized' },
    { status: 403, code: 'forbidden' },
    { status: 404, code: 'not_found' },
  ])('removes a permanently unavailable report intent for HTTP $status', async ({ status, code }) => {
    useStockPoolStore.setState({ historyItems: [historyItem] });
    vi.mocked(historyApi.getDetail).mockRejectedValue({
      response: {
        status,
        data: { error: code, message: 'The requested report is unavailable.' },
      },
    });
    renderWorkbench(buildAnalysisWorkbenchHref({ recordId: 404 }));

    await waitFor(() => {
      expect(renderedSearch().get(ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId)).toBeNull();
    });
    expect(screen.getByRole('alert')).toHaveTextContent('The requested report is unavailable.');
    expect(historyApi.getDetail).toHaveBeenCalledTimes(1);
    expect(useStockPoolStore.getState().selectedRecordId).toBeNull();
  });

  it('gives an empty history segment a primary launch action', async () => {
    renderWorkbench(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
    }));

    expect(await screen.findByText('暂无历史分析记录')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '发起与批量' }))
      .toHaveAttribute('data-variant', 'primary');
  });
});
