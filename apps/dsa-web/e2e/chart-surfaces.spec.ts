// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Product-surface smoke for the financial chart mounts from Issue #142 / PR #1015:
 * - Stock Details: shared KlineChart on real history quote wiring
 * - Portfolio: RiskHeatmap on real risk API projection
 *
 * Coverage: render / empty / loading / error / non-finite-or-out-of-range rejection.
 * Selectors prefer roles, accessible names, and stable data-testid chrome —
 * not brittle CSS class or layout-position chains.
 */
import { expect, test, type Page, type Route } from './playwright-test';
import { loginAsE2eAdmin } from './auth-fixture';

test.use({ locale: 'zh-CN' });

const STOCK_CODE = '600519';
const STOCK_NAME = '贵州茅台';

type HistoryMode =
  | 'render'
  | 'empty'
  | 'loading'
  | 'error'
  | 'dirty';

type RiskMode =
  | 'render'
  | 'empty'
  | 'invalid';

function fulfillJson(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

function makeCandles(count: number) {
  return Array.from({ length: count }, (_, index) => {
    const day = index + 1;
    const open = 100 + index;
    const close = open + (index % 2 === 0 ? 1.5 : -0.8);
    return {
      date: `2026-06-${String(day).padStart(2, '0')}`,
      open,
      high: Math.max(open, close) + 1.2,
      low: Math.min(open, close) - 1.1,
      close,
      volume: 10_000 + index * 100,
      change_percent: close - open,
    };
  });
}

function quotePayload() {
  return {
    stock_code: STOCK_CODE,
    stock_name: STOCK_NAME,
    current_price: 1700,
    change: 12.5,
    change_percent: 0.74,
    open: 1690,
    high: 1710,
    low: 1685,
    prev_close: 1687.5,
    volume: 123456,
    amount: 2_100_000_000,
    update_time: '2026-06-10T09:30:00Z',
  };
}

function historyPayload(mode: Exclude<HistoryMode, 'loading' | 'error'>) {
  if (mode === 'empty') {
    return {
      stock_code: STOCK_CODE,
      stock_name: STOCK_NAME,
      period: 'daily',
      data: [],
    };
  }
  if (mode === 'dirty') {
    // Wire-format can carry finite numbers with invalid calendar dates; KlineChart
    // must reject those rows instead of inventing axis geometry from them.
    return {
      stock_code: STOCK_CODE,
      stock_name: STOCK_NAME,
      period: 'daily',
      data: [
        {
          date: 'not-a-date',
          open: 10,
          high: 12,
          low: 9,
          close: 11,
          volume: 100,
          change_percent: 1,
        },
        {
          date: '2026-06-02',
          open: 11,
          high: 13,
          low: 10.5,
          close: 12.5,
          volume: 200,
          change_percent: 2,
        },
        {
          date: '2026-13-40',
          open: 12,
          high: 14,
          low: 11,
          close: 13,
          volume: 300,
          change_percent: 3,
        },
      ],
    };
  }
  return {
    stock_code: STOCK_CODE,
    stock_name: STOCK_NAME,
    period: 'daily',
    data: makeCandles(8),
  };
}

async function installStockChartRoutes(
  page: Page,
  options: {
    historyMode: HistoryMode;
    releaseHistory?: Promise<void>;
  },
): Promise<void> {
  await page.route(`**/api/v1/stocks/${STOCK_CODE}/quote**`, async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, quotePayload());
  });

  await page.route(`**/api/v1/stocks/${STOCK_CODE}/history**`, async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    if (options.historyMode === 'loading') {
      await options.releaseHistory;
      await fulfillJson(route, historyPayload('render'));
      return;
    }
    if (options.historyMode === 'error') {
      await fulfillJson(route, {
        error: 'history_unavailable',
        message: 'simulated history failure',
        params: {},
        details: null,
        trace_id: 'chart-e2e-history-error',
      }, 503);
      return;
    }
    await fulfillJson(route, historyPayload(options.historyMode));
  });

  // Stock Details also mounts DCF; keep it out of the chart contract path.
  await page.route('**/api/v1/valuation/estimate**', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, {
      stock_code: STOCK_CODE,
      fair_value: 1800,
      upside_pct: 5.8,
      assumptions: {},
      sensitivity: { rows: [], columns: [], matrix: [] },
    });
  });
}

