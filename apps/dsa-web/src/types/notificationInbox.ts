// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

export type NotificationInboxKind =
  | 'analysis_complete'
  | 'alert_triggered'
  | 'scheduled_task_result'
  | 'decision_signal';

export type NotificationInboxSeverity = 'info' | 'warning' | 'error';

export type NotificationInboxItem = {
  id: string;
  kind: NotificationInboxKind;
  title: string;
  summary: string;
  severity: NotificationInboxSeverity;
  createdAt: string;
  isRead: boolean;
  href: string;
  sourceId: string;
  metadata?: Record<string, unknown>;
};

export type NotificationInboxPage = {
  items: NotificationInboxItem[];
  page: number;
  pageSize: number;
  total: number;
  unreadTotal: number;
  retentionDays: number;
  maxItems: number;
};

export type NotificationInboxUnreadCount = {
  unreadTotal: number;
  retentionDays: number;
  maxItems: number;
};

export type NotificationInboxMarkReadResult = {
  markedCount: number;
  unreadTotal: number;
};

export type NotificationInboxListQuery = {
  page?: number;
  pageSize?: number;
  kind?: NotificationInboxKind | '';
  unreadOnly?: boolean;
};
