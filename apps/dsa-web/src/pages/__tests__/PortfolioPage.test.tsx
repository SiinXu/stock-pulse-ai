import type React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { decisionSignalsApi } from '../../api/decisionSignals';
import { createApiError, createParsedApiError } from '../../api/error';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import type { DecisionSignalItem } from '../../types/decisionSignals';
import { UI_LANGUAGE_STORAGE_KEY } from '../../utils/uiLanguage';
import {
  SIGNAL_CENTER_SCOPE_VALUES,
  SIGNAL_CENTER_TAB_VALUES,
  buildSignalCenterHref,
} from '../../routing/routes';
import PortfolioPage from '../PortfolioPage';
import { createDeferred, chooseOption } from '../../test-utils';

// jsdom does not implement scrollIntoView, while Select calls it to keep the active item visible when opening a dropdown.
if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

function chooseVisibleDate(label: string): string {
  fireEvent.click(screen.getByRole('textbox', { name: label }));
  const dialog = screen.getByRole('dialog', { name: label });
  const day = dialog.querySelector<HTMLButtonElement>('button[data-calendar-day="true"]:not(:disabled)')!;
  const value = day.dataset.date!;
  fireEvent.click(day);
  return value;
}

const {
  getAccounts,
  getSnapshot,
  getRisk,
  refreshFx,
  listImportBrokers,
  listTrades,
  listCashLedger,
  listCorporateActions,
  createTrade,
  createPaperTrade,
  deleteTrade,
  createCashLedger,
  deleteCashLedger,
  createCorporateAction,
  deleteCorporateAction,
  parseCsvImport,
  commitCsvImport,
  createAccount,
  updateAccount,
  deleteAccount,
  analyzePosition,
  listDecisionSignals,
  getLatestDecisionSignals,
} = vi.hoisted(() => ({
  getAccounts: vi.fn(),
  getSnapshot: vi.fn(),
  getRisk: vi.fn(),
  refreshFx: vi.fn(),
  listImportBrokers: vi.fn(),
  listTrades: vi.fn(),
  listCashLedger: vi.fn(),
  listCorporateActions: vi.fn(),
  createTrade: vi.fn(),
  createPaperTrade: vi.fn(),
  deleteTrade: vi.fn(),
  createCashLedger: vi.fn(),
  deleteCashLedger: vi.fn(),
  createCorporateAction: vi.fn(),
  deleteCorporateAction: vi.fn(),
  parseCsvImport: vi.fn(),
  commitCsvImport: vi.fn(),
  createAccount: vi.fn(),
  updateAccount: vi.fn(),
  deleteAccount: vi.fn(),
  analyzePosition: vi.fn(),
  listDecisionSignals: vi.fn(),
  getLatestDecisionSignals: vi.fn(),
}));

vi.mock('../../api/decisionSignals', () => ({
  decisionSignalsApi: {
    list: listDecisionSignals,
    getLatest: getLatestDecisionSignals,
  },
}));

vi.mock('../../api/portfolio', () => ({
  portfolioApi: {
    getAccounts,
    getSnapshot,
    getRisk,
    refreshFx,
    listImportBrokers,
    listTrades,
    listCashLedger,
    listCorporateActions,
    createTrade,
    createPaperTrade,
    deleteTrade,
    createCashLedger,
    deleteCashLedger,
    createCorporateAction,
    deleteCorporateAction,
    parseCsvImport,
    commitCsvImport,
    createAccount,
    updateAccount,
    deleteAccount,
    analyzePosition,
  },
}));

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PieChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Pie: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Tooltip: () => null,
  Legend: () => null,
  Cell: () => null,
}));

type AccountItem = {
  id: number;
  name: string;
  market?: 'cn' | 'hk' | 'us' | 'jp' | 'kr' | 'tw';
  baseCurrency?: string;
  accountType?: 'real' | 'paper';
};

function makeAccounts(items: AccountItem[] = [{ id: 1, name: 'Main' }]) {
  return {
    accounts: items.map((item) => ({
      id: item.id,
      name: item.name,
      broker: 'Demo',
      market: item.market ?? 'us',
      baseCurrency: item.baseCurrency ?? 'CNY',
      isActive: true,
      accountType: item.accountType ?? 'real',
      ownerId: null,
      createdAt: '2026-03-19T00:00:00Z',
      updatedAt: '2026-03-19T00:00:00Z',
    })),
  };
}

function makeSnapshot(options: {
  accountId?: number;
  fxStale?: boolean;
  accountCount?: number;
  dataQuality?: string;
  limitations?: string[];
  positions?: Array<Record<string, unknown>>;
} = {}) {
  const accountId = options.accountId ?? 1;
  return {
    asOf: '2026-03-19',
    costMethod: 'fifo' as const,
    currency: 'CNY',
    accountCount: options.accountCount ?? 1,
    totalCash: 1000,
    totalMarketValue: 2000,
    totalEquity: 3000,
    realizedPnl: 0,
    unrealizedPnl: 0,
    feeTotal: 0,
    taxTotal: 0,
    fxStale: options.fxStale ?? true,
    dataQuality: options.dataQuality ?? 'ok',
    limitations: options.limitations ?? [],
    accounts: [
      {
        accountId,
        accountName: `Account ${accountId}`,
        ownerId: null,
        broker: 'Demo',
        market: 'us',
        baseCurrency: 'CNY',
        asOf: '2026-03-19',
        costMethod: 'fifo' as const,
        totalCash: 1000,
        totalMarketValue: 2000,
        totalEquity: 3000,
        realizedPnl: 0,
        unrealizedPnl: 0,
        feeTotal: 0,
        taxTotal: 0,
        fxStale: options.fxStale ?? true,
        positions: options.positions ?? [],
      },
    ],
  };
}

function makePosition(overrides: Record<string, unknown> = {}) {
  return {
    symbol: '600519',
    market: 'cn',
    currency: 'CNY',
    quantity: 1,
    avgCost: 1500,
    totalCost: 1500,
    lastPrice: 1600,
    marketValueBase: 1600,
    unrealizedPnlBase: 100,
    unrealizedPnlPct: 6.67,
    valuationCurrency: 'CNY',
    priceSource: 'history_close',
    priceDate: '2026-06-17',
    priceStale: false,
    priceAvailable: true,
    ...overrides,
  };
}

function makeRisk(overrides: Record<string, unknown> = {}) {
  return {
    asOf: '2026-03-19',
    accountId: null,
    costMethod: 'fifo' as const,
    currency: 'CNY',
    thresholds: {},
    concentration: {
      totalMarketValue: 0,
      topWeightPct: 0,
      alert: false,
      topPositions: [],
    },
    sectorConcentration: {
      totalMarketValue: 0,
      topWeightPct: 0,
      alert: false,
      topSectors: [],
      coverage: {},
      errors: [],
    },
    drawdown: {
      seriesPoints: 0,
      maxDrawdownPct: 0,
      currentDrawdownPct: 0,
      alert: false,
      fxStale: false,
    },
    stopLoss: {
      nearAlert: false,
      triggeredCount: 0,
      nearCount: 0,
      items: [],
    },
    decisionSignalRisk: {
      available: true,
      total: 0,
      actions: { sell: 0, reduce: 0, alert: 0 },
      items: [],
    },
    ...overrides,
  };
}

function makeDecisionSignal(overrides: Partial<DecisionSignalItem> = {}): DecisionSignalItem {
  return {
    id: 100,
    stockCode: '600519',
    stockName: '贵州茅台',
    market: 'cn',
    sourceType: 'analysis',
    sourceReportId: 1,
    traceId: null,
    marketPhase: 'intraday',
    triggerSource: 'portfolio',
    action: 'hold',
    actionLabel: null,
    confidence: 0.7,
    score: 80,
    horizon: '3d',
    entryLow: null,
    entryHigh: null,
    stopLoss: null,
    targetPrice: null,
    invalidation: null,
    watchConditions: '观察量能',
    reason: '趋势延续',
    riskSummary: '短线回撤风险',
    catalystSummary: null,
    evidence: undefined,
    dataQualitySummary: undefined,
    planQuality: 'partial',
    status: 'active',
    expiresAt: null,
    createdAt: '2026-06-17T08:00:00',
    updatedAt: '2026-06-17T08:00:00',
    metadata: undefined,
    ...overrides,
  };
}

async function waitForPortfolioLoad() {
  await waitFor(() => {
    expect(screen.getByRole('button', { name: /^(刷新数据|Refresh data)$/ })).toBeEnabled();
  });
}

async function waitForInitialLoad() {
  await waitFor(() => expect(getAccounts).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(getSnapshot).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(getRisk).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(listTrades).toHaveBeenCalledTimes(1));
  await waitForPortfolioLoad();
}

