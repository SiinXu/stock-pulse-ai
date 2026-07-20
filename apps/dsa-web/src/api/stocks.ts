import apiClient from './index';
import { toCamelCase } from './utils';
import type { StockHistoryResponse, StockQuote } from '../types/stocks';

function toStockCodePath(stockCode: string): string {
  const trimmed = stockCode.trim();
  if (!trimmed) throw new Error('Stock code is required');
  if (trimmed.includes('/')) {
    throw new Error(
      'Stock code cannot contain "/" because the backend route accepts a single path segment; use 600519, HK00700, or AAPL.',
    );
  }
  return encodeURIComponent(trimmed);
}

export type ExtractItem = {
  code?: string | null;
  name?: string | null;
  confidence: string;
};

export type ExtractFromImageResponse = {
  codes: string[];
  items?: ExtractItem[];
  rawText?: string;
};

export const stocksApi = {
  async getQuote(stockCode: string): Promise<StockQuote> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/stocks/${toStockCodePath(stockCode)}/quote`,
    );
    return toCamelCase<StockQuote>(response.data);
  },

  // The backend only implements daily candles; weekly/monthly are aggregated
  // client-side, so this always requests the daily series.
  async getDailyHistory(stockCode: string, days = 30): Promise<StockHistoryResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/stocks/${toStockCodePath(stockCode)}/history`,
      { params: { period: 'daily', days } },
    );
    const data = toCamelCase<StockHistoryResponse>(response.data);
    if (!Array.isArray(data.data)) {
      throw new Error('Stock history response data must be an array');
    }
    return data;
  },

  async extractFromImage(file: File): Promise<ExtractFromImageResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const headers: { [key: string]: string | undefined } = { 'Content-Type': undefined };
    const response = await apiClient.post(
      '/api/v1/stocks/extract-from-image',
      formData,
      {
        headers,
        timeout: 60000, // Vision API can be slow; 60s
      },
    );

    const data = response.data as { codes?: string[]; items?: ExtractItem[]; raw_text?: string };
    return {
      codes: data.codes ?? [],
      items: data.items,
      rawText: data.raw_text,
    };
  },

  async parseImport(file?: File, text?: string): Promise<ExtractFromImageResponse> {
    if (file) {
      const formData = new FormData();
      formData.append('file', file);
      const headers: { [key: string]: string | undefined } = { 'Content-Type': undefined };
      const response = await apiClient.post('/api/v1/stocks/parse-import', formData, { headers });
      const data = response.data as { codes?: string[]; items?: ExtractItem[] };
      return { codes: data.codes ?? [], items: data.items };
    }
    if (text) {
      const response = await apiClient.post('/api/v1/stocks/parse-import', { text });
      const data = response.data as { codes?: string[]; items?: ExtractItem[] };
      return { codes: data.codes ?? [], items: data.items };
    }
    throw new Error('请提供文件或粘贴文本');
  },
};
