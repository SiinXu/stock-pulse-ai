// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { reportVersionCompareApi } from '../reportVersionCompare';

vi.mock('../index', () => ({
  default: {
    get: vi.fn(),
  },
}));

describe('reportVersionCompareApi', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('lists runs with snake_case params and camelCase response', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: {
        stock_code: '600519',
        total: 1,
        page: 1,
        limit: 20,
        items: [
          {
            run_id: '12',
            query_id: 'q1',
            stock_code: '600519',
            model_used: 'model-a',
            config_fingerprint: 'abc123',
            config_components: { model_used: 'model-a' },
          },
        ],
      },
    });

    const result = await reportVersionCompareApi.listRuns({
      stockCode: '600519',
      page: 1,
      limit: 20,
    });

    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/v1/report-version-compare/runs',
      expect.objectContaining({
        params: expect.objectContaining({ stock_code: '600519', page: 1, limit: 20 }),
      }),
    );
    expect(result.stockCode).toBe('600519');
    expect(result.items[0]?.runId).toBe('12');
    expect(result.items[0]?.configFingerprint).toBe('abc123');
  });

  it('compares runs and camelCases nested payloads', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: {
        status: 'engine_pending',
        stock_code: '600519',
        base_run: {
          run_id: '1',
          query_id: 'a',
          stock_code: '600519',
          config_components: {},
        },
        target_run: {
          run_id: '2',
          query_id: 'b',
          stock_code: '600519',
          config_components: {},
        },
        config_diff: {
          base_fingerprint: 'aaa',
          target_fingerprint: 'bbb',
          identical: false,
          has_differences: true,
          components: [
            {
              key: 'model_used',
              base_value: 'a',
              target_value: 'b',
              changed: true,
            },
          ],
        },
        field_diffs: [
          {
            field: 'action',
            base_value: 'buy',
            target_value: 'sell',
            changed: true,
            severity: 'major',
          },
        ],
        delta: null,
        engine_status: 'engine_pending',
      },
    });

    const result = await reportVersionCompareApi.compare({
      stockCode: '600519',
      baseRunId: '1',
      targetRunId: '2',
    });

    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/v1/report-version-compare/compare',
      expect.objectContaining({
        params: {
          stock_code: '600519',
          base_run_id: '1',
          target_run_id: '2',
        },
      }),
    );
    expect(result.status).toBe('engine_pending');
    expect(result.baseRun.runId).toBe('1');
    expect(result.configDiff.hasDifferences).toBe(true);
    expect(result.configDiff.components[0]?.baseValue).toBe('a');
    expect(result.fieldDiffs[0]?.severity).toBe('major');
  });
});
