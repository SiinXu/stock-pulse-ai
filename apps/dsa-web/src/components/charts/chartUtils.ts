// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { StockHistoryCandle } from '../../types/stocks';
import {
  changeSemantics,
  type ChangeColor,
  type ChangeColorPreference,
  type ChangeDirection,
  type MarketId,
} from '../../utils/marketFormat';

export function finiteNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) return null;
  return numeric;
}

export function normalizeRiskScore(value: unknown): number | null {
  const numeric = finiteNumber(value);
  if (numeric === null) return null;
  return Math.max(0, Math.min(100, numeric));
}

export type ChartCandle = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
  direction: ChangeDirection;
  color: ChangeColor;
};

export function sanitizeCandles(
  candles: readonly StockHistoryCandle[] | null | undefined,
  market: MarketId = 'cn',
  colorPreference?: ChangeColorPreference | null,
): ChartCandle[] {
  if (!candles || candles.length === 0) return [];
  const result: ChartCandle[] = [];
  for (const candle of candles) {
    if (!candle || typeof candle.date !== 'string' || !candle.date.trim()) continue;
    const open = finiteNumber(candle.open);
    const close = finiteNumber(candle.close);
    if (open === null || close === null) continue;
    const highRaw = finiteNumber(candle.high);
    const lowRaw = finiteNumber(candle.low);
    const high = highRaw === null ? Math.max(open, close) : Math.max(highRaw, open, close);
    const low = lowRaw === null ? Math.min(open, close) : Math.min(lowRaw, open, close);
    const volume = finiteNumber(candle.volume);
    const semantics = changeSemantics(close - open, market, colorPreference);
    result.push({
      date: candle.date.trim(), open, high, low, close, volume,
      direction: semantics.direction, color: semantics.color,
    });
  }
  return result;
}

export function computeMovingAverages(
  candles: readonly ChartCandle[],
  periods: readonly number[],
): Record<string, Array<number | null>> {
  const series: Record<string, Array<number | null>> = {};
  for (const period of periods) {
    if (!Number.isInteger(period) || period < 1) continue;
    const key = `ma${period}`;
    const values: Array<number | null> = [];
    let windowSum = 0;
    const window: number[] = [];
    for (let index = 0; index < candles.length; index += 1) {
      const close = candles[index].close;
      window.push(close);
      windowSum += close;
      if (window.length > period) windowSum -= window.shift() as number;
      values.push(window.length === period ? windowSum / period : null);
    }
    series[key] = values;
  }
  return series;
}

export function changeColorToCss(color: ChangeColor): string {
  if (color === 'red') return 'hsl(var(--danger))';
  if (color === 'green') return 'hsl(var(--success))';
  return 'hsl(var(--muted-foreground))';
}

export function directionMarker(direction: ChangeDirection): string {
  if (direction === 'up') return '▲';
  if (direction === 'down') return '▼';
  return '■';
}

export function directionWord(
  direction: ChangeDirection,
  labels: { up: string; down: string; flat: string },
): string {
  if (direction === 'up') return labels.up;
  if (direction === 'down') return labels.down;
  return labels.flat;
}

export function riskScoreFill(score: number | null): {
  background: string;
  textClass: string;
  level: 'missing' | 'low' | 'medium' | 'high' | 'critical';
} {
  if (score === null) return { background: 'hsl(var(--muted) / 0.35)', textClass: 'text-muted-text', level: 'missing' };
  if (score < 25) return { background: 'hsl(var(--success) / 0.22)', textClass: 'text-foreground', level: 'low' };
  if (score < 50) return { background: 'hsl(var(--warning) / 0.28)', textClass: 'text-foreground', level: 'medium' };
  if (score < 75) return { background: 'hsl(var(--warning) / 0.55)', textClass: 'text-foreground', level: 'high' };
  return { background: 'hsl(var(--danger) / 0.55)', textClass: 'text-foreground', level: 'critical' };
}

export type ChartExtent = { min: number; max: number };

export function priceExtent(candles: readonly ChartCandle[], paddingRatio = 0.06): ChartExtent {
  if (candles.length === 0) return { min: 0, max: 1 };
  let min = candles[0].low, max = candles[0].high;
  for (const candle of candles) {
    if (candle.low < min) min = candle.low;
    if (candle.high > max) max = candle.high;
  }
  if (min === max) {
    const pad = Math.max(Math.abs(min) * 0.01, 1);
    return { min: min - pad, max: max + pad };
  }
  const pad = (max - min) * paddingRatio;
  return { min: min - pad, max: max + pad };
}

export function volumeExtent(candles: readonly ChartCandle[]): ChartExtent {
  let max = 0, seen = false;
  for (const candle of candles) {
    if (candle.volume !== null) {
      seen = true;
      if (candle.volume > max) max = candle.volume;
    }
  }
  if (!seen) return { min: 0, max: 1 };
  return { min: 0, max: max <= 0 ? 1 : max };
}

export function summarizeCandleSeries(
  candles: readonly ChartCandle[],
  formatChange: (value: number | null) => string,
) {
  if (candles.length === 0) {
    return { count: 0, firstClose: null, lastClose: null, change: null, changeText: formatChange(null), high: null, low: null };
  }
  const firstClose = candles[0].close;
  const lastClose = candles[candles.length - 1].close;
  const change = firstClose === 0 ? null : ((lastClose - firstClose) / firstClose) * 100;
  let high = candles[0].high, low = candles[0].low;
  for (const candle of candles) {
    if (candle.high > high) high = candle.high;
    if (candle.low < low) low = candle.low;
  }
  return { count: candles.length, firstClose, lastClose, change, changeText: formatChange(change), high, low };
}
