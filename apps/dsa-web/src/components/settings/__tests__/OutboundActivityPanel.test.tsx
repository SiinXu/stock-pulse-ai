// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { outboundActivityApi } from '../../../api/outboundActivity';
import { UI_TEXT } from '../../../i18n/uiText';
import { createAppQueryClient } from '../../../query/createAppQueryClient';
import { createDeferred } from '../../../test-utils';
import type { LocalOnlyModeStatus, OutboundActivityPage } from '../../../types/outboundActivity';
import OutboundActivityPanel from '../OutboundActivityPanel';

vi.mock('../../../api/outboundActivity', () => ({
  outboundActivityApi: { getLocalOnlyStatus: vi.fn(), listActivity: vi.fn() },
}));

const getLocalOnlyStatus = vi.mocked(outboundActivityApi.getLocalOnlyStatus);
const listActivity = vi.mocked(outboundActivityApi.listActivity);

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
        <OutboundActivityPanel t={t} language="en" {...props} />
      </QueryClientProvider>,
    ),
  };
}

function enabledStatus(): LocalOnlyModeStatus {
  return {
    enabled: true,
    envKey: 'LOCAL_ONLY_MODE',
    policy: 'non_loopback_denied',
    allowedDestinationClasses: ['loopback'],
    blockedErrorReason: 'local_only_mode_blocked',
  };
}

function disabledStatus(): LocalOnlyModeStatus {
  return {
    enabled: false,
    envKey: 'LOCAL_ONLY_MODE',
    policy: 'non_loopback_denied',
    allowedDestinationClasses: ['loopback'],
    blockedErrorReason: 'local_only_mode_blocked',
  };
}

function pageWithRow(): OutboundActivityPage {
  return {
    localOnlyMode: true,
    limit: 50,
    returned: 1,
    maxRetained: 100,
    items: [{
      occurredAt: '2026-08-06T12:00:00Z',
      decision: 'blocked',
      destinationClass: 'public_hostname',
      scheme: 'https',
      hostType: 'hostname',
      reason: 'local_only_mode_blocked',
      correlationId: 'abcdef0123456789',
      localOnlyMode: true,
      allowlisted: false,
    }],
  };
}

function emptyPage(): OutboundActivityPage {
  return {
    localOnlyMode: false,
    limit: 50,
    returned: 0,
    maxRetained: 100,
    items: [],
  };
}

describe('OutboundActivityPanel', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('shows local-only status and redacted activity rows', async () => {
    getLocalOnlyStatus.mockResolvedValue(enabledStatus());
    listActivity.mockResolvedValue(pageWithRow());
    renderPanel();
    expect(await screen.findByTestId('settings-local-only-status')).toBeInTheDocument();
    expect(screen.getByText(/Local Only mode is on/i)).toBeInTheDocument();
    expect(await screen.findByText(/policy-owned HTTP is gated, not a sandbox/i)).toBeInTheDocument();
    expect(screen.queryByText(/only pure loopback egress is allowed/i)).not.toBeInTheDocument();
    expect(await screen.findByText('local_only_mode_blocked')).toBeInTheDocument();
    expect(screen.getByText('public_hostname')).toBeInTheDocument();
    expect(listActivity).toHaveBeenCalledWith({ limit: 50 });
  });

  it('shows empty state when no decisions are retained', async () => {
    getLocalOnlyStatus.mockResolvedValue(disabledStatus());
    listActivity.mockResolvedValue(emptyPage());
    renderPanel();
    await waitFor(() => {
      expect(screen.getByText(/No outbound decisions yet/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Local Only mode is off/i)).toBeInTheDocument();
  });

  it('still fetches on mount when disabled and only disables the refresh button', async () => {
    getLocalOnlyStatus.mockResolvedValue(enabledStatus());
    listActivity.mockResolvedValue(pageWithRow());
    renderPanel({ disabled: true });

    expect(await screen.findByTestId('settings-outbound-activity-list')).toBeInTheDocument();
    expect(getLocalOnlyStatus).toHaveBeenCalledTimes(1);
    expect(getLocalOnlyStatus.mock.calls[0]).toEqual([]);
    expect(listActivity).toHaveBeenCalledTimes(1);
    expect(listActivity.mock.calls[0]).toEqual([{ limit: 50 }]);
    expect(screen.getByRole('button', { name: /Refresh outbound activity/i })).toBeDisabled();
  });

  it('keeps prior rows visible while refresh is in flight and does not swap to the initial loader', async () => {
    getLocalOnlyStatus.mockResolvedValue(enabledStatus());
    listActivity.mockResolvedValue(pageWithRow());
    renderPanel();
    expect(await screen.findByTestId('settings-outbound-activity-list')).toBeInTheDocument();

    const pendingStatus = createDeferred<LocalOnlyModeStatus>();
    const pendingPage = createDeferred<OutboundActivityPage>();
    getLocalOnlyStatus.mockReturnValueOnce(pendingStatus.promise);
    listActivity.mockReturnValueOnce(pendingPage.promise);

    fireEvent.click(screen.getByRole('button', { name: /Refresh outbound activity/i }));

    await waitFor(() => {
      expect(getLocalOnlyStatus).toHaveBeenCalledTimes(2);
    });
    expect(screen.getByTestId('settings-outbound-activity-list')).toBeInTheDocument();
    expect(screen.getByText('public_hostname')).toBeInTheDocument();
    expect(screen.queryByText(UI_TEXT.en['common.loading'])).not.toBeInTheDocument();
    expect(document.querySelector('.animate-spin')).not.toBeNull();

    pendingStatus.resolve(disabledStatus());
    pendingPage.resolve(emptyPage());
    await waitFor(() => {
      expect(screen.getByText(/No outbound decisions yet/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Local Only mode is off/i)).toBeInTheDocument();
  });

  it('clears status and rows together on a hard error', async () => {
    getLocalOnlyStatus.mockRejectedValue(Object.assign(new Error('server'), {
      response: {
        status: 500,
        data: { error: 'internal', message: 'outbound activity unavailable' },
      },
    }));
    listActivity.mockResolvedValue(pageWithRow());
    renderPanel();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Refresh outbound activity/i })).toBeEnabled();
    });
    expect(screen.queryByTestId('settings-local-only-status')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-outbound-activity-list')).not.toBeInTheDocument();
    expect(screen.queryByText('public_hostname')).not.toBeInTheDocument();
  });
});
