// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getParsedApiError } from '../error';
import { portfolioInsightsApi } from '../portfolioInsights';

const { get, post, locallyRecoverableResourceConfig } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  locallyRecoverableResourceConfig: vi.fn(() => ({ localRecovery: true })),
}));

vi.mock('../index', () => ({
  default: { get, post },
  locallyRecoverableResourceConfig,
}));

const scenario = {
  id: 'market_down_10',
  name: 'Market down 10%',
  description: 'Deterministic market shock',
  category: 'market',
  shocks: [{ factor: 'market', value_pct: -10 }],
  requires_target_sector: false,
  availability: 'ready',
  source: 'built_in',
  version: 1,
  scenario_hash: 'a'.repeat(64),
};

const basketPayload = {
  formula_version: 'portfolio_level_analysis_v1',
  analysis_mode: 'portfolio_level_basket',
  snapshot_kind: 'synthetic_basket_v1',
  as_of: '2026-08-15',
  currency: 'USD',
  status: 'partial',
  status_message: 'One symbol was excluded.',
  disclaimer: 'Research aid only.',
  requested_symbols: ['AAPL', 'MSFT'],
  symbols_used: ['AAPL'],
  symbols_requested_count: 2,
  symbols_used_count: 1,
  max_symbols: 20,
  weighting_mode: 'equal_weight',
  weights: [{ symbol: 'AAPL', weight_pct: 100 }],
  degraded_symbols: [{ stock_code: 'MSFT', reason: 'missing_history', detail: 'No history' }],
  annotations: ['Weights were rebased.'],
  correlation: { status: 'ok', symbols: ['AAPL'], matrix: [[1]], observation_count: 80 },
  correlation_highlights: [],
  concentration: {
    status: 'ok', hhi: 1, effective_n: 1, diversification_score: 0,
    top_weight_pct: 100, position_count: 1,
  },
  var: { status: 'ok', confidence: 0.95, horizon_days: 1, var_pct: 2, var_value: 200, observation_count: 80 },
  shared_risk_exposures: [{ kind: 'concentration', symbols: ['AAPL'], size: 1, summary: 'Single-name risk', rank: 1 }],
  stance_distribution: {
    status: 'partial', scored_count: 1, unanalyzed_count: 1, average_score: 70,
    by_operation_advice: { hold: 1 }, items: [], formula_version: 'watchlist_score_v1',
  },
  health: { status: 'partial', partial_score: 40, coverage_ratio: 0.5, data_quality: { status: 'partial' } },
  stress: { status: 'ok', scenario: { id: 'market_down_10' } },
  risk_metrics_status: 'partial',
  risk_history: { aligned_days: 80 },
  assumptions: { synthetic_snapshot: true, provider_calls_on_hot_path: false },
  calculated_at: '2026-08-15T12:00:00Z',
};

const impact = {
  position_key: '7:AAPL:us',
  account_id: 7,
  symbol: 'AAPL',
  market_value: 10000,
  weight_pct: 100,
  shock_pct: -10,
  pnl: -1000,
  stressed_market_value: 9000,
  price_source: 'stored_daily',
  price_provider: 'test',
  price_date: '2026-08-15',
  price_stale: false,
  data_quality: 'ok',
  limitations: [],
};

const stressPayload = {
  as_of: '2026-08-15',
  calculated_at: '2026-08-15T12:00:00Z',
  snapshot_id: 'b'.repeat(64),
  snapshot_version: 'portfolio_snapshot_v1',
  account_id: 7,
  cost_method: 'avg',
  currency: 'USD',
  status: 'partial',
  status_message: 'One position excluded.',
  portfolio_value: 10000,
  authoritative_portfolio_value: 11000,
  reconciliation_delta: -1000,
  positions_used: 1,
  excluded_position_count: 1,
  excluded_known_market_value: 1000,
  excluded_unknown_value_count: 0,
  excluded_positions: [{ symbol: 'MSFT', reason: 'missing_price' }],
  simulation_method: 'deterministic_factor_shock',
  historical_replay_available: false,
  scenario,
  assumptions: {
    simplified_assumptions: ['Linear factor shock'],
    data_source: 'portfolio_snapshot',
  },
  snapshot_fx_stale: false,
  snapshot_data_quality: 'partial',
  snapshot_limitations: ['missing_price'],
  missing_data: ['MSFT'],
  portfolio_pnl: -1000,
  portfolio_pnl_pct: -10,
  stressed_portfolio_value: 9000,
  position_impacts: [impact],
  top_losers: [impact],
  top_winners: [],
  concentration: { status: 'partial', top_weight_pct: 100 },
};

