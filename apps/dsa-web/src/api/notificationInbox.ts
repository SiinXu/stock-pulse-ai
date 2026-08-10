// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import type {
  NotificationInboxListQuery,
  NotificationInboxMarkReadResult,
  NotificationInboxPage,
  NotificationInboxUnreadCount,
} from '../types/notificationInbox';
import apiClient from './index';
import { createApiError, createParsedApiError } from './error';
import { toCamelCase } from './utils';

const itemSchema = z.object({
  id: z.string(),
  kind: z.string(),
  titleKey: z.string(),
  titleParams: z.record(z.string(), z.string()),
  summary: z.string(),
  severity: z.string(),
  createdAt: z.string(),
  isRead: z.boolean(),
  href: z.string(),
  sourceId: z.string(),
  metadata: z.record(z.string(), z.unknown()).optional(),
}).passthrough();

const pageSchema = z.object({
  items: z.array(itemSchema),
  page: z.number(),
  pageSize: z.number(),
  total: z.number(),
  unreadTotal: z.number(),
  cursor: z.string().nullable().optional(),
  nextCursor: z.string().nullable().optional(),
  hasMore: z.boolean(),
  sourceStatuses: z.array(z.object({
    source: z.string(),
    available: z.boolean(),
    itemCount: z.number(),
    errorCode: z.string().nullable().optional(),
  }).passthrough()),
  retentionDays: z.number(),
  maxItems: z.number(),
}).passthrough();

const unreadSchema = z.object({
  unreadTotal: z.number(),
  sourceStatuses: z.array(z.object({
    source: z.string(),
    available: z.boolean(),
    itemCount: z.number(),
    errorCode: z.string().nullable().optional(),
  }).passthrough()),
  retentionDays: z.number(),
  maxItems: z.number(),
}).passthrough();

const markSchema = z.object({
  markedCount: z.number(),
  unreadTotal: z.number(),
}).passthrough();

function parseCamelCasePayload<T>(data: unknown, schema: z.ZodTypeAny, label: string): T {
  const camel = toCamelCase<unknown>(data);
  const result = schema.safeParse(camel);
  if (!result.success) {
    const issueSummary = result.error.issues
      .slice(0, 5)
      .map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`)
      .join('; ');
    throw createApiError(createParsedApiError({
      title: '响应校验失败',
      message: `接口响应未通过校验（${label}）。${issueSummary}`,
      rawMessage: result.error.message,
      category: 'unknown',
      code: 'api_response_validation_failed',
      params: { label, issues: issueSummary },
      details: result.error.issues,
    }));
  }
  return camel as T;
}

export const notificationInboxApi = {
  async list(query: NotificationInboxListQuery = {}): Promise<NotificationInboxPage> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/notification-inbox/items', {
      params: {
        ...(query.page === undefined ? {} : { page: query.page }),
        ...(query.pageSize === undefined ? {} : { page_size: query.pageSize }),
        ...(query.cursor ? { cursor: query.cursor } : {}),
        ...(query.kind ? { kind: query.kind } : {}),
        ...(query.unreadOnly ? { unread_only: true } : {}),
      },
    });
    return parseCamelCasePayload<NotificationInboxPage>(response.data, pageSchema, 'NotificationInboxPage');
  },

  async unreadCount(kind?: string): Promise<NotificationInboxUnreadCount> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/notification-inbox/unread-count',
      { params: kind ? { kind } : {} },
    );
    return parseCamelCasePayload<NotificationInboxUnreadCount>(
      response.data,
      unreadSchema,
      'NotificationInboxUnreadCount',
    );
  },

  async markRead(itemIds: string[]): Promise<NotificationInboxMarkReadResult> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/notification-inbox/items/mark-read',
      { item_ids: itemIds },
    );
    return parseCamelCasePayload<NotificationInboxMarkReadResult>(
      response.data,
      markSchema,
      'NotificationInboxMarkReadResult',
    );
  },

  async markAllRead(kind?: string): Promise<NotificationInboxMarkReadResult> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/notification-inbox/items/mark-all-read',
      kind ? { kind } : {},
    );
    return parseCamelCasePayload<NotificationInboxMarkReadResult>(
      response.data,
      markSchema,
      'NotificationInboxMarkAllReadResult',
    );
  },
};
