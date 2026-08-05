// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { backtestApi } from '../backtest';
import { getParsedApiError, isApiRequestError } from '../error';

vi.mock('../index', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

const mockGet = vi.mocked(apiClient.get);
const mockPost = vi.mocked(apiClient.post);

describe('backtestApi.run', () => {
  beforeEach(() => mockPost.mockReset());

  it('maps run response and preserves extras (pass-through)', async () => {
    mockPost.mockResolvedValue({
      data: {
        processed: 10,
        saved: 8,
        completed: 7,
        insufficient: 1,
        errors: 0,
        applied_eval_window_days: 5,
        message: null,
        unexpected_server_field: 'keep-me',
      },
    });
    const result = await backtestApi.run({ code: '600519', force: true });
    expect(result.processed).toBe(10);
    expect(result.appliedEvalWindowDays).toBe(5);
    expect(result).toEqual(expect.objectContaining({ unexpectedServerField: 'keep-me' }));
  });

  it('rejects missing required counts via ParsedApiError', async () => {
    mockPost.mockResolvedValue({
      data: { processed: 1, completed: 1, insufficient: 0, errors: 0, applied_eval_window_days: 5 },
    });
    await expect(backtestApi.run()).rejects.toSatisfy((error: unknown) => {
      expect(isApiRequestError(error)).toBe(true);
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.message).toContain('BacktestRunResponse');
      return true;
    });
  });
});

describe('backtestApi.getResults', () => {
  beforeEach(() => mockGet.mockReset());

  it('camelCases result items including money-math return fields', async () => {
    mockGet.mockResolvedValue({
      data: {
        total: 1, page: 1, limit: 20,
        items: [{
          analysis_history_id: 9, code: 'AAPL', eval_window_days: 5,
          engine_version: 'v1', eval_status: 'completed',
          start_price: 100, end_close: 110, stock_return_pct: 10, simulated_return_pct: 8.5,
        }],
      },
    });
    const results = await backtestApi.getResults({ code: 'AAPL' });
    expect(results.items[0].stockReturnPct).toBe(10);
    expect(results.items[0].simulatedReturnPct).toBe(8.5);
  });

  it('rejects numeric-string return pct (contract is number)', async () => {
    mockGet.mockResolvedValue({
      data: {
        total: 1, page: 1, limit: 20,
        items: [{
          analysis_history_id: 9, code: 'AAPL', eval_window_days: 5,
          engine_version: 'v1', eval_status: 'completed', stock_return_pct: '10.5',
        }],
      },
    });
    await expect(backtestApi.getResults()).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.message).toContain('BacktestResultsResponse');
      return true;
    });
  });

  it('defaults omitted items to []', async () => {
    mockGet.mockResolvedValue({ data: { total: 0, page: 1, limit: 20 } });
    const results = await backtestApi.getResults();
    expect(results.items).toEqual([]);
  });
});

describe('backtestApi performance metrics money-math', () => {
  beforeEach(() => mockGet.mockReset());

  const validMetrics = {
    scope: 'overall', eval_window_days: 5, engine_version: 'v1',
    total_evaluations: 10, completed_count: 8, insufficient_count: 2,
    long_count: 5, cash_count: 3, win_count: 4, loss_count: 3, neutral_count: 1,
    win_rate_pct: 50, avg_stock_return_pct: 1.25,
  };

  it('maps overall performance money fields', async () => {
    mockGet.mockResolvedValue({ data: validMetrics });
    const metrics = await backtestApi.getOverallPerformance();
    expect(metrics?.winRatePct).toBe(50);
    expect(metrics?.avgStockReturnPct).toBe(1.25);
  });

  it('rejects numeric-string win_rate_pct', async () => {
    mockGet.mockResolvedValue({ data: { ...validMetrics, win_rate_pct: '50' } });
    await expect(backtestApi.getOverallPerformance()).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.message).toContain('PerformanceMetrics');
      return true;
    });
  });

});