function accountPayload() {
  return {
    accounts: [
      {
        id: 1,
        name: 'Chart E2E',
        owner_id: null,
        broker: 'E2E',
        market: 'cn',
        base_currency: 'CNY',
        account_type: 'live',
        is_active: true,
        created_at: '2026-06-01T00:00:00Z',
        updated_at: '2026-06-01T00:00:00Z',
      },
    ],
  };
}

function snapshotPayload() {
  return {
    as_of: '2026-06-10',
    cost_method: 'fifo',
    currency: 'CNY',
    account_count: 1,
    total_cash: 1000,
    total_market_value: 5000,
    total_equity: 6000,
    realized_pnl: 0,
    unrealized_pnl: 200,
    fee_total: 0,
    tax_total: 0,
    fx_stale: false,
    data_quality: 'ok',
    limitations: [],
    accounts: [
      {
        account_id: 1,
        account_name: 'Chart E2E',
        owner_id: null,
        broker: 'E2E',
        market: 'cn',
        base_currency: 'CNY',
        as_of: '2026-06-10',
        cost_method: 'fifo',
        total_cash: 1000,
        total_market_value: 5000,
        total_equity: 6000,
        realized_pnl: 0,
        unrealized_pnl: 200,
        fee_total: 0,
        tax_total: 0,
        fx_stale: false,
        positions: [
          {
            symbol: '600519',
            market: 'cn',
            currency: 'CNY',
            quantity: 2,
            avg_cost: 1500,
            total_cost: 3000,
            last_price: 1600,
            market_value_base: 3200,
            unrealized_pnl_base: 200,
            unrealized_pnl_pct: 6.67,
            valuation_currency: 'CNY',
            price_source: 'history_close',
            price_date: '2026-06-10',
            price_stale: false,
            price_available: true,
          },
        ],
      },
    ],
  };
}

function riskPayload(mode: RiskMode) {
  if (mode === 'empty') {
    return {
      as_of: '2026-06-10',
      account_id: null,
      cost_method: 'fifo',
      currency: 'CNY',
      thresholds: {},
      concentration: {
        total_market_value: 0,
        top_weight_pct: null,
        alert: false,
        top_positions: [],
      },
      sector_concentration: {
        total_market_value: 0,
        top_weight_pct: 0,
        alert: false,
        top_sectors: [],
        coverage: {},
        errors: [],
      },
      drawdown: {
        series_points: 0,
        max_drawdown_pct: null,
        current_drawdown_pct: null,
        alert: false,
        fx_stale: false,
      },
      stop_loss: {
        near_alert: false,
        triggered_count: 0,
        near_count: 0,
        items: [],
      },
      decision_signal_risk: {
        available: true,
        total: 0,
        actions: { sell: 0, reduce: 0, alert: 0 },
        items: [],
      },
    };
  }

  if (mode === 'invalid') {
    // Out-of-range / null risk units must surface as Missing, not invented paint.
    return {
      as_of: '2026-06-10',
      account_id: null,
      cost_method: 'fifo',
      currency: 'CNY',
      thresholds: {},
      concentration: {
        total_market_value: 5000,
        top_weight_pct: 150,
        alert: true,
        top_positions: [
          {
            symbol: '600519',
            market_value_base: 3200,
            weight_pct: null,
            is_alert: true,
          },
          {
            symbol: 'AAPL',
            market_value_base: 1800,
            weight_pct: 12,
            is_alert: false,
          },
        ],
      },
      sector_concentration: {
        total_market_value: 5000,
        top_weight_pct: 50,
        alert: false,
        top_sectors: [],
        coverage: {},
        errors: [],
      },
      drawdown: {
        series_points: 2,
        max_drawdown_pct: 200,
        current_drawdown_pct: -5,
        alert: false,
        fx_stale: false,
      },
      stop_loss: {
        near_alert: true,
        triggered_count: 1,
        near_count: 1,
        items: [
          {
            account_id: 1,
            symbol: '600519',
            avg_cost: 1500,
            last_price: 1400,
            loss_pct: 101,
            near_threshold_pct: 10,
            is_triggered: true,
          },
          {
            account_id: 1,
            symbol: 'AAPL',
            avg_cost: 180,
            last_price: 190,
            loss_pct: 8,
            near_threshold_pct: 10,
            is_triggered: false,
          },
        ],
      },
      decision_signal_risk: {
        available: true,
        total: 0,
        actions: { sell: 0, reduce: 0, alert: 0 },
        items: [],
      },
    };
  }

  return {
    as_of: '2026-06-10',
    account_id: null,
    cost_method: 'fifo',
    currency: 'CNY',
    thresholds: {},
    concentration: {
      total_market_value: 5000,
      top_weight_pct: 40,
      alert: true,
      top_positions: [
        {
          symbol: '600519',
          market_value_base: 3200,
          weight_pct: 40,
          is_alert: true,
        },
        {
          symbol: 'AAPL',
          market_value_base: 1800,
          weight_pct: 22,
          is_alert: false,
        },
      ],
    },
    sector_concentration: {
      total_market_value: 5000,
      top_weight_pct: 40,
      alert: false,
      top_sectors: [],
      coverage: {},
      errors: [],
    },
    drawdown: {
      series_points: 20,
      max_drawdown_pct: 18,
      current_drawdown_pct: 12,
      alert: false,
      fx_stale: false,
    },
    stop_loss: {
      near_alert: true,
      triggered_count: 1,
      near_count: 1,
      items: [
        {
          account_id: 1,
          symbol: '600519',
          avg_cost: 1500,
          last_price: 1400,
          loss_pct: 15,
          near_threshold_pct: 10,
          is_triggered: true,
        },
      ],
    },
    decision_signal_risk: {
      available: true,
      total: 0,
      actions: { sell: 0, reduce: 0, alert: 0 },
      items: [],
    },
  };
}

