// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { outboundActivityApi } from '../../../api/outboundActivity';
import { UI_TEXT } from '../../../i18n/uiText';
import OutboundActivityPanel from '../OutboundActivityPanel';

vi.mock('../../../api/outboundActivity', () => ({
  outboundActivityApi: { getLocalOnlyStatus: vi.fn(), listActivity: vi.fn() },
}));

const t = (key: keyof typeof UI_TEXT.en, params?: Record<string, string | number>) => {
  const template = UI_TEXT.en[key] ?? String(key);
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (
    params[name] === undefined ? match : String(params[name])
  ));
};

describe('OutboundActivityPanel', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('shows local-only status and redacted activity rows', async () => {
    vi.mocked(outboundActivityApi.getLocalOnlyStatus).mockResolvedValue({
      enabled: true, envKey: 'LOCAL_ONLY_MODE', policy: 'non_loopback_denied',
      allowedDestinationClasses: ['loopback'], blockedErrorReason: 'local_only_mode_blocked',
    });
    vi.mocked(outboundActivityApi.listActivity).mockResolvedValue({
      localOnlyMode: true, limit: 50, returned: 1, maxRetained: 100,
      items: [{
        occurredAt: '2026-08-06T12:00:00Z', decision: 'blocked', destinationClass: 'public_hostname',
        scheme: 'https', hostType: 'hostname', reason: 'local_only_mode_blocked',
        correlationId: 'abcdef0123456789', localOnlyMode: true, allowlisted: false,
      }],
    });
    render(<OutboundActivityPanel t={t} language="en" />);
    expect(await screen.findByTestId('settings-local-only-status')).toBeInTheDocument();
    expect(screen.getByText(/Local Only mode is on/i)).toBeInTheDocument();
    expect(await screen.findByText('local_only_mode_blocked')).toBeInTheDocument();
    expect(screen.getByText('public_hostname')).toBeInTheDocument();
  });

  it('shows empty state when no decisions are retained', async () => {
    vi.mocked(outboundActivityApi.getLocalOnlyStatus).mockResolvedValue({
      enabled: false, envKey: 'LOCAL_ONLY_MODE', policy: 'non_loopback_denied',
      allowedDestinationClasses: ['loopback'], blockedErrorReason: 'local_only_mode_blocked',
    });
    vi.mocked(outboundActivityApi.listActivity).mockResolvedValue({
      localOnlyMode: false, limit: 50, returned: 0, maxRetained: 100, items: [],
    });
    render(<OutboundActivityPanel t={t} language="en" />);
    await waitFor(() => {
      expect(screen.getByText(/No outbound decisions yet/i)).toBeInTheDocument();
    });
  });
});
