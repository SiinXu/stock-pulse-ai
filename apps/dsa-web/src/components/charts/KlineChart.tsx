// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo, useState } from 'react';
import { EmptyState, Surface } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { CHARTS_TEXT } from '../../locales/charts';
import type { StockHistoryCandle } from '../../types/stocks';
import { changeSemantics, type ChangeColorPreference, type MarketId } from '../../utils/marketFormat';
import { cn } from '../../utils/cn';
import {
  changeColorToCss, computeMovingAverages, directionMarker, directionWord,
  priceExtent, sanitizeCandles, summarizeCandleSeries, volumeExtent, type ChartCandle,
} from './chartUtils';

const DEFAULT_MA_PERIODS = [5, 10, 20] as const;
const MA_STROKES = ['hsl(var(--primary))', 'hsl(var(--warning))', 'hsl(var(--color-purple))'] as const;

export type KlineChartProps = {
  candles: readonly StockHistoryCandle[] | null | undefined;
  market?: MarketId;
  colorPreference?: ChangeColorPreference | null;
  height?: number;
  showVolume?: boolean;
  maPeriods?: readonly number[];
  className?: string;
  'data-testid'?: string;
};

function formatPrice(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—';
  const abs = Math.abs(value);
  return value.toFixed(abs >= 1 ? 2 : 4);
}
function formatChangePct(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
}
function formatVolume(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—';
  if (value >= 1e8) return `${(value / 1e8).toFixed(2)}e8`;
  if (value >= 1e4) return `${(value / 1e4).toFixed(1)}e4`;
  return String(Math.round(value));
}
function buildMaPath(
  candles: readonly ChartCandle[], values: readonly (number | null)[],
  xAt: (i: number) => number, yAt: (p: number) => number,
): string {
  let path = '', drawing = false;
  for (let i = 0; i < candles.length; i += 1) {
    const v = values[i];
    if (v === null || !Number.isFinite(v)) { drawing = false; continue; }
    path += `${drawing ? 'L' : 'M'}${xAt(i).toFixed(2)} ${yAt(v).toFixed(2)} `;
    drawing = true;
  }
  return path.trim();
}

