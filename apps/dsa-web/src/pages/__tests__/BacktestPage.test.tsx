import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import { UI_LANGUAGE_STORAGE_KEY } from '../../utils/uiLanguage';
import BacktestPage from '../BacktestPage';

// jsdom 未实现 scrollIntoView，而 Select 打开下拉时会调用它保持活动项可见。
if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

function chooseOption(trigger: HTMLElement, value: string) {
  fireEvent.click(trigger);
  const listbox = document.getElementById(trigger.getAttribute('aria-controls')!)!;
  const option = within(listbox)
    .getAllByRole('option')
    .find((item) => item.getAttribute('data-value') === value)!;
  fireEvent.click(option);
}

const {
  mockGetResults,
  mockGetOverallPerformance,
  mockGetStockPerformance,
  mockRun,
} = vi.hoisted(() => ({
  mockGetResults: vi.fn(),
  mockGetOverallPerformance: vi.fn(),
  mockGetStockPerformance: vi.fn(),
  mockRun: vi.fn(),
}));

vi.mock('../../api/backtest', () => ({
  backtestApi: {
    getResults: mockGetResults,
    getOverallPerformance: mockGetOverallPerformance,
    getStockPerformance: mockGetStockPerformance,
    run: mockRun,
  },
}));

const basePerformance = {
  scope: 'overall',
  evalWindowDays: 10,
  engineVersion: 'test-engine',
  totalEvaluations: 3,
  completedCount: 2,
  insufficientCount: 1,
  longCount: 2,
  cashCount: 1,
  winCount: 1,
  lossCount: 1,
  neutralCount: 0,
  directionAccuracyPct: 66.7,
  winRatePct: 50,
  neutralRatePct: 0,
  avgStockReturnPct: 2.4,
  avgSimulatedReturnPct: 1.2,
  stopLossTriggerRate: 10,
  takeProfitTriggerRate: 20,
  ambiguousRate: 0,
  avgDaysToFirstHit: 3.5,
  adviceBreakdown: {},
  diagnostics: {},
};

const baseResultItem = {
  analysisHistoryId: 101,
  code: '600519',
  stockName: '贵州茅台',
  analysisDate: '2026-03-20',
  evalWindowDays: 10,
  engineVersion: 'test-engine',
  evalStatus: 'completed',
  operationAdvice: '继续持有',
  action: 'watch',
  actionLabel: '观望',
  trendPrediction: '震荡偏多',
  actualMovement: 'up',
  actualReturnPct: 3.8,
  directionExpected: 'long',
  directionCorrect: true,
  outcome: 'win',
  simulatedReturnPct: 3.8,
};

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

function renderBacktestPage(initialEntry = '/backtest', language: 'zh' | 'en' = 'zh') {
  window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, language);
  const router = createMemoryRouter(
    [
      {
        path: '/backtest',
        element: (
          <UiLanguageProvider>
            <BacktestPage />
          </UiLanguageProvider>
        ),
      },
    ],
    { initialEntries: [initialEntry] },
  );
  render(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  mockGetOverallPerformance.mockResolvedValue(basePerformance);
  mockGetStockPerformance.mockResolvedValue(null);
  mockGetResults.mockResolvedValue({
    total: 1,
    page: 1,
    limit: 20,
    items: [baseResultItem],
  });
  mockRun.mockResolvedValue({
    processed: 1,
    saved: 1,
    completed: 1,
    insufficient: 0,
    errors: 0,
  });
});

