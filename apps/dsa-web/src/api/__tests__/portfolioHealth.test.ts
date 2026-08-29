// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getParsedApiError } from '../error';
import * as parseCamelCasePayloadModule from '../parseCamelCasePayload';
import { portfolioHealthApi } from '../portfolioHealth';
import { toCamelCase } from '../utils';

const { get, post, locallyRecoverableResourceConfig } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  locallyRecoverableResourceConfig: vi.fn(() => ({ localRecovery: true })),
}));

vi.mock('../index', () => ({
  default: { get, post },
  locallyRecoverableResourceConfig,
}));

function healthPayload(status: 'ok' | 'partial' | 'empty_portfolio' | 'unavailable' = 'ok') {
  const dimension = {
    formula: 'test',
    input: {},
    reason: null,
    score: status === 'unavailable' ? null : 80,
    status: status === 'unavailable' ? 'unavailable' : 'ok',
    status_message: status === 'unavailable' ? 'Metric unavailable' : 'Within threshold',
  };
  const weights = {
    concentration: 0.25,
    risk_exposure: 0.25,
    diversification: 0.2,
    pnl: 0.15,
    cash_ratio: 0.15,
  };
  return {
    account_id: 7,
    as_of: '2026-08-15',
    band: status === 'ok' ? 'healthy' : null,
    bands: [{ max_exclusive: 101, min_inclusive: 80, name: 'healthy' }],
    comparable: status === 'ok',
    config: {
      cash_high_alert_pct: 50,
      cash_low_alert_pct: 2,
      concentration_alert_pct: 35,
      diversification_alert: 0.35,
      pnl_loss_alert_pct: -15,
      source: 'shared_config',
      var_alert_pct: 5,
      weights,
    },
    cost_method: 'avg',
    coverage_ratio: status === 'ok' ? 1 : 0.75,
    currency: 'USD',
    data_quality: {
      fx_stale: status === 'partial',
      limitations: status === 'partial' ? ['fx_stale'] : [],
      missing_price_symbols: [],
      partial_reasons: status === 'partial' ? ['fx_stale'] : [],
      risk_metrics_status: status,
      snapshot_data_quality: status === 'ok' ? 'ok' : 'partial',
      status: status === 'ok' ? 'ok' : status === 'empty_portfolio' ? 'empty' : status,
    },
    dimensions: {
      concentration: dimension,
      risk_exposure: dimension,
      diversification: dimension,
      pnl: dimension,
      cash_ratio: dimension,
    },
    status,
    status_message: status === 'ok' ? 'Healthy' : `Portfolio health ${status}`,
    disclaimer: 'Research aid only.',
    effective_weights: weights,
    formula_version: 'portfolio_health_v2',
    inputs: {
      cash_pct: 10,
      diversification_score: 0.8,
      top_weight_pct: 20,
      total_cash: 1000,
      total_equity: 10000,
      total_market_value: 9000,
      unrealized_pnl_pct: 4,
      var_pct: 2,
    },
    insights: [],
    llm_can_modify_score: false,
    partial_score: status === 'ok' ? null : 60,
    persisted: true,
    provenance: {
      calculated_at: '2026-08-15T12:00:00Z',
      config_hash: 'config',
      risk_hash: 'risk',
      snapshot_hash: 'snapshot',
    },
    score: status === 'ok' ? 85 : null,
    score_source: 'rules',
    unavailable_dimensions: status === 'unavailable' ? ['risk_exposure'] : [],
    weights,
  };
}

