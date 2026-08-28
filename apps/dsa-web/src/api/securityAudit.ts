// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import type { SecurityAuditEventPage, SecurityAuditListQuery } from '../types/securityAudit';
import apiClient from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { components } from '../types/api.generated';

type OpenApiSecurityAuditEventPage = components['schemas']['SecurityAuditEventPage'];
type OpenApiSecurityAuditEvent = components['schemas']['SecurityAuditEvent'];
type _AssertPage = keyof OpenApiSecurityAuditEventPage;
type _AssertEvent = keyof OpenApiSecurityAuditEvent;
const _pageAnchor: _AssertPage = 'page_size';
const _eventAnchor: _AssertEvent = 'event_type';
void _pageAnchor;
void _eventAnchor;

const securityAuditActorSchema = z.object({ type: z.string(), id: z.string() }).passthrough();
const securityAuditTargetSchema = z.object({ type: z.string(), id: z.string() }).passthrough();

const securityAuditEventSchema = z.object({
  id: z.number(),
  schemaVersion: z.string().optional(),
  occurredAt: z.string().optional(),
  eventType: z.string(),
  phase: z.string(),
  actor: securityAuditActorSchema,
  executionId: z.string(),
  action: z.string(),
  target: securityAuditTargetSchema,
  outcome: z.string(),
  reasonCode: z.string(),
  correlationId: z.string(),
  metadata: z.record(z.string(), z.unknown()).optional(),
}).passthrough();

const securityAuditEventPageSchema = z.object({
  items: z.array(securityAuditEventSchema),
  page: z.number(),
  pageSize: z.number(),
  total: z.number(),
}).passthrough();

export const securityAuditApi = {
  async list(query: SecurityAuditListQuery = {}): Promise<SecurityAuditEventPage> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/security/audit-events', {
      params: {
        ...(query.page === undefined ? {} : { page: query.page }),
        ...(query.pageSize === undefined ? {} : { page_size: query.pageSize }),
        ...(query.eventType ? { event_type: query.eventType } : {}),
        ...(query.outcome ? { outcome: query.outcome } : {}),
        ...(query.correlationId ? { correlation_id: query.correlationId } : {}),
        ...(query.occurredFrom ? { occurred_from: query.occurredFrom } : {}),
        ...(query.occurredTo ? { occurred_to: query.occurredTo } : {}),
      },
    });
    return parseCamelCasePayload<SecurityAuditEventPage>(
      response.data,
      securityAuditEventPageSchema,
      'SecurityAuditEventPage',
      'securityAudit',
    );
  },
};
