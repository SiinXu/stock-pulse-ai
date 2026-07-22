import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AlertsPage from '../AlertsPage';

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

const {
  listRules,
  createRule,
  getRule,
  updateRule,
  deleteRule,
  enableRule,
  disableRule,
  testRule,
  listTriggers,
  listNotifications,
} = vi.hoisted(() => ({
  listRules: vi.fn(),
  createRule: vi.fn(),
  getRule: vi.fn(),
  updateRule: vi.fn(),
  deleteRule: vi.fn(),
  enableRule: vi.fn(),
  disableRule: vi.fn(),
  testRule: vi.fn(),
  listTriggers: vi.fn(),
  listNotifications: vi.fn(),
}));

vi.mock('../../api/alerts', () => ({
  alertsApi: {
    listRules,
    createRule,
    getRule,
    updateRule,
    deleteRule,
    enableRule,
    disableRule,
    testRule,
    listTriggers,
    listNotifications,
  },
}));

vi.mock('../../api/portfolio', () => ({
  portfolioApi: {
    getAccounts: vi.fn().mockResolvedValue({ accounts: [] }),
  },
}));

const parsedError = {
  title: '加载失败',
  message: '告警 API 不可用',
  rawMessage: '告警 API 不可用',
  category: 'http_error' as const,
  status: 500,
};

const rule = {
  id: 1,
  name: '茅台价格突破',
  targetScope: 'single_symbol' as const,
  target: '600519',
  alertType: 'price_cross' as const,
  parameters: { direction: 'above' as const, price: 1800 },
  severity: 'warning' as const,
  enabled: true,
  source: 'api',
  createdAt: '2026-05-18T09:00:00',
  updatedAt: '2026-05-18T09:30:00',
};

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

beforeEach(() => {
  vi.clearAllMocks();
  listRules.mockResolvedValue({ items: [rule], total: 1, page: 1, pageSize: 20 });
  listTriggers.mockResolvedValue({
    items: [
      {
        id: 10,
        ruleId: 1,
        target: '600519',
        observedValue: 1801,
        threshold: 1800,
        reason: '600519 price above 1800',
        dataSource: 'realtime_quote',
        dataTimestamp: '2026-05-18T09:30:00',
        triggeredAt: '2026-05-18T09:30:01',
        status: 'triggered',
      },
    ],
    total: 1,
    page: 1,
    pageSize: 20,
  });
  listNotifications.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });
  testRule.mockResolvedValue({
    ruleId: 1,
    status: 'triggered',
    triggered: true,
    observedValue: 1801,
    message: '600519 price above 1800',
  });
  createRule.mockResolvedValue(rule);
  getRule.mockResolvedValue(rule);
  updateRule.mockResolvedValue({ ...rule, parameters: { direction: 'above', price: 1900 } });
  disableRule.mockResolvedValue({ ...rule, enabled: false });
  enableRule.mockResolvedValue(rule);
  deleteRule.mockResolvedValue({ deleted: 1 });
});

