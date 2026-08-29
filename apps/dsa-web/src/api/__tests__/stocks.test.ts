import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { stocksApi } from '../stocks';
import { getParsedApiError, isApiRequestError } from '../error';
import * as parseCamelCasePayloadModule from '../parseCamelCasePayload';
import { toCamelCase } from '../utils';

vi.mock('../index', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const mockGet = vi.mocked(apiClient.get);
const mockPost = vi.mocked(apiClient.post);

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

describe('stocksApi.getFieldTrust', () => {
  beforeEach(() => mockGet.mockReset());

  it('requests the trust path and camelCases source, lag, stale, conflict, and health', async () => {
    mockGet.mockResolvedValue({
      data: {
        schema_version: 'field_trust_view/1.0',
        stock_code: '600519',
        status: 'degraded',
        metadata_present: true,
        quote_source: 'efinance',
        stale_seconds: 7200,
        is_stale: true,
        missing_fields: [],
        fields: [
          {
            field: 'price',
            value: 1688,
            source: 'efinance',
            origin: 'primary',
            staleness: 'stale',
            conflict: true,
          },
        ],
        conflicts: [
          {
            field: 'price',
            severity: 'warn',
            values: [
              { provider: 'efinance', value: 1688 },
              { provider: 'akshare_em', value: 2100 },
            ],
          },
        ],
        conflict_checks: [],
        provider_health: [{ provider: 'efinance', status: 'ok', role: 'primary' }],
        analysis_input: {
          schema_version: 'field_trust_analysis_input/1.0',
          confidence: 'low',
          gaps: [{ code: 'conflict', field: 'price', detail: 'providers disagreed' }],
          conflict_count: 1,
          failed_provider_count: 0,
        },
      },
    });
    const view = await stocksApi.getFieldTrust('600519');
    expect(mockGet).toHaveBeenCalledWith('/api/v1/stocks/600519/trust');
    expect(view.stockCode).toBe('600519');
    expect(view.staleSeconds).toBe(7200);
    expect(view.isStale).toBe(true);
    expect(view.fields[0].conflict).toBe(true);
    expect(view.providerHealth[0].provider).toBe('efinance');
    expect(view.analysisInput?.confidence).toBe('low');
    expect(view.analysisInput?.gaps[0]?.code).toBe('conflict');
    expect(view.message).toBeUndefined();
  });

  it('surfaces shape mismatches through ParsedApiError', async () => {
    mockGet.mockResolvedValue({
      data: { schema_version: 'field_trust_view/1.0', stock_code: '600519' },
    });
    await expect(stocksApi.getFieldTrust('600519')).rejects.toSatisfy((error: unknown) => {
      expect(isApiRequestError(error)).toBe(true);
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.message).toContain('StockFieldTrustResponse');
      return true;
    });
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
      expect(parsed.params).toMatchObject({ label: 'StockHistoryResponse' });
      return true;
    });
  });

  it('accepts contract-valid history payloads that omit optional data and defaults to []', async () => {
    mockGet.mockResolvedValue({
      data: {
        stock_code: '600519',
        period: 'daily',
      },
    });
    const history = await stocksApi.getDailyHistory('600519');
    expect(history.stockCode).toBe('600519');
    expect(history.period).toBe('daily');
    expect(history.data).toEqual([]);
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
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.title).toBe('响应校验失败');
      return true;
    });
  });
});

const imageFile = () => new File(['png'], 'shot.png', { type: 'image/png' });
const importFile = () => new File(['AAPL'], 'codes.csv', { type: 'text/csv' });

const extractCallers = [
  { name: 'extractFromImage', call: () => stocksApi.extractFromImage(imageFile()) },
  { name: 'parseImport file', call: () => stocksApi.parseImport(importFile()) },
  { name: 'parseImport text', call: () => stocksApi.parseImport(undefined, 'AAPL MSFT') },
] as const;

function validExtractPayload(overrides: Record<string, unknown> = {}) {
  return {
    codes: ['AAPL', '600519'],
    items: [
      { code: 'AAPL', name: 'Apple', confidence: 'high' },
      { code: '600519', name: 'Kweichow Moutai', confidence: 'medium' },
    ],
    raw_text: 'llm raw',
    ...overrides,
  };
}

function expectExtractValidationFailed(error: unknown): boolean {
  expect(isApiRequestError(error)).toBe(true);
  const parsed = getParsedApiError(error);
  expect(parsed.code).toBe('api_response_validation_failed');
  expect(parsed.message).toContain('ExtractFromImageResponse');
  return true;
}