function riskMetricsEmptyPayload() {
  return {
    as_of: '2026-06-10',
    account_id: null,
    cost_method: 'fifo',
    currency: 'CNY',
    status: 'empty_portfolio',
    status_message: 'No positions for metrics.',
    portfolio_value: 0,
    positions_used: 0,
    assumptions: {
      var_method: 'historical',
      confidence: 0.95,
      horizon_days: 1,
      lookback_trading_days: 252,
      min_return_observations: 60,
      min_correlation_observations: 30,
      return_definition: 'simple_close_to_close',
      portfolio_aggregation: 'static_current_market_value_weights',
      cash_excluded: true,
      weight_basis: 'market_value_base',
      horizon_scaling: 'none',
      distribution_assumption: 'empirical',
      correlation_method: 'pearson',
      concentration_metrics: 'hhi_effective_n_normalized_diversification_score',
      data_source: 'stored_stock_daily_closes_and_portfolio_holdings',
      provider_calls_on_hot_path: false,
    },
    var: {
      status: 'unavailable',
      status_message: 'empty',
      observation_count: 0,
    },
    correlation: {
      status: 'unavailable',
      status_message: 'empty',
      symbols: [],
      matrix: [],
      observation_count: 0,
    },
    concentration: {
      status: 'empty_portfolio',
      hhi: null,
      effective_n: null,
      diversification_score: null,
      top_weight_pct: null,
      position_count: 0,
      weights: [],
    },
    history: {
      aligned_trading_days: 0,
      lookback_trading_days_requested: 252,
      price_series_symbols: [],
      aligned_start: null,
      aligned_end: null,
    },
  };
}

async function installPortfolioChartRoutes(
  page: Page,
  options: { riskMode: RiskMode },
): Promise<void> {
  await page.route('**/api/v1/portfolio/accounts**', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, accountPayload());
  });

  await page.route('**/api/v1/portfolio/snapshot**', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, snapshotPayload());
  });

  await page.route('**/api/v1/portfolio/risk-metrics**', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, riskMetricsEmptyPayload());
  });

  await page.route('**/api/v1/portfolio/risk**', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, riskPayload(options.riskMode));
  });

  await page.route('**/api/v1/portfolio/trades**', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, { total: 0, page: 1, page_size: 20, items: [] });
  });

  await page.route('**/api/v1/portfolio/cash-ledger**', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, { total: 0, page: 1, page_size: 20, items: [] });
  });

  await page.route('**/api/v1/portfolio/corporate-actions**', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, { total: 0, page: 1, page_size: 20, items: [] });
  });

  await page.route('**/api/v1/portfolio/import/brokers**', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, { brokers: [] });
  });
}

