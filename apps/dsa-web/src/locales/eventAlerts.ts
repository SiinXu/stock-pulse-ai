// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import type { CorporateEventCategory } from '../types/eventAlerts';

export const EVENT_ALERT_PAGE_TEXT = createUiLanguageRecord('locales.eventAlerts.EVENT_ALERT_PAGE_TEXT', {
  zh: {
    documentTitle: '事件告警 - StockPulse', title: '事件驱动告警',
    description: '查看已触发的企业事件告警，包括事件分类、为何重要与影响上下文。说明文案由后端生成，前端仅展示。',
    subtitle: '{count} 条事件告警', refresh: '刷新', loading: '正在加载事件告警', loadErrorTitle: '加载失败',
    emptyTitle: '暂无事件告警', emptyDescription: '当 corporate_event 规则匹配托管情报项后，触发记录会显示在这里。',
    listTitle: '告警列表', detailTitle: '告警详情', selectPrompt: '从左侧选择一条告警以查看详情。',
    whatHappened: '发生了什么', whyItMatters: '为何重要', impactContext: '影响上下文', eventCategory: '事件类型',
    relatedSymbol: '关联标的', relatedAnalysis: '相关分析', affectedScope: '影响范围', inWatchlist: '在自选中',
    inPortfolio: '在持仓中', notInHoldingsOrWatchlist: '不在持仓/自选中', weight: '持仓权重约 {value}%',
    degradedNote: '上下文部分降级（托管数据不完整）', matchedCount: '匹配条目：{count}', triggeredAt: '触发时间',
    status: '状态', gradeMajor: '重大', gradeRoutine: '常规', noWhyProvided: '后端未提供「为何重要」说明。',
    noWhatProvided: '后端未提供事件摘要。', filterAll: '全部等级', filterMajor: '仅重大', filterRoutine: '仅常规',
  },
  en: {
    documentTitle: 'Event alerts - StockPulse', title: 'Event-driven alerts',
    description: 'Review fired corporate-event alerts with category, why-it-matters, and impact context. Explanation text is backend-owned; the Web layer only renders it.',
    subtitle: '{count} event alerts', refresh: 'Refresh', loading: 'Loading event alerts', loadErrorTitle: 'Failed to load',
    emptyTitle: 'No event alerts', emptyDescription: 'When corporate_event rules match managed intelligence items, triggers appear here.',
    listTitle: 'Alert list', detailTitle: 'Alert detail', selectPrompt: 'Select an alert on the left to inspect details.',
    whatHappened: 'What happened', whyItMatters: 'Why it matters', impactContext: 'Impact context', eventCategory: 'Event type',
    relatedSymbol: 'Symbol', relatedAnalysis: 'Related analysis', affectedScope: 'Affected', inWatchlist: 'On watchlist',
    inPortfolio: 'In holdings', notInHoldingsOrWatchlist: 'Not in holdings/watchlist', weight: 'Holding weight ~{value}%',
    degradedNote: 'Partial context (managed data incomplete)', matchedCount: 'Matched items: {count}', triggeredAt: 'Triggered at',
    status: 'Status', gradeMajor: 'Major', gradeRoutine: 'Routine', noWhyProvided: 'Backend did not provide a why-it-matters explanation.',
    noWhatProvided: 'Backend did not provide an event summary.', filterAll: 'All grades', filterMajor: 'Major only', filterRoutine: 'Routine only',
  },
} as const);

export const EVENT_CATEGORY_LABELS = createUiLanguageRecord('locales.eventAlerts.EVENT_CATEGORY_LABELS', {
  zh: { earnings: '业绩/财报', shareholder: '股东变动', mna: '并购重组', regulatory: '监管合规', analyst: '分析师评级' } satisfies Record<CorporateEventCategory, string>,
  en: { earnings: 'Earnings', shareholder: 'Shareholder', mna: 'M&A', regulatory: 'Regulatory', analyst: 'Analyst' } satisfies Record<CorporateEventCategory, string>,
});
