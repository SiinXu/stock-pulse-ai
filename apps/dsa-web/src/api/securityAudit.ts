// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type {
  SecurityAuditEventPage,
  SecurityAuditListQuery,
} from '../types/securityAudit';
import apiClient from './index';
import { toCamelCase } from './utils';

/**
 * Read-only client for Phase 1 durable security audit events.
 * Payloads are already redacted server-side; this client does not mutate events.
 */
export const securityAuditApi = {
  async list(query: SecurityAuditListQuery = {}): Promise<SecurityAuditEventPage> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/security/audit-events',
      {
        params: {
          ...(query.page === undefined ? {} : { page: query.page }),
          ...(query.pageSize === undefined ? {} : { page_size: query.pageSize }),
          ...(query.eventType ? { event_type: query.eventType } : {}),
          ...(query.outcome ? { outcome: query.outcome } : {}),
          ...(query.correlationId ? { correlation_id: query.correlationId } : {}),
          ...(query.occurredFrom ? { occurred_from: query.occurredFrom } : {}),
          ...(query.occurredTo ? { occurred_to: query.occurredTo } : {}),
        },
      },
    );
    return toCamelCase<SecurityAuditEventPage>(response.data);
  },
};
