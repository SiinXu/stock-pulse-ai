import { describe, expect, it } from 'vitest';
import { aggregateCandles, summarizeCandles } from '../klineAggregate';
import type { StockHistoryCandle } from '../../types/stocks';

function candle(
  date: string,
  open: number,
  high: number,
  low: number,
  close: number,
  volume: number | null = 100,
): StockHistoryCandle {
  return { date, open, high, low, close, volume };
}

const daily: StockHistoryCandle[] = [
  candle('2026-01-05', 10, 12, 9, 11, 100), // Mon, week A
  candle('2026-01-06', 11, 13, 10, 12, 200), // Tue, week A
  candle('2026-01-12', 12, 15, 11, 14, 300), // Mon, week B
];

describe('aggregateCandles', () => {
  it('returns a sorted copy for daily', () => {
    const shuffled = [daily[2], daily[0], daily[1]];
    expect(aggregateCandles(shuffled, 'daily').map((c) => c.date)).toEqual([
      '2026-01-05',
      '2026-01-06',
      '2026-01-12',
    ]);
  });

  it('aggregates weekly candles with open-first/close-last and high/low/volume rollups', () => {
    const weekly = aggregateCandles(daily, 'weekly');
    expect(weekly).toHaveLength(2);
    const [weekA, weekB] = weekly;
    expect(weekA.date).toBe('2026-01-06');
    expect(weekA.open).toBe(10);
    expect(weekA.close).toBe(12);
    expect(weekA.high).toBe(13);
    expect(weekA.low).toBe(9);
    expect(weekA.volume).toBe(300);
    expect(weekB.date).toBe('2026-01-12');
    expect(weekB.open).toBe(12);
    expect(weekB.close).toBe(14);
  });

  it('aggregates monthly candles across month boundaries', () => {
    const spanning = [
      candle('2026-01-20', 10, 11, 9, 10),
      candle('2026-01-30', 10, 12, 9, 11),
      candle('2026-02-02', 11, 14, 10, 13),
    ];
    const monthly = aggregateCandles(spanning, 'monthly');
    expect(monthly.map((c) => c.date)).toEqual(['2026-01-30', '2026-02-02']);
    expect(monthly[0].open).toBe(10);
    expect(monthly[0].close).toBe(11);
    expect(monthly[0].high).toBe(12);
    expect(monthly[1].close).toBe(13);
  });

  it('returns an empty array for no candles', () => {
    expect(aggregateCandles([], 'weekly')).toEqual([]);
  });

  it('does not poison high/low into NaN when a candle reports null high/low', () => {
    const dirty: StockHistoryCandle[] = [
      { date: '2026-04-06', open: 10, high: null as unknown as number, low: null as unknown as number, close: 11, volume: 100 },
      candle('2026-04-07', 11, 13, 9, 12),
    ];
    const [weekly] = aggregateCandles(dirty, 'weekly');
    expect(Number.isNaN(weekly.high)).toBe(false);
    expect(Number.isNaN(weekly.low)).toBe(false);
    expect(weekly.high).toBe(13);
    expect(weekly.low).toBe(9);
  });

  it('keeps volume null when no bucket member reports volume', () => {
    const noVolume = [candle('2026-03-02', 1, 2, 1, 2, null), candle('2026-03-03', 2, 3, 1, 2, null)];
    expect(aggregateCandles(noVolume, 'weekly')[0].volume).toBeNull();
  });
});

describe('summarizeCandles', () => {
  it('summarizes range, extremes, and close change', () => {
    const summary = summarizeCandles(daily);
    expect(summary.count).toBe(3);
    expect(summary.periodStart).toBe('2026-01-05');
    expect(summary.periodEnd).toBe('2026-01-12');
    expect(summary.first).toBe(11);
    expect(summary.last).toBe(14);
    expect(summary.high).toBe(15);
    expect(summary.low).toBe(9);
    expect(summary.changePercent).toBeCloseTo(((14 - 11) / 11) * 100, 6);
  });

  it('returns nulls for an empty series', () => {
    const summary = summarizeCandles([]);
    expect(summary.count).toBe(0);
    expect(summary.changePercent).toBeNull();
  });
});
