import { fireEvent, render, screen, within } from '@testing-library/react';
import type React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AlertRuleList } from '../AlertRuleList';
import { chooseOption, openListbox } from '../../../test-utils';

// jsdom does not implement scrollIntoView, while Select calls it to keep the active item visible when opening a dropdown.
if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { AlertRuleItem } from '../../../types/alerts';
import { UI_LANGUAGE_STORAGE_KEY } from '../../../utils/uiLanguage';

/** Capture before any test overrides so afterEach can restore (vi.restoreAllMocks does not undo defineProperty). */
const originalMatchMediaDescriptor = Object.getOwnPropertyDescriptor(window, 'matchMedia');

function setDesktopViewport(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

function restoreMatchMedia() {
  if (originalMatchMediaDescriptor) {
    Object.defineProperty(window, 'matchMedia', originalMatchMediaDescriptor);
  }
}

const rules: AlertRuleItem[] = [
  {
    id: 1,
    name: '茅台价格突破',
    targetScope: 'single_symbol',
    target: '600519',
    alertType: 'price_cross',
    parameters: { direction: 'above', price: 1800 },
    severity: 'warning',
    enabled: true,
    source: 'api',
    cooldownUntil: '2099-05-18T10:30:00',
    cooldownActive: true,
    createdAt: '2026-05-18T09:00:00',
    updatedAt: '2026-05-18T09:30:00',
  },
  {
    id: 2,
    name: 'MACD 金叉',
    targetScope: 'single_symbol',
    target: '300750',
    alertType: 'macd_cross',
    parameters: { direction: 'bullish_cross', fastPeriod: 12, slowPeriod: 26, signalPeriod: 9 },
    severity: 'info',
    enabled: true,
    source: 'api',
    cooldownPolicy: { cooldown_seconds: 0 },
    cooldownActive: false,
    createdAt: '2026-05-18T09:00:00',
    updatedAt: '2026-05-18T09:30:00',
  },
  {
    id: 3,
    name: 'KDJ 死叉',
    targetScope: 'single_symbol',
    target: '000001',
    alertType: 'kdj_cross',
    parameters: { direction: 'bearish_cross', period: 9, kPeriod: 3, dPeriod: 3 },
    severity: 'warning',
    enabled: true,
    source: 'api',
    cooldownPolicy: { cooldown_seconds: 3600 },
    cooldownActive: false,
    createdAt: '2026-05-18T09:00:00',
    updatedAt: '2026-05-18T09:30:00',
  },
];

describe('AlertRuleList', () => {
  const onEnabledFilterChange = vi.fn();
  const onAlertTypeFilterChange = vi.fn();
  const onPageChange = vi.fn();
  const onToggleEnabled = vi.fn();
  const onDelete = vi.fn();
  const onEdit = vi.fn();
  const onTest = vi.fn();
  const onCreateRule = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    // Default to mobile viewport so existing AdvancedFilterSheet / dialog coverage stays valid.
    setDesktopViewport(false);
  });

  afterEach(() => {
    restoreMatchMedia();
  });

  function openFilters() {
    fireEvent.click(screen.getByRole('button', { name: /筛选/ }));
    return screen.getByRole('dialog', { name: '筛选' });
  }

  function applyFilters(dialog: HTMLElement) {
    fireEvent.click(within(dialog).getByRole('button', { name: '应用筛选' }));
  }

  function renderList(overrides: Partial<React.ComponentProps<typeof AlertRuleList>> = {}) {
    render(
      <AlertRuleList
        rules={rules}
        total={40}
        page={1}
        pageSize={20}
        enabledFilter="all"
        alertTypeFilter="all"
        onEnabledFilterChange={onEnabledFilterChange}
        onAlertTypeFilterChange={onAlertTypeFilterChange}
        onPageChange={onPageChange}
        onToggleEnabled={onToggleEnabled}
        onDelete={onDelete}
        onEdit={onEdit}
        onTest={onTest}
        onCreateRule={onCreateRule}
        createRuleLabel="创建告警规则"
        {...overrides}
      />,
    );
  }

  function renderEnglishList(overrides: Partial<React.ComponentProps<typeof AlertRuleList>> = {}) {
    window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'en');
    render(
      <UiLanguageProvider>
        <AlertRuleList
          rules={rules}
          total={40}
          page={1}
          pageSize={20}
          enabledFilter="all"
          alertTypeFilter="all"
          onEnabledFilterChange={onEnabledFilterChange}
          onAlertTypeFilterChange={onAlertTypeFilterChange}
          onPageChange={onPageChange}
          onToggleEnabled={onToggleEnabled}
          onDelete={onDelete}
          onEdit={onEdit}
          onTest={onTest}
          onCreateRule={onCreateRule}
          createRuleLabel="Create alert rule"
          {...overrides}
        />
      </UiLanguageProvider>,
    );
  }

  it('renders rules, collapsed filters, and pagination', () => {
    renderList();

    expect(screen.getByText('茅台价格突破')).toBeInTheDocument();
    expect(screen.getByText('600519')).toBeInTheDocument();
    expect(screen.getAllByText('价格突破').length).toBeGreaterThan(0);
    expect(screen.getByText('上破 1800')).toBeInTheDocument();
    expect(screen.getAllByText('MACD 金叉/死叉').length).toBeGreaterThan(0);
    expect(screen.getByText('MACD(12,26,9) 金叉')).toBeInTheDocument();
    expect(screen.getByText('KDJ(9,3,3) 死叉')).toBeInTheDocument();
    expect(screen.getByText('冷却中')).toBeInTheDocument();
    expect(screen.getByText('后端默认 · 24 小时')).toBeInTheDocument();
    expect(screen.getByText('关闭冷却 · 0 秒')).toBeInTheDocument();
    expect(screen.getByText('自定义 · 3,600 秒')).toBeInTheDocument();

    const dialog = openFilters();
    chooseOption(within(dialog).getByLabelText('启停状态'), 'enabled');
    chooseOption(within(dialog).getByLabelText('规则类型'), 'price_cross');
    applyFilters(dialog);

    fireEvent.click(screen.getByRole('button', { name: '2' }));

    expect(onEnabledFilterChange).toHaveBeenCalledWith('enabled');
    expect(onAlertTypeFilterChange).toHaveBeenCalledWith('price_cross');
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it('keeps the filter entry in the card header and shows active filter chips', () => {
    renderList({ enabledFilter: 'enabled', alertTypeFilter: 'price_cross' });

    const heading = screen.getByRole('heading', { name: '告警规则' });
    const header = heading.parentElement?.parentElement;
    expect(header).toContainElement(screen.getByRole('button', { name: '筛选，已启用 2 项' }));
    expect(heading.closest('[data-surface-level]')).toHaveClass(
      '[&>div:first-child]:flex-col',
      'sm:[&>div:first-child]:flex-row',
    );
    expect(screen.getByRole('list', { name: '已应用筛选' })).toBeVisible();
    expect(screen.getByRole('button', { name: '移除启停状态筛选' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '移除规则类型筛选' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '清除筛选' }));
    expect(onEnabledFilterChange).toHaveBeenCalledWith('all');
    expect(onAlertTypeFilterChange).toHaveBeenCalledWith('all');
  });

  it('uses backend cooldownActive instead of parsing cooldownUntil locally', () => {
    renderList({
      rules: [
        {
          ...rules[0],
          cooldownUntil: '2099-05-18T10:30:00',
          cooldownActive: false,
        },
      ],
    });

    expect(screen.getByText('未冷却')).toBeInTheDocument();
  });

  it('renders portfolio scope labels and child-target cooldown hint', () => {
    renderList({
      rules: [
        {
          id: 4,
          name: '持仓 RSI',
          targetScope: 'portfolio_holdings',
          target: 'all',
          alertType: 'rsi_threshold',
          parameters: { direction: 'below', period: 12, threshold: 30 },
          severity: 'warning',
          enabled: true,
          source: 'api',
          cooldownActive: false,
        },
        {
          id: 5,
          name: '组合止损',
          targetScope: 'portfolio_account',
          target: '9',
          alertType: 'portfolio_stop_loss',
          parameters: { mode: 'breach' },
          severity: 'critical',
          enabled: true,
          source: 'api',
          cooldownActive: false,
        },
      ],
    });

    expect(screen.getByText('持仓标的')).toBeInTheDocument();
    expect(screen.getByText('子目标见触发历史')).toBeInTheDocument();
    expect(screen.getByText('账户 9')).toBeInTheDocument();
    expect(screen.getAllByText('组合止损').length).toBeGreaterThan(0);
    expect(screen.getByText('已触发止损')).toBeInTheDocument();
  });

  it('renders portfolio drawdown alert labels in English UI mode', () => {
    renderEnglishList({
      rules: [
        {
          id: 8,
          name: 'Drawdown rule',
          targetScope: 'portfolio_account',
          target: 'all',
          alertType: 'portfolio_drawdown',
          parameters: {},
          severity: 'warning',
          enabled: true,
          source: 'api',
          cooldownActive: false,
        },
      ],
    });

    expect(screen.getByRole('heading', { name: 'Alert rules' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Filters' }));
    const dialog = screen.getByRole('dialog', { name: 'Filters' });
    const statusSelect = within(dialog).getByLabelText('Status');
    const statusListbox = openListbox(statusSelect);
    expect(within(statusListbox).getByRole('option', { name: 'All statuses' })).toBeInTheDocument();
    fireEvent.click(statusSelect);
    expect(screen.getAllByText('Portfolio drawdown').length).toBeGreaterThan(0);
    expect(screen.getByText('Portfolio account')).toBeInTheDocument();
    expect(screen.getAllByText('Enabled').length).toBeGreaterThan(0);
    expect(screen.getByText('Warning')).toBeInTheDocument();
    expect(screen.queryByText('组合回撤')).not.toBeInTheDocument();
  });

  it('renders market scope labels, filters, and parameters', () => {
    renderList({
      rules: [
        {
          id: 6,
          name: 'A 股红黄灯',
          targetScope: 'market',
          target: 'cn',
          alertType: 'market_light_status',
          parameters: { statuses: ['red', 'yellow'] },
          severity: 'critical',
          enabled: true,
          source: 'api',
          cooldownActive: false,
        },
        {
          id: 7,
          name: '美股分数下降',
          targetScope: 'market',
          target: 'us',
          alertType: 'market_light_score_drop',
          parameters: { minDrop: 15 },
          severity: 'warning',
          enabled: true,
          source: 'api',
          cooldownActive: false,
        },
      ],
    });

    expect(screen.getByText('A 股')).toBeInTheDocument();
    expect(screen.getByText('美股')).toBeInTheDocument();
    expect(screen.getAllByText('大盘市场').length).toBeGreaterThan(0);
    expect(screen.getAllByText('大盘红绿灯状态').length).toBeGreaterThan(0);
    expect(screen.getByText('红灯 / 黄灯')).toBeInTheDocument();
    expect(screen.getByText('Score 下降 >= 15')).toBeInTheDocument();

    const dialog = openFilters();
    chooseOption(within(dialog).getByLabelText('规则类型'), 'market_light_score_drop');
    applyFilters(dialog);

    expect(onAlertTypeFilterChange).toHaveBeenCalledWith('market_light_score_drop');
  });

  it('runs test and toggles enabled state', () => {
    renderList();

    fireEvent.click(screen.getAllByRole('button', { name: '测试' })[0]);
    fireEvent.click(screen.getAllByRole('button', { name: '停用' })[0]);

    expect(onTest).toHaveBeenCalledWith(rules[0]);
    expect(onToggleEnabled).toHaveBeenCalledWith(rules[0]);
  });

  it('keeps the action name stable and shows loading text only for the active rule operation', () => {
    renderList({ busyRules: { 1: 'toggle' } });

    expect(screen.getAllByRole('button', { name: '测试' })[0]).toBeDisabled();
    const busyToggle = screen.getAllByRole('button', { name: '停用' })[0];
    expect(busyToggle).toHaveAttribute('aria-busy', 'true');
    expect(busyToggle).toHaveTextContent('停用中');
    expect(screen.queryByText('测试中')).not.toBeInTheDocument();
  });

  it('confirms deletion before calling onDelete', async () => {
    renderList();

    fireEvent.click(screen.getByLabelText('删除 茅台价格突破'));
    expect(await screen.findByRole('heading', { name: '删除告警规则' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '删除' }));

    expect(onDelete).toHaveBeenCalledWith(rules[0]);
  });

  it('shows an empty state for no rules with create CTA', () => {
    renderList({ rules: [], total: 0 });

    expect(screen.getByText('暂无告警规则')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '创建告警规则' }));
    expect(onCreateRule).toHaveBeenCalledTimes(1);
  });

  it('shows a distinct filtered empty state with clear-filters action', () => {
    renderList({
      rules: [],
      total: 0,
      enabledFilter: 'enabled',
      alertTypeFilter: 'all',
    });

    expect(screen.getByText('无匹配的告警规则')).toBeInTheDocument();
    expect(screen.queryByText('暂无告警规则')).not.toBeInTheDocument();
    const emptyPanel = screen.getByText('无匹配的告警规则').closest('[data-state-panel="empty"]');
    expect(emptyPanel).not.toBeNull();
    fireEvent.click(within(emptyPanel as HTMLElement).getByRole('button', { name: '清除筛选' }));
    expect(onEnabledFilterChange).toHaveBeenCalledWith('all');
    expect(onAlertTypeFilterChange).toHaveBeenCalledWith('all');
  });

  it('keeps primary filters behind the Filters dialog on mobile viewports', () => {
    setDesktopViewport(false);
    renderList();

    expect(screen.getByRole('button', { name: /筛选/ })).toBeInTheDocument();
    expect(screen.queryByLabelText('启停状态')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('规则类型')).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '筛选' })).toBeNull();

    const dialog = openFilters();
    expect(within(dialog).getByLabelText('启停状态')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('规则类型')).toBeInTheDocument();
  });

  it('exposes primary filters inline above the 48rem breakpoint without a Filters dialog', () => {
    setDesktopViewport(true);
    renderList();

    expect(screen.getByLabelText('启停状态')).toBeInTheDocument();
    expect(screen.getByLabelText('规则类型')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /筛选/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '筛选' })).toBeNull();

    chooseOption(screen.getByLabelText('启停状态'), 'enabled');
    chooseOption(screen.getByLabelText('规则类型'), 'price_cross');

    expect(onEnabledFilterChange).toHaveBeenCalledWith('enabled');
    expect(onAlertTypeFilterChange).toHaveBeenCalledWith('price_cross');
  });
});
