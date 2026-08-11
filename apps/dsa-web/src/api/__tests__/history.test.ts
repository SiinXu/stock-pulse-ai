import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { historyApi } from '../history';

vi.mock('../index', () => ({
  default: { get: vi.fn() },
  locallyRecoverableResourceConfig: vi.fn(() => ({})),
}));

const mockGet = vi.mocked(apiClient.get);

describe('historyApi.search', () => {
  beforeEach(() => mockGet.mockReset());

  it('trims the literal query, caps the limit, forwards cancellation, and camelCases items', async () => {
    const controller = new AbortController();
    mockGet.mockResolvedValue({
      data: {
        query: 'long-term value',
        limit: 10,
        items: [{
          id: 42,
          stock_code: '600519.SH',
          stock_name: 'Kweichow Moutai',
          report_type: 'detailed',
          summary: 'Long-term value remains intact',
          created_at: '2026-08-10T09:30:00+08:00',
        }],
      },
    });

    const result = await historyApi.search('  long-term value  ', {
      limit: 99,
      signal: controller.signal,
    });

    expect(mockGet).toHaveBeenCalledWith('/api/v1/history/search', {
      params: { q: 'long-term value', limit: 10 },
      signal: controller.signal,
    });
    expect(result.items[0]).toMatchObject({
      stockCode: '600519.SH',
      stockName: 'Kweichow Moutai',
      reportType: 'detailed',
      summary: 'Long-term value remains intact',
    });
  });
});
