// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';

export const PERSONAL_PERFORMANCE_TEXT = createUiLanguageRecord(
  'locales.personalPerformance.PERSONAL_PERFORMANCE_TEXT',
  {
    zh: {
      documentTitle: '个人表现（过程分）- StockPulse',
      title: '个人表现 · 过程质量',
      description:
        '对模拟盘操作打过程分：分析支撑、风险门遵守、仓位纪律。这不是收益/胜率评价；结果指标由 DecisionSignal 后验校准（#987）负责。',
      processOnlyBadge: '过程分 · 非收益',
      refresh: '刷新',
      refreshAria: '刷新模拟盘过程质量分',
      selectAccount: '选择模拟盘账户',
      noPaperAccountsTitle: '没有模拟盘账户',
      noPaperAccountsDescription:
        '请先在组合页创建 paper 账户并记录模拟成交，再查看过程质量分。',
      openPortfolio: '打开组合',
      emptyTradesTitle: '暂无模拟成交',
      emptyTradesDescription: '记录 paper 买卖后，将在此显示可追溯的过程分明细。',
      aggregateTitle: '已评分成交样本',
      sampleSize: '已评分 {count} / 共 {total} 笔成交',
      formulaVersion: '公式 {version}',
      dimAnalysis: '分析支撑',
      dimRiskGate: '风险门',
      dimPosition: '仓位纪律',
      tradeListTitle: '成交过程明细',
      colTrade: '成交',
      colSide: '方向',
      colDate: '日期',
      colScore: '过程分',
      colSignal: '关联信号',
      colReasons: '原因',
      noSignal: '无',
      outcomePlaceholderTitle: '结果指标（#987）',
      outcomePlaceholderDescription:
        '胜率、实现收益与风格校准由 DecisionSignal 后验校准看板负责，本页不重复实现，避免与 #987 重叠。',
      disclaimer:
        '过程分仅反映决策纪律，不构成投资建议，也不表示历史或未来收益。',
      loadErrorTitle: '加载过程分失败',
      realAccountHint: '当前账户不是模拟盘；过程分仅适用于 paper 账户。',
    },
    en: {
      documentTitle: 'Personal performance (process) - StockPulse',
      title: 'Personal performance · process quality',
      description:
        'Score paper trades on process: analysis support, risk-gate compliance, and position discipline. This is not a return/win-rate evaluation; outcome metrics are owned by DecisionSignal post-hoc calibration (#987).',
      processOnlyBadge: 'Process · not return',
      refresh: 'Refresh',
      refreshAria: 'Refresh paper decision process quality',
      selectAccount: 'Paper account',
      noPaperAccountsTitle: 'No paper accounts',
      noPaperAccountsDescription:
        'Create a paper portfolio and record simulated trades on the Portfolio page first.',
      openPortfolio: 'Open portfolio',
      emptyTradesTitle: 'No paper trades yet',
      emptyTradesDescription:
        'Record paper buys/sells to see explainable process scores here.',
      aggregateTitle: 'Scored trade sample',
      sampleSize: 'Scored {count} of {total} trades',
      formulaVersion: 'Formula {version}',
      dimAnalysis: 'Analysis support',
      dimRiskGate: 'Risk gate',
      dimPosition: 'Position discipline',
      tradeListTitle: 'Trade process breakdown',
      colTrade: 'Trade',
      colSide: 'Side',
      colDate: 'Date',
      colScore: 'Process score',
      colSignal: 'Linked signal',
      colReasons: 'Reasons',
      noSignal: 'None',
      outcomePlaceholderTitle: 'Outcome metrics (#987)',
      outcomePlaceholderDescription:
        'Win rate, realized return, and style calibration remain owned by the DecisionSignal post-hoc dashboard. This page intentionally does not reimplement them.',
      disclaimer:
        'Process scores reflect decision discipline only. They are not investment advice and do not imply historical or future returns.',
      loadErrorTitle: 'Failed to load process scores',
      realAccountHint: 'Process scores apply only to paper accounts.',
    },
  },
);