const rebalancePayload = {
  as_of: '2026-08-15',
  account_id: 7,
  cost_method: 'avg',
  currency: 'USD',
  status: 'refused',
  status_message: 'Insufficient risk data.',
  disclaimer: 'Research aid only.',
  risk_tolerance: 'moderate',
  is_suggestion_only: true,
  auto_execute: false,
  target_model: {
    name: 'risk_band_v1', description: 'Risk-band targets', max_single_weight_pct: 25,
    band_max_single_weight_pct: 25, soft_max_single_name_weight: 0.25,
    min_effective_n: 4, max_hhi: 0.35, target_var_pct_ceiling: 3.5, notes: ['No execution'],
  },
  current: {
    portfolio_value: 10000, weights: [{ symbol: 'AAPL', weight_pct: 100 }],
    risk_status: 'unavailable', var_pct: null, hhi: 1, effective_n: 1,
    diversification_score: 0,
  },
  drift: { max_abs_weight_drift_pct: 75, breaches: [] },
  suggestions: [],
  position_bands: [],
  assumptions: {
    method: 'risk_band_drift_v1',
    risk_metrics_source: 'PortfolioRiskMetricsService',
    tax_and_transaction_costs: 'not_modeled_v1',
    recommendation_honesty: 'explicit_refusal_when_insufficient_data',
  },
  risk_metrics_summary: {
    status: 'unavailable', var_status: 'unavailable', correlation_status: 'unavailable',
    concentration_status: 'ok',
  },
};

describe('portfolioInsightsApi', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('maps basket requests and preserves limitations, assumptions, and sources', async () => {
    post.mockResolvedValueOnce({ data: basketPayload });
    const result = await portfolioInsightsApi.analyzeBasket({
      stockCodes: ['aapl', 'msft'],
      currency: 'usd',
      includeStress: true,
    });

    expect(result.status).toBe('partial');
    expect(result.degradedSymbols[0].reason).toBe('missing_history');
    expect(result.assumptions.syntheticSnapshot).toBe(true);
    expect(result.riskHistory.alignedDays).toBe(80);
    expect(post).toHaveBeenCalledWith('/api/v1/analysis/portfolio', expect.objectContaining({
      stock_codes: ['AAPL', 'MSFT'],
      currency: 'USD',
      include_stress: true,
    }));
  });

  it('preserves stress context, exclusions, assumptions, and price provenance', async () => {
    get.mockResolvedValueOnce({ data: stressPayload });
    const result = await portfolioInsightsApi.runStressPreset({
      scenarioId: 'market_down_10',
      accountId: 7,
      costMethod: 'avg',
    });

    expect(result.accountId).toBe(7);
    expect(result.costMethod).toBe('avg');
    expect(result.excludedPositions[0].reason).toBe('missing_price');
    expect(result.assumptions.simplifiedAssumptions).toEqual(['Linear factor shock']);
    expect(result.positionImpacts[0].priceProvider).toBe('test');
  });

  it('preserves explicit rebalance refusal and suggestion-only guarantees', async () => {
    get.mockResolvedValueOnce({ data: rebalancePayload });
    const result = await portfolioInsightsApi.getRebalancing({
      accountId: 7,
      costMethod: 'avg',
      riskTolerance: 'moderate',
    });

    expect(result.status).toBe('refused');
    expect(result.isSuggestionOnly).toBe(true);
    expect(result.autoExecute).toBe(false);
    expect(result.assumptions.recommendationHonesty)
      .toBe('explicit_refusal_when_insufficient_data');
  });

  it('rejects schema drift for basket, stress, and rebalance responses', async () => {
    post.mockResolvedValueOnce({ data: { ...basketPayload, formula_version: 'v2' } });
    await expect(portfolioInsightsApi.analyzeBasket({ stockCodes: ['AAPL'] }))
      .rejects.toSatisfy((error: unknown) => {
        expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
        return true;
      });

    get.mockResolvedValueOnce({ data: { ...stressPayload, cost_method: 'lifo' } });
    await expect(portfolioInsightsApi.runStressPreset({ scenarioId: 'market_down_10' }))
      .rejects.toSatisfy((error: unknown) => {
        expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
        return true;
      });

    get.mockResolvedValueOnce({ data: { ...rebalancePayload, auto_execute: true } });
    await expect(portfolioInsightsApi.getRebalancing())
      .rejects.toSatisfy((error: unknown) => {
        expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
        return true;
      });
  });

  it('rejects invalid custom stress requests before network I/O', async () => {
    await expect(portfolioInsightsApi.runStressCustom({
      scenarioId: 'market_down_10',
      customShocks: [{ factor: 'market', valuePct: -10 }],
    })).rejects.toSatisfy((error: unknown) => {
      expect(getParsedApiError(error).code).toBe('invalid_params');
      return true;
    });
    expect(post).not.toHaveBeenCalled();
  });
});