describe('PortfolioPage FX refresh', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();

    getAccounts.mockResolvedValue(makeAccounts());
    getSnapshot.mockImplementation(async ({ accountId }: { accountId?: number } = {}) => makeSnapshot({ accountId, fxStale: true }));
    getRisk.mockResolvedValue(makeRisk());
    refreshFx.mockResolvedValue({
      asOf: '2026-03-19',
      accountCount: 1,
      refreshEnabled: true,
      disabledReason: null,
      pairCount: 1,
      updatedCount: 1,
      staleCount: 0,
      errorCount: 0,
    });
    listImportBrokers.mockResolvedValue({
      brokers: [{ broker: 'huatai', aliases: [], displayName: '华泰' }],
    });
    listTrades.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });
    listCashLedger.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });
    listCorporateActions.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });
    createTrade.mockResolvedValue({ id: 1 });
    createPaperTrade.mockResolvedValue({ id: 2, price: 205, priceSource: 'manual' });
    deleteTrade.mockResolvedValue({ deleted: 1 });
    createCashLedger.mockResolvedValue({ id: 1 });
    deleteCashLedger.mockResolvedValue({ deleted: 1 });
    createCorporateAction.mockResolvedValue({ id: 1 });
    deleteCorporateAction.mockResolvedValue({ deleted: 1 });
    parseCsvImport.mockResolvedValue({ broker: 'huatai', recordCount: 0, skippedCount: 0, errorCount: 0, records: [], errors: [] });
    commitCsvImport.mockResolvedValue({
      accountId: 1,
      recordCount: 0,
      insertedCount: 0,
      duplicateCount: 0,
      failedCount: 0,
      dryRun: true,
      errors: [],
    });
    createAccount.mockResolvedValue({ id: 1 });
    deleteAccount.mockResolvedValue({ deleted: 1 });
    analyzePosition.mockResolvedValue({
      taskId: 'task-portfolio-1',
      traceId: 'task-portfolio-1',
      status: 'pending',
      message: '分析任务已加入队列: HK00700',
      analysisPhase: 'auto',
    });
    getLatestDecisionSignals.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 1 });
  });

  function renderPortfolioPage(initialEntry = '/portfolio') {
    const router = createMemoryRouter(
      [{ path: '/portfolio', element: <PortfolioPage /> }],
      { initialEntries: [initialEntry] },
    );
    render(<RouterProvider router={router} />);
    return router;
  }

  function renderEnglishPage() {
    window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'en');
    const router = createMemoryRouter(
      [{ path: '/portfolio', element: <PortfolioPage /> }],
      { initialEntries: ['/portfolio'] },
    );
    render(
      <UiLanguageProvider>
        <RouterProvider router={router} />
      </UiLanguageProvider>,
    );
  }


  async function openPortfolioRiskTab() {
    const riskTab = screen.queryByRole('tab', { name: '风险' })
      ?? screen.getByRole('tab', { name: 'Risk' });
    fireEvent.click(riskTab);
    expect(await screen.findByTestId('portfolio-tab-risk')).toBeInTheDocument();
  }

  async function openCsvImportWizardAndReachConfirm(file: File) {
    fireEvent.click(screen.getByRole('button', { name: '券商 CSV 导入' }));
    expect(await screen.findByTestId('portfolio-import-wizard')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    expect(screen.getByLabelText('选择 CSV')).toHaveAttribute('data-control', 'file-input');
    expect(screen.getByRole('button', { name: '选择 CSV' })).toHaveAttribute('data-control', 'button');
    fireEvent.change(screen.getByLabelText('选择 CSV'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    await screen.findByText('CSV 解析结果');
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    expect(screen.getByRole('button', { name: '提交导入' })).toBeInTheDocument();
  }

  it('uses the shared page shell and keeps the overview separate from positions', async () => {
    renderPortfolioPage();
    await waitForInitialLoad();

    const heading = screen.getByRole('heading', { name: '持仓管理' });
    const page = heading.closest('[data-pattern="app-page"]');
    expect(page).toHaveClass('portfolio-page');
    expect(heading.closest('[data-pattern="page-header"]')).not.toBeNull();
    const portfolioIdentity = page!.querySelector('[data-portfolio-switcher="single"]');
    expect(portfolioIdentity).toHaveTextContent('组合');
    expect(portfolioIdentity?.closest('button, [role="button"], select')).toBeNull();

    const overview = Array.from(page!.querySelectorAll('section')).find((section) => (
      section.className.includes('xl:grid-cols-3')
    ));
    expect(overview).toBeDefined();
    expect(within(overview as HTMLElement).getByText('总权益')).toBeInTheDocument();
    expect(within(overview as HTMLElement).getByText('行业数据暂不可用，当前展示个股集中度')).toBeInTheDocument();

    const positionsSection = screen.getByRole('heading', { name: '持仓明细' }).closest('section');
    expect(positionsSection).not.toBe(overview);
  });

  it('shows the page-level portfolio error in a toast', async () => {
    getSnapshot.mockRejectedValueOnce(
      createApiError(
        createParsedApiError({
          title: '持仓加载失败',
          message: '无法加载持仓',
          rawMessage: 'GET /api/portfolio/snapshot returned 404',
          category: 'http_error',
        }),
      ),
    );

    renderPortfolioPage();

    const alert = (await screen.findByText('持仓加载失败')).closest('[role="alert"]');
    expect(alert?.closest('[data-overlay-root="toast"]')).not.toBeNull();
  });

  it('restores selected account from the URL and keeps Back navigation in sync', async () => {
    getAccounts.mockResolvedValueOnce(makeAccounts([
      { id: 1, name: 'Main' },
      { id: 2, name: 'Growth' },
    ]));
    getSnapshot.mockImplementation(async ({ accountId }: { accountId?: number } = {}) => makeSnapshot({
      accountId,
      accountCount: accountId ? 1 : 2,
    }));
    const router = renderPortfolioPage('/portfolio?account=2&ref=notification');

    await waitFor(() => expect(getSnapshot).toHaveBeenCalledWith({
      accountId: 2,
      costMethod: 'fifo',
      includeRealtime: false,
    }));
    expect(router.state.location.search).toBe('?account=2&ref=notification');

    chooseOption(screen.getAllByRole('combobox')[0], '1');
    await waitFor(() => expect(router.state.location.search).toBe('?account=1&ref=notification'));

    await act(async () => {
      await router.navigate(-1);
    });
    await waitFor(() => expect(router.state.location.search).toBe('?account=2&ref=notification'));
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({
      accountId: 2,
      costMethod: 'fifo',
      includeRealtime: false,
    }));
  });


  it('restores workspace tab and selected position from the URL', async () => {
    getSnapshot.mockResolvedValueOnce(makeSnapshot({
      accountId: 1,
      positions: [makePosition({ symbol: 'AAPL', market: 'us' })],
    }));
    const router = renderPortfolioPage('/portfolio?account=1&tab=risk&selected=1-AAPL-us');
    await waitForInitialLoad();
    expect(router.state.location.search).toContain('tab=risk');
    expect(router.state.location.search).toContain('selected=1-AAPL-us');
    expect(screen.getByTestId('portfolio-tab-risk')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '持仓明细' }));
    await waitFor(() => expect(router.state.location.search).not.toContain('tab=risk'));
  });

  it('replaces an unavailable account deep link with the first active account', async () => {
    getAccounts.mockResolvedValueOnce(makeAccounts([
      { id: 1, name: 'Main' },
      { id: 2, name: 'Growth' },
    ]));
    const router = renderPortfolioPage('/portfolio?account=999&keep=yes');

    await waitFor(() => expect(router.state.location.search).toBe('?account=1&keep=yes'));
    expect(screen.getAllByRole('combobox')[0]).toHaveTextContent('Main (#1)');
    expect(screen.getByRole('status')).toHaveTextContent('链接无效');
    expect(screen.getByRole('status')).toHaveTextContent('链接包含无效或敏感的状态参数');
  });

  it('drops a late snapshot response after switching account scope', async () => {
    const accountOneSnapshot = createDeferred<ReturnType<typeof makeSnapshot>>();
    getAccounts.mockResolvedValueOnce(makeAccounts([
      { id: 1, name: 'Main' },
      { id: 2, name: 'Alt' },
    ]));
    getSnapshot.mockImplementation(({ accountId }: { accountId?: number } = {}) => {
      if (accountId === 1) return accountOneSnapshot.promise;
      return Promise.resolve(makeSnapshot({
        accountId,
        accountCount: accountId ? 1 : 2,
        positions: [makePosition({ symbol: accountId === 2 ? 'ACCOUNT_TWO' : 'ALL_ACCOUNTS' })],
      }));
    });

    renderPortfolioPage();
    await waitForInitialLoad();

    const accountSelect = screen.getAllByRole('combobox')[0];
    chooseOption(accountSelect, '1');
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({
      accountId: 1,
      costMethod: 'fifo',
      includeRealtime: false,
    }));

    chooseOption(accountSelect, '2');
    expect(await screen.findByText('ACCOUNT_TWO')).toBeInTheDocument();

    await act(async () => {
      accountOneSnapshot.resolve(makeSnapshot({
        accountId: 1,
        positions: [makePosition({ symbol: 'ACCOUNT_ONE' })],
      }));
      await accountOneSnapshot.promise;
    });

    expect(screen.getByText('ACCOUNT_TWO')).toBeInTheDocument();
    expect(screen.queryByText('ACCOUNT_ONE')).not.toBeInTheDocument();
  });

  it('shows only the account onboarding state when no portfolio account exists', async () => {
    getAccounts.mockResolvedValueOnce(makeAccounts([]));

    renderPortfolioPage();

    expect(await screen.findByText('还没有可用账户，请先创建账户后再录入交易或导入 CSV。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '添加账户' })).toBeInTheDocument();
    expect(screen.queryByText('总权益')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '持仓明细' })).not.toBeInTheDocument();
  });

  it('defaults new accounts to the real account type', async () => {
    getAccounts
      .mockResolvedValueOnce(makeAccounts([]))
      .mockResolvedValueOnce(makeAccounts([{ id: 3, name: 'Live book', accountType: 'real' }]));
    createAccount.mockResolvedValue({
      ...makeAccounts([{ id: 3, name: 'Live book', accountType: 'real' }]).accounts[0],
    });
    renderPortfolioPage();

    fireEvent.click(await screen.findByRole('button', { name: '添加账户' }));
    expect(screen.getByRole('combobox', { name: '账户类型' })).toHaveTextContent('实盘账户');
    fireEvent.change(screen.getByLabelText('账户名称'), { target: { value: 'Live book' } });
    fireEvent.click(screen.getByRole('button', { name: '新建账户' }));

    await waitFor(() => expect(createAccount).toHaveBeenCalledWith({
      name: 'Live book',
      broker: 'Demo',
      market: 'cn',
      baseCurrency: 'CNY',
      accountType: 'real',
    }));
  });

  it('creates and visually labels a paper account', async () => {
    getAccounts
      .mockResolvedValueOnce(makeAccounts([]))
      .mockResolvedValueOnce(makeAccounts([{ id: 4, name: 'Practice', accountType: 'paper' }]));
    createAccount.mockResolvedValue({
      ...makeAccounts([{ id: 4, name: 'Practice', accountType: 'paper' }]).accounts[0],
    });
    renderPortfolioPage();

    fireEvent.click(await screen.findByRole('button', { name: '添加账户' }));
    chooseOption(screen.getByRole('combobox', { name: '账户类型' }), 'paper');
    fireEvent.change(screen.getByLabelText('账户名称'), { target: { value: 'Practice' } });
    fireEvent.click(screen.getByRole('button', { name: '新建账户' }));

    await waitFor(() => expect(createAccount).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Practice',
      accountType: 'paper',
    })));
    await waitFor(() => {
      expect(screen.getAllByRole('combobox')[0]).toHaveTextContent('Practice (#4) · 纸上账户');
    });
    expect(screen.getAllByText('纸上账户').length).toBeGreaterThan(0);
  });

  it('edits the selected account via a PUT that preserves the account id', async () => {
    updateAccount.mockResolvedValue({ id: 1, name: 'Renamed', broker: 'Demo', market: 'us', baseCurrency: 'CNY', isActive: true });
    getSnapshot.mockImplementation(async ({ accountId }: { accountId?: number } = {}) => {
      if (accountId === 1) {
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
      return makeSnapshot({ accountId, fxStale: true });
    });
    renderPortfolioPage();
    await waitForInitialLoad();

    chooseOption(screen.getAllByRole('combobox')[0], '1');
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({
      accountId: 1,
      costMethod: 'fifo',
      includeRealtime: false,
    }));
    const editButton = screen.getByRole('button', { name: '编辑账户' });
    await waitFor(() => expect(editButton).toBeEnabled());
    fireEvent.click(editButton);

    const nameInput = await screen.findByDisplayValue('Main');
    fireEvent.change(nameInput, { target: { value: 'Renamed' } });
    fireEvent.click(screen.getByRole('button', { name: '保存修改' }));

    await waitFor(() => expect(updateAccount).toHaveBeenCalledWith(1, expect.objectContaining({
      name: 'Renamed',
      market: 'us',
      baseCurrency: 'CNY',
    })));
  });

  it('uses fast portfolio valuation for page snapshot and risk loads', async () => {
    renderPortfolioPage();

    await waitForInitialLoad();

    expect(getSnapshot).toHaveBeenCalledWith({ accountId: undefined, costMethod: 'fifo', includeRealtime: false });
    expect(getRisk).toHaveBeenCalledWith({ accountId: undefined, costMethod: 'fifo', includeRealtime: false });
  });

  it('does not synthesize broker options when the broker catalog is empty', async () => {
    listImportBrokers.mockResolvedValueOnce({ brokers: [] });

    renderPortfolioPage();
    await waitForInitialLoad();
    await waitFor(() => expect(listImportBrokers).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole('button', { name: '券商 CSV 导入' }));
    const wizard = await screen.findByTestId('portfolio-import-wizard');

    expect(within(wizard).getByText('券商列表为空，暂时无法导入 CSV。')).toBeInTheDocument();
    expect(within(wizard).getByRole('combobox', { name: '券商' })).toBeDisabled();
    expect(within(wizard).getByRole('button', { name: '下一步' })).toBeDisabled();
  });

  it('renders stale FX status with a manual refresh button', async () => {
    renderPortfolioPage();

    await waitForInitialLoad();

    expect(await screen.findByText('过期')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '刷新汇率' })).toHaveAttribute('data-size', 'comfortable');
  });

  it('shows aggregate partial valuation limitations near summary totals', async () => {
    getSnapshot.mockResolvedValueOnce(makeSnapshot({
      dataQuality: 'partial',
      limitations: ['realtime_quote_best_effort', 'fx_and_cost_basis_partial'],
    }));

    renderPortfolioPage();

    await waitForInitialLoad();

    expect(await screen.findByText('组合估值限制')).toBeInTheDocument();
    expect(screen.getByText(/实时行情为尽力获取/)).toBeInTheDocument();
    expect(screen.getByText(/汇率与成本基础为部分口径/)).toBeInTheDocument();
  });

  it('renders portfolio risk drawdown labels in English UI mode', async () => {
    renderEnglishPage();

    await waitForInitialLoad();
    await openPortfolioRiskTab();

    expect(await screen.findByText('Portfolio management')).toBeInTheDocument();
    expect(screen.getByText('Drawdown monitor')).toBeInTheDocument();
    expect(screen.getByText(/Max drawdown:/)).toBeInTheDocument();
    expect(screen.getByText(/Current drawdown:/)).toBeInTheDocument();
    expect(screen.getByText('Stop-loss proximity warning')).toBeInTheDocument();
    expect(screen.getByText('Scope')).toBeInTheDocument();
    expect(screen.getByText('AI risk signals')).toBeInTheDocument();
    expect(screen.getByText('No defensive signals')).toBeInTheDocument();
    expect(screen.queryByText('回撤监控')).not.toBeInTheDocument();
  });

  it('renders portfolio decision signal risk summary', async () => {
    getRisk.mockResolvedValueOnce(makeRisk({
      decisionSignalRisk: {
        available: true,
        total: 2,
        actions: { sell: 1, reduce: 0, alert: 1 },
        items: [
          {
            accountId: 1,
            symbol: '600519',
            market: 'cn',
            signal: makeDecisionSignal({ id: 201, action: 'sell', actionLabel: null }),
          },
          {
            accountId: 1,
            symbol: '300750',
            market: 'cn',
            signal: makeDecisionSignal({ id: 202, stockCode: '300750', action: 'alert', actionLabel: null }),
          },
        ],
      },
    }));

    renderPortfolioPage();

    await waitForInitialLoad();
    await openPortfolioRiskTab();

    expect(screen.getByText('AI 风险信号')).toBeInTheDocument();
    expect(screen.getByText(/风险信号: 2/)).toBeInTheDocument();
    expect(screen.getByText(/卖出: 1 · 减仓: 0 · 预警: 1/)).toBeInTheDocument();
    expect(screen.getByText('600519 · 卖出')).toBeInTheDocument();
    expect(screen.getByText('300750 · 预警')).toBeInTheDocument();
    expect(screen.queryByText('600519 · sell')).not.toBeInTheDocument();
    expect(screen.queryByText('300750 · alert')).not.toBeInTheDocument();
  });

  it('uses the current UI language for portfolio decision signal risk action labels', async () => {
    getRisk.mockResolvedValueOnce(makeRisk({
      decisionSignalRisk: {
        available: true,
        total: 1,
        actions: { sell: 1, reduce: 0, alert: 0 },
        items: [
          {
            accountId: 1,
            symbol: '600519',
            market: 'cn',
            signal: makeDecisionSignal({ id: 203, action: 'sell', actionLabel: '卖出' }),
          },
        ],
      },
    }));

    renderEnglishPage();

    await waitForInitialLoad();
    await openPortfolioRiskTab();

    expect(screen.getByText('AI risk signals')).toBeInTheDocument();
    expect(screen.getByText('600519 · Sell')).toBeInTheDocument();
    expect(screen.queryByText('600519 · 卖出')).not.toBeInTheDocument();
    expect(screen.queryByText('600519 · sell')).not.toBeInTheDocument();
  });

  it('uses top-level action when portfolio risk presentation fields conflict', async () => {
    getRisk.mockResolvedValueOnce(makeRisk({
      decisionSignalRisk: {
        available: true,
        total: 1,
        actions: { sell: 1, reduce: 0, alert: 0 },
        items: [
          {
            accountId: 1,
            symbol: '600519',
            market: 'cn',
            signal: makeDecisionSignal({
              id: 204,
              action: 'sell',
              actionLabel: 'Sell',
              presentation: {
                action: 'buy',
                label: 'Buy',
                confidence: 0.91,
                summary: 'Canonical summary',
                risk: 'Canonical risk',
                timestamp: '2026-07-18T12:00:00Z',
              },
            }),
          },
        ],
      },
    }));

    renderPortfolioPage();

    await waitForInitialLoad();
    await openPortfolioRiskTab();

    expect(screen.getByText(/卖出: 1 · 减仓: 0 · 预警: 0/)).toBeInTheDocument();
    expect(screen.getByText('600519 · 卖出')).toBeInTheDocument();
    expect(screen.queryByText('600519 · 买入')).not.toBeInTheDocument();
    expect(screen.queryByText('600519 · Buy')).not.toBeInTheDocument();
  });

  it('renders portfolio decision signal risk fail-open state', async () => {
    getRisk.mockResolvedValueOnce(makeRisk({
      decisionSignalRisk: {
        available: false,
        total: 0,
        actions: { sell: 0, reduce: 0, alert: 0 },
        items: [],
      },
    }));

    renderPortfolioPage();

    await waitForInitialLoad();
    await openPortfolioRiskTab();

    expect(screen.getByText('信号风险暂不可用')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '查看全部' })).toHaveAttribute(
      'href',
      buildSignalCenterHref({ scope: SIGNAL_CENTER_SCOPE_VALUES.holdings }),
    );
  });

  it('refreshes FX for a single selected account and only reloads snapshot/risk', async () => {
    const selectedAccountRisk = createDeferred<ReturnType<typeof makeRisk>>();
    getSnapshot
      .mockResolvedValueOnce(makeSnapshot({ fxStale: true }))
      .mockResolvedValueOnce(makeSnapshot({ accountId: 1, fxStale: true }))
      .mockResolvedValueOnce(makeSnapshot({ accountId: 1, fxStale: false }));
    getRisk
      .mockResolvedValueOnce(makeRisk())
      .mockReturnValueOnce(selectedAccountRisk.promise);

    renderPortfolioPage();

    await waitForInitialLoad();

    const accountSelect = screen.getAllByRole('combobox')[0];
    chooseOption(accountSelect, '1');

    await waitFor(() => {
      expect(getSnapshot).toHaveBeenLastCalledWith({ accountId: 1, costMethod: 'fifo', includeRealtime: false });
    });
    expect(screen.getByRole('button', { name: '刷新汇率' })).toBeDisabled();

    await act(async () => {
      selectedAccountRisk.resolve(makeRisk());
      await selectedAccountRisk.promise;
    });
    await waitForPortfolioLoad();

    const snapshotCallsBeforeRefresh = getSnapshot.mock.calls.length;
    const riskCallsBeforeRefresh = getRisk.mock.calls.length;
    const tradeCallsBeforeRefresh = listTrades.mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: '刷新汇率' }));

    await waitFor(() => expect(refreshFx).toHaveBeenCalledWith({ accountId: 1 }));
    expect(await screen.findByText('汇率已刷新，共更新 1 对。')).toBeInTheDocument();
    await waitFor(() => expect(getSnapshot).toHaveBeenCalledTimes(snapshotCallsBeforeRefresh + 1));
    await waitFor(() => expect(getRisk).toHaveBeenCalledTimes(riskCallsBeforeRefresh + 1));
    expect(listTrades).toHaveBeenCalledTimes(tradeCallsBeforeRefresh);
    expect(listCashLedger).not.toHaveBeenCalled();
    expect(listCorporateActions).not.toHaveBeenCalled();
    expect(screen.getByText('最新')).toBeInTheDocument();
  });

  it('refreshes FX for the full portfolio without sending accountId and shows neutral feedback when no pair exists', async () => {
    refreshFx.mockResolvedValueOnce({
      asOf: '2026-03-19',
      accountCount: 1,
      refreshEnabled: true,
      disabledReason: null,
      pairCount: 0,
      updatedCount: 0,
      staleCount: 0,
      errorCount: 0,
    });

    renderPortfolioPage();

    await waitForInitialLoad();

    fireEvent.click(screen.getByRole('button', { name: '刷新汇率' }));

    await waitFor(() => expect(refreshFx).toHaveBeenCalledWith({ accountId: undefined }));
    expect(await screen.findByText('当前范围无可刷新的汇率对。')).toBeInTheDocument();
  });

  it('shows disabled feedback when FX online refresh is disabled even without a disabled reason', async () => {
    refreshFx.mockResolvedValueOnce({
      asOf: '2026-03-19',
      accountCount: 1,
      refreshEnabled: false,
      pairCount: 1,
      updatedCount: 0,
      staleCount: 0,
      errorCount: 0,
    });

    renderPortfolioPage();

    await waitForInitialLoad();

    fireEvent.click(screen.getByRole('button', { name: '刷新汇率' }));

    expect(await screen.findByText('汇率在线刷新已被禁用。')).toBeInTheDocument();
  });

  it('renders backend-provided position valuation fields and stale missing-price hint', async () => {
    getSnapshot.mockResolvedValueOnce(makeSnapshot({ fxStale: true, positions: [
      { symbol: 'HK00700', market: 'hk', currency: 'HKD', quantity: 10, avgCost: 400, totalCost: 4000, lastPrice: 420, marketValueBase: 4200, unrealizedPnlBase: 200, unrealizedPnlPct: 5, valuationCurrency: 'HKD', priceSource: 'history_close', priceDate: '2026-03-18', priceStale: true, priceAvailable: true },
      { symbol: 'AAPL', market: 'us', currency: 'USD', quantity: 5, avgCost: 100, totalCost: 500, lastPrice: 0, marketValueBase: 0, unrealizedPnlBase: 0, unrealizedPnlPct: null, valuationCurrency: 'USD', priceSource: 'missing', priceDate: null, priceStale: true, priceAvailable: false },
    ] }));

    renderPortfolioPage();

    await waitForInitialLoad();

    expect(await screen.findByText('HK00700')).toBeInTheDocument();
    expect(screen.getByText('420.0000')).toBeInTheDocument();
    expect(screen.getByText('HKD 4,200.00')).toBeInTheDocument();
    expect(screen.getByText('+5.00%')).toBeInTheDocument();
    expect(screen.getByText('收盘价 · 2026-03-18')).toBeInTheDocument();
    expect(screen.getByText('缺价')).toBeInTheDocument();
    expect(screen.getAllByText('--').length).toBeGreaterThanOrEqual(2);

    const hkRow = screen.getByText('HK00700').closest('tr');
    const aaplRow = screen.getByText('AAPL').closest('tr');
    expect(hkRow).not.toBeNull();
    expect(aaplRow).not.toBeNull();

    const hkRowCells = within(hkRow as HTMLTableRowElement).getAllByRole('cell');
    const aaplRowCells = within(aaplRow as HTMLTableRowElement).getAllByRole('cell');
    expect(hkRowCells.at(-3)?.querySelector('span')).toHaveClass('text-success');
    expect(aaplRowCells.at(-3)?.querySelector('span')).toHaveClass('text-secondary');
  });

  it('loads latest active signals for holdings without scanning paginated signal lists', async () => {
    getSnapshot.mockResolvedValueOnce(makeSnapshot({ positions: [
      { symbol: '600519', market: 'cn', currency: 'CNY', quantity: 1, avgCost: 1500, totalCost: 1500, lastPrice: 1600, marketValueBase: 1600, unrealizedPnlBase: 100, unrealizedPnlPct: 6.67, valuationCurrency: 'CNY', priceSource: 'history_close', priceDate: '2026-06-17', priceStale: false, priceAvailable: true },
    ] }));
    const latestSignal = makeDecisionSignal({
      id: 101,
      stockCode: '600519',
      riskSummary: '分页后的风险摘要',
      watchConditions: '分页后的观察条件',
    });
    getLatestDecisionSignals.mockResolvedValueOnce({ items: [latestSignal], total: 1, page: 1, pageSize: 1 });

    renderPortfolioPage();

    expect(await screen.findByText('600519')).toBeInTheDocument();
    expect(await screen.findByText('分页后的风险摘要')).toBeInTheDocument();
    expect(decisionSignalsApi.getLatest).toHaveBeenCalledWith('600519', {
      market: 'cn',
      limit: 1,
    });
    expect(decisionSignalsApi.list).not.toHaveBeenCalled();
  });

  it('selects the latest equivalent holding signal by canonical presentation timestamp', async () => {
    getSnapshot.mockResolvedValueOnce(makeSnapshot({ positions: [
      { symbol: '600519', market: 'cn', currency: 'CNY', quantity: 1, avgCost: 1500, totalCost: 1500, lastPrice: 1600, marketValueBase: 1600, unrealizedPnlBase: 100, unrealizedPnlPct: 6.67, valuationCurrency: 'CNY', priceSource: 'history_close', priceDate: '2026-06-17', priceStale: false, priceAvailable: true },
    ] }));
    const flatNewerCanonicalOlder = makeDecisionSignal({
      id: 301,
      createdAt: '2026-12-01T00:00:00Z',
      riskSummary: 'Flat timestamp winner must not render',
      presentation: {
        action: 'hold',
        label: 'Hold',
        confidence: 0.5,
        summary: 'Canonical older',
        risk: 'Canonical older risk',
        timestamp: '2026-01-01T00:00:00Z',
      },
    });
    const flatOlderCanonicalNewer = makeDecisionSignal({
      id: 302,
      createdAt: '2026-01-01T00:00:00Z',
      riskSummary: 'Flat timestamp loser',
      presentation: {
        action: 'hold',
        label: 'Hold',
        confidence: 0.9,
        summary: 'Canonical newest',
        risk: 'Canonical timestamp winner',
        timestamp: '2026-12-01T00:00:00Z',
      },
    });
    getLatestDecisionSignals.mockResolvedValueOnce({
      items: [flatNewerCanonicalOlder, flatOlderCanonicalNewer],
      total: 2,
      page: 1,
      pageSize: 1,
    });

    renderPortfolioPage();

    expect(await screen.findByText('Canonical timestamp winner')).toBeInTheDocument();
    expect(screen.queryByText('Canonical older risk')).not.toBeInTheDocument();
    expect(screen.queryByText('Flat timestamp winner must not render')).not.toBeInTheDocument();
  });

  it('refreshes holding signals when manually refreshing unchanged portfolio data', async () => {
    const position = { symbol: '600519', market: 'cn', currency: 'CNY', quantity: 1, avgCost: 1500, totalCost: 1500, lastPrice: 1600, marketValueBase: 1600, unrealizedPnlBase: 100, unrealizedPnlPct: 6.67, valuationCurrency: 'CNY', priceSource: 'history_close', priceDate: '2026-06-17', priceStale: false, priceAvailable: true };
    getSnapshot.mockResolvedValue(makeSnapshot({ positions: [position] }));
    getLatestDecisionSignals
      .mockResolvedValueOnce({
        items: [makeDecisionSignal({ stockCode: '600519', riskSummary: '旧 AI 风险' })],
        total: 1,
        page: 1,
        pageSize: 1,
      })
      .mockResolvedValueOnce({
        items: [makeDecisionSignal({ stockCode: '600519', riskSummary: '新 AI 风险' })],
        total: 1,
        page: 1,
        pageSize: 1,
      });

    renderPortfolioPage();

    expect(await screen.findByText('旧 AI 风险')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '刷新数据' }));

    expect(await screen.findByText('新 AI 风险')).toBeInTheDocument();
    await waitFor(() => expect(getLatestDecisionSignals).toHaveBeenCalledTimes(2));
    expect(screen.queryByText('旧 AI 风险')).not.toBeInTheDocument();
  });

  it('waits for the selected-account snapshot before loading account-scoped holding signals', async () => {
    getAccounts.mockResolvedValueOnce(makeAccounts([
      { id: 1, name: 'Main' },
      { id: 2, name: 'Alt' },
    ]));
    const accountTwoSnapshot = createDeferred<ReturnType<typeof makeSnapshot>>();
    getSnapshot
      .mockResolvedValueOnce(makeSnapshot({
        accountCount: 2,
        positions: [
          { symbol: '600519', market: 'cn', currency: 'CNY', quantity: 1, avgCost: 1500, totalCost: 1500, lastPrice: 1600, marketValueBase: 1600, unrealizedPnlBase: 100, unrealizedPnlPct: 6.67, valuationCurrency: 'CNY', priceSource: 'history_close', priceDate: '2026-06-17', priceStale: false, priceAvailable: true },
        ],
      }))
      .mockReturnValueOnce(accountTwoSnapshot.promise);
    getLatestDecisionSignals.mockResolvedValue({
      items: [makeDecisionSignal({ stockCode: '600519', riskSummary: '账号信号' })],
      total: 1,
      page: 1,
      pageSize: 1,
    });

    renderPortfolioPage();

    expect(await screen.findByText('账号信号')).toBeInTheDocument();
    const signalCallsBeforeSwitch = getLatestDecisionSignals.mock.calls.length;

    const accountSelect = screen.getAllByRole('combobox')[0];
    chooseOption(accountSelect, '2');

    await waitFor(() => {
      expect(getSnapshot).toHaveBeenLastCalledWith({ accountId: 2, costMethod: 'fifo', includeRealtime: false });
    });
    expect(screen.queryByText('账号信号')).not.toBeInTheDocument();
    expect(getLatestDecisionSignals).toHaveBeenCalledTimes(signalCallsBeforeSwitch);

    await act(async () => {
      accountTwoSnapshot.resolve(makeSnapshot({
        accountId: 2,
        positions: [
          { symbol: '600519', market: 'cn', currency: 'CNY', quantity: 1, avgCost: 1500, totalCost: 1500, lastPrice: 1600, marketValueBase: 1600, unrealizedPnlBase: 100, unrealizedPnlPct: 6.67, valuationCurrency: 'CNY', priceSource: 'history_close', priceDate: '2026-06-17', priceStale: false, priceAvailable: true },
        ],
      }));
      await accountTwoSnapshot.promise;
    });

    await waitFor(() => {
      expect(getLatestDecisionSignals).toHaveBeenLastCalledWith('600519', {
        market: 'cn',
        limit: 1,
      });
    });
  });

  it('drops late holding-signal responses after switching account scope', async () => {
    getAccounts.mockResolvedValueOnce(makeAccounts([
      { id: 1, name: 'Main' },
      { id: 2, name: 'Alt' },
    ]));
    getSnapshot
      .mockResolvedValueOnce(makeSnapshot({
        accountCount: 2,
        positions: [
          { symbol: '600519', market: 'cn', currency: 'CNY', quantity: 1, avgCost: 1500, totalCost: 1500, lastPrice: 1600, marketValueBase: 1600, unrealizedPnlBase: 100, unrealizedPnlPct: 6.67, valuationCurrency: 'CNY', priceSource: 'history_close', priceDate: '2026-06-17', priceStale: false, priceAvailable: true },
        ],
      }))
      .mockResolvedValueOnce(makeSnapshot({
        accountId: 2,
        positions: [
          { symbol: '600519', market: 'cn', currency: 'CNY', quantity: 1, avgCost: 1500, totalCost: 1500, lastPrice: 1600, marketValueBase: 1600, unrealizedPnlBase: 100, unrealizedPnlPct: 6.67, valuationCurrency: 'CNY', priceSource: 'history_close', priceDate: '2026-06-17', priceStale: false, priceAvailable: true },
        ],
      }));
    const oldSignals = createDeferred<{
      items: DecisionSignalItem[];
      total: number;
      page: number;
      pageSize: number;
    }>();
    getLatestDecisionSignals
      .mockReturnValueOnce(oldSignals.promise)
      .mockResolvedValueOnce({
        items: [makeDecisionSignal({ stockCode: '600519', riskSummary: '新账号信号' })],
        total: 1,
        page: 1,
        pageSize: 1,
      });

    renderPortfolioPage();

    expect(await screen.findByText('600519')).toBeInTheDocument();

    const accountSelect = screen.getAllByRole('combobox')[0];
    chooseOption(accountSelect, '2');

    expect(await screen.findByText('新账号信号')).toBeInTheDocument();

    await act(async () => {
      oldSignals.resolve({
        items: [makeDecisionSignal({ stockCode: '600519', riskSummary: '旧账号晚返回信号' })],
        total: 1,
        page: 1,
        pageSize: 1,
      });
      await oldSignals.promise;
    });

    expect(screen.getByText('新账号信号')).toBeInTheDocument();
    expect(screen.queryByText('旧账号晚返回信号')).not.toBeInTheDocument();
  });

  it('matches holding signals by stock-code equivalence and leaves unmatched rows empty', async () => {
    getSnapshot.mockResolvedValueOnce(makeSnapshot({ positions: [
      { symbol: '600519', market: 'cn', currency: 'CNY', quantity: 1, avgCost: 1500, totalCost: 1500, lastPrice: 1600, marketValueBase: 1600, unrealizedPnlBase: 100, unrealizedPnlPct: 6.67, valuationCurrency: 'CNY', priceSource: 'history_close', priceDate: '2026-06-17', priceStale: false, priceAvailable: true },
      { symbol: 'SH600519', market: 'cn', currency: 'CNY', quantity: 1, avgCost: 1500, totalCost: 1500, lastPrice: 1600, marketValueBase: 1600, unrealizedPnlBase: 100, unrealizedPnlPct: 6.67, valuationCurrency: 'CNY', priceSource: 'history_close', priceDate: '2026-06-17', priceStale: false, priceAvailable: true },
      { symbol: '00700.HK', market: 'hk', currency: 'HKD', quantity: 10, avgCost: 400, totalCost: 4000, lastPrice: 420, marketValueBase: 4200, unrealizedPnlBase: 200, unrealizedPnlPct: 5, valuationCurrency: 'HKD', priceSource: 'history_close', priceDate: '2026-06-17', priceStale: false, priceAvailable: true },
      { symbol: 'AAPL', market: 'us', currency: 'USD', quantity: 2, avgCost: 180, totalCost: 360, lastPrice: 190, marketValueBase: 380, unrealizedPnlBase: 20, unrealizedPnlPct: 5.56, valuationCurrency: 'USD', priceSource: 'history_close', priceDate: '2026-06-17', priceStale: false, priceAvailable: true },
    ] }));
    getLatestDecisionSignals.mockImplementation(async (stockCode: string) => {
      if (stockCode.includes('600519')) {
        return {
          items: [makeDecisionSignal({ id: 1, stockCode: '600519', market: 'cn', riskSummary: 'A 股风险' })],
          total: 1,
          page: 1,
          pageSize: 1,
        };
      }
      if (stockCode.includes('00700')) {
        return {
          items: [makeDecisionSignal({ id: 2, stockCode: 'HK00700', market: 'hk', riskSummary: '港股风险', watchConditions: '观察回购' })],
          total: 1,
          page: 1,
          pageSize: 1,
        };
      }
      return { items: [], total: 0, page: 1, pageSize: 1 };
    });

    renderPortfolioPage();

    expect(await screen.findAllByText('A 股风险')).toHaveLength(2);
    expect(screen.getByText('港股风险')).toBeInTheDocument();
    const firstAshareRow = screen.getAllByText('600519')[0].closest('tr');
    expect(firstAshareRow).not.toBeNull();
    expect(within(firstAshareRow as HTMLTableRowElement).getByRole('link', {
      name: '从此信号创建规则',
    })).toHaveAttribute('href', buildSignalCenterHref({
      tab: SIGNAL_CENTER_TAB_VALUES.rules,
      createRule: true,
      stock: '600519',
    }));
    expect(screen.getByRole('link', { name: '查看全部' })).toHaveAttribute(
      'href',
      buildSignalCenterHref({ scope: SIGNAL_CENTER_SCOPE_VALUES.holdings }),
    );
    const latestLookupSymbols = getLatestDecisionSignals.mock.calls.map(([stockCode]) => String(stockCode));
    expect(latestLookupSymbols.filter((stockCode) => stockCode.includes('600519'))).toEqual(['600519']);
    expect(getLatestDecisionSignals).toHaveBeenCalledTimes(3);
    expect(getLatestDecisionSignals).toHaveBeenCalledWith('00700.HK', {
      market: 'hk',
      limit: 1,
    });
    const aaplRow = screen.getByText('AAPL').closest('tr');
    expect(aaplRow).not.toBeNull();
    expect(within(aaplRow as HTMLTableRowElement).getByText('—')).toBeInTheDocument();
  });

  it('shows a visible partial warning when one latest holding signal lookup fails', async () => {
    getSnapshot.mockResolvedValueOnce(makeSnapshot({ positions: [
      { symbol: '600519', market: 'cn', currency: 'CNY', quantity: 1, avgCost: 1500, totalCost: 1500, lastPrice: 1600, marketValueBase: 1600, unrealizedPnlBase: 100, unrealizedPnlPct: 6.67, valuationCurrency: 'CNY', priceSource: 'history_close', priceDate: '2026-06-17', priceStale: false, priceAvailable: true },
      { symbol: 'AAPL', market: 'us', currency: 'USD', quantity: 2, avgCost: 180, totalCost: 360, lastPrice: 190, marketValueBase: 380, unrealizedPnlBase: 20, unrealizedPnlPct: 5.56, valuationCurrency: 'USD', priceSource: 'history_close', priceDate: '2026-06-17', priceStale: false, priceAvailable: true },
    ] }));
    getLatestDecisionSignals
      .mockResolvedValueOnce({
        items: [makeDecisionSignal({ stockCode: '600519', riskSummary: '已加载风险' })],
        total: 1,
        page: 1,
        pageSize: 1,
      })
      .mockRejectedValueOnce(new Error('latest AAPL failed'));

    renderPortfolioPage();

    expect(await screen.findByText('已加载风险')).toBeInTheDocument();
    expect(await screen.findByText('AI 建议降级')).toBeInTheDocument();
    expect(screen.getByText(/请求未能完成，请稍后重试/)).toBeInTheDocument();
    expect(screen.queryByText(/latest AAPL failed/)).not.toBeInTheDocument();
  });

  it('loads each unique holding through the latest endpoint once', async () => {
    getSnapshot.mockResolvedValueOnce(makeSnapshot({ positions: [
      { symbol: '600519', market: 'cn', currency: 'CNY', quantity: 1, avgCost: 1500, totalCost: 1500, lastPrice: 1600, marketValueBase: 1600, unrealizedPnlBase: 100, unrealizedPnlPct: 6.67, valuationCurrency: 'CNY', priceSource: 'history_close', priceDate: '2026-06-17', priceStale: false, priceAvailable: true },
      { symbol: '600519', market: 'cn', currency: 'CNY', quantity: 2, avgCost: 1500, totalCost: 3000, lastPrice: 1600, marketValueBase: 3200, unrealizedPnlBase: 200, unrealizedPnlPct: 6.67, valuationCurrency: 'CNY', priceSource: 'history_close', priceDate: '2026-06-17', priceStale: false, priceAvailable: true },
    ] }));
    getLatestDecisionSignals.mockResolvedValueOnce({
      items: [makeDecisionSignal({ stockCode: '600519', riskSummary: '唯一 latest 风险' })],
      total: 1,
      page: 1,
      pageSize: 1,
    });

    renderPortfolioPage();

    expect(await screen.findAllByText('唯一 latest 风险')).toHaveLength(2);
    expect(getLatestDecisionSignals).toHaveBeenCalledTimes(1);
    expect(decisionSignalsApi.list).not.toHaveBeenCalled();
  });

  it('limits concurrent latest lookups for large portfolios', async () => {
    const positions = Array.from({ length: 10 }, (_, index) => makePosition({
      symbol: `AAPL${index}`,
      market: 'us',
      currency: 'USD',
      totalCost: 100 + index,
      marketValueBase: 120 + index,
    }));
    getSnapshot.mockResolvedValueOnce(makeSnapshot({ positions }));
    let inFlight = 0;
    let maxInFlight = 0;
    getLatestDecisionSignals.mockImplementation(async () => {
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      await new Promise((resolve) => setTimeout(resolve, 5));
      inFlight -= 1;
      return { items: [], total: 0, page: 1, pageSize: 1 };
    });

    renderPortfolioPage();

    expect(await screen.findByText('AAPL0')).toBeInTheDocument();
    await waitFor(() => expect(getLatestDecisionSignals).toHaveBeenCalledTimes(10));
    await waitFor(() => expect(inFlight).toBe(0));
    expect(maxInFlight).toBeLessThanOrEqual(6);
  });

  it('submits manual analysis for a held position without exposing portfolio details in the UI call', async () => {
    getSnapshot.mockResolvedValueOnce(makeSnapshot({ fxStale: true, positions: [
      { symbol: 'HK00700', market: 'hk', currency: 'HKD', quantity: 10, avgCost: 400, totalCost: 4000, lastPrice: 420, marketValueBase: 4200, unrealizedPnlBase: 200, unrealizedPnlPct: 5, valuationCurrency: 'HKD', priceSource: 'history_close', priceDate: '2026-03-18', priceStale: true, priceAvailable: true },
    ] }));

    renderPortfolioPage();

    await waitForInitialLoad();

    const row = screen.getByText('HK00700').closest('tr');
    expect(row).not.toBeNull();
    const analyzeButton = within(row as HTMLTableRowElement).getByRole('button', { name: '分析' });
    expect(analyzeButton).toHaveAttribute('data-size', 'comfortable');
    fireEvent.click(analyzeButton);

    await waitFor(() => {
      expect(analyzePosition).toHaveBeenCalledWith('HK00700', {
        accountId: 1,
        analysisPhase: 'auto',
        force: false,
      });
    });
    expect(await screen.findByText('已提交 HK00700 分析任务：task-portfolio-1')).toBeInTheDocument();
  });

  it('sends an explicit phase for portfolio-triggered analysis', async () => {
    getSnapshot.mockResolvedValueOnce(makeSnapshot({
      positions: [makePosition({ symbol: 'AAPL', market: 'us', currency: 'USD' })],
    }));
    renderPortfolioPage();
    await waitForInitialLoad();

    chooseOption(screen.getByRole('combobox', { name: '分析阶段' }), 'postmarket');
    const row = screen.getByText('AAPL').closest('tr');
    fireEvent.click(within(row as HTMLTableRowElement).getByRole('button', { name: '分析' }));

    await waitFor(() => expect(analyzePosition).toHaveBeenCalledWith('AAPL', {
      accountId: 1,
      analysisPhase: 'postmarket',
      force: false,
    }));
  });

  it('prefers disabled feedback over empty-pair feedback when refresh is disabled', async () => {
    refreshFx.mockResolvedValueOnce({
      asOf: '2026-03-19',
      accountCount: 1,
      refreshEnabled: false,
      disabledReason: 'portfolio_fx_update_disabled',
      pairCount: 0,
      updatedCount: 0,
      staleCount: 0,
      errorCount: 0,
    });

    renderPortfolioPage();

    await waitForInitialLoad();

    fireEvent.click(screen.getByRole('button', { name: '刷新汇率' }));

    expect(await screen.findByText('汇率在线刷新已被禁用。')).toBeInTheDocument();
    expect(screen.queryByText('当前范围无可刷新的汇率对。')).not.toBeInTheDocument();
  });

  it('shows warning feedback when FX refresh still falls back to stale rates', async () => {
    refreshFx.mockResolvedValueOnce({
      asOf: '2026-03-19',
      accountCount: 1,
      pairCount: 2,
      updatedCount: 1,
      staleCount: 1,
      errorCount: 0,
    });

    renderPortfolioPage();

    await waitForInitialLoad();

    fireEvent.click(screen.getByRole('button', { name: '刷新汇率' }));

    expect(await screen.findByText(/stale\/fallback 汇率/)).toBeInTheDocument();
  });

  it('shows warning feedback when FX refresh returns online errors without stale pairs', async () => {
    refreshFx.mockResolvedValueOnce({
      asOf: '2026-03-19',
      accountCount: 1,
      pairCount: 1,
      updatedCount: 0,
      staleCount: 0,
      errorCount: 1,
    });

    renderPortfolioPage();

    await waitForInitialLoad();

    const snapshotCallsBeforeRefresh = getSnapshot.mock.calls.length;
    const riskCallsBeforeRefresh = getRisk.mock.calls.length;
    const tradeCallsBeforeRefresh = listTrades.mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: '刷新汇率' }));

    expect(await screen.findByText(/在线刷新未完全成功/)).toBeInTheDocument();
    await waitFor(() => expect(getSnapshot).toHaveBeenCalledTimes(snapshotCallsBeforeRefresh + 1));
    await waitFor(() => expect(getRisk).toHaveBeenCalledTimes(riskCallsBeforeRefresh + 1));
    expect(listTrades).toHaveBeenCalledTimes(tradeCallsBeforeRefresh);
    expect(listCashLedger).not.toHaveBeenCalled();
    expect(listCorporateActions).not.toHaveBeenCalled();
  });

  it('restores the button state and shows the existing error alert when FX refresh fails', async () => {
    refreshFx.mockRejectedValueOnce(
      createApiError(
        createParsedApiError({
          title: '刷新失败',
          message: '汇率服务暂时不可用',
        }),
      ),
    );

    renderPortfolioPage();

    await waitForInitialLoad();

    const refreshButton = screen.getByRole('button', { name: '刷新汇率' });
    fireEvent.click(refreshButton);

    const fxAlertTitle = await screen.findByText('刷新失败');
    expect(fxAlertTitle.closest('[role="alert"]')).toHaveTextContent('汇率服务暂时不可用');
    await waitFor(() => expect(screen.getByRole('button', { name: '刷新汇率' })).not.toBeDisabled());
  });

  it('does not keep success feedback when snapshot reload fails after FX refresh succeeds', async () => {
    getSnapshot
      .mockResolvedValueOnce(makeSnapshot({ fxStale: true }))
      .mockRejectedValueOnce(
        createApiError(
          createParsedApiError({
            title: '快照刷新失败',
            message: '无法加载最新持仓快照',
          }),
        ),
      );

    renderPortfolioPage();

    await waitForInitialLoad();

    fireEvent.click(screen.getByRole('button', { name: '刷新汇率' }));

    const fxAlertTitle = await screen.findByText('快照刷新失败');
    expect(fxAlertTitle.closest('[role="alert"]')).toHaveTextContent('无法加载最新持仓快照');
    await waitFor(() => expect(screen.queryByText('汇率已刷新，共更新 1 对。')).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole('button', { name: '刷新汇率' })).not.toBeDisabled());
  });

  it('drops late FX refresh results after switching to another account scope', async () => {
    getAccounts.mockResolvedValueOnce(makeAccounts([{ id: 1, name: 'Main' }, { id: 2, name: 'Alt' }]));
    getSnapshot.mockImplementation(async ({ accountId }: { accountId?: number } = {}) => {
      if (accountId === 2) {
        return makeSnapshot({ accountId: 2, fxStale: false });
      }
      return makeSnapshot({ accountId: accountId ?? 1, fxStale: true, accountCount: accountId ? 1 : 2 });
    });

    const pendingRefresh = createDeferred<{
      asOf: string;
      accountCount: number;
      pairCount: number;
      updatedCount: number;
      staleCount: number;
      errorCount: number;
    }>();
    refreshFx.mockImplementationOnce(() => pendingRefresh.promise);

    renderPortfolioPage();

    await waitForInitialLoad();

    const accountSelect = screen.getAllByRole('combobox')[0];
    chooseOption(accountSelect, '1');
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({ accountId: 1, costMethod: 'fifo', includeRealtime: false }));
    await waitForPortfolioLoad();

    fireEvent.click(screen.getByRole('button', { name: '刷新汇率' }));
    const refreshButton = await screen.findByRole('button', { name: '刷新汇率' });
    expect(refreshButton).toBeDisabled();
    expect(refreshButton).toHaveAttribute('aria-busy', 'true');
    expect(refreshButton).toHaveTextContent('刷新中...');

    chooseOption(accountSelect, '2');
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({ accountId: 2, costMethod: 'fifo', includeRealtime: false }));
    await waitFor(() => expect(screen.getByRole('button', { name: '刷新汇率' })).not.toBeDisabled());

    const snapshotCallsAfterSwitch = getSnapshot.mock.calls.length;
    const riskCallsAfterSwitch = getRisk.mock.calls.length;

    await act(async () => {
      pendingRefresh.resolve({
        asOf: '2026-03-19',
        accountCount: 1,
        pairCount: 1,
        updatedCount: 1,
        staleCount: 0,
        errorCount: 0,
      });
      await pendingRefresh.promise;
    });

    expect(getSnapshot).toHaveBeenCalledTimes(snapshotCallsAfterSwitch);
    expect(getRisk).toHaveBeenCalledTimes(riskCallsAfterSwitch);
    expect(screen.queryByText('汇率已刷新，共更新 1 对。')).not.toBeInTheDocument();
  });

  it('drops late FX refresh results after switching cost method', async () => {
    const pendingRefresh = createDeferred<{
      asOf: string;
      accountCount: number;
      pairCount: number;
      updatedCount: number;
      staleCount: number;
      errorCount: number;
    }>();
    refreshFx.mockImplementationOnce(() => pendingRefresh.promise);

    renderPortfolioPage();

    await waitForInitialLoad();

    const costMethodSelect = screen.getAllByRole('combobox')[1];

    fireEvent.click(screen.getByRole('button', { name: '刷新汇率' }));
    const refreshButton = await screen.findByRole('button', { name: '刷新汇率' });
    expect(refreshButton).toBeDisabled();
    expect(refreshButton).toHaveAttribute('aria-busy', 'true');
    expect(refreshButton).toHaveTextContent('刷新中...');

    chooseOption(costMethodSelect, 'avg');
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({ accountId: undefined, costMethod: 'avg', includeRealtime: false }));
    await waitFor(() => expect(screen.getByRole('button', { name: '刷新汇率' })).not.toBeDisabled());

    const snapshotCallsAfterSwitch = getSnapshot.mock.calls.length;
    const riskCallsAfterSwitch = getRisk.mock.calls.length;

    await act(async () => {
      pendingRefresh.resolve({
        asOf: '2026-03-19',
        accountCount: 1,
        pairCount: 1,
        updatedCount: 1,
        staleCount: 0,
        errorCount: 0,
      });
      await pendingRefresh.promise;
    });

    expect(getSnapshot).toHaveBeenCalledTimes(snapshotCallsAfterSwitch);
    expect(getRisk).toHaveBeenCalledTimes(riskCallsAfterSwitch);
    expect(screen.queryByText('汇率已刷新，共更新 1 对。')).not.toBeInTheDocument();
  });

  it('deactivates the selected account from the account toolbar and reloads accounts', async () => {
    const selectedAccountRisk = createDeferred<ReturnType<typeof makeRisk>>();
    getAccounts
      .mockResolvedValueOnce(makeAccounts([{ id: 1, name: 'Main' }, { id: 2, name: 'Alt' }]))
      .mockResolvedValueOnce(makeAccounts([{ id: 2, name: 'Alt' }]));
    getRisk
      .mockResolvedValueOnce(makeRisk())
      .mockReturnValueOnce(selectedAccountRisk.promise);

    renderPortfolioPage();

    await waitForInitialLoad();

    const accountSelect = screen.getAllByRole('combobox')[0];
    chooseOption(accountSelect, '1');

    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({ accountId: 1, costMethod: 'fifo', includeRealtime: false }));
    expect(screen.getByRole('button', { name: '删除账户' })).toBeDisabled();

    await act(async () => {
      selectedAccountRisk.resolve(makeRisk());
      await selectedAccountRisk.promise;
    });
    await waitForPortfolioLoad();
    fireEvent.click(screen.getByRole('button', { name: '删除账户' }));

    const dialog = await screen.findByText('删除持仓账户');
    expect(dialog.closest('[role="dialog"]') ?? document.body).toHaveTextContent(
      '删除后该账户会从默认列表、快照、风险和录入入口隐藏',
    );
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }));

    await waitFor(() => expect(deleteAccount).toHaveBeenCalledWith(1));
    await waitFor(() => expect(getAccounts).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText('Main (#1)')).not.toBeInTheDocument());
    fireEvent.click(accountSelect);
    const accountListbox = document.getElementById(accountSelect.getAttribute('aria-controls')!)!;
    expect(within(accountListbox).getByRole('option', { name: 'Alt (#2)' })).toBeInTheDocument();
    expect(within(accountListbox).queryByRole('option', { name: 'Main (#1)' })).not.toBeInTheDocument();
  });

  it('keeps the paper-trade endpoint unavailable for real accounts', async () => {
    renderPortfolioPage();
    await waitForInitialLoad();

    chooseOption(screen.getAllByRole('combobox')[0], '1');
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({
      accountId: 1,
      costMethod: 'fifo',
      includeRealtime: false,
    }));

    expect(screen.queryByRole('button', { name: '纸上交易' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '录入交易' })).toBeEnabled();
  });

  it('records an explicit-price paper buy and refreshes portfolio surfaces', async () => {
    getAccounts.mockResolvedValue(makeAccounts([
      { id: 1, name: 'Practice', accountType: 'paper' },
    ]));
    createPaperTrade.mockResolvedValueOnce({
      id: 81,
      price: 205.5,
      priceSource: 'manual',
    });
    renderPortfolioPage();
    await waitForInitialLoad();

    const accountSelect = screen.getAllByRole('combobox')[0];
    expect(accountSelect).toHaveTextContent('全部账户');
    chooseOption(accountSelect, '1');
    await waitFor(() => expect(accountSelect).toHaveTextContent('Practice (#1) · 纸上账户'));
    await waitForPortfolioLoad();
    expect(screen.queryByRole('button', { name: '录入交易' })).not.toBeInTheDocument();

    const snapshotCallsBeforeTrade = getSnapshot.mock.calls.length;
    const riskCallsBeforeTrade = getRisk.mock.calls.length;
    const accountCallsBeforeTrade = getAccounts.mock.calls.length;
    const tradeListCallsBeforeTrade = listTrades.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: '纸上交易' }));
    const dialog = screen.getByRole('dialog', { name: '纸上交易' });
    expect(dialog).toHaveTextContent('不计算手续费、税费或滑点');
    fireEvent.change(within(dialog).getByLabelText('股票代码'), { target: { value: 'AAPL' } });
    fireEvent.change(within(dialog).getByLabelText('数量'), { target: { value: '2' } });
    fireEvent.change(within(dialog).getByLabelText('成交价'), { target: { value: '205.5' } });
    fireEvent.change(within(dialog).getByLabelText('备注'), { target: { value: 'Practice entry' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '纸上交易' }));

    await waitFor(() => expect(createPaperTrade).toHaveBeenCalledWith(
      1,
      expect.objectContaining({
        symbol: 'AAPL',
        side: 'buy',
        quantity: 2,
        price: 205.5,
        note: 'Practice entry',
        operationId: expect.stringMatching(/^portfolio-paper-trade-/),
      }),
    ));
    expect(await screen.findByText(/已记录买入 AAPL.*成交价 205.5（输入价格）/u))
      .toBeInTheDocument();
    await waitFor(() => expect(getAccounts).toHaveBeenCalledTimes(accountCallsBeforeTrade + 1));
    await waitFor(() => expect(getSnapshot).toHaveBeenCalledTimes(snapshotCallsBeforeTrade + 1));
    await waitFor(() => expect(getRisk).toHaveBeenCalledTimes(riskCallsBeforeTrade + 1));
    await waitFor(() => expect(listTrades.mock.calls.length).toBeGreaterThan(tradeListCallsBeforeTrade));
  });

  it('keeps a recorded paper trade successful when the follow-up refresh fails and retries only the refresh', async () => {
    getAccounts.mockResolvedValue(makeAccounts([
      { id: 1, name: 'Practice', accountType: 'paper' },
    ]));
    createPaperTrade.mockResolvedValueOnce({
      id: 83,
      price: 205.5,
      priceSource: 'manual',
    });
    renderPortfolioPage();
    await waitForInitialLoad();

    chooseOption(screen.getAllByRole('combobox')[0], '1');
    await waitForPortfolioLoad();
    const accountCallsBeforeTrade = getAccounts.mock.calls.length;
    getAccounts.mockRejectedValueOnce(new Error('post-trade account refresh failed'));

    fireEvent.click(screen.getByRole('button', { name: '纸上交易' }));
    const dialog = screen.getByRole('dialog', { name: '纸上交易' });
    fireEvent.change(within(dialog).getByLabelText('股票代码'), { target: { value: 'AAPL' } });
    fireEvent.change(within(dialog).getByLabelText('数量'), { target: { value: '2' } });
    fireEvent.change(within(dialog).getByLabelText('成交价'), { target: { value: '205.5' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '纸上交易' }));

    expect(await screen.findByText(/已记录买入 AAPL.*成交价 205.5（输入价格）/u))
      .toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '纸上交易' })).not.toBeInTheDocument();
    expect(screen.queryByText('纸上交易失败')).not.toBeInTheDocument();
    expect(screen.queryByText(/余额、持仓和交易流水已刷新/u)).not.toBeInTheDocument();
    expect(await screen.findByText('纸上交易已记录，页面数据未完全刷新'))
      .toBeInTheDocument();
    expect(screen.getByText(
      '成交已经保存，但余额、持仓、风险或交易流水未能全部刷新。请重试刷新，不要重复提交同一笔交易。',
    )).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '重试刷新' }));

    await waitFor(() => expect(getAccounts).toHaveBeenCalledTimes(accountCallsBeforeTrade + 2));
    await waitFor(() => expect(
      screen.queryByText('纸上交易已记录，页面数据未完全刷新'),
    ).not.toBeInTheDocument());
    expect(createPaperTrade).toHaveBeenCalledTimes(1);
  });

  it('uses latest-close paper execution when price is omitted', async () => {
    getAccounts.mockResolvedValue(makeAccounts([
      { id: 1, name: 'Practice', accountType: 'paper' },
    ]));
    createPaperTrade.mockResolvedValueOnce({
      id: 82,
      price: 204,
      priceSource: 'latest_close',
    });
    renderPortfolioPage();
    await waitForInitialLoad();

    chooseOption(screen.getAllByRole('combobox')[0], '1');
    await waitForPortfolioLoad();
    fireEvent.click(screen.getByRole('button', { name: '纸上交易' }));
    const dialog = screen.getByRole('dialog', { name: '纸上交易' });
    fireEvent.change(within(dialog).getByLabelText('股票代码'), { target: { value: 'AAPL' } });
    fireEvent.change(within(dialog).getByLabelText('数量'), { target: { value: '1' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '纸上交易' }));

    await waitFor(() => expect(createPaperTrade).toHaveBeenCalledWith(
      1,
      expect.objectContaining({
        symbol: 'AAPL',
        quantity: 1,
        price: undefined,
      }),
    ));
    expect(await screen.findByText(/成交价 204（最新收盘价）/u)).toBeInTheDocument();
  });

  it('shows actionable paper-trade server errors and preserves the draft', async () => {
    getAccounts.mockResolvedValue(makeAccounts([
      { id: 1, name: 'Practice', accountType: 'paper' },
    ]));
    createPaperTrade.mockRejectedValueOnce({
      response: {
        status: 400,
        data: {
          error: 'insufficient_cash',
          message: 'required=10000 available=1000',
        },
      },
    });
    renderPortfolioPage();
    await waitForInitialLoad();

    chooseOption(screen.getAllByRole('combobox')[0], '1');
    await waitForPortfolioLoad();
    fireEvent.click(screen.getByRole('button', { name: '纸上交易' }));
    const dialog = screen.getByRole('dialog', { name: '纸上交易' });
    fireEvent.change(within(dialog).getByLabelText('股票代码'), { target: { value: 'AAPL' } });
    fireEvent.change(within(dialog).getByLabelText('数量'), { target: { value: '100' } });
    fireEvent.change(within(dialog).getByLabelText('成交价'), { target: { value: '100' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '纸上交易' }));

    expect(await screen.findByText(
      '模拟现金不足。请减少买入数量或填写更低的有效成交价。',
    )).toBeInTheDocument();
    expect(within(dialog).queryByText(
      '模拟现金不足。请减少买入数量或填写更低的有效成交价。',
    )).not.toBeInTheDocument();
    expect(within(dialog).getByLabelText('股票代码')).toHaveValue('AAPL');
    expect(within(dialog).getByLabelText('数量')).toHaveValue(100);
  });

  it('reuses a manual-trade operation ID only for the same failed command and refreshes after commit', async () => {
    createTrade
      .mockRejectedValueOnce(
        createApiError(createParsedApiError({ title: '提交失败', message: '响应超时' })),
      )
      .mockResolvedValueOnce({ id: 90 });
    renderPortfolioPage();
    await waitForInitialLoad();

    chooseOption(screen.getAllByRole('combobox')[0], '1');
    await waitForPortfolioLoad();
    const snapshotCallsBeforeSubmit = getSnapshot.mock.calls.length;
    const tradeListCallsBeforeSubmit = listTrades.mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: '录入交易' }));
    fireEvent.change(screen.getByLabelText('股票代码'), { target: { value: 'AAPL' } });
    fireEvent.change(screen.getByLabelText('数量'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('成交价'), { target: { value: '210' } });
    fireEvent.click(screen.getByRole('button', { name: '提交交易' }));

    expect(await screen.findByText('提交失败')).toBeInTheDocument();
    const firstOperationId = createTrade.mock.calls[0][0].operationId;
    expect(firstOperationId).toMatch(/^portfolio-trade-/);
    expect(getSnapshot).toHaveBeenCalledTimes(snapshotCallsBeforeSubmit);
    expect(listTrades).toHaveBeenCalledTimes(tradeListCallsBeforeSubmit);

    fireEvent.click(screen.getByRole('button', { name: '提交交易' }));
    await waitFor(() => expect(createTrade).toHaveBeenCalledTimes(2));
    expect(createTrade.mock.calls[1][0].operationId).toBe(firstOperationId);
    await waitFor(() => expect(getSnapshot).toHaveBeenCalledTimes(snapshotCallsBeforeSubmit + 1));
    await waitFor(() => expect(listTrades).toHaveBeenCalledTimes(tradeListCallsBeforeSubmit + 1));
  });

  it('scopes paper-trade operation identity to the selected account after a failed attempt', async () => {
    getAccounts.mockResolvedValue(makeAccounts([
      { id: 1, name: 'Practice One', accountType: 'paper' },
      { id: 2, name: 'Practice Two', accountType: 'paper' },
    ]));
    createPaperTrade
      .mockRejectedValueOnce(
        createApiError(createParsedApiError({ title: '纸上交易失败', message: '响应超时' })),
      )
      .mockResolvedValueOnce({ id: 93, price: 205, priceSource: 'manual' });
    renderPortfolioPage();
    await waitForInitialLoad();

    const accountSelect = screen.getAllByRole('combobox')[0];
    chooseOption(accountSelect, '1');
    await waitForPortfolioLoad();
    fireEvent.click(screen.getByRole('button', { name: '纸上交易' }));
    const dialog = screen.getByRole('dialog', { name: '纸上交易' });
    fireEvent.change(within(dialog).getByLabelText('股票代码'), { target: { value: 'AAPL' } });
    fireEvent.change(within(dialog).getByLabelText('数量'), { target: { value: '1' } });
    fireEvent.change(within(dialog).getByLabelText('成交价'), { target: { value: '205' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '纸上交易' }));

    expect(await screen.findByText('纸上交易失败')).toBeInTheDocument();
    expect(within(dialog).queryByText('纸上交易失败')).not.toBeInTheDocument();
    const accountOneOperationId = createPaperTrade.mock.calls[0][1].operationId;

    chooseOption(accountSelect, '2');
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({
      accountId: 2,
      costMethod: 'fifo',
      includeRealtime: false,
    }));
    fireEvent.click(within(dialog).getByRole('button', { name: '纸上交易' }));

    await waitFor(() => expect(createPaperTrade).toHaveBeenCalledTimes(2));
    expect(createPaperTrade.mock.calls[1][0]).toBe(2);
    expect(createPaperTrade.mock.calls[1][1].operationId).not.toBe(accountOneOperationId);
  });

  it('reuses the cash operation ID after a failed request and preserves the form', async () => {
    createCashLedger
      .mockRejectedValueOnce(
        createApiError(createParsedApiError({ title: '提交失败', message: '响应超时' })),
      )
      .mockResolvedValueOnce({ id: 91 });
    renderPortfolioPage();
    await waitForInitialLoad();

    chooseOption(screen.getAllByRole('combobox')[0], '1');
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({ accountId: 1, costMethod: 'fifo', includeRealtime: false }));
    fireEvent.click(screen.getByRole('button', { name: '录入资金流水' }));
    fireEvent.change(screen.getByLabelText('金额'), { target: { value: '1200' } });
    fireEvent.click(screen.getByRole('button', { name: '提交资金流水' }));

    expect(await screen.findByText('提交失败')).toBeInTheDocument();
    expect(screen.getByLabelText('金额')).toHaveValue(1200);
    const firstOperationId = createCashLedger.mock.calls[0][0].operationId;
    expect(firstOperationId).toMatch(/^portfolio-cash-/);

    fireEvent.click(screen.getByRole('button', { name: '提交资金流水' }));
    await waitFor(() => expect(createCashLedger).toHaveBeenCalledTimes(2));
    expect(createCashLedger.mock.calls[1][0].operationId).toBe(firstOperationId);
  });

  it('reuses a corporate-action operation ID after failure and refreshes after commit', async () => {
    createCorporateAction
      .mockRejectedValueOnce(
        createApiError(createParsedApiError({ title: '提交失败', message: '响应超时' })),
      )
      .mockResolvedValueOnce({ id: 94 });
    renderPortfolioPage();
    await waitForInitialLoad();

    chooseOption(screen.getAllByRole('combobox')[0], '1');
    await waitForPortfolioLoad();
    const snapshotCallsBeforeSubmit = getSnapshot.mock.calls.length;
    const tradeListCallsBeforeSubmit = listTrades.mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: '录入公司行为' }));
    fireEvent.change(screen.getByLabelText('股票代码'), { target: { value: 'AAPL' } });
    fireEvent.change(screen.getByLabelText('每股分红'), { target: { value: '0.25' } });
    fireEvent.click(screen.getByRole('button', { name: '提交公司行为' }));

    expect(await screen.findByText('提交失败')).toBeInTheDocument();
    const firstOperationId = createCorporateAction.mock.calls[0][0].operationId;
    expect(firstOperationId).toMatch(/^portfolio-corporate-/);

    fireEvent.click(screen.getByRole('button', { name: '提交公司行为' }));
    await waitFor(() => expect(createCorporateAction).toHaveBeenCalledTimes(2));
    expect(createCorporateAction.mock.calls[1][0].operationId).toBe(firstOperationId);
    await waitFor(() => expect(getSnapshot).toHaveBeenCalledTimes(snapshotCallsBeforeSubmit + 1));
    await waitFor(() => expect(listTrades).toHaveBeenCalledTimes(tradeListCallsBeforeSubmit + 1));
  });

  it('refreshes the active account scope when a pending mutation commits after navigation', async () => {
    const pendingTrade = createDeferred<{ id: number }>();
    getAccounts.mockResolvedValueOnce(makeAccounts([
      { id: 1, name: 'Main' },
      { id: 2, name: 'Alt' },
    ]));
    createTrade.mockReturnValueOnce(pendingTrade.promise);
    renderPortfolioPage();
    await waitForInitialLoad();

    const accountSelect = screen.getAllByRole('combobox')[0];
    chooseOption(accountSelect, '1');
    await waitForPortfolioLoad();
    fireEvent.click(screen.getByRole('button', { name: '录入交易' }));
    fireEvent.change(screen.getByLabelText('股票代码'), { target: { value: 'AAPL' } });
    fireEvent.change(screen.getByLabelText('数量'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('成交价'), { target: { value: '210' } });
    fireEvent.click(screen.getByRole('button', { name: '提交交易' }));

    chooseOption(accountSelect, '2');
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({
      accountId: 2,
      costMethod: 'fifo',
      includeRealtime: false,
    }));
    const snapshotCallsBeforeCommit = getSnapshot.mock.calls.length;
    const tradeListCallsBeforeCommit = listTrades.mock.calls.length;

    await act(async () => {
      pendingTrade.resolve({ id: 95 });
      await pendingTrade.promise;
    });

    await waitFor(() => expect(getSnapshot).toHaveBeenCalledTimes(snapshotCallsBeforeCommit + 1));
    await waitFor(() => expect(listTrades).toHaveBeenCalledTimes(tradeListCallsBeforeCommit + 1));
    expect(getSnapshot).toHaveBeenLastCalledWith({
      accountId: 2,
      costMethod: 'fifo',
      includeRealtime: false,
    });
    expect(listTrades).toHaveBeenLastCalledWith(expect.objectContaining({ accountId: 2 }));
  });

  it('locks trade fields and close behavior while a mutation is pending', async () => {
    const pendingTrade = createDeferred<{ id: number }>();
    createTrade.mockReturnValueOnce(pendingTrade.promise);
    renderPortfolioPage();
    await waitForInitialLoad();

    chooseOption(screen.getAllByRole('combobox')[0], '1');
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({ accountId: 1, costMethod: 'fifo', includeRealtime: false }));
    fireEvent.click(screen.getByRole('button', { name: '录入交易' }));
    expect(screen.getByLabelText('股票代码')).toHaveAttribute('data-size', 'comfortable');
    expect(screen.getByLabelText('数量')).toHaveAttribute('data-size', 'comfortable');
    expect(screen.getByLabelText('成交价')).toHaveAttribute('data-size', 'comfortable');
    fireEvent.change(screen.getByLabelText('股票代码'), { target: { value: 'AAPL' } });
    fireEvent.change(screen.getByLabelText('数量'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('成交价'), { target: { value: '210' } });
    fireEvent.click(screen.getByRole('button', { name: '提交交易' }));

    const dialog = screen.getByRole('dialog', { name: '手工录入：交易' });
    expect(screen.getByLabelText('股票代码')).toBeDisabled();
    expect(screen.getByLabelText('数量')).toBeDisabled();
    const submitButton = screen.getByRole('button', { name: '提交交易' });
    expect(submitButton).toBeDisabled();
    expect(submitButton).toHaveAttribute('aria-busy', 'true');
    expect(submitButton).toHaveTextContent('提交中');
    expect(screen.getByLabelText('交易日期').closest('.grid')).toHaveClass('grid-cols-1', 'sm:grid-cols-2');
    expect(within(dialog).getByRole('button', { name: '关闭' })).toBeDisabled();
    fireEvent.click(within(dialog).getByRole('button', { name: '关闭' }));
    expect(screen.getByRole('dialog', { name: '手工录入：交易' })).toBeInTheDocument();

    await act(async () => {
      pendingTrade.resolve({ id: 92 });
      await pendingTrade.promise;
    });
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '手工录入：交易' })).not.toBeInTheDocument());
  });

  it('removes event-log date filters after both dates are set and cleared', async () => {
    renderPortfolioPage();
    fireEvent.click(await screen.findByRole('button', { name: '事件记录' }));
    const from = chooseVisibleDate('开始日期');
    const to = chooseVisibleDate('结束日期');
    listTrades.mockClear();
    fireEvent.click(screen.getByRole('button', { name: '刷新流水' }));

    await waitFor(() => {
      expect(listTrades).toHaveBeenLastCalledWith(expect.objectContaining({
        dateFrom: from,
        dateTo: to,
      }));
    });

    fireEvent.click(screen.getByRole('button', { name: '清除 开始日期' }));
    fireEvent.click(screen.getByRole('button', { name: '清除 结束日期' }));
    expect(screen.getByLabelText('开始日期')).toHaveValue('');
    expect(screen.getByLabelText('结束日期')).toHaveValue('');
    await waitFor(() => expect(screen.getByRole('button', { name: '刷新流水' })).toBeEnabled());

    listTrades.mockClear();
    fireEvent.click(screen.getByRole('button', { name: '刷新流水' }));

    await waitFor(() => {
      expect(listTrades).toHaveBeenLastCalledWith(expect.objectContaining({
        dateFrom: undefined,
        dateTo: undefined,
      }));
    });
  });

  it('reuses a failed CSV commit operation and keeps result mode separate from the checkbox', async () => {
    commitCsvImport
      .mockRejectedValueOnce(
        createApiError(createParsedApiError({ title: '导入失败', message: '响应超时' })),
      )
      .mockResolvedValueOnce({
        accountId: 1,
        recordCount: 1,
        insertedCount: 1,
        duplicateCount: 0,
        failedCount: 0,
        dryRun: false,
        errors: [],
      });
    renderPortfolioPage();
    await waitForInitialLoad();

    chooseOption(screen.getAllByRole('combobox')[0], '1');
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({ accountId: 1, costMethod: 'fifo', includeRealtime: false }));
    const file = new File(['header\nrow'], 'trades.csv', { type: 'text/csv' });
    await openCsvImportWizardAndReachConfirm(file);
    expect(screen.getByLabelText('仅预演（不写入）').closest('label')).toHaveClass('min-h-11');
    fireEvent.click(screen.getByLabelText('仅预演（不写入）'));
    fireEvent.click(screen.getByRole('button', { name: '提交导入' }));

    expect(await screen.findByText('导入失败')).toBeInTheDocument();
    const firstOperationId = commitCsvImport.mock.calls[0][3];
    const snapshotCallsBeforeRetry = getSnapshot.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: '提交导入' }));
    await waitFor(() => expect(commitCsvImport).toHaveBeenCalledTimes(2));
    expect(commitCsvImport.mock.calls[1][3]).toBe(firstOperationId);
    expect(await screen.findByText('CSV 提交结果')).toBeInTheDocument();
    await waitFor(() => expect(getSnapshot).toHaveBeenCalledTimes(snapshotCallsBeforeRetry + 1));

    fireEvent.click(screen.getByLabelText('仅预演（不写入）'));
    expect(screen.getByText('CSV 提交结果')).toBeInTheDocument();
    expect(screen.queryByText('CSV 预演结果')).not.toBeInTheDocument();
  });

  it('starts a new CSV operation after a partial result so failed rows can retry', async () => {
    commitCsvImport
      .mockResolvedValueOnce({
        accountId: 1,
        recordCount: 2,
        insertedCount: 1,
        duplicateCount: 0,
        failedCount: 1,
        dryRun: false,
        errors: ['idx=1: temporary failure'],
      })
      .mockResolvedValueOnce({
        accountId: 1,
        recordCount: 2,
        insertedCount: 1,
        duplicateCount: 1,
        failedCount: 0,
        dryRun: false,
        errors: [],
      });
    renderPortfolioPage();
    await waitForInitialLoad();

    chooseOption(screen.getAllByRole('combobox')[0], '1');
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({ accountId: 1, costMethod: 'fifo', includeRealtime: false }));
    const file = new File(['header\nrow'], 'partial-trades.csv', { type: 'text/csv' });
    await openCsvImportWizardAndReachConfirm(file);
    fireEvent.click(screen.getByLabelText('仅预演（不写入）'));
    fireEvent.click(screen.getByRole('button', { name: '提交导入' }));

    await waitFor(() => expect(commitCsvImport).toHaveBeenCalledTimes(1));
    const firstOperationId = commitCsvImport.mock.calls[0][3];
    await screen.findByText(/失败 1 条/);
    fireEvent.click(screen.getByRole('button', { name: '提交导入' }));

    await waitFor(() => expect(commitCsvImport).toHaveBeenCalledTimes(2));
    expect(commitCsvImport.mock.calls[1][3]).not.toBe(firstOperationId);
  });
});
