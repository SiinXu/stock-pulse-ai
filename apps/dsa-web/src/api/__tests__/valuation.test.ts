// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { getParsedApiError, isApiRequestError } from '../error';
import { buildPeerValuationCanvas } from '../valuation';

vi.mock('../index', () => ({
  __esModule: true,
  default: { post: vi.fn() },
}));

describe('buildPeerValuationCanvas', () => {
  beforeEach(() => vi.clearAllMocks());

  it('posts the constrained peer set and validates the camelCase response', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: {
        schema_version: 'peer-valuation-canvas-v1',
        status: 'ok',
        stock_code: '600519',
        base_currency: 'CNY',
        rows: [{ stock_code: '600519', role: 'target', metrics: {} }],
      },
    });

    const result = await buildPeerValuationCanvas({
      stockCode: '600519',
      peerSource: 'custom',
      peerCodes: ['000858'],
      industryLabel: null,
      baseCurrency: 'CNY',
    });

    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/valuation/peer-canvas', {
      stock_code: '600519',
      peer_source: 'custom',
      peer_codes: ['000858'],
      industry_label: undefined,
      base_currency: 'CNY',
    });
    expect(result).toEqual(expect.objectContaining({
      schemaVersion: 'peer-valuation-canvas-v1',
      stockCode: '600519',
      baseCurrency: 'CNY',
    }));
  });

  it('surfaces malformed responses through the shared parsed API error contract', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { stock_code: '600519' } });

    await expect(buildPeerValuationCanvas({ stockCode: '600519' })).rejects.toSatisfy(
      (error: unknown) => {
        expect(isApiRequestError(error)).toBe(true);
        expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
        return true;
      },
    );
  });
});
