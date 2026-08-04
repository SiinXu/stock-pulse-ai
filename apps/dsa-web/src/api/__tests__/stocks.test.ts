import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { stocksApi } from '../stocks';
import { getParsedApiError, isApiRequestError } from '../error';

vi.mock('../index', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const mockGet = vi.mocked(apiClient.get);

describe('stocksApi.getQuote', () => {
  beforeEach(() => mockGet.mockReset());

  it('requests the quote path and camelCases the response', async () => {
    mockGet.mockResolvedValue({
      data: { stock_code: '600519', stock_name: 'Kweichow Moutai', current_price: 1700, change_percent: 1.2, prev_close: 1680 },
    });
    const quote = await stocksApi.getQuote('600519');
    expect(mockGet).toHaveBeenCalledWith('/api/v1/stocks/600519/quote');
    expect(quote.currentPrice).toBe(1700);
    expect(quote.changePercent).toBe(1.2);
    expect(quote.prevClose).toBe(1680);
    expect(quote.stockName).toBe('Kweichow Moutai');
  });

  it('preserves extra keys on valid payloads (byte-identical toCamelCase pass-through)', async () => {
    mockGet.mockResolvedValue({
      data: {
        stock_code: '600519',
        current_price: 100,
        unexpected_server_field: 'keep-me',
      },
    });
    const quote = await stocksApi.getQuote('600519');
    expect(quote).toEqual({
      stockCode: '600519',
      currentPrice: 100,
      unexpectedServerField: 'keep-me',
    });
  });

  it('surfaces shape mismatches through ParsedApiError', async () => {
    mockGet.mockResolvedValue({
      data: {
        stock_code: '600519',
        // current_price missing — required by StockQuote contract
        stock_name: 'broken',
      },
    });
    await expect(stocksApi.getQuote('600519')).rejects.toSatisfy((error: unknown) => {
      expect(isApiRequestError(error)).toBe(true);
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.message).toContain('StockQuote');
      return true;
    });
  });

  it('encodes the code and rejects a slash that would break the path segment', async () => {
    mockGet.mockResolvedValue({ data: { stock_code: 'HK00700', current_price: 1 } });
    await stocksApi.getQuote('HK00700');
    expect(mockGet).toHaveBeenCalledWith('/api/v1/stocks/HK00700/quote');
    await expect(stocksApi.getQuote('a/b')).rejects.toThrow();
  });
});

describe('stocksApi.getDailyHistory', () => {
  beforeEach(() => mockGet.mockReset());

  it('always requests the daily series with the day count and camelCases candles', async () => {
    mockGet.mockResolvedValue({
      data: {
        stock_code: '600519',
        period: 'daily',
        data: [{ date: '2026-01-05', open: 10, high: 12, low: 9, close: 11, volume: 100, change_percent: 1.5 }],
      },
    });
    const history = await stocksApi.getDailyHistory('600519', 90);
    expect(mockGet).toHaveBeenCalledWith('/api/v1/stocks/600519/history', { params: { period: 'daily', days: 90 } });
    expect(history.data[0].close).toBe(11);
    expect(history.data[0].changePercent).toBe(1.5);
  });

  it('throws when the response data is not an array', async () => {
    mockGet.mockResolvedValue({ data: { stock_code: 'x', period: 'daily', data: null } });
    await expect(stocksApi.getDailyHistory('x')).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.message).toContain('StockHistoryResponse');
      return true;
    });
  });

  it('rejects history payloads missing required candle fields via ParsedApiError', async () => {
    mockGet.mockResolvedValue({
      data: {
        stock_code: '600519',
        period: 'daily',
        data: [{ date: '2026-01-05', open: 10 }],
      },
    });
    await expect(stocksApi.getDailyHistory('600519')).rejects.toSatisfy((error: unknown) => {
      expect(isApiRequestError(error)).toBe(true);
      expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
      return true;
    });
  });
});