describe('portfolioHealthApi', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it.each(['ok', 'partial', 'unavailable'] as const)(
    'parses %s responses and preserves evidence fields',
    async (status) => {
      get.mockResolvedValueOnce({ data: healthPayload(status) });
      const result = await portfolioHealthApi.getSummary({ accountId: 7, costMethod: 'avg' });

      expect(result?.status).toBe(status);
      expect(result?.accountId).toBe(7);
      expect(result?.costMethod).toBe('avg');
      expect(result?.provenance.snapshotHash).toBe('snapshot');
      expect(get).toHaveBeenCalledWith('/api/v1/portfolio/health', {
        localRecovery: true,
        params: { account_id: 7, cost_method: 'avg' },
      });
    },
  );

  it('maps a missing stored snapshot to null without hiding other errors', async () => {
    get.mockRejectedValueOnce({ response: { status: 404 } });
    await expect(portfolioHealthApi.getSummary()).resolves.toBeNull();

    const unavailable = new Error('service unavailable');
    get.mockRejectedValueOnce(unavailable);
    await expect(portfolioHealthApi.getSummary()).rejects.toBe(unavailable);
  });

  it('refreshes persistently by default and rejects response schema drift', async () => {
    post.mockResolvedValueOnce({ data: healthPayload('partial') });
    const result = await portfolioHealthApi.refresh({ accountId: 7, costMethod: 'avg' });
    expect(result.status).toBe('partial');
    expect(post).toHaveBeenCalledWith(
      '/api/v1/portfolio/health/refresh',
      undefined,
      { params: { account_id: 7, cost_method: 'avg', persist: true } },
    );

    post.mockResolvedValueOnce({ data: { ...healthPayload(), score: '85' } });
    await expect(portfolioHealthApi.refresh()).rejects.toSatisfy((error: unknown) => {
      expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
      return true;
    });
  });

  it('preserves extra keys and the camelCase object identity after parse', async () => {
    const spy = vi.spyOn(parseCamelCasePayloadModule, 'parseCamelCasePayload');
    const payload = { ...healthPayload(), unexpected_server_field: 'keep-me' };
    get.mockResolvedValueOnce({ data: payload });
    const result = await portfolioHealthApi.getSummary();
    expect(result).toEqual(toCamelCase(payload));
    expect((result as { unexpectedServerField?: string } | null)?.unexpectedServerField).toBe('keep-me');
    expect(spy).toHaveBeenCalledTimes(1);
    expect(result).toBe(spy.mock.results[0]?.value);
    spy.mockRestore();
  });

  it('rejects omitted required OpenAPI fields on both GET and POST', async () => {
    const withoutDisclaimer = (({ disclaimer: _omitted, ...rest }) => {
      void _omitted;
      return rest;
    })(healthPayload());
    const withoutAsOf = (({ as_of: _omitted, ...rest }) => {
      void _omitted;
      return rest;
    })(healthPayload());
    const withoutRiskExposure = (() => {
      const payload = healthPayload();
      const { risk_exposure: _omitted, ...dimensions } = payload.dimensions;
      void _omitted;
      return { ...payload, dimensions };
    })();

    for (const payload of [withoutDisclaimer, withoutAsOf, withoutRiskExposure]) {
      get.mockResolvedValueOnce({ data: payload });
      await expect(portfolioHealthApi.getSummary()).rejects.toSatisfy((error: unknown) => {
        expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
        return true;
      });
      post.mockResolvedValueOnce({ data: payload });
      await expect(portfolioHealthApi.refresh()).rejects.toSatisfy((error: unknown) => {
        expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
        return true;
      });
    }
  });

  it.each([
    { status: 'disabled' },
    { band: 'great' },
    { formula_version: 'portfolio_health_v1' },
    { score: Number.NaN },
    { score: Number.POSITIVE_INFINITY },
    { score: Number.NEGATIVE_INFINITY },
  ])('rejects illegal or non-finite response values %o on GET and POST', async (override) => {
    const payload = { ...healthPayload(), ...override };
    get.mockResolvedValueOnce({ data: payload });
    await expect(portfolioHealthApi.getSummary()).rejects.toSatisfy((error: unknown) => {
      expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
      return true;
    });
    post.mockResolvedValueOnce({ data: payload });
    await expect(portfolioHealthApi.refresh()).rejects.toSatisfy((error: unknown) => {
      expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
      return true;
    });
  });

  it('parses a legal empty_portfolio payload', async () => {
    get.mockResolvedValueOnce({ data: healthPayload('empty_portfolio') });
    const result = await portfolioHealthApi.getSummary();
    expect(result?.status).toBe('empty_portfolio');
  });

  it('encodes persist false on refresh instead of dropping the query flag', async () => {
    post.mockResolvedValueOnce({ data: healthPayload('ok') });
    await portfolioHealthApi.refresh({ persist: false });
    expect(post).toHaveBeenCalledWith(
      '/api/v1/portfolio/health/refresh',
      undefined,
      { params: { persist: false } },
    );
  });

  it('rejects a string score through the shared GET parser', async () => {
    get.mockResolvedValueOnce({ data: { ...healthPayload(), score: '85' } });
    await expect(portfolioHealthApi.getSummary()).rejects.toSatisfy((error: unknown) => {
      expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
      return true;
    });
  });
});
