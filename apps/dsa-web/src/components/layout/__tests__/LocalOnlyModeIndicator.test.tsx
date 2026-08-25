// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { outboundActivityApi } from '../../../api/outboundActivity';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { LocalOnlyModeStatus } from '../../../types/outboundActivity';
import { LocalOnlyModeIndicator } from '../LocalOnlyModeIndicator';
import { buildLocalOnlyModeSettingsHref } from '../localOnlyMode';

vi.mock('../../../api/outboundActivity', () => ({
  outboundActivityApi: {
    getLocalOnlyStatus: vi.fn(),
    listActivity: vi.fn(),
  },
}));

const getLocalOnlyStatus = vi.mocked(outboundActivityApi.getLocalOnlyStatus);

const ENABLED_STATUS: LocalOnlyModeStatus = {
  enabled: true,
  envKey: 'LOCAL_ONLY_MODE',
  policy: 'non_loopback_denied',
  allowedDestinationClasses: ['loopback'],
  blockedErrorReason: 'local_only_mode_blocked',
};

const DISABLED_STATUS: LocalOnlyModeStatus = {
  ...ENABLED_STATUS,
  enabled: false,
};

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="current location">{`${location.pathname}${location.search}`}</output>;
}

function renderIndicator() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <UiLanguageProvider initialLanguage="en">
        <LocalOnlyModeIndicator />
        <LocationProbe />
      </UiLanguageProvider>
    </MemoryRouter>,
  );
}

describe('LocalOnlyModeIndicator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders when the endpoint reports enabled and links to Auth & Security', async () => {
    getLocalOnlyStatus.mockResolvedValue(ENABLED_STATUS);
    renderIndicator();

    const indicator = await screen.findByTestId('shell-local-only-indicator');
    expect(indicator).toHaveAttribute('data-local-only-mode', 'on');
    expect(indicator).toHaveAttribute('aria-label', 'Local Only Mode is on. Open Settings to review this mode.');
    expect(indicator).toHaveAttribute('href', buildLocalOnlyModeSettingsHref());
    expect(indicator.getAttribute('aria-label') ?? '').not.toMatch(
      /airtight|every destination|all outbound|protected|blocked/i,
    );

    fireEvent.click(indicator);
    expect(screen.getByRole('status', { name: 'current location' })).toHaveTextContent(
      '/settings?section=system_security&view=security&field=LOCAL_ONLY_MODE',
    );
  });

  it('renders nothing when Local Only is disabled', async () => {
    getLocalOnlyStatus.mockResolvedValue(DISABLED_STATUS);
    renderIndicator();

    await waitFor(() => expect(getLocalOnlyStatus).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId('shell-local-only-indicator')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Local Only/i })).not.toBeInTheDocument();
  });

  it('does not claim protection when the endpoint fails', async () => {
    getLocalOnlyStatus.mockRejectedValue(new Error('network down'));
    renderIndicator();

    await waitFor(() => expect(getLocalOnlyStatus).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId('shell-local-only-indicator')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Local Only/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Local Only/i)).not.toBeInTheDocument();
  });

  it('does not claim protection while status is still unknown', () => {
    getLocalOnlyStatus.mockReturnValue(new Promise(() => undefined));
    renderIndicator();

    expect(screen.queryByTestId('shell-local-only-indicator')).not.toBeInTheDocument();
    expect(screen.queryByText(/Local Only/i)).not.toBeInTheDocument();
  });
});
