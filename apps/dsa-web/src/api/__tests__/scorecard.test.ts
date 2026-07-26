// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { scorecardApi } from '../scorecard';

vi.mock('../index', () => ({
  __esModule: true,
  default: {
    get: vi.fn(),
  },
  locallyRecoverableResourceConfig: () => ({ handleUnauthorizedLocally: true }),
}));

describe('scorecardApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('maps the public scorecard payload to camelCase', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: {
        min_samples: 10,
        overall: {
          status: 'ok',
          sample_size: 12,
          completed: 14,
          hit_rate_pct: 50.0,
          avg_return_pct: 1.5,
        },
        by_signal_type_horizon: [
          {
            signal_type: 'buy',
            horizon: '5d',
            status: 'ok',
            sample_size: 8,
            completed: 8,
            hit_rate_pct: 62.5,
            avg_return_pct: 2.0,
          },
        ],
        return_distribution: [
          { band: '+2% ~ +5%', count: 3, share_pct: 25.0 },
        ],
        recent_misses: [
          {
            signal_type: 'buy',
            horizon: '5d',
            return_pct: -4.0,
            anchor_date: '2026-07-01',
          },
        ],
      },
    });

    const result = await scorecardApi.getPublic();

    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/v1/scorecard',
      expect.objectContaining({ handleUnauthorizedLocally: true }),
    );
    expect(result.minSamples).toBe(10);
    expect(result.overall.hitRatePct).toBe(50);
    expect(result.bySignalTypeHorizon[0].signalType).toBe('buy');
    expect(result.returnDistribution[0].band).toBe('+2% ~ +5%');
    expect(result.recentMisses[0].anchorDate).toBe('2026-07-01');
  });
});
