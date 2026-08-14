// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { getParsedApiError } from '../error';
import { researchTimelineApi } from '../researchTimeline';

vi.mock('../index', () => ({
  default: { get: vi.fn() },
}));

const getMock = vi.mocked(apiClient.get);

describe('researchTimelineApi', () => {
  beforeEach(() => getMock.mockReset());

  it('camel-cases and validates the timeline envelope', async () => {
    getMock.mockResolvedValue({
      data: {
        stock_code: '600519',
        items: [{
          id: 'analysis_run:1',
          kind: 'analysis_run',
          occurred_at: '2026-08-01T10:00:00Z',
          title: 'Hold',
          link: { type: 'analysis_history', record_id: 1 },
        }],
        next_cursor: null,
        has_more: false,
        limit: 20,
        sources: { analysis_run: 'ok', chat: 'empty', signal: 'empty', hypothesis: 'unavailable' },
      },
    });

    const result = await researchTimelineApi.list('600519');
    expect(result.stockCode).toBe('600519');
    expect(result.items[0].occurredAt).toBe('2026-08-01T10:00:00Z');
    expect(result.items[0].link.recordId).toBe(1);
  });

  it('uses the shared parsed error contract for malformed envelopes', async () => {
    getMock.mockResolvedValue({
      data: { stock_code: '600519', items: [], has_more: 'false', limit: 20, sources: {} },
    });

    await expect(researchTimelineApi.list('600519')).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.params?.label).toBe('ResearchTimelineResponse');
      return true;
    });
  });
});