test.describe('financial chart product surfaces', () => {
  test('Stock Details renders K-line canvas from history candles', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await installStockChartRoutes(page, { historyMode: 'render' });

    await page.goto(`/stocks/${STOCK_CODE}`);
    await expect(page.getByRole('heading', { name: STOCK_NAME })).toBeVisible();
    await expect(page.getByRole('heading', { name: '历史 K 线' })).toBeVisible();

    const chart = page.getByTestId('stock-details-kline-chart');
    await expect(chart).toBeVisible();
    const canvas = page.getByTestId('stock-details-kline-chart-canvas');
    await expect(canvas).toBeVisible();
    await expect(canvas).toHaveAttribute('role', 'img');
    await expect(canvas).toHaveAttribute('aria-label', /K 线图，共 8 根 K 线/);
    await expect(page.getByTestId('stock-details-kline-chart-candle-0')).toBeVisible();
    await expect(page.getByTestId('stock-details-kline-chart-candle-7')).toBeVisible();
    await expect(page.getByTestId('stock-details-kline-chart-empty')).toHaveCount(0);
  });

  test('Stock Details history empty state does not paint a false chart', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await installStockChartRoutes(page, { historyMode: 'empty' });

    await page.goto(`/stocks/${STOCK_CODE}`);
    await expect(page.getByRole('heading', { name: STOCK_NAME })).toBeVisible();
    await expect(page.getByRole('heading', { name: '暂无历史数据' })).toBeVisible();
    await expect(page.getByText('未获取到该股票的历史 K 线数据。')).toBeVisible();
    await expect(page.getByTestId('stock-details-kline-chart')).toHaveCount(0);
    await expect(page.getByTestId('stock-details-kline-chart-canvas')).toHaveCount(0);
  });

  test('Stock Details history loading state stays busy without a chart', async ({ page }) => {
    let releaseHistory!: () => void;
    const historyGate = new Promise<void>((resolve) => {
      releaseHistory = resolve;
    });
    await loginAsE2eAdmin(page);
    await installStockChartRoutes(page, {
      historyMode: 'loading',
      releaseHistory: historyGate,
    });

    await page.goto(`/stocks/${STOCK_CODE}`);
    await expect(page.getByRole('heading', { name: STOCK_NAME })).toBeVisible();

    const loading = page.locator('[data-state-panel="loading"]').filter({ hasText: '正在加载' });
    await expect(loading.first()).toBeVisible();
    await expect(loading.first()).toHaveAttribute('aria-busy', 'true');
    await expect(page.getByTestId('stock-details-kline-chart')).toHaveCount(0);

    releaseHistory();
    await expect(page.getByTestId('stock-details-kline-chart-canvas')).toBeVisible();
  });

  test('Stock Details history error shows toast retry and never paints a chart', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await installStockChartRoutes(page, { historyMode: 'error' });

    await page.goto(`/stocks/${STOCK_CODE}`);
    await expect(page.getByRole('heading', { name: STOCK_NAME })).toBeVisible();

    const dangerToast = page.locator('[data-toast-tone="danger"]');
    await expect(dangerToast.first()).toBeVisible();
    await expect(dangerToast.getByRole('button', { name: '重试' }).first()).toBeVisible();
    await expect(page.getByTestId('stock-details-kline-chart')).toHaveCount(0);
    await expect(page.getByTestId('stock-details-kline-chart-empty')).toHaveCount(0);
  });

  test('Stock Details rejects invalid calendar candles instead of inventing bars', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await installStockChartRoutes(page, { historyMode: 'dirty' });

    await page.goto(`/stocks/${STOCK_CODE}`);
    await expect(page.getByRole('heading', { name: STOCK_NAME })).toBeVisible();

    const canvas = page.getByTestId('stock-details-kline-chart-canvas');
    await expect(canvas).toBeVisible();
    await expect(canvas).toHaveAttribute('aria-label', /K 线图，共 1 根 K 线/);
    await expect(page.getByTestId('stock-details-kline-chart-candle-0')).toBeVisible();
    await expect(page.getByTestId('stock-details-kline-chart-candle-1')).toHaveCount(0);
    await expect(page.getByTestId('stock-details-kline-chart-readout')).toContainText('2026-06-02');
  });

  test('Portfolio risk heatmap renders mapped weight / stop-loss / drawdown cells', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await installPortfolioChartRoutes(page, { riskMode: 'render' });

    await page.goto('/portfolio');
    await expect(page.getByRole('heading', { name: '持仓管理' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '持仓风险热力图' })).toBeVisible();

    const heatmap = page.getByTestId('portfolio-risk-heatmap');
    await expect(heatmap).toBeVisible();
    await expect(page.getByRole('table', { name: /风险热力图/ })).toBeVisible();
    await expect(page.getByTestId('portfolio-risk-heatmap-cell-portfolio-drawdown')).toHaveAttribute(
      'data-risk-level',
      'low',
    );
    await expect(page.getByTestId('portfolio-risk-heatmap-cell-portfolio-weight')).toHaveAttribute(
      'data-risk-level',
      'medium',
    );
    await expect(page.getByTestId('portfolio-risk-heatmap-cell-pos:600519-weight')).toContainText('40');
    await expect(page.getByTestId('portfolio-risk-heatmap-cell-pos:600519-stopLoss')).toContainText('15');
    await expect(page.getByTestId('portfolio-risk-heatmap-empty')).toHaveCount(0);
  });

  test('Portfolio risk heatmap empty state when risk projection yields no cells', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await installPortfolioChartRoutes(page, { riskMode: 'empty' });

    await page.goto('/portfolio');
    await expect(page.getByRole('heading', { name: '持仓风险热力图' })).toBeVisible();
    await expect(page.getByTestId('portfolio-risk-heatmap-empty')).toBeVisible();
    await expect(page.getByText('暂无风险热力数据', { exact: true })).toBeVisible();
    await expect(page.getByRole('table', { name: /风险热力图/ })).toHaveCount(0);
  });

  test('Portfolio risk heatmap marks out-of-range scores Missing instead of inventing levels', async ({ page }) => {
    await loginAsE2eAdmin(page);
    await installPortfolioChartRoutes(page, { riskMode: 'invalid' });

    await page.goto('/portfolio');
    await expect(page.getByRole('heading', { name: '持仓风险热力图' })).toBeVisible();

    // Invalid portfolio-level drawdown/weight never become painted cells.
    await expect(page.getByTestId('portfolio-risk-heatmap-cell-portfolio-drawdown')).toHaveCount(0);
    await expect(page.getByTestId('portfolio-risk-heatmap-cell-portfolio-weight')).toHaveCount(0);

    // Position rows still exist for declared instruments, but invalid scores stay Missing.
    await expect(page.getByTestId('portfolio-risk-heatmap-cell-pos:600519-weight')).toHaveAttribute(
      'data-risk-level',
      'missing',
    );
    await expect(page.getByTestId('portfolio-risk-heatmap-cell-pos:600519-stopLoss')).toHaveAttribute(
      'data-risk-level',
      'missing',
    );
    await expect(page.getByTestId('portfolio-risk-heatmap-cell-pos:AAPL-weight')).toHaveAttribute(
      'data-risk-level',
      'low',
    );
    await expect(page.getByTestId('portfolio-risk-heatmap-cell-pos:AAPL-stopLoss')).toHaveAttribute(
      'data-risk-level',
      'low',
    );
    await expect(page.getByTestId('portfolio-risk-heatmap-cell-pos:AAPL-weight')).toContainText('12');
    await expect(page.getByTestId('portfolio-risk-heatmap-cell-pos:AAPL-stopLoss')).toContainText('8');
  });
});
