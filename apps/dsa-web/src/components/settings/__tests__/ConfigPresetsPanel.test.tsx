// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { configProfilesApi } from '../../../api/configProfiles';
import { UI_TEXT } from '../../../i18n/uiText';
import ConfigPresetsPanel from '../ConfigPresetsPanel';

vi.mock('../../../api/configProfiles', () => ({
  configProfilesApi: {
    listPresets: vi.fn(),
    previewPreset: vi.fn(),
    applyPreset: vi.fn(),
    exportProfile: vi.fn(),
    previewImport: vi.fn(),
    applyImport: vi.fn(),
  },
}));

const t = (key: keyof typeof UI_TEXT.en, params?: Record<string, string | number>) => {
  const template = UI_TEXT.en[key] ?? String(key);
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (
    params[name] === undefined ? match : String(params[name])
  ));
};

describe('ConfigPresetsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(configProfilesApi.listPresets).mockResolvedValue({
      recommendedPresetId: 'local-first',
      detection: {
        ollamaHealthy: true,
        modelPackPresent: false,
        cliDetected: [],
        cloudReady: false,
      },
      presets: [
        {
          id: 'local-first',
          displayName: 'Local-first (Ollama / Model Pack)',
          description: 'Prefer local models',
          tags: ['local'],
          preferenceOrder: ['ollama'],
          configValues: {},
          strategies: {},
          features: { beginner_mode: true },
          requirements: {},
          recommended: true,
          score: 110,
          meetsRequirements: true,
        },
      ],
    });
  });

  it('lists recommended presets and previews apply', async () => {
    vi.mocked(configProfilesApi.previewPreset).mockResolvedValue({
      presetId: 'local-first',
      displayName: 'Local-first (Ollama / Model Pack)',
      configVersion: 'v1',
      features: {},
      changes: [{ key: 'GENERATION_BACKEND', fromValue: '', to: 'litellm' }],
      changeCount: 1,
    });

    render(
      <ConfigPresetsPanel
        configVersion="v1"
        t={t}
        language="en"
        onApplied={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('Local-first (Ollama / Model Pack)')).toBeInTheDocument();
    });
    expect(screen.getByText(UI_TEXT.en['settings.configPresetsRecommended'])).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: UI_TEXT.en['settings.configPresetsApply'] }));
    await waitFor(() => {
      expect(configProfilesApi.previewPreset).toHaveBeenCalledWith('local-first', {
        configVersion: 'v1',
      });
    });
    expect(await screen.findByText(UI_TEXT.en['settings.configPresetsConfirmTitle'])).toBeInTheDocument();
  });
});
