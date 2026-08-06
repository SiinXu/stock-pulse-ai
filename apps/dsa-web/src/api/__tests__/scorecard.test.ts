// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { scorecardApi } from '../scorecard';
import { getParsedApiError, isApiRequestError } from '../error';

vi.mock('../index', () => ({
  __esModule: true,
  default: { get: vi.fn() },
  locallyRecoverableResourceConfig: () => ({ handleUnauthorizedLocally: true }),
}));

const validScorecard = {
  min_samples: 10,
  overall: { status: 'ok', sample_size: 12, completed: 14, hit_rate_pct: 50.0, avg_return_pct: 1.5 },
  by_signal_type_horizon: [
    { signal_type: 'buy', horizon: '5d', status: 'ok', sample_size: 8, completed: 8, hit_rate_pct: 62.5, avg_return_pct: 2.0 },
  ],
  return_distribution: [{ band: '+2% ~ +5%', count: 3, share_pct: 25.0 }],
  recent_misses: [{ signal_type: 'buy', horizon: '5d', return_pct: -4.0, anchor_date: '2026-07-01' }],
};

describe('scorecardApi', () => {
  beforeEach(() => vi.clearAllMocks());

  it('maps the public scorecard payload to camelCase', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: validScorecard });
    const result = await scorecardApi.getPublic();
    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/v1/scorecard',
      expect.objectContaining({ handleUnauthorizedLocally: true }),
    );
    expect(result.minSamples).toBe(10);
    expect(result.overall.hitRatePct).toBe(50);
    expect(result.bySignalTypeHorizon[0].signalType).toBe('buy');
  });

  it('preserves extra keys on valid payloads (byte-identical pass-through)', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { ...validScorecard, unexpected_server_field: 'keep-me' },
    });
    const result = await scorecardApi.getPublic();
    expect(result).toEqual(expect.objectContaining({
      minSamples: 10,
      unexpectedServerField: 'keep-me',
    }));
  });

  it('rejects numeric-string hit_rate_pct / avg_return_pct (contract is number)', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: {
        ...validScorecard,
        overall: { ...validScorecard.overall, hit_rate_pct: '50.0', avg_return_pct: '1.5' },
      },
    });
    await expect(scorecardApi.getPublic()).rejects.toSatisfy((error: unknown) => {
      expect(isApiRequestError(error)).toBe(true);
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.message).toContain('SignalScorecardResponse');
      return true;
    });
  });

  it('rejects missing required overall block via ParsedApiError', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { min_samples: 10, by_signal_type_horizon: [], return_distribution: [], recent_misses: [] },
    });
    await expect(scorecardApi.getPublic()).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      return true;
    });
  });
});