export const KlineChart: React.FC<KlineChartProps> = ({
  candles, market = 'cn', colorPreference = null, height = 320,
  showVolume = true, maPeriods = DEFAULT_MA_PERIODS, className,
  'data-testid': testId = 'kline-chart',
}) => {
  const { language } = useUiLanguage();
  const text = CHARTS_TEXT[language];
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [windowStart, setWindowStart] = useState(0);
  const sanitized = useMemo(() => sanitizeCandles(candles, market, colorPreference), [candles, market, colorPreference]);
  const maxStart = Math.max(0, sanitized.length - 1);
  const clampedStart = Math.min(Math.max(0, windowStart), maxStart);
  const visible = useMemo(() => (sanitized.length === 0 ? [] : sanitized.slice(clampedStart)), [sanitized, clampedStart]);
  const maSeries = useMemo(() => computeMovingAverages(visible, maPeriods), [visible, maPeriods]);
  const summary = useMemo(() => summarizeCandleSeries(visible, formatChangePct), [visible]);

  if (sanitized.length === 0) {
    return <EmptyState data-testid={`${testId}-empty`} title={text.klineEmptyTitle} description={text.klineEmptyDescription} className={className} />;
  }

  const volumeHeight = showVolume ? Math.round(height * 0.28) : 0;
  const priceHeight = height - volumeHeight - (showVolume ? 8 : 0);
  const width = 640, padLeft = 8, padRight = 8, padTop = 12, padBottom = 20;
  const plotWidth = width - padLeft - padRight;
  const plotHeight = priceHeight - padTop - padBottom;
  const extent = priceExtent(visible);
  const volExtent = volumeExtent(visible);
  const count = visible.length;
  const slot = plotWidth / Math.max(count, 1);
  const bodyWidth = Math.max(2, Math.min(14, slot * 0.62));
  const xAt = (i: number) => padLeft + slot * i + slot / 2;
  const yAt = (price: number) => padTop + plotHeight * (1 - (price - extent.min) / (extent.max - extent.min || 1));
  const volYAt = (volume: number) => volumeHeight - Math.max(1, (volume / (volExtent.max || 1)) * (volumeHeight - 4));
  const activeIndex = hoverIndex !== null && hoverIndex >= 0 && hoverIndex < count ? hoverIndex : count - 1;
  const active = visible[activeIndex];
  const ariaLabel = formatUiText(text.klineChartLabel, { count: String(summary.count) });
  const summaryText = formatUiText(text.klineSummary, {
    start: visible[0]?.date ?? '—', end: visible[count - 1]?.date ?? '—',
    first: formatPrice(summary.firstClose), last: formatPrice(summary.lastClose),
    change: summary.changeText, high: formatPrice(summary.high), low: formatPrice(summary.low),
  });
  const directionLabels = { up: text.klineLegendUp, down: text.klineLegendDown, flat: text.klineLegendFlat };
  const upPaint = changeColorToCss(changeSemantics(1, market, colorPreference).color);
  const downPaint = changeColorToCss(changeSemantics(-1, market, colorPreference).color);

  return (
    <Surface level="section" padding="sm" className={cn('flex flex-col gap-2', className)} data-testid={testId}>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-text">
        <div className="flex flex-wrap items-center gap-3" data-testid={`${testId}-legend`}>
          <span className="inline-flex items-center gap-1">
            <span aria-hidden="true" style={{ color: upPaint }}>{directionMarker('up')}</span>
            <span>{text.klineLegendUp}</span>
            <span className="text-muted-text">/</span>
            <span aria-hidden="true" style={{ color: downPaint }}>{directionMarker('down')}</span>
            <span>{text.klineLegendDown}</span>
          </span>
          {maPeriods.filter((p) => Number.isInteger(p) && p >= 1).map((period, index) => (
            <span key={period} className="inline-flex items-center gap-1">
              <span className="inline-block h-0.5 w-3 rounded" style={{ background: MA_STROKES[index % MA_STROKES.length] }} aria-hidden="true" />
              {formatUiText(text.klineMa, { period: String(period) })}
            </span>
          ))}
        </div>
        {sanitized.length > 20 && (
          <div className="flex items-center gap-2">
            <label className="inline-flex items-center gap-1">
              <span className="sr-only">{text.klineZoomIn}</span>
              <input type="range" min={0} max={maxStart} value={clampedStart}
                onChange={(e) => setWindowStart(Number(e.target.value))}
                aria-label={text.klineZoomIn} data-testid={`${testId}-zoom`}
                className="h-1.5 w-28 accent-[hsl(var(--primary))]" />
            </label>
            <button type="button" className="rounded border border-border px-1.5 py-0.5 text-[11px] text-foreground hover:bg-hover"
              onClick={() => setWindowStart(0)} data-testid={`${testId}-zoom-reset`}>{text.klineZoomOut}</button>
          </div>
        )}
      </div>
      <div className="rounded-lg border border-border bg-card px-2 py-1 text-xs text-foreground" data-testid={`${testId}-readout`}>
        <span className="font-mono text-muted-text">{active.date}</span>
        {' · '}
        <span aria-hidden="true" style={{ color: changeColorToCss(active.color) }}>{directionMarker(active.direction)}</span>
        {' '}<span className="sr-only">{directionWord(active.direction, directionLabels)}</span>
        <span>{text.klineOpen} {formatPrice(active.open)}</span>{' '}
        <span>{text.klineHigh} {formatPrice(active.high)}</span>{' '}
        <span>{text.klineLow} {formatPrice(active.low)}</span>{' '}
        <span>{text.klineClose} {formatPrice(active.close)}</span>
        {showVolume && <>{' · '}<span>{text.klineVolume} {formatVolume(active.volume)}</span></>}
      </div>
      <div role="img" aria-label={`${ariaLabel}. ${summaryText}`} className="w-full" data-testid={`${testId}-canvas`}>
        <svg viewBox={`0 0 ${width} ${priceHeight}`} className="h-auto w-full" preserveAspectRatio="none" onMouseLeave={() => setHoverIndex(null)}>
          {[0.25, 0.5, 0.75].map((ratio) => {
            const y = padTop + plotHeight * ratio;
            return <line key={ratio} x1={padLeft} x2={width - padRight} y1={y} y2={y} stroke="hsl(var(--border))" strokeDasharray="3 3" />;
          })}
          {visible.map((candle, index) => {
            const cx = xAt(index);
            const yHigh = yAt(candle.high), yLow = yAt(candle.low);
            const yOpen = yAt(candle.open), yClose = yAt(candle.close);
            const bodyTop = Math.min(yOpen, yClose), bodyBottom = Math.max(yOpen, yClose);
            const bodyH = Math.max(1, bodyBottom - bodyTop);
            const stroke = changeColorToCss(candle.color);
            return (
              <g key={`${candle.date}-${index}`} data-testid={`${testId}-candle-${index}`}
                onMouseEnter={() => setHoverIndex(index)} onFocus={() => setHoverIndex(index)}>
                <rect x={cx - slot / 2} y={padTop} width={slot} height={plotHeight} fill="transparent" />
                <line x1={cx} x2={cx} y1={yHigh} y2={yLow} stroke={stroke} strokeWidth={index === activeIndex ? 1.5 : 1} />
                <rect x={cx - bodyWidth / 2} y={bodyTop} width={bodyWidth} height={bodyH}
                  fill={stroke} stroke={stroke} strokeWidth={1.25} opacity={candle.direction === 'flat' ? 0.55 : 0.92} />
              </g>
            );
          })}
          {Object.entries(maSeries).map(([key, values], seriesIndex) => {
            const path = buildMaPath(visible, values, xAt, yAt);
            if (!path) return null;
            return <path key={key} d={path} fill="none" stroke={MA_STROKES[seriesIndex % MA_STROKES.length]}
              strokeWidth={1.25} strokeLinejoin="round" strokeLinecap="round" data-testid={`${testId}-${key}`} />;
          })}
          {[0, Math.floor((count - 1) / 2), count - 1]
            .filter((v, i, a) => a.indexOf(v) === i && v >= 0 && v < count)
            .map((index) => (
              <text key={`label-${index}`} x={xAt(index)} y={priceHeight - 4} textAnchor="middle"
                className="fill-[hsl(var(--muted-text))]" fontSize={10}>{visible[index].date}</text>
            ))}
        </svg>
        {showVolume && (
          <svg viewBox={`0 0 ${width} ${volumeHeight}`} className="mt-1 h-auto w-full" preserveAspectRatio="none"
            aria-hidden="true" data-testid={`${testId}-volume`}>
            {visible.map((candle, index) => {
              if (candle.volume === null) return null;
              const cx = xAt(index);
              return (
                <rect key={`vol-${candle.date}-${index}`} x={cx - bodyWidth / 2} y={volYAt(candle.volume)}
                  width={bodyWidth} height={Math.max(1, volumeHeight - volYAt(candle.volume))}
                  fill={changeColorToCss(candle.color)} opacity={0.55} onMouseEnter={() => setHoverIndex(index)} />
              );
            })}
            <text x={padLeft} y={12} className="fill-[hsl(var(--muted-text))]" fontSize={10}>{text.klineVolume}</text>
          </svg>
        )}
      </div>
      <p className="sr-only" data-testid={`${testId}-summary`}>{summaryText}</p>
    </Surface>
  );
};
KlineChart.displayName = 'KlineChart';
