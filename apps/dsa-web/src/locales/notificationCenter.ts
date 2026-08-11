// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import { formatUiText } from '../i18n/uiText';
import type { NotificationInboxItem } from '../types/notificationInbox';

export const NOTIFICATION_CENTER_TEXT = createUiLanguageRecord(
  'locales.notificationCenter.NOTIFICATION_CENTER_TEXT',
  {
    zh: {
      title: '通知中心',
      description: '聚合分析完成、告警触发、调度任务结果与决策信号，便于稍后回看。',
      refresh: '刷新',
      markAllRead: '全部标为已读',
      markRead: '标为已读',
      filterAll: '全部',
      filterUnread: '仅未读',
      kindAll: '全部类型',
      kindAnalysis: '分析完成',
      kindAlert: '告警触发',
      kindScheduled: '调度任务',
      kindSignal: '决策信号',
      emptyTitle: '暂无通知',
      emptyDescription: '完成分析、触发告警或调度任务后，相关事件会出现在这里。',
      emptyFilteredTitle: '没有匹配的通知',
      emptyFilteredDescription: '试试调整类型或已读筛选。',
      unreadBadge: '{count} 条未读',
      retentionHint: '默认保留 {days} 天，最多聚合 {max} 条。',
      loadError: '无法加载通知中心',
      open: '打开',
      read: '已读',
      unread: '未读',
      loadMore: '加载更多',
    },
    en: {
      title: 'Notification Center',
      description: 'Aggregate completed analyses, alert triggers, scheduled task results, and decision signals for later review.',
      refresh: 'Refresh',
      markAllRead: 'Mark all read',
      markRead: 'Mark read',
      filterAll: 'All',
      filterUnread: 'Unread only',
      kindAll: 'All types',
      kindAnalysis: 'Analysis complete',
      kindAlert: 'Alert triggered',
      kindScheduled: 'Scheduled task',
      kindSignal: 'Decision signal',
      emptyTitle: 'No notifications yet',
      emptyDescription: 'When analyses finish, alerts fire, or scheduled tasks complete, they will appear here.',
      emptyFilteredTitle: 'No matching notifications',
      emptyFilteredDescription: 'Try adjusting the type or read filter.',
      unreadBadge: '{count} unread',
      retentionHint: 'Default retention {days} days, up to {max} aggregated items.',
      loadError: 'Unable to load the notification center',
      open: 'Open',
      read: 'Read',
      unread: 'Unread',
      loadMore: 'Load more',
    },
  } as const,
);

type NotificationCenterText = (typeof NOTIFICATION_CENTER_TEXT)[keyof typeof NOTIFICATION_CENTER_TEXT];

export function formatNotificationInboxTitle(
  item: Pick<NotificationInboxItem, 'titleKey' | 'titleParams'>,
  text: NotificationCenterText,
): string {
  if (item.titleKey === 'analysisCompleteTitle') {
    return formatUiText(`${text.kindAnalysis}: {label}`, item.titleParams);
  }
  if (item.titleKey === 'alertTriggeredTitle') {
    return formatUiText(`${text.kindAlert}: {target}`, item.titleParams);
  }
  if (item.titleKey === 'scheduledTaskResultTitle') {
    return formatUiText(`${text.kindScheduled}: {taskId}`, item.titleParams);
  }
  return formatUiText(`${text.kindSignal}: {label}`, item.titleParams);
}