describe('AlertsPage rule editing', () => {
  it('loads the current rule on edit and PATCHes an updated payload', async () => {
    render(<AlertsPage />);
    await waitFor(() => expect(listRules).toHaveBeenCalled());

    fireEvent.click(await screen.findByRole('button', { name: '编辑 茅台价格突破' }));
    await waitFor(() => expect(getRule).toHaveBeenCalledWith(1));

    // The edit modal seeds the current threshold; change it and save.
    const priceInput = await screen.findByDisplayValue('1800');
    fireEvent.change(priceInput, { target: { value: '1900' } });
    fireEvent.click(screen.getByRole('button', { name: '更新规则' }));

    await waitFor(() => expect(updateRule).toHaveBeenCalledWith(1, expect.objectContaining({
      alertType: 'price_cross',
      parameters: { direction: 'above', price: 1900 },
    })));
    await waitFor(() => expect(screen.getByText('更新成功')).toBeTruthy());
  });

  it('does not let a slower edit-load overwrite a newer one', async () => {
    const ruleB = { ...rule, id: 2, name: 'B 规则', parameters: { direction: 'above' as const, price: 2000 } };
    listRules.mockResolvedValue({ items: [rule, ruleB], total: 2, page: 1, pageSize: 20 });
    const deferredA = createDeferred<typeof rule>();
    getRule.mockImplementation((id: number) => (id === 1 ? deferredA.promise : Promise.resolve(ruleB)));

    render(<AlertsPage />);
    await waitFor(() => expect(listRules).toHaveBeenCalled());

    fireEvent.click(await screen.findByRole('button', { name: '编辑 茅台价格突破' }));
    await waitFor(() => expect(getRule).toHaveBeenCalledWith(1));
    // Close rule A's modal (its load stays pending) so the list is reachable,
    // then open rule B.
    fireEvent.keyDown(document.body, { key: 'Escape' });
    fireEvent.click(await screen.findByRole('button', { name: '编辑 B 规则' }));
    await waitFor(() => expect(screen.getByDisplayValue('2000')).toBeTruthy());

    await act(async () => {
      deferredA.resolve(rule);
      await Promise.resolve();
    });

    // The late rule-A response must not replace the newer rule-B form.
    expect(screen.getByDisplayValue('2000')).toBeTruthy();
    expect(screen.queryByDisplayValue('1800')).toBeNull();
  });
});

