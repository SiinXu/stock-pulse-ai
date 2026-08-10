// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { calculatorsApi } from '../calculators';
import apiClient from '../index';

vi.mock('../index', () => ({
  default: { post: vi.fn() },
}));

describe('calculatorsApi', () => {
  beforeEach(() => vi.resetAllMocks());

  it('forwards cancellation and accepts the strict compound contract', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: {
        status: 'ok',
        principal: 1000,
        annual_rate: 0.12,
        years: 1,
        contribution_per_period: 0,
        periods_per_year: 12,
        period_count: 12,
        period_rate: 0.01,
        final_value: 1126.83,
        total_contributed: 1000,
        total_gain: 126.83,
        series_total_points: 13,
        series_returned_points: 2,
        series_sampled: true,
        series_stride: 12,
        series: [
          { period: 0, balance: 1000, total_contributed: 1000, gain: 0 },
          { period: 12, balance: 1126.83, total_contributed: 1000, gain: 126.83 },
        ],
      },
    });
    const controller = new AbortController();

    const result = await calculatorsApi.compoundGrowth({
      principal: 1000,
      annualRate: 0.12,
      years: 1,
      contributionPerPeriod: 0,
      periodsPerYear: 12,
    }, { signal: controller.signal });

    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/calculators/compound-growth',
      expect.objectContaining({ annual_rate: 0.12, periods_per_year: 12 }),
      { signal: controller.signal },
    );
    expect(result.seriesTotalPoints).toBe(13);
  });

  it('rejects unknown target-duration statuses instead of rendering them', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: {
        status: 'pending',
        reason_code: 'target_unreachable',
        target: 5000,
        principal: 1000,
        annual_rate: 0,
        contribution_per_period: 0,
        periods_per_year: 12,
        period_rate: 0,
        period_count: null,
        years: null,
      },
    });

    await expect(calculatorsApi.targetDuration({
      target: 5000,
      principal: 1000,
      annualRate: 0,
      contributionPerPeriod: 0,
      periodsPerYear: 12,
    })).rejects.toMatchObject({
      parsedError: expect.objectContaining({ code: 'api_response_validation_failed' }),
    });
  });
});
