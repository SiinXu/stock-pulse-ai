// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getPortfolioRiskMetrics } from '../portfolioRiskMetrics';
import { getParsedApiError, isApiRequestError } from '../error';

const { get } = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock('../index', () => ({
  default: { get },
}));

const baseAssumptions = {
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
};

describe('getPortfolioRiskMetrics', () => {
  beforeEach(() => {
    get.mockReset();
  });

  it('maps a successful risk-metrics payload and preserves null VaR honesty', async () => {
    get.mockResolvedValue({
      data: {
        as_of: '2026-06-01',
        account_id: 1,
        cost_method: 'fifo',
        currency: 'CNY',
        status: 'insufficient_history',
        status_message: 'Insufficient aligned trading-day history (10 < 60 required).',
        portfolio_value: 10000.0,
        positions_used: 2,
        assumptions: baseAssumptions,
        var: {
          status: 'insufficient_history',
          status_message: 'Need at least 60 observations',
          confidence: 0.95,
          horizon_days: 1,
          var_pct: null,
          var_value: null,
          observation_count: 10,
          percentile_used: 0.05,
        },
        correlation: {
          status: 'insufficient_history',
          symbols: ['AAA', 'BBB'],
          matrix: [],
          observation_count: 10,
        },
        concentration: {
          status: 'ok',
          hhi: 0.5,
          effective_n: 2.0,
          diversification_score: 1.0,
          top_weight_pct: 50.0,
          position_count: 2,
          weights: [
            { symbol: 'AAA', weight_pct: 50.0 },
            { symbol: 'BBB', weight_pct: 50.0 },
          ],
        },
      },
    });

    const result = await getPortfolioRiskMetrics({
      accountId: 1,
      asOf: '2026-06-01',
      costMethod: 'fifo',
    });

    expect(get).toHaveBeenCalledWith('/api/v1/portfolio/risk-metrics', {
      params: {
        account_id: 1,
        as_of: '2026-06-01',
        cost_method: 'fifo',
      },
    });
    expect(result.status).toBe('insufficient_history');
    expect(result.var.varPct).toBeNull();
    expect(result.var.varValue).toBeNull();
    expect(result.concentration.diversificationScore).toBe(1.0);
    expect(result.assumptions.providerCallsOnHotPath).toBe(false);
    expect(result.concentration.weights).toEqual([
      { symbol: 'AAA', weightPct: 50.0 },
      { symbol: 'BBB', weightPct: 50.0 },
    ]);
  });

  it('rejects non-finite VaR percentages instead of accepting silent zeros', async () => {
    get.mockResolvedValue({
      data: {
        as_of: '2026-06-01',
        cost_method: 'fifo',
        currency: 'CNY',
        status: 'ok',
        portfolio_value: 10000.0,
        positions_used: 1,
        assumptions: baseAssumptions,
        var: {
          status: 'ok',
          var_pct: Number.NaN,
          var_value: 0,
          observation_count: 100,
        },
        correlation: {
          status: 'unavailable',
          symbols: [],
          matrix: [],
          observation_count: 0,
        },
        concentration: {
          status: 'ok',
          hhi: 1,
          effective_n: 1,
          diversification_score: 0,
          top_weight_pct: 100,
          position_count: 1,
          weights: [{ symbol: 'AAA', weight_pct: 100 }],
        },
      },
    });

    await expect(getPortfolioRiskMetrics()).rejects.toSatisfy((error: unknown) => {
      expect(isApiRequestError(error)).toBe(true);
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      return true;
    });
  });

  it('rejects ±Infinity correlation cells', async () => {
    get.mockResolvedValue({
      data: {
        as_of: '2026-06-01',
        cost_method: 'fifo',
        currency: 'CNY',
        status: 'ok',
        portfolio_value: 10000.0,
        positions_used: 2,
        assumptions: baseAssumptions,
        var: {
          status: 'ok',
          var_pct: 2.5,
          var_value: 250,
          observation_count: 100,
        },
        correlation: {
          status: 'ok',
          symbols: ['AAA', 'BBB'],
          matrix: [
            [1.0, Number.POSITIVE_INFINITY],
            [Number.NEGATIVE_INFINITY, 1.0],
          ],
          observation_count: 100,
        },
        concentration: {
          status: 'ok',
          hhi: 0.5,
          effective_n: 2,
          diversification_score: 1,
          top_weight_pct: 50,
          position_count: 2,
          weights: [
            { symbol: 'AAA', weight_pct: 50 },
            { symbol: 'BBB', weight_pct: 50 },
          ],
        },
      },
    });

    await expect(getPortfolioRiskMetrics()).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      return true;
    });
  });
});