describe('AlertsPage', () => {
  it('loads rules, trigger history, and notification empty state', async () => {
    render(<AlertsPage />);

    expect(screen.getByText('管理事件告警、日线技术指标、自选股、持仓/账户联动和大盘红绿灯规则，执行一次性测试，并查看后台评估任务记录的触发历史。')).toBeInTheDocument();
    expect(await screen.findByText('茅台价格突破')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '触发历史' }));
    expect(await screen.findByText('600519 price above 1800')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '通知尝试记录' }));
    expect(await screen.findByText('暂无通知尝试记录')).toBeInTheDocument();
    expect(listRules).toHaveBeenCalledWith({
      enabled: undefined,
      alertType: undefined,
      page: 1,
      pageSize: 20,
    });
    expect(listTriggers).toHaveBeenCalledWith({ page: 1, pageSize: 20 });
    expect(listNotifications).toHaveBeenCalledWith({ page: 1, pageSize: 20 });
  });

  it('filters notification attempts by channel and delivery status', async () => {
    render(<AlertsPage />);

    await screen.findByText('茅台价格突破');
    fireEvent.click(screen.getByRole('tab', { name: '通知尝试记录' }));
    chooseOption(screen.getByLabelText('渠道'), 'email');
    await waitFor(() => expect(listNotifications).toHaveBeenLastCalledWith({
      channel: 'email',
      page: 1,
      pageSize: 20,
    }));

    chooseOption(screen.getByLabelText('状态'), 'failure');
    await waitFor(() => expect(listNotifications).toHaveBeenLastCalledWith({
      channel: 'email',
      success: false,
      page: 1,
      pageSize: 20,
    }));
  });

  it('runs a dry-run test and renders only declared response fields', async () => {
    listTriggers.mockResolvedValueOnce({ items: [], total: 0, page: 1, pageSize: 20 });
    render(<AlertsPage />);

    fireEvent.click(await screen.findByRole('button', { name: '测试' }));

    await waitFor(() => expect(testRule).toHaveBeenCalledWith(1));
    const testResultTitle = await screen.findByText('测试结果');
    const testResult = testResultTitle.closest('[role="status"]');
    expect(testResult).not.toBeNull();
    expect(within(testResult as HTMLElement).getByText(/600519 price above 1800/)).toBeInTheDocument();
    expect(within(testResult as HTMLElement).getByText(/观察值: 1801/)).toBeInTheDocument();
    expect(within(testResult as HTMLElement).queryByText(/realtime_quote/)).not.toBeInTheDocument();
  });

  it('renders batch dry-run summary and target results', async () => {
    testRule.mockResolvedValueOnce({
      ruleId: 1,
      targetScope: 'watchlist',
      status: 'triggered',
      triggered: true,
      observedValue: 11,
      message: 'Evaluated 2 targets',
      evaluatedCount: 2,
      triggeredCount: 1,
      degradedCount: 1,
      skippedCount: 0,
      targetResults: [
        {
          target: '600519',
          displayTarget: '自选股 - 600519',
          status: 'triggered',
          recordStatus: 'triggered',
          triggered: true,
          observedValue: 11,
          message: 'triggered',
        },
        {
          target: '000001',
          displayTarget: '自选股 - 000001',
          status: 'not_triggered',
          recordStatus: 'degraded',
          triggered: false,
          observedValue: null,
          message: 'degraded',
        },
      ],
    });
    render(<AlertsPage />);

    fireEvent.click(await screen.findByRole('button', { name: '测试' }));

    expect(await screen.findByText(/评估 2 · 触发 1 · 降级 1 · 跳过 0/)).toBeInTheDocument();
    expect(screen.getByText('自选股 - 600519')).toBeInTheDocument();
    expect(screen.getByText(/未触发 \/ 降级/)).toBeInTheDocument();
  });

  it('creates a rule through the page form and reloads rules', async () => {
    render(<AlertsPage />);

    await screen.findByText('茅台价格突破');
    fireEvent.click(screen.getByRole('button', { name: '创建告警规则' }));
    fireEvent.change(screen.getByLabelText('标的代码'), { target: { value: 'aapl' } });
    fireEvent.change(screen.getByLabelText('价格阈值'), { target: { value: '200' } });
    fireEvent.click(screen.getByRole('button', { name: '创建规则' }));

    await waitFor(() => {
      expect(createRule).toHaveBeenCalledWith(expect.objectContaining({
        target: 'AAPL',
        alertType: 'price_cross',
        parameters: { direction: 'above', price: 200 },
      }));
    });
    expect(await screen.findByText(/已创建告警规则/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '关闭' })).toHaveClass('min-h-11', 'min-w-11');
  });

  it('keeps create form values when create API fails', async () => {
    createRule.mockRejectedValueOnce({ parsedError });
    render(<AlertsPage />);

    await screen.findByText('茅台价格突破');
    fireEvent.click(screen.getByRole('button', { name: '创建告警规则' }));
    fireEvent.change(screen.getByLabelText('标的代码'), { target: { value: 'aapl' } });
    fireEvent.change(screen.getByLabelText('价格阈值'), { target: { value: '200' } });
    fireEvent.click(screen.getByRole('button', { name: '创建规则' }));

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('加载失败')).toBeInTheDocument();
    expect(screen.getByLabelText('标的代码')).toHaveValue('aapl');
    expect(screen.getByLabelText('价格阈值')).toHaveValue(200);
  });

  it('keeps concurrent operations busy for each rule independently', async () => {
    const secondRule = { ...rule, id: 2, name: '苹果价格突破', target: 'AAPL' };
    const disableRequest = createDeferred<typeof rule>();
    const testRequest = createDeferred<{
      ruleId: number;
      status: 'not_triggered';
      triggered: boolean;
      message: string;
    }>();
    listRules.mockResolvedValue({ items: [rule, secondRule], total: 2, page: 1, pageSize: 20 });
    disableRule.mockReturnValueOnce(disableRequest.promise);
    testRule.mockReturnValueOnce(testRequest.promise);

    render(<AlertsPage />);

    const firstRow = (await screen.findByText('茅台价格突破')).closest('tr') as HTMLElement;
    const secondRow = screen.getByText('苹果价格突破').closest('tr') as HTMLElement;
    fireEvent.click(within(firstRow).getByRole('button', { name: '停用' }));
    fireEvent.click(within(secondRow).getByRole('button', { name: '测试' }));
    const firstToggle = within(firstRow).getByRole('button', { name: '停用' });
    const secondTest = within(secondRow).getByRole('button', { name: '测试' });
    expect(firstToggle).toBeDisabled();
    expect(firstToggle).toHaveAttribute('aria-busy', 'true');
    expect(firstToggle).toHaveTextContent('停用中');
    expect(secondTest).toBeDisabled();
    expect(secondTest).toHaveAttribute('aria-busy', 'true');
    expect(secondTest).toHaveTextContent('测试中');

    await act(async () => {
      disableRequest.resolve({ ...rule, enabled: false });
    });
    await waitFor(() => expect(within(firstRow).getByRole('button', { name: '停用' })).not.toHaveAttribute('aria-busy'));
    expect(within(secondRow).getByRole('button', { name: '测试' })).toHaveAttribute('aria-busy', 'true');

    await act(async () => {
      testRequest.resolve({ ruleId: 2, status: 'not_triggered', triggered: false, message: 'not triggered' });
    });
    await waitFor(() => expect(within(secondRow).getByRole('button', { name: '测试' })).not.toHaveAttribute('aria-busy'));
  });

  it('clamps rules pagination when a mutation leaves the current page empty', async () => {
    const page2Rule = { ...rule, id: 2, name: '第二页规则', target: 'AAPL' };
    listRules
      .mockResolvedValueOnce({ items: [rule], total: 21, page: 1, pageSize: 20 })
      .mockResolvedValueOnce({ items: [page2Rule], total: 21, page: 2, pageSize: 20 })
      .mockResolvedValueOnce({ items: [], total: 20, page: 2, pageSize: 20 })
      .mockResolvedValue({ items: [rule], total: 20, page: 1, pageSize: 20 });

    render(<AlertsPage />);

    expect(await screen.findByText('茅台价格突破')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '2' }));
    expect(await screen.findByText('第二页规则')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('删除 第二页规则'));
    fireEvent.click(await screen.findByRole('button', { name: '删除' }));

    await waitFor(() => expect(deleteRule).toHaveBeenCalledWith(2));
    await waitFor(() => {
      expect(listRules).toHaveBeenCalledWith({
        enabled: undefined,
        alertType: undefined,
        page: 1,
        pageSize: 20,
      });
    });
    expect(await screen.findByText('茅台价格突破')).toBeInTheDocument();
  });

  it('keeps the latest rules response when filter requests resolve out of order', async () => {
    const initialRequest = createDeferred<{ items: Array<typeof rule>; total: number; page: number; pageSize: number }>();
    const filteredRequest = createDeferred<{ items: Array<typeof rule>; total: number; page: number; pageSize: number }>();
    const staleRule = { ...rule, id: 3, name: '旧筛选规则', enabled: true };
    const filteredRule = { ...rule, id: 4, name: '停用规则', enabled: false };
    listRules
      .mockReset()
      .mockReturnValueOnce(initialRequest.promise)
      .mockReturnValueOnce(filteredRequest.promise);

    render(<AlertsPage />);

    chooseOption(screen.getByLabelText('启停状态'), 'disabled');
    await waitFor(() => expect(listRules).toHaveBeenCalledTimes(2));

    filteredRequest.resolve({ items: [filteredRule], total: 1, page: 1, pageSize: 20 });
    expect(await screen.findByText('停用规则')).toBeInTheDocument();

    initialRequest.resolve({ items: [staleRule], total: 1, page: 1, pageSize: 20 });
    await waitFor(() => expect(screen.queryByText('旧筛选规则')).not.toBeInTheDocument());
    expect(screen.getByText('停用规则')).toBeInTheDocument();
  });

  it('renders API errors through ApiErrorAlert', async () => {
    listRules.mockRejectedValueOnce({ parsedError });

    render(<AlertsPage />);

    expect(await screen.findByText('加载失败')).toBeInTheDocument();
    expect(screen.getByText('告警 API 不可用')).toBeInTheDocument();
  });
});