describe('BacktestPage', () => {
  function renderEnglishPage() {
    return renderBacktestPage('/backtest', 'en');
  }

  it('renders shared surface inputs and prediction tracking outputs', async () => {
    renderBacktestPage();

    const filterInput = await screen.findByPlaceholderText('按股票代码筛选（留空表示全部）');
    const windowInput = screen.getByPlaceholderText('10');

    expect(filterInput).toHaveClass('h-8');
    expect(filterInput).toHaveClass('rounded-[10px]');
    expect(windowInput).toHaveClass('h-8');
    expect(windowInput).toHaveClass('rounded-[10px]');

    expect(await screen.findByText('盈利')).toBeInTheDocument();
    expect(screen.getByText('已完成')).toBeInTheDocument();
    expect(screen.getByText('600519')).toBeInTheDocument();
    expect(screen.getByText('贵州茅台')).toBeInTheDocument();
    const resultRow = screen.getByText('600519').closest('tr');
    expect(resultRow).not.toBeNull();
    const rowScope = within(resultRow as HTMLElement);
    expect(rowScope.getByText('观望')).toBeInTheDocument();
    expect(rowScope.getByText('震荡偏多')).toBeInTheDocument();
    expect(rowScope.getByText('继续持有')).toBeInTheDocument();
    expect(screen.getByText('上涨')).toBeInTheDocument();
    expect(screen.getByText('窗口收益')).toBeInTheDocument();
    expect(screen.getByText('方向匹配')).toBeInTheDocument();
    expect(screen.getByText('做多')).toBeInTheDocument();
    expect(screen.getAllByLabelText('是').length).toBeGreaterThan(0);
    expect(screen.getByText('方向准确率')).toBeInTheDocument();
    expect(screen.getByText('平均模拟收益')).toBeInTheDocument();
  });

  it('falls back to the taxonomy label when backtest actionLabel is missing', async () => {
    mockGetResults.mockResolvedValueOnce({
      total: 1,
      page: 1,
      limit: 20,
      items: [
        {
          ...baseResultItem,
          action: 'watch',
          actionLabel: null,
        },
      ],
    });

    renderBacktestPage();

    const codeCell = await screen.findByText('600519');
    const resultRow = codeCell.closest('tr');
    expect(resultRow).not.toBeNull();
    const rowScope = within(resultRow as HTMLElement);
    expect(rowScope.getByText('观望')).toBeInTheDocument();
    expect(rowScope.getByText('继续持有')).toBeInTheDocument();
  });

  it('uses localized taxonomy labels before server labels in English UI mode', async () => {
    mockGetResults.mockResolvedValueOnce({
      total: 1,
      page: 1,
      limit: 20,
      items: [
        {
          ...baseResultItem,
          operationAdvice: 'continue holding',
          action: 'watch',
          actionLabel: '观望',
          trendPrediction: 'range-bound',
        },
      ],
    });

    renderEnglishPage();

    const codeCell = await screen.findByText('600519');
    const resultRow = codeCell.closest('tr');
    expect(resultRow).not.toBeNull();
    const rowScope = within(resultRow as HTMLElement);
    expect(rowScope.getByText('Watch')).toBeInTheDocument();
    expect(rowScope.getByText('continue holding')).toBeInTheDocument();
    expect(rowScope.queryByText('观望')).not.toBeInTheDocument();
  });

  it('keeps operation advice visible when backtest action fields are absent for multi-guard advice', async () => {
    mockGetResults.mockResolvedValueOnce({
      total: 1,
      page: 1,
      limit: 20,
      items: [
        {
          ...baseResultItem,
          operationAdvice: 'risk alert, avoid buying',
          action: null,
          actionLabel: null,
        },
      ],
    });

    renderBacktestPage();

    const codeCell = await screen.findByText('600519');
    const resultRow = codeCell.closest('tr');
    expect(resultRow).not.toBeNull();
    const rowScope = within(resultRow as HTMLElement);
    expect(rowScope.getByText('震荡偏多')).toBeInTheDocument();
    expect(rowScope.getByText('risk alert, avoid buying')).toBeInTheDocument();
    expect(rowScope.queryByText('回避')).not.toBeInTheDocument();
    expect(rowScope.queryByText('预警')).not.toBeInTheDocument();
  });

  it('renders backtest controls and result headings in English UI mode', async () => {
    renderEnglishPage();

    expect(await screen.findByPlaceholderText('Filter by stock code (leave empty for all)')).toBeInTheDocument();
    expect(screen.getByText('Evaluation window')).toBeInTheDocument();
    expect(screen.getAllByText('Phase').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Run backtest' })).toBeInTheDocument();
    expect(screen.getByText('Window return')).toBeInTheDocument();
    expect(screen.getByText('Direction match')).toBeInTheDocument();
    expect(screen.getByText('Direction accuracy')).toBeInTheDocument();
    expect(screen.queryByText('运行回测')).not.toBeInTheDocument();
    expect(screen.queryByText('窗口收益')).not.toBeInTheDocument();
  });

  it('hydrates filters and requests from the initial URL', async () => {
    mockGetResults.mockResolvedValueOnce({
      total: 61,
      page: 3,
      limit: 20,
      items: [baseResultItem],
    });
    mockGetStockPerformance.mockResolvedValueOnce({
      ...basePerformance,
      scope: 'stock',
      code: 'AAPL',
    });

    const router = renderBacktestPage(
      '/backtest?code=aapl&window=20&from=2026-03-01&to=2026-03-31&phase=intraday&page=3',
    );

    expect(await screen.findByPlaceholderText('按股票代码筛选（留空表示全部）')).toHaveValue('AAPL');
    expect(screen.getByPlaceholderText('10')).toHaveValue(20);
    expect(screen.getByLabelText('分析开始日期')).toHaveValue('2026-03-01');
    expect(screen.getByLabelText('分析结束日期')).toHaveValue('2026-03-31');
    expect(screen.getByLabelText('结果筛选 · 阶段')).toHaveTextContent('盘中');

    await waitFor(() => {
      expect(mockGetResults).toHaveBeenCalledWith({
        code: 'AAPL',
        evalWindowDays: 20,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
        analysisPhase: 'intraday',
        page: 3,
        limit: 20,
      });
      expect(mockGetStockPerformance).toHaveBeenCalledWith('AAPL', {
        evalWindowDays: 20,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
        analysisPhase: 'intraday',
      });
      expect(new URLSearchParams(router.state.location.search).get('code')).toBe('AAPL');
    });
  });

  it('replaces invalid route values with the canonical default state', async () => {
    mockGetOverallPerformance.mockResolvedValueOnce(null);
    const router = renderBacktestPage(
      '/backtest?code=aapl&window=121&from=2026-02-30&to=bad&phase=closing&page=0',
    );

    await waitFor(() => {
      expect(mockGetResults).toHaveBeenCalledWith({
        code: 'AAPL',
        evalWindowDays: undefined,
        analysisDateFrom: undefined,
        analysisDateTo: undefined,
        analysisPhase: undefined,
        page: 1,
        limit: 20,
      });
    });

    const params = new URLSearchParams(router.state.location.search);
    expect(params.get('code')).toBe('AAPL');
    expect(params.has('window')).toBe(false);
    expect(params.has('from')).toBe(false);
    expect(params.has('to')).toBe(false);
    expect(params.has('phase')).toBe(false);
    expect(params.has('page')).toBe(false);
  });

  it('filters results with stock code, window, phase, and analysis date range when clicking Filter', async () => {
    const router = renderBacktestPage();

    const filterInput = await screen.findByPlaceholderText('按股票代码筛选（留空表示全部）');
    const windowInput = screen.getByPlaceholderText('10');
    const phaseSelect = screen.getByLabelText('结果筛选 · 阶段');
    expect(phaseSelect).toHaveTextContent('全部阶段');
    const fromInput = screen.getByLabelText('分析开始日期');
    const toInput = screen.getByLabelText('分析结束日期');

    fireEvent.change(filterInput, { target: { value: 'aapl' } });
    fireEvent.change(windowInput, { target: { value: '20' } });
    chooseOption(phaseSelect, 'intraday');
    // Phase applies immediately; wait for that fetch to settle so the Filter
    // button (disabled while results load) re-enables before we click it.
    await waitFor(() =>
      expect(mockGetResults).toHaveBeenCalledWith(expect.objectContaining({ analysisPhase: 'intraday' })),
    );
    fireEvent.change(fromInput, { target: { value: '2026-03-01' } });
    fireEvent.change(toInput, { target: { value: '2026-03-31' } });
    fireEvent.click(screen.getByRole('button', { name: '筛选' }));

    await waitFor(() => {
      expect(mockGetResults).toHaveBeenCalledWith({
        code: 'AAPL',
        evalWindowDays: 20,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
        analysisPhase: 'intraday',
        page: 1,
        limit: 20,
      });
      expect(mockGetStockPerformance).toHaveBeenCalledWith('AAPL', {
        evalWindowDays: 20,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
        analysisPhase: 'intraday',
      });
    });

    const params = new URLSearchParams(router.state.location.search);
    expect(params.get('code')).toBe('AAPL');
    expect(params.get('window')).toBe('20');
    expect(params.get('from')).toBe('2026-03-01');
    expect(params.get('to')).toBe('2026-03-31');
    expect(params.get('phase')).toBe('intraday');
    expect(params.has('page')).toBe(false);
  });

  it('applies the phase filter immediately without waiting for Filter or Run', async () => {
    renderBacktestPage();

    const filterInput = await screen.findByPlaceholderText('按股票代码筛选（留空表示全部）');
    fireEvent.change(filterInput, { target: { value: 'aapl' } });
    const phaseSelect = screen.getByLabelText('结果筛选 · 阶段');

    mockGetResults.mockClear();
    mockGetStockPerformance.mockClear();
    mockRun.mockClear();
    chooseOption(phaseSelect, 'intraday');

    await waitFor(() => {
      expect(mockGetResults).toHaveBeenCalledWith(
        expect.objectContaining({ code: 'AAPL', analysisPhase: 'intraday', page: 1 }),
      );
      expect(mockGetStockPerformance).toHaveBeenCalledWith(
        'AAPL',
        expect.objectContaining({ analysisPhase: 'intraday' }),
      );
    });
    // The phase filter must never be sent to the run endpoint.
    expect(mockRun).not.toHaveBeenCalled();
  });

  it('runs a backtest and refreshes results using the shared filter values', async () => {
    mockRun.mockResolvedValueOnce({
      processed: 0,
      saved: 0,
      completed: 0,
      insufficient: 0,
      errors: 0,
      message: '未找到符合条件的历史分析记录',
      diagnostics: { emptyReason: 'no_matching_analysis' },
    });
    renderBacktestPage();

    const filterInput = await screen.findByPlaceholderText('按股票代码筛选（留空表示全部）');
    const windowInput = screen.getByPlaceholderText('10');
    const fromInput = screen.getByLabelText('分析开始日期');
    const toInput = screen.getByLabelText('分析结束日期');

    fireEvent.change(filterInput, { target: { value: '600519.SH' } });
    fireEvent.change(windowInput, { target: { value: '15' } });
    fireEvent.change(fromInput, { target: { value: '2026-03-01' } });
    fireEvent.change(toInput, { target: { value: '2026-03-31' } });
    fireEvent.click(screen.getByRole('button', { name: '运行回测' }));

    await waitFor(() => {
      expect(mockRun).toHaveBeenCalledWith({
        code: '600519.SH',
        force: undefined,
        minAgeDays: undefined,
        evalWindowDays: 15,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
      });
    });

    await waitFor(() => {
      expect(mockGetResults).toHaveBeenLastCalledWith({
        code: '600519.SH',
        evalWindowDays: 15,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
        analysisPhase: undefined,
        page: 1,
        limit: 20,
      });
      expect(mockGetStockPerformance).toHaveBeenLastCalledWith('600519.SH', {
        evalWindowDays: 15,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
        analysisPhase: undefined,
      });
    });

    expect(await screen.findByText('已处理:')).toBeInTheDocument();
    expect(screen.getByText('已保存:')).toBeInTheDocument();
    expect(screen.getByText('未找到符合条件的历史分析记录')).toBeInTheDocument();
  });

  it('uses backend-applied eval window when run input is empty', async () => {
    mockRun.mockResolvedValueOnce({
      processed: 0,
      saved: 0,
      completed: 0,
      insufficient: 0,
      errors: 0,
      appliedEvalWindowDays: 10,
      message: '未找到符合条件的历史分析记录',
      diagnostics: { emptyReason: 'no_matching_analysis' },
    });
    renderBacktestPage();

    const filterInput = await screen.findByPlaceholderText('按股票代码筛选（留空表示全部）');
    const windowInput = screen.getByPlaceholderText('10');
    const fromInput = screen.getByLabelText('分析开始日期');
    const toInput = screen.getByLabelText('分析结束日期');

    fireEvent.change(filterInput, { target: { value: '600519.SH' } });
    fireEvent.change(windowInput, { target: { value: '' } });
    fireEvent.change(fromInput, { target: { value: '2026-03-01' } });
    fireEvent.change(toInput, { target: { value: '2026-03-31' } });
    fireEvent.click(screen.getByRole('button', { name: '运行回测' }));

    await waitFor(() => {
      expect(mockRun).toHaveBeenCalledWith({
        code: '600519.SH',
        force: undefined,
        minAgeDays: undefined,
        evalWindowDays: undefined,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
      });
    });

    await waitFor(() => {
      expect(windowInput).toHaveValue(10);
      expect(mockGetResults).toHaveBeenLastCalledWith({
        code: '600519.SH',
        evalWindowDays: 10,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
        analysisPhase: undefined,
        page: 1,
        limit: 20,
      });
      expect(mockGetStockPerformance).toHaveBeenLastCalledWith('600519.SH', {
        evalWindowDays: 10,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
        analysisPhase: undefined,
      });
      expect(mockGetOverallPerformance).toHaveBeenLastCalledWith({
        evalWindowDays: 10,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
        analysisPhase: undefined,
      });
    });

    expect(await screen.findByText('未找到符合条件的历史分析记录')).toBeInTheDocument();
  });

  it('switches to next-day validation with the 1D shortcut', async () => {
    const router = renderBacktestPage();

    await screen.findByPlaceholderText('按股票代码筛选（留空表示全部）');
    fireEvent.click(screen.getByRole('button', { name: '1 日验证' }));

    await waitFor(() => {
      expect(mockGetResults).toHaveBeenLastCalledWith({
        code: undefined,
        evalWindowDays: 1,
        analysisDateFrom: undefined,
        analysisDateTo: undefined,
        analysisPhase: undefined,
        page: 1,
        limit: 20,
      });
      expect(mockGetOverallPerformance).toHaveBeenLastCalledWith({
        evalWindowDays: 1,
        analysisDateFrom: undefined,
        analysisDateTo: undefined,
        analysisPhase: undefined,
      });
    });

    expect(screen.getByText('实际表现')).toBeInTheDocument();
    expect(screen.getByText('准确性')).toBeInTheDocument();
    expect(screen.getByText('1 日验证模式会用下一个交易日收盘表现校验 AI 预测。')).toBeInTheDocument();
    expect(new URLSearchParams(router.state.location.search).get('window')).toBe('1');
  });

  it('paginates with applied URL filters instead of unsubmitted drafts', async () => {
    mockGetResults.mockImplementation(async (params: { page?: number }) => ({
      total: 60,
      page: params.page ?? 1,
      limit: 20,
      items: [baseResultItem],
    }));
    const router = renderBacktestPage(
      '/backtest?code=MSFT&window=10&from=2026-02-01&to=2026-02-28&phase=premarket',
    );

    const codeInput = await screen.findByPlaceholderText('按股票代码筛选（留空表示全部）');
    const windowInput = screen.getByPlaceholderText('10');
    await screen.findByRole('button', { name: '下一页' });

    fireEvent.change(codeInput, { target: { value: 'AAPL' } });
    fireEvent.change(windowInput, { target: { value: '30' } });
    fireEvent.change(screen.getByLabelText('分析开始日期'), { target: { value: '2026-03-01' } });
    fireEvent.change(screen.getByLabelText('分析结束日期'), { target: { value: '2026-03-31' } });
    fireEvent.click(screen.getByRole('button', { name: '下一页' }));

    await waitFor(() => {
      expect(mockGetResults).toHaveBeenLastCalledWith({
        code: 'MSFT',
        evalWindowDays: 10,
        analysisDateFrom: '2026-02-01',
        analysisDateTo: '2026-02-28',
        analysisPhase: 'premarket',
        page: 2,
        limit: 20,
      });
    });

    const params = new URLSearchParams(router.state.location.search);
    expect(params.get('code')).toBe('MSFT');
    expect(params.get('page')).toBe('2');
    expect(codeInput).toHaveValue('MSFT');
    expect(windowInput).toHaveValue(10);
  });

  it('restores applied filters and requests across browser back and forward', async () => {
    mockGetResults.mockImplementation(async (params: { code?: string; page?: number }) => ({
      total: 1,
      page: params.page ?? 1,
      limit: 20,
      items: [{ ...baseResultItem, code: params.code ?? 'ALL' }],
    }));
    const router = renderBacktestPage('/backtest?code=BASE&window=10');
    const codeInput = await screen.findByPlaceholderText('按股票代码筛选（留空表示全部）');
    const windowInput = screen.getByPlaceholderText('10');
    const filterButton = screen.getByRole('button', { name: '筛选' });

    fireEvent.change(codeInput, { target: { value: 'AAPL' } });
    fireEvent.change(windowInput, { target: { value: '20' } });
    fireEvent.click(filterButton);
    await waitFor(() => expect(router.state.location.search).toContain('code=AAPL'));
    await waitFor(() => expect(filterButton).not.toBeDisabled());

    fireEvent.change(codeInput, { target: { value: 'MSFT' } });
    fireEvent.change(windowInput, { target: { value: '30' } });
    fireEvent.click(filterButton);
    await waitFor(() => expect(router.state.location.search).toContain('code=MSFT'));

    mockGetResults.mockClear();
    await act(async () => {
      await router.navigate(-1);
    });
    await waitFor(() => {
      expect(codeInput).toHaveValue('AAPL');
      expect(windowInput).toHaveValue(20);
      expect(mockGetResults).toHaveBeenLastCalledWith(expect.objectContaining({
        code: 'AAPL',
        evalWindowDays: 20,
        page: 1,
      }));
    });

    mockGetResults.mockClear();
    await act(async () => {
      await router.navigate(1);
    });
    await waitFor(() => {
      expect(codeInput).toHaveValue('MSFT');
      expect(windowInput).toHaveValue(30);
      expect(mockGetResults).toHaveBeenLastCalledWith(expect.objectContaining({
        code: 'MSFT',
        evalWindowDays: 30,
        page: 1,
      }));
    });
  });

  it('refreshes an unchanged applied route after a run without sending phase', async () => {
    const router = renderBacktestPage('/backtest?code=AAPL&window=10&phase=intraday');
    await screen.findByText('贵州茅台');
    const searchBeforeRun = router.state.location.search;
    mockGetResults.mockClear();
    mockGetOverallPerformance.mockClear();
    mockGetStockPerformance.mockClear();

    fireEvent.click(screen.getByRole('button', { name: '运行回测' }));

    await waitFor(() => {
      expect(mockRun).toHaveBeenCalledWith({
        code: 'AAPL',
        force: undefined,
        minAgeDays: undefined,
        evalWindowDays: 10,
        analysisDateFrom: undefined,
        analysisDateTo: undefined,
      });
      expect(mockGetResults).toHaveBeenCalledWith(expect.objectContaining({
        code: 'AAPL',
        evalWindowDays: 10,
        analysisPhase: 'intraday',
        page: 1,
      }));
      expect(mockGetOverallPerformance).toHaveBeenCalledWith(expect.objectContaining({
        evalWindowDays: 10,
        analysisPhase: 'intraday',
      }));
    });
    expect(router.state.location.search).toBe(searchBeforeRun);
  });

  it('keeps the latest results and performance when filters resolve out of order', async () => {
    renderBacktestPage('/backtest?window=10');
    const filterInput = await screen.findByPlaceholderText('按股票代码筛选（留空表示全部）');
    await screen.findByText('贵州茅台');

    const staleResults = createDeferred<{
      total: number;
      page: number;
      limit: number;
      items: Array<typeof baseResultItem>;
    }>();
    const latestResults = createDeferred<{
      total: number;
      page: number;
      limit: number;
      items: Array<typeof baseResultItem>;
    }>();
    const stalePerformance = createDeferred<typeof basePerformance>();
    const latestPerformance = createDeferred<typeof basePerformance>();
    mockGetResults
      .mockReset()
      .mockReturnValueOnce(staleResults.promise)
      .mockReturnValueOnce(latestResults.promise);
    mockGetOverallPerformance
      .mockReset()
      .mockReturnValueOnce(stalePerformance.promise)
      .mockReturnValueOnce(latestPerformance.promise);
    mockGetStockPerformance.mockResolvedValue({
      ...basePerformance,
      scope: 'stock',
      code: 'AAPL',
      directionAccuracyPct: 99,
    });

    fireEvent.change(filterInput, { target: { value: 'aapl' } });
    const phaseSelect = screen.getByLabelText('结果筛选 · 阶段');
    chooseOption(phaseSelect, 'intraday');
    chooseOption(phaseSelect, 'postmarket');

    await waitFor(() => {
      expect(mockGetResults).toHaveBeenCalledTimes(2);
      expect(mockGetOverallPerformance).toHaveBeenCalledTimes(2);
    });

    await act(async () => {
      latestResults.resolve({
        total: 1,
        page: 1,
        limit: 20,
        items: [{ ...baseResultItem, code: 'LATEST', stockName: '最新结果' }],
      });
      latestPerformance.resolve({ ...basePerformance, directionAccuracyPct: 88 });
      await Promise.all([latestResults.promise, latestPerformance.promise]);
    });
    expect(await screen.findByText('LATEST')).toBeInTheDocument();
    expect(await screen.findByText('88.0%')).toBeInTheDocument();

    await act(async () => {
      staleResults.resolve({
        total: 1,
        page: 1,
        limit: 20,
        items: [{ ...baseResultItem, code: 'STALE', stockName: '旧结果' }],
      });
      stalePerformance.resolve({ ...basePerformance, directionAccuracyPct: 1 });
      await Promise.all([staleResults.promise, stalePerformance.promise]);
    });

    expect(screen.getByText('LATEST')).toBeInTheDocument();
    expect(screen.getByText('88.0%')).toBeInTheDocument();
    expect(screen.queryByText('STALE')).not.toBeInTheDocument();
    expect(screen.queryByText('1.0%')).not.toBeInTheDocument();
    expect(mockGetStockPerformance).toHaveBeenCalledTimes(1);
  });

  it('loads results independently when the initial performance request fails', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    mockGetOverallPerformance.mockRejectedValueOnce(new Error('performance unavailable'));

    renderBacktestPage();

    expect(await screen.findByText('贵州茅台')).toBeInTheDocument();
    expect(mockGetResults).toHaveBeenCalledWith(expect.objectContaining({ page: 1, limit: 20 }));
    consoleError.mockRestore();
  });
});
