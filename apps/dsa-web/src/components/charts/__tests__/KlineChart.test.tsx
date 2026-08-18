// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ComponentProps } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  it('computes moving averages from full history before slicing the viewport', () => {
    renderChart(Array.from({ length: 25 }, (_, i) => candle(i + 1, 10 + i, 10.5 + i)), { maPeriods: [5] });
    fireEvent.change(screen.getByTestId('kline-chart-zoom'), { target: { value: '1' } });
    expect(screen.getByTestId('kline-chart-ma5').getAttribute('d')).toMatch(/^M99\.00 /);
  });
  it('exposes truthful date bounds, keeps five candles visible, and resets zoom for new data', async () => {
    const initial = Array.from({ length: 25 }, (_, i) => candle(i + 1, 10 + i, 10.5 + i));
    const rendered = renderChart(initial);
    const zoom = screen.getByTestId('kline-chart-zoom');
    expect(zoom).toHaveAttribute('max', '20');
    fireEvent.change(zoom, { target: { value: '20' } });
    expect(zoom).toHaveAttribute('aria-valuetext', 'Showing 2026-01-21 to 2026-01-25');

    const replacement = Array.from({ length: 22 }, (_, i) => candle(i + 1, 30 + i, 30.5 + i));
    rendered.rerender(
      <UiLanguageProvider initialLanguage="en"><KlineChart candles={replacement} /></UiLanguageProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('kline-chart-zoom')).toHaveValue('0'));
  });
  it('uses shared market-aware price and localized volume formatting', () => {
    renderChart([candle(1, 10, 11)], { market: 'hk' });
    expect(screen.getByTestId('kline-chart-readout')).toHaveTextContent('HKD 10.000');
    expect(screen.getByTestId('kline-chart-readout')).toHaveTextContent('1K');
  });
  it('guards non-finite chart height', () => {
    renderChart([candle(1, 10, 11)], { height: Number.POSITIVE_INFINITY });
    expect(screen.getByTestId('kline-chart-canvas').querySelector('svg')).toHaveAttribute('viewBox', '0 0 640 222');
  });
  it('paints CN rising/falling candles with price hue tokens, not status tokens', () => {
    renderChart([candle(1, 10, 11), candle(2, 11, 10)], { market: 'cn' });
    const upBody = screen.getByTestId('kline-chart-candle-0').querySelector('rect[fill]:not([fill="transparent"])');
    const downBody = screen.getByTestId('kline-chart-candle-1').querySelector('rect[fill]:not([fill="transparent"])');
    expect(upBody).toHaveAttribute('fill', 'var(--price-red)');
    expect(downBody).toHaveAttribute('fill', 'var(--price-green)');
    expect(upBody?.getAttribute('fill')).not.toContain('--danger');
    expect(downBody?.getAttribute('fill')).not.toContain('--success');
  });
  it('paints US rising/falling candles with the inverse price hues', () => {
    renderChart([candle(1, 10, 11), candle(2, 11, 10)], { market: 'us' });
    const upBody = screen.getByTestId('kline-chart-candle-0').querySelector('rect[fill]:not([fill="transparent"])');
    const downBody = screen.getByTestId('kline-chart-candle-1').querySelector('rect[fill]:not([fill="transparent"])');
    expect(upBody).toHaveAttribute('fill', 'var(--price-green)');
    expect(downBody).toHaveAttribute('fill', 'var(--price-red)');
  });
  it('honors red_up preference on a US market rising candle', () => {
    renderChart([candle(1, 10, 11)], { market: 'us', colorPreference: 'red_up' });
    expect(
      screen.getByTestId('kline-chart-candle-0').querySelector('rect[fill]:not([fill="transparent"])'),
    ).toHaveAttribute('fill', 'var(--price-red)');
  });
  it('honors green_up preference on a CN market rising candle', () => {
    renderChart([candle(1, 10, 11)], { market: 'cn', colorPreference: 'green_up' });
    expect(
      screen.getByTestId('kline-chart-candle-0').querySelector('rect[fill]:not([fill="transparent"])'),
    ).toHaveAttribute('fill', 'var(--price-green)');
  });
  it('uses the muted-foreground fallback for a flat candle', () => {
    renderChart([{ date: '2026-01-01', open: 10, high: 10, low: 10, close: 10, volume: 1 }], { market: 'cn' });
    expect(
      screen.getByTestId('kline-chart-candle-0').querySelector('rect[fill]:not([fill="transparent"])'),
    ).toHaveAttribute('fill', 'hsl(var(--muted-foreground))');
  });
});
