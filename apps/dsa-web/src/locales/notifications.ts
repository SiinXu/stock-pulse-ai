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
    paletteDescription: '搜索页面、操作和股票',
    searchPlaceholder: '搜索页面或操作',
    pagesGroup: '页面',
    actionsGroup: '操作',
    runMarketReview: '运行大盘复盘',
    stocksGroup: '股票',
    noResults: '没有匹配的页面或操作',
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
    paletteDescription: 'Search pages, actions, and stocks',
    searchPlaceholder: 'Search pages or actions',
    pagesGroup: 'Pages',
    actionsGroup: 'Actions',
    runMarketReview: 'Run market review',
    stocksGroup: 'Stocks',
    noResults: 'No matching pages or actions',
  },
} as const);
