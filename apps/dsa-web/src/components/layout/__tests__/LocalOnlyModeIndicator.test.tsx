// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { outboundActivityApi } from '../../../api/outboundActivity';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { ADDITIONAL_UI_LANGUAGES } from '../../../i18n/uiLanguages';
import { loadUiLanguageTranslations } from '../../../i18n/translations';
import type { LocalOnlyModeStatus } from '../../../types/outboundActivity';
import { getFieldTitle } from '../../../utils/systemConfigI18n';
import { LocalOnlyModeIndicator } from '../LocalOnlyModeIndicator';
import {
  buildLocalOnlyModeSettingsHref,
  LOCAL_ONLY_MODE_FIELD_KEY,
  localOnlyModeFieldTitle,
} from '../localOnlyMode';

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

function renderIndicator(language: 'en' | 'zh' | 'de' = 'en') {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <UiLanguageProvider initialLanguage={language}>
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
    expect(indicator).toHaveAttribute('aria-label', localOnlyModeFieldTitle('en'));
    expect(indicator).toHaveAttribute('aria-label', 'Local Only Mode');
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

  it('resolves the existing Local Only field title for every extra locale', async () => {
    await Promise.all(ADDITIONAL_UI_LANGUAGES.map((language) => loadUiLanguageTranslations(language)));
    const titles = ADDITIONAL_UI_LANGUAGES.map((language) => ({
      language,
      title: localOnlyModeFieldTitle(language),
      catalog: getFieldTitle(LOCAL_ONLY_MODE_FIELD_KEY, undefined, language),
    }));
    for (const { language, title, catalog } of titles) {
      expect(title.trim().length, `field title for ${language}`).toBeGreaterThan(0);
      expect(title, `field title for ${language}`).toBe(catalog);
      expect(title, `field title for ${language}`).not.toMatch(
        /airtight|every destination|all outbound|protected|blocked/i,
      );
    }
    expect(localOnlyModeFieldTitle('en')).toBe(getFieldTitle(LOCAL_ONLY_MODE_FIELD_KEY, undefined, 'en'));
    expect(localOnlyModeFieldTitle('zh')).toBe(getFieldTitle(LOCAL_ONLY_MODE_FIELD_KEY, undefined, 'zh'));
    expect(localOnlyModeFieldTitle('de')).toBe('Nur-lokal-Modus');
  });

  it('renders the German catalog field title after extra-locale load', async () => {
    await loadUiLanguageTranslations('de');
    getLocalOnlyStatus.mockResolvedValue(ENABLED_STATUS);
    renderIndicator('de');

    const indicator = await screen.findByTestId('shell-local-only-indicator');
    expect(indicator).toHaveAttribute('aria-label', 'Nur-lokal-Modus');
  });
});
