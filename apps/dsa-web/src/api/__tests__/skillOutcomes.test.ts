// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { skillOutcomesApi } from '../skillOutcomes';

vi.mock('../index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('skillOutcomesApi', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('loads performance stats with camelCase conversion and repeated query params', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: {
        engine_version: 'skill-opinion-outcome-v1',
        minimum_evaluated_sample_size: 30,
        buckets: [{
          skill_id: 'momentum',
          horizon: '5d',
          engine_version: 'skill-opinion-outcome-v1',
          total: 12,
          pending: 2,
          evaluated: 8,
          observational: 1,
          unable: 1,
          hit: 5,
          miss: 3,
          sample_sufficient: false,
          sample_status: 'insufficient',
          hit_rate_pct: null,
          miss_rate_pct: null,
          avg_directional_return_pct: null,
          unable_rate_pct: null,
        }],
      },
    });

    const stats = await skillOutcomesApi.getStats({
      skillIds: ['momentum', 'value'],
      horizons: ['5d', '10d'],
    });

    expect(apiClient.get).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/skill-outcomes/stats?'),
    );
    const url = vi.mocked(apiClient.get).mock.calls[0]?.[0] as string;
    expect(url).toContain('skill_ids=momentum');
    expect(url).toContain('skill_ids=value');
    expect(url).toContain('horizons=5d');
    expect(stats.minimumEvaluatedSampleSize).toBe(30);
    expect(stats.buckets?.[0]?.skillId).toBe('momentum');
    expect(stats.buckets?.[0]?.sampleSufficient).toBe(false);
  });

  it('posts run payload in snake_case and returns camelCase summary', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: {
        items: [],
        processed_keys: 4,
        created: 1,
        updated: 2,
        skipped: 1,
        failed: 0,
        errors: [],
        histories_scanned: 3,
        samples_created: 1,
        limit_unit: 'outcome_keys',
        engine_version: 'skill-opinion-outcome-v1',
      },
    });

    const result = await skillOutcomesApi.runOutcomes({
      limit: 100,
      skillId: 'momentum',
      horizons: ['1d', '3d'],
    });

    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/skill-outcomes/run',
      {
        skill_id: 'momentum',
        horizons: ['1d', '3d'],
        limit: 100,
      },
    );
    expect(result.processedKeys).toBe(4);
    expect(result.historiesScanned).toBe(3);
  });
});