describe('stocksApi.extractFromImage and parseImport', () => {
  beforeEach(() => mockPost.mockReset());

  it.each(extractCallers)(
    '$name preserves extra keys and the camelCase object identity after parse',
    async ({ call }) => {
      const spy = vi.spyOn(parseCamelCasePayloadModule, 'parseCamelCasePayload');
      const payload = validExtractPayload({ unexpected_server_field: 'keep-me' });
      mockPost.mockResolvedValueOnce({ data: payload });
      const result = await call();
      expect(result).toEqual(toCamelCase(payload));
      expect(result.codes).toEqual(['AAPL', '600519']);
      expect(result.rawText).toBe('llm raw');
      expect((result as { unexpectedServerField?: string }).unexpectedServerField).toBe('keep-me');
      expect(spy).toHaveBeenCalledTimes(1);
      expect(result).toBe(spy.mock.results[0]?.value);
      spy.mockRestore();
    },
  );

  it.each(extractCallers)(
    '$name rejects omitted required codes ({}) as the live codes ?? [] counterexample',
    async ({ call }) => {
      mockPost.mockResolvedValueOnce({ data: {} });
      await expect(call()).rejects.toSatisfy(expectExtractValidationFailed);
    },
  );

  it.each(extractCallers)(
    '$name rejects omitted required codes when only items is present',
    async ({ call }) => {
      mockPost.mockResolvedValueOnce({ data: { items: [] } });
      await expect(call()).rejects.toSatisfy(expectExtractValidationFailed);
    },
  );

  it.each([
    { codes: null },
    { codes: 'AAPL' },
  ])('rejects non-array codes %o on extract and import', async (override) => {
    const payload = validExtractPayload(override);
    for (const { call } of extractCallers) {
      mockPost.mockResolvedValueOnce({ data: payload });
      await expect(call()).rejects.toSatisfy(expectExtractValidationFailed);
    }
  });

  it.each(extractCallers)(
    '$name rejects present items that is not an array',
    async ({ call }) => {
      mockPost.mockResolvedValueOnce({ data: validExtractPayload({ items: { code: 'AAPL' } }) });
      await expect(call()).rejects.toSatisfy(expectExtractValidationFailed);
      mockPost.mockResolvedValueOnce({ data: validExtractPayload({ items: null }) });
      await expect(call()).rejects.toSatisfy(expectExtractValidationFailed);
    },
  );

  it.each(extractCallers)(
    '$name accepts legal empty codes: []',
    async ({ call }) => {
      mockPost.mockResolvedValueOnce({ data: { codes: [] } });
      const result = await call();
      expect(result.codes).toEqual([]);
      expect(result.items).toBeUndefined();
      expect(result.rawText).toBeUndefined();
    },
  );

  it.each(extractCallers)(
    '$name accepts omitted optional items and raw_text',
    async ({ call }) => {
      mockPost.mockResolvedValueOnce({ data: { codes: ['AAPL'] } });
      const result = await call();
      expect(result).toEqual({ codes: ['AAPL'] });
    },
  );

  it.each(extractCallers)(
    '$name accepts raw_text: null as rawText: null',
    async ({ call }) => {
      mockPost.mockResolvedValueOnce({ data: { codes: ['AAPL'], raw_text: null } });
      const result = await call();
      expect(result.rawText).toBeNull();
      expect(result.codes).toEqual(['AAPL']);
    },
  );

  it('posts extract FormData with the 60s vision timeout', async () => {
    const file = imageFile();
    mockPost.mockResolvedValueOnce({ data: { codes: ['AAPL'] } });
    await stocksApi.extractFromImage(file);
    expect(mockPost).toHaveBeenCalledTimes(1);
    const [path, body, options] = mockPost.mock.calls[0] as [string, FormData, Record<string, unknown>];
    expect(path).toBe('/api/v1/stocks/extract-from-image');
    expect(body).toBeInstanceOf(FormData);
    expect(body.get('file')).toBe(file);
    expect(options).toEqual({
      headers: { 'Content-Type': undefined },
      timeout: 60000,
    });
  });

  it('posts parseImport multipart file to /api/v1/stocks/parse-import', async () => {
    const file = importFile();
    mockPost.mockResolvedValueOnce({ data: { codes: ['AAPL'] } });
    await stocksApi.parseImport(file);
    expect(mockPost).toHaveBeenCalledTimes(1);
    const [path, body, options] = mockPost.mock.calls[0] as [string, FormData, Record<string, unknown>];
    expect(path).toBe('/api/v1/stocks/parse-import');
    expect(body).toBeInstanceOf(FormData);
    expect(body.get('file')).toBe(file);
    expect(options).toEqual({ headers: { 'Content-Type': undefined } });
  });

  it('posts parseImport JSON text to /api/v1/stocks/parse-import', async () => {
    mockPost.mockResolvedValueOnce({ data: { codes: ['AAPL'] } });
    await stocksApi.parseImport(undefined, 'AAPL MSFT');
    expect(mockPost).toHaveBeenCalledWith('/api/v1/stocks/parse-import', { text: 'AAPL MSFT' });
  });

  it('throws before network when parseImport is missing file and text', async () => {
    await expect(stocksApi.parseImport()).rejects.toThrow('请提供文件或粘贴文本');
    await expect(stocksApi.parseImport(undefined, '')).rejects.toThrow('请提供文件或粘贴文本');
    expect(mockPost).not.toHaveBeenCalled();
  });
});
