// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getParsedApiError } from '../error';
import { portfolioInsightsApi } from '../portfolioInsights';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('../index', () => ({
  default: { get, post },
  locallyRecoverableResourceConfig: () => ({ handleUnauthorizedLocally: true }),
}));

const scenario = {
  id: 'market_down_10', name: 'Market down 10%', description: 'Broad market shock',
  category: 'market', shocks: [{ factor: 'market', value_pct: -10 }],
  requires_target_sector: false, availability: 'ready', source: 'built_in', version: 1,
  scenario_hash: 'a'.repeat(64),
};

function basketPayload() {
  return {
    formula_version: 'portfolio_level_analysis_v1', analysis_mode: 'portfolio_level_basket',
    snapshot_kind: 'synthetic_basket_v1', as_of: '2026-08-13', currency: 'CNY', status: 'partial',
    status_message: 'One symbol was excluded.', disclaimer: 'Research aid only.',
    requested_symbols: ['AAPL', 'MISSING'], symbols_used: ['AAPL'], symbols_requested_count: 2,
    symbols_used_count: 1, max_symbols: 20, weighting_mode: 'equal',
    weights: [{ symbol: 'AAPL', weight_pct: 100 }],
    degraded_symbols: [{ stock_code: 'MISSING', reason: 'price_unavailable' }],
    stance_distribution: { status: 'partial', scored_count: 1, unanalyzed_count: 1 },
    health: { status: 'partial', partial_score: 55, coverage_ratio: 0.6 },
    calculated_at: '2026-08-13T12:00:00Z',
  };
}

function stressPayload(overrides: Record<string, unknown> = {}) {
  return {
    as_of: '2026-08-13', calculated_at: '2026-08-13T12:00:00Z', account_id: 7,
    cost_method: 'fifo', currency: 'CNY', status: 'partial', status_message: 'Unit beta used.',
    portfolio_value: 1000, positions_used: 1, excluded_position_count: 0,
    portfolio_pnl: -100, portfolio_pnl_pct: -10, stressed_portfolio_value: 900,
    scenario, position_impacts: [{
      position_key: '7-AAPL', account_id: 7, symbol: 'AAPL', market_value: 1000,
      weight_pct: 100, shock_pct: -10, pnl: -100, stressed_market_value: 900,
      data_quality: 'partial', limitations: ['unit_beta'],
    }],
    top_losers: [], top_winners: [], snapshot_limitations: [], missing_data: [],
    ...overrides,
  };
}

function rebalancePayload(overrides: Record<string, unknown> = {}) {
  return {
    as_of: '2026-08-13', account_id: 7, cost_method: 'fifo', currency: 'CNY',
    status: 'insufficient_data', status_message: 'Need more history.', disclaimer: 'Research aid only.',
    risk_tolerance: 'moderate', is_suggestion_only: true, auto_execute: false,
    target_model: { name: 'risk_band_v1', description: 'Moderate', max_single_weight_pct: 15, min_effective_n: 4, max_hhi: 0.35, target_var_pct_ceiling: 3.5 },
    current: { portfolio_value: 1000, var_pct: null, hhi: 1, effective_n: 1 },
    drift: { max_abs_weight_drift_pct: 0 }, suggestions: [], position_bands: [],
    ...overrides,
  };
}

describe('portfolioInsightsApi', () => {
  beforeEach(() => { get.mockReset(); post.mockReset(); });

  it('normalizes and validates a partial basket response', async () => {
    post.mockResolvedValue({ data: basketPayload() });
    const result = await portfolioInsightsApi.analyzeBasket({ stockCodes: ['aapl', 'missing'], includeStress: false });
    expect(post).toHaveBeenCalledWith('/api/v1/analysis/portfolio', expect.objectContaining({
      stock_codes: ['AAPL', 'MISSING'], include_stress: false, lookback_trading_days: 252,
    }));
    expect(result.degradedSymbols[0].stockCode).toBe('MISSING');
    expect(result.correlationHighlights).toEqual([]);
  });

  it('uses the catalog and GET preset contracts', async () => {
    get.mockResolvedValueOnce({ data: { scenarios: [scenario], simulation_method: 'deterministic_factor_shock', historical_replay_available: false } });
    get.mockResolvedValueOnce({ data: stressPayload() });
    const catalog = await portfolioInsightsApi.listStressScenarios();
    const result = await portfolioInsightsApi.runStressPreset({ scenarioId: catalog.scenarios[0].id, accountId: 7 });
    expect(get).toHaveBeenNthCalledWith(1, '/api/v1/portfolio/stress-test/scenarios', { handleUnauthorizedLocally: true });
    expect(get).toHaveBeenNthCalledWith(2, '/api/v1/portfolio/stress-test', { params: expect.objectContaining({ scenario_id: 'market_down_10', account_id: 7, cost_method: 'fifo' }) });
    expect(result.portfolioPnl).toBe(-100);
  });

  it('converts custom rate shocks to the POST wire contract', async () => {
    post.mockResolvedValue({ data: stressPayload() });
    await portfolioInsightsApi.runStressCustom({ accountId: 7, customShocks: [{ factor: 'rate', valueBp: 100 }] });
    expect(post).toHaveBeenCalledWith('/api/v1/portfolio/stress-test', expect.objectContaining({
      account_id: 7,
      custom_shocks: [{ factor: 'rate', value_bp: 100 }],
    }));
  });

  it('preserves an explicit rebalancing refusal as a successful response', async () => {
    get.mockResolvedValue({ data: rebalancePayload() });
    const result = await portfolioInsightsApi.getRebalancing({ accountId: 7, riskTolerance: 'conservative' });
    expect(result.status).toBe('insufficient_data');
    expect(result.suggestions).toEqual([]);
    expect(get).toHaveBeenCalledWith('/api/v1/portfolio/rebalancing-recommendations', { params: expect.objectContaining({ account_id: 7, risk_tolerance: 'conservative' }) });
  });

  it('rejects schema drift and invalid requests before consumers see them', async () => {
    get.mockResolvedValue({ data: rebalancePayload({ current: { portfolio_value: Number.NaN } }) });
    await expect(portfolioInsightsApi.getRebalancing()).rejects.toSatisfy((error: unknown) => {
      expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
      return true;
    });
    await expect(portfolioInsightsApi.analyzeBasket({ stockCodes: [] })).rejects.toSatisfy((error: unknown) => {
      expect(getParsedApiError(error).code).toBe('invalid_params');
      return true;
    });
  });
});
