// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import type { StockHistoryCandle } from '../../../types/stocks';
import { computeMovingAverages, finiteNumber, normalizeRiskScore, priceExtent, riskScoreFill, sanitizeCandles, summarizeCandleSeries, volumeExtent } from '../chartUtils';

function candle(overrides: Partial<StockHistoryCandle> & Pick<StockHistoryCandle, 'date'>): StockHistoryCandle {
  return { open: 10, high: 12, low: 9, close: 11, volume: 1000, ...overrides };
}
describe('chartUtils finite guards', () => {
  it('rejects NaN and ±Infinity', () => {
    expect(finiteNumber(Number.NaN)).toBeNull();
    expect(finiteNumber(Number.POSITIVE_INFINITY)).toBeNull();
    expect(finiteNumber(12.5)).toBe(12.5);
  });
  it('clamps risk scores', () => {
    expect(normalizeRiskScore(Number.NaN)).toBeNull();
    expect(normalizeRiskScore(-5)).toBe(0);
    expect(normalizeRiskScore(140)).toBe(100);
  });
});
describe('sanitizeCandles', () => {
  it('returns empty for invalid', () => {
    expect(sanitizeCandles(null)).toEqual([]);
    expect(sanitizeCandles([candle({ date: '2026-01-01', open: Number.NaN, close: 10 })])).toEqual([]);
  });
  it('repairs high/low and colors CN red-up', () => {
    const result = sanitizeCandles([candle({ date: '2026-01-02', open: 10, close: 12, high: Number.NaN, low: Number.POSITIVE_INFINITY, volume: Number.NaN })], 'cn');
    expect(result).toHaveLength(1);
    expect(result[0].high).toBe(12);
    expect(result[0].low).toBe(10);
    expect(result[0].volume).toBeNull();
    expect(result[0].color).toBe('red');
  });
  it('US green-up', () => {
    expect(sanitizeCandles([candle({ date: '2026-01-01', open: 10, close: 11 })], 'us')[0].color).toBe('green');
  });
  it('single point ok', () => {
    const r = sanitizeCandles([candle({ date: '2026-01-01' })]);
    expect(r).toHaveLength(1);
    expect(priceExtent(r).min).toBeLessThan(priceExtent(r).max);
    expect(volumeExtent(r).max).toBeGreaterThan(0);
    expect(summarizeCandleSeries(r, String).count).toBe(1);
  });
});
describe('computeMovingAverages', () => {
  it('null until full', () => {
    const c = sanitizeCandles([
      candle({ date: '2026-01-01', open: 1, high: 1, low: 1, close: 1 }),
      candle({ date: '2026-01-02', open: 2, high: 2, low: 2, close: 2 }),
      candle({ date: '2026-01-03', open: 3, high: 3, low: 3, close: 3 }),
    ]);
    expect(computeMovingAverages(c, [2]).ma2).toEqual([null, 1.5, 2.5]);
  });
});
describe('riskScoreFill', () => {
  it('bands', () => {
    expect(riskScoreFill(null).level).toBe('missing');
    expect(riskScoreFill(90).background).toContain('--danger');
  });
});
