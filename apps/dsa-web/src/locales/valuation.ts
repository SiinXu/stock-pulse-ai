// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiLanguage } from '../i18n/uiText';

const zh = {
  title: 'DCF 敏感性',
  description: '消费服务端 growth×discount 敏感性表；假设可见且可调。模型估算不是投资建议。',
  stockCode: '股票代码',
  stockCodePlaceholder: '如 600519 / AAPL',
  assumptions: '关键假设',
  growthRate: '增长率',
  discountRate: '折现率',
  terminalGrowth: '永续增长率',
  projectionYears: '预测年数',
  recompute: '按假设重估',
  recomputing: '重估中…',
  equityValue: '股权价值',
  intrinsicPerShare: '每股内在价值',
  sensitivityTable: '敏感性矩阵（股权价值）',
  growthAxis: '增长率 →',
  discountAxis: '折现率 ↓',
  rangeLow: '低',
  rangeMid: '中',
  rangeHigh: '高',
  emptyTitle: '暂无估值敏感性数据',
  emptyDescription: '缺少 DCF 敏感性行时不展示热力表。可调整假设后重估，或等待基本面可用。',
  insufficientTitle: '基本面不足',
  insufficientDescription: '现金流或假设不足时不会编造估值数字。',
  disclaimer: '模型估算仅供研究参考，不是投资建议；结论对假设高度敏感。',
  status: '状态',
  baseCase: '基准情景',
  percentHint: '小数，如 0.05 表示 5%',
  loadFailed: '估值请求失败',
  noEstimate: '未提供估值结果',
} as const;

const en = {
  title: 'DCF sensitivity',
  description:
    'Consumes the server-side growth×discount sensitivity table. Assumptions are visible and adjustable. Model estimate is not investment advice.',
  stockCode: 'Stock code',
  stockCodePlaceholder: 'e.g. 600519 / AAPL',
  assumptions: 'Key assumptions',
  growthRate: 'Growth rate',
  discountRate: 'Discount rate',
  terminalGrowth: 'Terminal growth',
  projectionYears: 'Projection years',
  recompute: 'Re-estimate with assumptions',
  recomputing: 'Re-estimating…',
  equityValue: 'Equity value',
  intrinsicPerShare: 'Intrinsic value / share',
  sensitivityTable: 'Sensitivity matrix (equity value)',
  growthAxis: 'Growth →',
  discountAxis: 'Discount ↓',
  rangeLow: 'Low',
  rangeMid: 'Mid',
  rangeHigh: 'High',
  emptyTitle: 'No sensitivity data',
  emptyDescription:
    'The heat table is omitted when DCF sensitivity rows are missing. Adjust assumptions and re-estimate, or wait until fundamentals are available.',
  insufficientTitle: 'Insufficient fundamentals',
  insufficientDescription: 'Missing cash flow or assumptions never produce fabricated valuation numbers.',
  disclaimer:
    'Model estimate for research support only. Not investment advice; highly sensitive to assumptions.',
  status: 'Status',
  baseCase: 'Base case',
  percentHint: 'Decimal, e.g. 0.05 means 5%',
  loadFailed: 'Valuation request failed',
  noEstimate: 'No valuation estimate provided',
} as const;

export type ValuationText = { readonly [Key in keyof typeof en]: string };

/** Bilingual copy for the DCF sensitivity panel (zh source + en; other UI langs fall back to en). */
export const VALUATION_TEXT: Record<UiLanguage, ValuationText> = {
  zh,
  en,
  'zh-TW': zh,
  ja: en,
  ko: en,
  de: en,
  es: en,
  ms: en,
  fr: en,
  id: en,
};
