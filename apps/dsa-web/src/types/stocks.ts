export type StockHistoryPeriod = 'daily' | 'weekly' | 'monthly';

export interface StockQuote {
  stockCode: string;
  stockName?: string | null;
  currentPrice: number;
  change?: number | null;
  changePercent?: number | null;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  prevClose?: number | null;
  volume?: number | null;
  amount?: number | null;
  /** Server fetch time of the quote, not a proven market-data timestamp. */
  updateTime?: string | null;
}

export interface StockHistoryCandle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number | null;
  amount?: number | null;
  changePercent?: number | null;
}

export interface StockHistoryResponse {
  stockCode: string;
  stockName?: string | null;
  period: StockHistoryPeriod;
  data: StockHistoryCandle[];
}
