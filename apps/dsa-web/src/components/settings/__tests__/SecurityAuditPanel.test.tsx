// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { securityAuditApi } from '../../../api/securityAudit';
import { createParsedApiError } from '../../../api/error';
import { UI_TEXT } from '../../../i18n/uiText';
import { createAppQueryClient } from '../../../query/createAppQueryClient';
import { createDeferred } from '../../../test-utils';
import type { SecurityAuditEventPage } from '../../../types/securityAudit';
import SecurityAuditPanel from '../SecurityAuditPanel';

vi.mock('../../../api/securityAudit', () => ({
  securityAuditApi: {
    list: vi.fn(),
  },
}));

const t = (key: keyof typeof UI_TEXT.en, params?: Record<string, string | number>) => {
  const template = UI_TEXT.en[key] ?? String(key);
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (
    params[name] === undefined ? match : String(params[name])
  ));
};

function renderPanel(props: { disabled?: boolean } = {}) {
  const client = createAppQueryClient();
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <SecurityAuditPanel t={t} language="en" {...props} />
      </QueryClientProvider>,
    ),
  };
}

function pageWithRow(): SecurityAuditEventPage {
  return {
    page: 1,
    pageSize: 50,
    total: 1,
    items: [{
      id: 12,
      schemaVersion: 'security-audit-v1',
      occurredAt: '2026-07-24T12:00:00Z',
      eventType: 'auth.login',
      phase: 'completion',
      actor: { type: 'admin', id: 'local_admin' },
      executionId: 'exec-1',
      action: 'login',
      target: { type: 'session', id: 'web' },
      outcome: 'success',
      reasonCode: 'authenticated',
      correlationId: '0123456789abcdef0123456789abcdef',
      metadata: { keySample: ['AUTH_ENABLED'] },
    }],
  };
}

function emptyPage(): SecurityAuditEventPage {
  return {
    page: 1,
    pageSize: 50,
    total: 0,
    items: [],
  };
}

describe('SecurityAuditPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists redacted audit events from the query API', async () => {
    vi.mocked(securityAuditApi.list).mockResolvedValue(pageWithRow());

    renderPanel();

    expect(await screen.findByText('auth.login')).toBeInTheDocument();
    expect(screen.getByText('success')).toBeInTheDocument();
    expect(screen.getByText(/local_admin/)).toBeInTheDocument();
    expect(screen.getByText('Metadata (redacted)')).toBeInTheDocument();
    expect(securityAuditApi.list).toHaveBeenCalledWith({
      page: 1,
      pageSize: 50,
    });
  });

  it('shows an honest blocked state when administrator auth is disabled (403)', async () => {
    vi.mocked(securityAuditApi.list).mockRejectedValue(
      createParsedApiError({
        title: 'Security audit requires administrator authentication',
        message: 'Auth required',
        status: 403,
        code: 'security_audit_auth_required',
        category: 'http_error',
      }),
    );

    renderPanel();

    expect(
      await screen.findByText('Administrator authentication required'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/returns HTTP 403 when administrator authentication is disabled/i),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('settings-security-audit-list')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    // Operators must be able to retry after enabling authentication.
    expect(screen.getByRole('button', { name: 'Refresh audit events' })).not.toBeDisabled();
  });

  it('retries after a 403 when the operator refreshes', async () => {
    vi.mocked(securityAuditApi.list)
      .mockRejectedValueOnce(
        createParsedApiError({
          title: 'Security audit requires administrator authentication',
          message: 'Auth required',
          status: 403,
          code: 'security_audit_auth_required',
          category: 'http_error',
        }),
      )
      .mockResolvedValueOnce(emptyPage());

    renderPanel();
    expect(
      await screen.findByText('Administrator authentication required'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Refresh audit events' }));
    expect(await screen.findByText('No audit events')).toBeInTheDocument();
    expect(securityAuditApi.list).toHaveBeenCalledTimes(2);
  });

  it('applies event type filter on demand', async () => {
    vi.mocked(securityAuditApi.list).mockResolvedValue(emptyPage());

    renderPanel();

    await screen.findByText('No audit events');

    fireEvent.change(screen.getByLabelText('Event type'), {
      target: { value: 'system_config.write' },
    });
    expect(securityAuditApi.list).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }));

    await waitFor(() => {
      expect(securityAuditApi.list).toHaveBeenLastCalledWith({
        page: 1,
        pageSize: 50,
        eventType: 'system_config.write',
      });
    });
    expect(securityAuditApi.list).toHaveBeenCalledTimes(2);
  });

  it('still fetches on mount when disabled and only disables controls', async () => {
    vi.mocked(securityAuditApi.list).mockResolvedValue(pageWithRow());
    renderPanel({ disabled: true });

    expect(await screen.findByText('auth.login')).toBeInTheDocument();
    expect(securityAuditApi.list).toHaveBeenCalledTimes(1);
    expect(securityAuditApi.list).toHaveBeenCalledWith({
      page: 1,
      pageSize: 50,
    });
    expect(screen.getByRole('button', { name: 'Refresh audit events' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Apply filters' })).toBeDisabled();
    expect(screen.getByLabelText('Event type')).toBeDisabled();
  });

  it('keeps prior rows visible while refresh is in flight and does not swap to the initial loader', async () => {
    vi.mocked(securityAuditApi.list).mockResolvedValue(pageWithRow());
    renderPanel();
    expect(await screen.findByTestId('settings-security-audit-list')).toBeInTheDocument();

    const pending = createDeferred<SecurityAuditEventPage>();
    vi.mocked(securityAuditApi.list).mockReturnValueOnce(pending.promise);
    fireEvent.click(screen.getByRole('button', { name: 'Refresh audit events' }));

    await waitFor(() => {
      expect(securityAuditApi.list).toHaveBeenCalledTimes(2);
    });
    expect(screen.getByTestId('settings-security-audit-list')).toBeInTheDocument();
    expect(screen.getByText('auth.login')).toBeInTheDocument();
    expect(screen.queryByText(UI_TEXT.en['common.loading'])).not.toBeInTheDocument();
    expect(document.querySelector('.animate-spin')).not.toBeNull();

    pending.resolve(emptyPage());
    await waitFor(() => {
      expect(screen.getByText('No audit events')).toBeInTheDocument();
    });
  });
});
