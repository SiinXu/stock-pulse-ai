// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';

export const NOTIFICATIONS_TEXT = createUiLanguageRecord('locales.notifications.NOTIFICATIONS_TEXT', {
  zh: {
    bellLabel: '通知',
    bellLabelWithUnread: '通知，{count} 条未读',
    signalsGroup: '信号',
    alertsGroup: '告警',
    viewAll: '查看全部',
    unavailable: '暂时无法加载通知',
    partialUnavailable: '部分通知暂时无法加载。',
    paletteTitle: '快速前往',
    paletteDescription: '搜索股票、报告、页面和操作',
    searchPlaceholder: '搜索股票、报告、页面或操作',
    pagesGroup: '页面',
    actionsGroup: '操作',
    reportsGroup: '报告',
    searchUnavailable: '报告搜索暂时不可用',
    runMarketReview: '运行大盘复盘',
    stocksGroup: '股票',
    noResults: '没有匹配的结果',
  },
  en: {
    bellLabel: 'Notifications',
    bellLabelWithUnread: 'Notifications, {count} unread',
    signalsGroup: 'Signals',
    alertsGroup: 'Alerts',
    viewAll: 'View all',
    unavailable: 'Notifications are temporarily unavailable',
    partialUnavailable: 'Some notifications are temporarily unavailable.',
    paletteTitle: 'Quick access',
    paletteDescription: 'Search stocks, reports, pages, and actions',
    searchPlaceholder: 'Search stocks, reports, pages, or actions',
    pagesGroup: 'Pages',
    actionsGroup: 'Actions',
    reportsGroup: 'Reports',
    searchUnavailable: 'Report search is temporarily unavailable',
    runMarketReview: 'Run market review',
    stocksGroup: 'Stocks',
    noResults: 'No matching results',
  },
} as const);
