// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getParsedApiError } from '../error';
import { portfolioHealthApi } from '../portfolioHealth';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock('../index', () => ({
  default: { get, post },
  locallyRecoverableResourceConfig: () => ({ handleUnauthorizedLocally: true }),
}));

function payload(overrides: Record<string, unknown> = {}) {
  const dimension = { status: 'ok', score: 80, input: {} };
  return {
    account_id: 7,
    as_of: '2026-08-13',
    band: 'healthy',
    bands: [{ min_inclusive: 80, max_exclusive: 101, name: 'healthy' }],
    comparable: true,
    config: {
      cash_high_alert_pct: 50,
      cash_low_alert_pct: 2,
      concentration_alert_pct: 35,
      diversification_alert: 0.35,
      pnl_loss_alert_pct: -15,
      source: 'shared_config',
      var_alert_pct: 5,
      weights: {
        concentration: 0.25,
        risk_exposure: 0.25,
        diversification: 0.2,
        pnl: 0.15,
        cash_ratio: 0.15,
      },
    },
    cost_method: 'avg',
    coverage_ratio: 1,
    currency: 'CNY',
    data_quality: {
      fx_stale: false,
      status: 'ok',
    },
    dimensions: {
      concentration: dimension,
      risk_exposure: dimension,
      diversification: dimension,
      pnl: dimension,
      cash_ratio: dimension,
    },
    disclaimer: 'For information only.',
    effective_weights: {
      concentration: 0.25,
      risk_exposure: 0.25,
      diversification: 0.2,
      pnl: 0.15,
      cash_ratio: 0.15,
    },
    formula_version: 'portfolio_health_v2',
    inputs: {
      total_cash: 100,
      total_equity: 1000,
      total_market_value: 900,
    },
    llm_can_modify_score: false,
    partial_score: null,
    persisted: true,
    provenance: {
      calculated_at: '2026-08-13T12:00:00Z',
      config_hash: 'config',
      risk_hash: 'risk',
      snapshot_hash: 'snapshot',
    },
    score: 82,
    score_source: 'rules',
    status: 'ok',
    weights: {
      concentration: 0.25,
      risk_exposure: 0.25,
      diversification: 0.2,
      pnl: 0.15,
      cash_ratio: 0.15,
    },
    ...overrides,
  };
}

describe('portfolioHealthApi', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it('reads a stored response with account and cost-method parameters', async () => {
    get.mockResolvedValue({ data: payload() });

    const result = await portfolioHealthApi.getSummary({ accountId: 7, costMethod: 'avg' });

    expect(get).toHaveBeenCalledWith('/api/v1/portfolio/health', {
      handleUnauthorizedLocally: true,
      params: { account_id: 7, cost_method: 'avg' },
    });
    expect(result?.dimensions.riskExposure.score).toBe(80);
    expect(result?.insights).toEqual([]);
    expect(result?.dataQuality.partialReasons).toEqual([]);
  });

  it('maps a missing stored snapshot to null', async () => {
    get.mockRejectedValue({ response: { status: 404 } });
    await expect(portfolioHealthApi.getSummary()).resolves.toBeNull();
  });

  it('refreshes explicitly with persistence and parses partial results', async () => {
    post.mockResolvedValue({
      data: payload({
        status: 'partial',
        comparable: false,
        score: null,
        partial_score: 52,
        coverage_ratio: 0.7,
        band: null,
        unavailable_dimensions: ['risk_exposure'],
      }),
    });

    const result = await portfolioHealthApi.refresh({ accountId: 7, costMethod: 'fifo' });

    expect(post).toHaveBeenCalledWith('/api/v1/portfolio/health/refresh', undefined, {
      params: { account_id: 7, cost_method: 'fifo', persist: true },
    });
    expect(result.status).toBe('partial');
    expect(result.partialScore).toBe(52);
    expect(result.unavailableDimensions).toEqual(['risk_exposure']);
  });

  it('rejects response schema drift and non-finite scores', async () => {
    get.mockResolvedValue({ data: payload({ score: Number.NaN }) });
    await expect(portfolioHealthApi.getSummary()).rejects.toSatisfy((error: unknown) => {
      expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
      return true;
    });
  });

  it('rejects invalid account ids before sending a request', async () => {
    await expect(portfolioHealthApi.refresh({ accountId: 0 })).rejects.toSatisfy(
      (error: unknown) => {
        expect(getParsedApiError(error).code).toBe('invalid_params');
        return true;
      },
    );
    expect(post).not.toHaveBeenCalled();
  });
});
