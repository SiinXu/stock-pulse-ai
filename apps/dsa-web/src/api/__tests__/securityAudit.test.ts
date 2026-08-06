// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { securityAuditApi } from '../securityAudit';
import { getParsedApiError, isApiRequestError } from '../error';

const { get } = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock('../index', () => ({
  default: { get },
}));

describe('securityAuditApi', () => {
  beforeEach(() => {
    get.mockReset();
  });

  it('lists audit events with snake_case query params and camel-cases the page', async () => {
    get.mockResolvedValueOnce({
      data: {
        items: [{
          id: 7,
          schema_version: 'security-audit-v1',
          occurred_at: '2026-07-24T12:00:00Z',
          event_type: 'auth.login',
          phase: 'completion',
          actor: { type: 'admin', id: 'local_admin' },
          execution_id: 'exec-1',
          action: 'login',
          target: { type: 'session', id: 'web' },
          outcome: 'success',
          reason_code: 'authenticated',
          correlation_id: '0123456789abcdef0123456789abcdef',
          metadata: { key_sample: ['AUTH_ENABLED'] },
        }],
        page: 2,
        page_size: 25,
        total: 51,
      },
    });

    const page = await securityAuditApi.list({
      page: 2,
      pageSize: 25,
      eventType: 'auth.login',
      outcome: 'success',
      correlationId: '0123456789abcdef0123456789abcdef',
      occurredFrom: '2026-07-01T00:00:00Z',
      occurredTo: '2026-07-24T23:59:59Z',
    });

    expect(get).toHaveBeenCalledWith('/api/v1/security/audit-events', {
      params: {
        page: 2,
        page_size: 25,
        event_type: 'auth.login',
        outcome: 'success',
        correlation_id: '0123456789abcdef0123456789abcdef',
        occurred_from: '2026-07-01T00:00:00Z',
        occurred_to: '2026-07-24T23:59:59Z',
      },
    });
    expect(page).toMatchObject({
      page: 2,
      pageSize: 25,
      total: 51,
    });
    expect(page.items[0]).toMatchObject({
      id: 7,
      schemaVersion: 'security-audit-v1',
      occurredAt: '2026-07-24T12:00:00Z',
      eventType: 'auth.login',
      correlationId: '0123456789abcdef0123456789abcdef',
      metadata: { keySample: ['AUTH_ENABLED'] },
    });
  });

  it('omits empty optional filters from the request', async () => {
    get.mockResolvedValueOnce({
      data: { items: [], page: 1, page_size: 50, total: 0 },
    });

    await securityAuditApi.list({ page: 1, pageSize: 50 });

    expect(get).toHaveBeenCalledWith('/api/v1/security/audit-events', {
      params: {
        page: 1,
        page_size: 50,
      },
    });
  });

  it('preserves extra keys on valid payloads (byte-identical toCamelCase pass-through)', async () => {
    get.mockResolvedValueOnce({
      data: { items: [], page: 1, page_size: 10, total: 0, unexpected_server_field: 'keep-me' },
    });
    const page = await securityAuditApi.list();
    expect(page).toEqual({
      items: [], page: 1, pageSize: 10, total: 0, unexpectedServerField: 'keep-me',
    });
  });

  it('surfaces shape mismatches through ParsedApiError', async () => {
    get.mockResolvedValueOnce({ data: { page: 1, page_size: 10, total: 0 } });
    await expect(securityAuditApi.list()).rejects.toSatisfy((error: unknown) => {
      expect(isApiRequestError(error)).toBe(true);
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.message).toContain('SecurityAuditEventPage');
      return true;
    });
  });

});
