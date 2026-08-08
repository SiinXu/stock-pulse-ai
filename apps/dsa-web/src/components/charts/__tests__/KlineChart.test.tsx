// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ComponentProps } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { StockHistoryCandle } from '../../../types/stocks';
import { KlineChart } from '../KlineChart';

function candle(day: number, open: number, close: number): StockHistoryCandle {
  return { date: `2026-01-${String(day).padStart(2, '0')}`, open, high: Math.max(open, close) + 1, low: Math.min(open, close) - 1, close, volume: 1000 };
}
function renderChart(candles: StockHistoryCandle[] | null, props: Partial<ComponentProps<typeof KlineChart>> = {}) {
  window.localStorage.setItem('dsa.uiLanguage', 'en');
  return render(<UiLanguageProvider><KlineChart candles={candles} {...props} /></UiLanguageProvider>);
}
describe('KlineChart', () => {
  it('empty state', () => {
    renderChart(null);
    expect(screen.getByTestId('kline-chart-empty')).toBeInTheDocument();
    expect(screen.getByText('No candlestick data')).toBeInTheDocument();
  });
  it('filters dirty candles', () => {
    renderChart([
      candle(1, 10, 11),
      { date: '2026-01-02', open: Number.NaN, high: 12, low: 9, close: 11, volume: 1 },
      candle(3, 11, 10),
      { date: '2026-01-04', open: 10, high: Number.POSITIVE_INFINITY, low: 8, close: 9, volume: Number.NaN },
    ]);
    expect(screen.getByTestId('kline-chart-candle-0')).toBeInTheDocument();
    expect(screen.getByTestId('kline-chart-candle-2')).toBeInTheDocument();
    expect(screen.queryByTestId('kline-chart-candle-3')).not.toBeInTheDocument();
  });
  it('single candle', () => {
    renderChart([candle(1, 100, 101)]);
    expect(screen.getByTestId('kline-chart-canvas')).toHaveAttribute('role', 'img');
    expect(screen.getByTestId('kline-chart-legend')).toHaveTextContent('Up');
  });
  it('MA path', () => {
    renderChart(Array.from({ length: 12 }, (_, i) => candle(i + 1, 10 + i, 10.5 + i)), { maPeriods: [5] });
    expect(screen.getByTestId('kline-chart-ma5')).toBeInTheDocument();
  });
});
