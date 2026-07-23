import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import { UI_LANGUAGE_STORAGE_KEY } from '../../utils/uiLanguage';
import BacktestPage from '../BacktestPage';

// jsdom does not implement scrollIntoView, while Select calls it to keep the active item visible when opening a dropdown.
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

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => {
    resolve = next;
  });
  return { promise, resolve };
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

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.history.replaceState({}, '', APP_ROUTE_PATHS.researchBacktest);
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
  function renderPage() {
    return render(
      <BrowserRouter>
        <BacktestPage />
      </BrowserRouter>,
    );
  }

  function renderEnglishPage() {
    window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'en');
    render(
      <BrowserRouter>
        <UiLanguageProvider>
          <BacktestPage />
        </UiLanguageProvider>
      </BrowserRouter>,
    );
  }

  it('renders shared surface inputs and prediction tracking outputs', async () => {
    renderPage();

    const filterInput = await screen.findByPlaceholderText('按股票代码筛选（留空表示全部）');
    const windowInput = screen.getByPlaceholderText('10');
    const startDateInput = screen.getByLabelText('分析开始日期');
    const endDateInput = screen.getByLabelText('分析结束日期');

    expect(filterInput).toHaveAttribute('data-control', 'input');
    expect(filterInput).toHaveAttribute('data-size', 'default');
    expect(windowInput).toHaveAttribute('data-control', 'input');
    expect(windowInput).toHaveAttribute('data-size', 'default');
    expect(screen.getByRole('button', { name: '筛选' })).toHaveAttribute('data-size', 'primary');
    expect(screen.getByRole('button', { name: '运行回测' })).toHaveAttribute('data-size', 'primary');
    expect(startDateInput).toHaveAttribute('aria-haspopup', 'dialog');
    expect(startDateInput).toHaveAttribute('aria-expanded', 'false');
    expect(endDateInput).toHaveAttribute('aria-haspopup', 'dialog');
    expect(endDateInput).toHaveAttribute('aria-expanded', 'false');
    expect(startDateInput.parentElement).toHaveAttribute('data-size', 'compact');
    expect(endDateInput.parentElement).toHaveAttribute('data-size', 'compact');

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

  it('renders one page-level empty state before any backtest data exists', async () => {
    mockGetOverallPerformance.mockResolvedValueOnce(null);
    mockGetResults.mockResolvedValue({
      total: 0,
      page: 1,
      limit: 20,
      items: [],
    });

    renderPage();

    expect(await screen.findByRole('heading', { name: '暂无结果' })).toBeInTheDocument();
    expect(screen.getAllByText('暂无结果')).toHaveLength(1);
    expect(screen.getByRole('button', { name: '运行回测 · 暂无结果' }))
      .toHaveAttribute('data-variant', 'primary');
    expect(screen.queryByLabelText('结果筛选 · 阶段')).not.toBeInTheDocument();
    expect(screen.queryByText('暂无指标')).not.toBeInTheDocument();
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

    renderPage();

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

    renderPage();

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
    type ResultsResponse = {
      total: number;
      page: number;
      limit: number;
      items: Array<typeof baseResultItem>;
    };
    let resolveResults!: (response: ResultsResponse) => void;
    const delayedResults = new Promise<ResultsResponse>((resolve) => {
      resolveResults = resolve;
    });
    mockGetResults.mockReturnValueOnce(delayedResults);
    renderEnglishPage();

    expect(await screen.findByPlaceholderText('Filter by stock code (leave empty for all)'))
      .toHaveAttribute('data-size', 'default');
    expect(screen.getByRole('tab', { name: 'Evaluation window' })).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByLabelText('Result filters · Phase')).toHaveTextContent('All phases');
    expect(screen.getByRole('button', { name: 'Run backtest' })).toBeInTheDocument();

    await act(async () => {
      resolveResults({ total: 1, page: 1, limit: 20, items: [baseResultItem] });
      await delayedResults;
    });

    expect(await screen.findByText('Window return')).toBeInTheDocument();
    expect(screen.getByText('Direction match')).toBeInTheDocument();
    expect(screen.getByText('Direction accuracy')).toBeInTheDocument();
    expect(screen.queryByText('运行回测')).not.toBeInTheDocument();
    expect(screen.queryByText('窗口收益')).not.toBeInTheDocument();
  });

  it('filters results with stock code, window, phase, and analysis date range when clicking Filter', async () => {
    window.history.replaceState(
      {},
      '',
      `${APP_ROUTE_PATHS.researchBacktest}?ref=dashboard#results`,
    );
    renderPage();

    const filterInput = await screen.findByPlaceholderText('按股票代码筛选（留空表示全部）');
    const windowInput = screen.getByPlaceholderText('10');
    const phaseSelect = await screen.findByLabelText('结果筛选 · 阶段');
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
    expect(new URLSearchParams(window.location.search).get('ref')).toBe('dashboard');
    expect(window.location.hash).toBe('#results');
  });

  it('applies the phase filter immediately without waiting for Filter or Run', async () => {
    renderPage();

    const filterInput = await screen.findByPlaceholderText('按股票代码筛选（留空表示全部）');
    fireEvent.change(filterInput, { target: { value: 'aapl' } });
    const phaseSelect = await screen.findByLabelText('结果筛选 · 阶段');

    mockGetResults.mockClear();
    mockGetStockPerformance.mockClear();
    mockRun.mockClear();
    chooseOption(phaseSelect, 'intraday');

    await waitFor(() => {
      expect(mockGetResults).toHaveBeenCalledWith(
        expect.objectContaining({ code: undefined, analysisPhase: 'intraday', page: 1 }),
      );
      expect(mockGetOverallPerformance).toHaveBeenCalledWith(
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
    renderPage();

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

  it('rejects an empty evaluation window before running a backtest', async () => {
    renderPage();

    const filterInput = await screen.findByPlaceholderText('按股票代码筛选（留空表示全部）');
    const windowInput = screen.getByPlaceholderText('10');
    const fromInput = screen.getByLabelText('分析开始日期');
    const toInput = screen.getByLabelText('分析结束日期');

    fireEvent.change(filterInput, { target: { value: '600519.SH' } });
    fireEvent.change(windowInput, { target: { value: '' } });
    fireEvent.change(fromInput, { target: { value: '2026-03-01' } });
    fireEvent.change(toInput, { target: { value: '2026-03-31' } });
    fireEvent.click(screen.getByRole('button', { name: '运行回测' }));

    expect(mockRun).not.toHaveBeenCalled();
    expect(windowInput).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('评估窗口必须是 1 到 120 之间的整数')).toBeInTheDocument();
    expect(windowInput).toHaveFocus();
  });

  it('switches to next-day validation with the 1D shortcut', async () => {
    renderPage();

    await screen.findByText('600519');
    const oneDayButton = screen.getByRole('tab', { name: '1 日验证' });
    expect(oneDayButton).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByRole('switch', { name: '强制重跑' })).toHaveAttribute('aria-checked', 'false');
    const nextDayResults = createDeferred<{
      total: number;
      page: number;
      limit: number;
      items: typeof baseResultItem[];
    }>();
    const nextDayPerformance = createDeferred<typeof basePerformance>();
    mockGetResults.mockReturnValueOnce(nextDayResults.promise);
    mockGetOverallPerformance.mockReturnValueOnce(nextDayPerformance.promise);
    fireEvent.click(oneDayButton);

    expect(await screen.findByText('正在加载结果...')).toBeInTheDocument();
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

    await act(async () => {
      nextDayResults.resolve({
        total: 1,
        page: 1,
        limit: 20,
        items: [{ ...baseResultItem, evalWindowDays: 1 }],
      });
      nextDayPerformance.resolve({ ...basePerformance, evalWindowDays: 1 });
      await Promise.all([nextDayResults.promise, nextDayPerformance.promise]);
    });

    expect(await screen.findByText('实际表现')).toBeInTheDocument();
    expect(screen.queryByText('正在加载结果...')).not.toBeInTheDocument();
    expect(screen.getByText('准确性')).toBeInTheDocument();
    expect(screen.getByText('1 日验证模式会用下一个交易日收盘表现校验 AI 预测。')).toBeInTheDocument();
    expect(oneDayButton).toHaveAttribute('aria-selected', 'true');

    fireEvent.click(screen.getByRole('tab', { name: '评估窗口' }));
    await waitFor(() => expect(mockGetResults).toHaveBeenLastCalledWith(expect.objectContaining({
      evalWindowDays: 10,
    })));
    expect(screen.getByPlaceholderText('10')).toHaveValue(10);
  });

  it('restores applied filters and pagination from the URL', async () => {
    window.history.replaceState(
      {},
      '',
      `${APP_ROUTE_PATHS.researchBacktest}?code=aapl&window=20&from=2026-03-01&to=2026-03-31&phase=intraday&page=3`,
    );
    mockGetResults.mockResolvedValueOnce({
      total: 45,
      page: 3,
      limit: 20,
      items: [{ ...baseResultItem, code: 'AAPL', stockName: 'Apple' }],
    });

    renderPage();

    expect(await screen.findByPlaceholderText('按股票代码筛选（留空表示全部）')).toHaveValue('AAPL');
    expect(screen.getByPlaceholderText('10')).toHaveValue(20);
    expect(screen.getByLabelText('分析开始日期')).toHaveValue('2026-03-01');
    expect(screen.getByLabelText('分析结束日期')).toHaveValue('2026-03-31');
    expect(await screen.findByLabelText('结果筛选 · 阶段')).toHaveTextContent('盘中');
    await waitFor(() => expect(mockGetResults).toHaveBeenCalledWith({
      code: 'AAPL',
      evalWindowDays: 20,
      analysisDateFrom: '2026-03-01',
      analysisDateTo: '2026-03-31',
      analysisPhase: 'intraday',
      page: 3,
      limit: 20,
    }));
  });

  it('keeps only the latest results and performance when phase requests resolve out of order', async () => {
    type ResultsResponse = { total: number; page: number; limit: number; items: typeof baseResultItem[] };
    let resolveOldResults!: (value: ResultsResponse) => void;
    let resolveNewResults!: (value: ResultsResponse) => void;
    let resolveOldPerformance!: (value: typeof basePerformance) => void;
    let resolveNewPerformance!: (value: typeof basePerformance) => void;

    renderPage();
    await screen.findByText('600519');
    mockGetResults
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOldResults = resolve; }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveNewResults = resolve; }));
    mockGetOverallPerformance
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOldPerformance = resolve; }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveNewPerformance = resolve; }));

    const phaseSelect = screen.getByLabelText('结果筛选 · 阶段');
    chooseOption(phaseSelect, 'intraday');
    chooseOption(phaseSelect, 'postmarket');
    await waitFor(() => expect(mockGetResults).toHaveBeenCalledTimes(3));

    await act(async () => {
      resolveNewResults({
        total: 1,
        page: 1,
        limit: 20,
        items: [{ ...baseResultItem, code: 'NEW', stockName: 'Latest result' }],
      });
      resolveNewPerformance({ ...basePerformance, winRatePct: 88 });
    });
    expect(await screen.findByText('NEW')).toBeInTheDocument();
    expect(await screen.findByText('88.0%')).toBeInTheDocument();

    await act(async () => {
      resolveOldResults({
        total: 1,
        page: 1,
        limit: 20,
        items: [{ ...baseResultItem, code: 'OLD', stockName: 'Stale result' }],
      });
      resolveOldPerformance({ ...basePerformance, winRatePct: 11 });
    });
    expect(screen.queryByText('OLD')).not.toBeInTheDocument();
    expect(screen.queryByText('11.0%')).not.toBeInTheDocument();
    expect(screen.getByText('NEW')).toBeInTheDocument();
  });

  it('does not continue the initial results request after unmount', async () => {
    let resolvePerformance!: (value: typeof basePerformance) => void;
    mockGetOverallPerformance.mockImplementationOnce(() => new Promise((resolve) => {
      resolvePerformance = resolve;
    }));
    const { unmount } = renderPage();
    await waitFor(() => expect(mockGetOverallPerformance).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      resolvePerformance(basePerformance);
    });
    expect(mockGetResults).not.toHaveBeenCalled();
  });
});
