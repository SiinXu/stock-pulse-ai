import type { StockHistoryCandle, StockHistoryPeriod } from '../types/stocks';

function parseUtcDate(date: string): Date {
  return new Date(`${date}T00:00:00Z`);
}

function weekKey(date: string): string {
  const parsed = parseUtcDate(date);
  const day = parsed.getUTCDay();
  const toMonday = day === 0 ? -6 : 1 - day;
  const monday = new Date(parsed);
  monday.setUTCDate(parsed.getUTCDate() + toMonday);
  return monday.toISOString().slice(0, 10);
}

function monthKey(date: string): string {
  return date.slice(0, 7);
}

function sumOptional(values: Array<number | null | undefined>): number | null {
  let total = 0;
  let seen = false;
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      total += value;
      seen = true;
    }
  }
  return seen ? total : null;
}

function finiteNumbers(values: Array<number | null | undefined>): number[] {
  return values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
}

function sortByDate(candles: StockHistoryCandle[]): StockHistoryCandle[] {
  return [...candles]
    .filter((candle) => candle && typeof candle.date === 'string' && candle.date)
    .sort((left, right) => (left.date < right.date ? -1 : left.date > right.date ? 1 : 0));
}

/**
 * Aggregate a daily candle series into weekly/monthly candles client-side.
 * The backend only serves daily data, so higher periods are derived here.
 */
export function aggregateCandles(
  daily: StockHistoryCandle[],
  period: StockHistoryPeriod,
): StockHistoryCandle[] {
  const sorted = sortByDate(daily);
  if (period === 'daily') return sorted;

  const keyOf = period === 'weekly' ? weekKey : monthKey;
  const buckets = new Map<string, StockHistoryCandle[]>();
  for (const candle of sorted) {
    const key = keyOf(candle.date);
    const group = buckets.get(key);
    if (group) group.push(candle);
    else buckets.set(key, [candle]);
  }

  return [...buckets.entries()]
    .sort((left, right) => (left[0] < right[0] ? -1 : 1))
    .map(([, group]) => {
      const first = group[0];
      const last = group[group.length - 1];
      const open = first.open;
      const close = last.close;
      // Guard against dirty backend candles with null/NaN high/low, which
      // would otherwise poison Math.max/min (NaN) and break the chart axis.
      const highs = finiteNumbers(group.map((candle) => candle.high));
      const lows = finiteNumbers(group.map((candle) => candle.low));
      return {
        date: last.date,
        open,
        high: highs.length ? Math.max(...highs) : Math.max(open, close),
        low: lows.length ? Math.min(...lows) : Math.min(open, close),
        close,
        volume: sumOptional(group.map((candle) => candle.volume)),
        amount: sumOptional(group.map((candle) => candle.amount)),
        changePercent: open ? ((close - open) / open) * 100 : null,
      };
    });
}

export interface StockHistorySummary {
  count: number;
  periodStart: string | null;
  periodEnd: string | null;
  first: number | null;
  last: number | null;
  high: number | null;
  low: number | null;
  changePercent: number | null;
}

export function summarizeCandles(candles: StockHistoryCandle[]): StockHistorySummary {
  if (candles.length === 0) {
    return {
      count: 0,
      periodStart: null,
      periodEnd: null,
      first: null,
      last: null,
      high: null,
      low: null,
      changePercent: null,
    };
  }
  const first = candles[0];
  const last = candles[candles.length - 1];
  const firstClose = first.close;
  const lastClose = last.close;
  const highs = finiteNumbers(candles.map((candle) => candle.high));
  const lows = finiteNumbers(candles.map((candle) => candle.low));
  return {
    count: candles.length,
    periodStart: first.date,
    periodEnd: last.date,
    first: firstClose,
    last: lastClose,
    high: highs.length ? Math.max(...highs) : null,
    low: lows.length ? Math.min(...lows) : null,
    changePercent: firstClose ? ((lastClose - firstClose) / firstClose) * 100 : null,
  };
}
