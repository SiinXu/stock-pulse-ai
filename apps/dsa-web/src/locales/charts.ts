// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../i18n/uiText';

const zh = {
  klineEmptyTitle: '暂无 K 线数据',
  klineEmptyDescription: '提供有效的开高低收序列后即可渲染蜡烛图。',
  klineChartLabel: 'K 线图，共 {count} 根 K 线',
  klineSummary: '区间 {start} 至 {end}，收盘从 {first} 到 {last}，涨跌 {change}，最高 {high}，最低 {low}',
  klineLegendUp: '上涨',
  klineLegendDown: '下跌',
  klineLegendFlat: '平盘',
  klineVolume: '成交量',
  klineMa: 'MA{period}',
  klineZoomIn: '放大可见区间',
  klineZoomOut: '显示全部区间',
  klineZoomRange: '当前显示 {start} 至 {end}',
  klineOpen: '开',
  klineHigh: '高',
  klineLow: '低',
  klineClose: '收',
  riskEmptyTitle: '暂无风险热力数据',
  riskEmptyDescription: '提供行/列维度与风险分数后即可渲染热力图。',
  riskChartLabel: '风险热力图，{rows} 行 × {columns} 列',
  riskDimension: '标的',
  riskMissing: '缺失',
  riskScore: '风险分 {score}',
  riskLevelLow: '低',
  riskLevelMedium: '中',
  riskLevelHigh: '偏高',
  riskLevelCritical: '高',
  riskLegend: '风险分范围为 0–100：低 <25，中 25–49，偏高 50–74，高 75–100；缺失或无效值不参与分级。',
} as const;

const en: Record<keyof typeof zh, string> = {
  klineEmptyTitle: 'No candlestick data',
  klineEmptyDescription: 'Provide a valid open-high-low-close series to render the chart.',
  klineChartLabel: 'Candlestick chart with {count} bars',
  klineSummary: 'Range {start} to {end}, close {first} → {last}, change {change}, high {high}, low {low}',
  klineLegendUp: 'Up',
  klineLegendDown: 'Down',
  klineLegendFlat: 'Flat',
  klineVolume: 'Volume',
  klineMa: 'MA{period}',
  klineZoomIn: 'Zoom visible range',
  klineZoomOut: 'Show full range',
  klineZoomRange: 'Showing {start} to {end}',
  klineOpen: 'O',
  klineHigh: 'H',
  klineLow: 'L',
  klineClose: 'C',
  riskEmptyTitle: 'No risk heatmap data',
  riskEmptyDescription: 'Provide row/column dimensions and risk scores to render the heatmap.',
  riskChartLabel: 'Risk heatmap, {rows} rows × {columns} columns',
  riskDimension: 'Instrument',
  riskMissing: 'Missing',
  riskScore: 'Risk score {score}',
  riskLevelLow: 'Low',
  riskLevelMedium: 'Medium',
  riskLevelHigh: 'Elevated',
  riskLevelCritical: 'High',
  riskLegend: 'Risk scores use 0–100: Low <25, Medium 25–49, Elevated 50–74, High 75–100; missing or invalid values are unclassified.',
};

export const CHARTS_TEXT: Record<UiLanguage, Record<keyof typeof zh, string>> = createUiLanguageRecord(
  'locales.charts.CHARTS_TEXT',
  { zh, en },
);

export type ChartsText = (typeof CHARTS_TEXT)[UiLanguage];
