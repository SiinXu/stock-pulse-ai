// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createParsedApiError } from '../../../api/error';
import { configProfilesApi } from '../../../api/configProfiles';
import { UI_TEXT } from '../../../i18n/uiText';
import { createAppQueryClient } from '../../../query/createAppQueryClient';
import ConfigPresetsPanel, { type ConfigPresetsPanelProps } from '../ConfigPresetsPanel';

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

const localFirstPreset = {
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
};

const listPayload = {
  recommendedPresetId: 'local-first',
  detection: {
    ollamaHealthy: true,
    modelPackPresent: false,
    cliDetected: [] as string[],
    cloudReady: false,
  },
  presets: [localFirstPreset],
};

function serverError() {
  return createParsedApiError({
    title: 'Unavailable',
    message: 'config presets unavailable',
    status: 500,
    code: 'internal',
    category: 'http_error',
  });
}

function renderPanel(ui: ReactElement) {
  const client = createAppQueryClient();
  return render(
    <QueryClientProvider client={client}>
      {ui}
    </QueryClientProvider>,
  );
}

function renderDefault(overrides: {
  disabled?: boolean;
  onApplied?: ConfigPresetsPanelProps['onApplied'];
} = {}) {
  return renderPanel(
    <ConfigPresetsPanel
      configVersion="v1"
      disabled={overrides.disabled}
      t={t}
      language="en"
      onApplied={overrides.onApplied ?? (async () => undefined)}
    />,
  );
}

describe('ConfigPresetsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(configProfilesApi.listPresets).mockResolvedValue(listPayload);
  });

  it('lists recommended presets from a single mount GET', async () => {
    renderDefault();

    await waitFor(() => {
      expect(screen.getByText('Local-first (Ollama / Model Pack)')).toBeInTheDocument();
    });
    expect(configProfilesApi.listPresets).toHaveBeenCalledTimes(1);
    expect(vi.mocked(configProfilesApi.listPresets).mock.calls[0]).toEqual([]);
    expect(screen.getByText(UI_TEXT.en['settings.configPresetsRecommended'])).toBeInTheDocument();
  });

  it('still lists on mount when disabled and only disables controls', async () => {
    renderDefault({ disabled: true });

    await waitFor(() => {
      expect(screen.getByText('Local-first (Ollama / Model Pack)')).toBeInTheDocument();
    });
    expect(configProfilesApi.listPresets).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: UI_TEXT.en['settings.configPresetsApply'] })).toBeDisabled();
    expect(screen.getByRole('button', { name: UI_TEXT.en['settings.configPresetsRefreshAria'] })).toBeDisabled();
    expect(screen.getByRole('button', { name: UI_TEXT.en['settings.configPresetsExport'] })).toBeDisabled();
    expect(screen.getByRole('button', { name: UI_TEXT.en['settings.configPresetsImport'] })).toBeDisabled();
  });

  it('treats empty 200 as success EmptyState', async () => {
    vi.mocked(configProfilesApi.listPresets).mockResolvedValueOnce({
      recommendedPresetId: null,
      detection: listPayload.detection,
      presets: [],
    });
    renderDefault();

    expect(await screen.findByText(UI_TEXT.en['settings.configPresetsEmptyTitle'])).toBeInTheDocument();
    expect(screen.queryByText(UI_TEXT.en['settings.configPresetsLoading'])).not.toBeInTheDocument();
  });

  it('clears presets and shows parsed error on an initial 500', async () => {
    vi.mocked(configProfilesApi.listPresets).mockRejectedValueOnce(serverError());
    renderDefault();

    expect(await screen.findByText('config presets unavailable')).toBeInTheDocument();
    expect(screen.queryByText('Local-first (Ollama / Model Pack)')).not.toBeInTheDocument();
    expect(screen.queryByText(UI_TEXT.en['settings.configPresetsEmptyTitle'])).not.toBeInTheDocument();
  });

  it('clears last-good presets when a later refresh 500 fail-closes', async () => {
    renderDefault();
    await waitFor(() => {
      expect(screen.getByText('Local-first (Ollama / Model Pack)')).toBeInTheDocument();
    });

    vi.mocked(configProfilesApi.listPresets).mockRejectedValueOnce(serverError());
    fireEvent.click(screen.getByRole('button', { name: UI_TEXT.en['settings.configPresetsRefreshAria'] }));

    expect(await screen.findByText('config presets unavailable')).toBeInTheDocument();
    expect(screen.queryByText('Local-first (Ollama / Model Pack)')).not.toBeInTheDocument();
    expect(configProfilesApi.listPresets).toHaveBeenCalledTimes(2);
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

    renderDefault();

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

  it('confirms apply, calls onApplied, then reloads the list', async () => {
    const onApplied = vi.fn(async (_updatedKeys: string[]) => undefined);
    vi.mocked(configProfilesApi.previewPreset).mockResolvedValue({
      presetId: 'local-first',
      displayName: 'Local-first (Ollama / Model Pack)',
      configVersion: 'v1',
      features: {},
      changes: [{ key: 'GENERATION_BACKEND', fromValue: '', to: 'litellm' }],
      changeCount: 1,
    });
    vi.mocked(configProfilesApi.applyPreset).mockResolvedValue({
      presetId: 'local-first',
      displayName: 'Local-first (Ollama / Model Pack)',
      applied: true,
      configVersion: 'v1',
      newConfigVersion: 'v2',
      updatedKeys: ['GENERATION_BACKEND'],
      changes: [{ key: 'GENERATION_BACKEND', fromValue: '', to: 'litellm' }],
      features: {},
      message: 'Applied',
    });

    renderDefault({ onApplied });
    await waitFor(() => {
      expect(screen.getByText('Local-first (Ollama / Model Pack)')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: UI_TEXT.en['settings.configPresetsApply'] }));
    expect(await screen.findByText(UI_TEXT.en['settings.configPresetsConfirmTitle'])).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: UI_TEXT.en['settings.configPresetsConfirmApply'] }));

    await waitFor(() => {
      expect(configProfilesApi.applyPreset).toHaveBeenCalledWith('local-first', {
        configVersion: 'v1',
        reloadNow: true,
      });
    });
    await waitFor(() => {
      expect(onApplied).toHaveBeenCalledWith(['GENERATION_BACKEND']);
    });
    await waitFor(() => {
      expect(configProfilesApi.listPresets).toHaveBeenCalledTimes(2);
    });
    expect(vi.mocked(configProfilesApi.listPresets).mock.calls[1]).toEqual([]);
  });

  it('keeps export panel-owned and does not pass configVersion to the list GET', async () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:profile');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    vi.mocked(configProfilesApi.exportProfile).mockResolvedValue({
      content: 'name: local',
      configVersion: 'v1',
      filename: 'stockpulse-profile.yaml',
      keysExported: ['GENERATION_BACKEND'],
      keysRedacted: 2,
    });

    renderDefault();
    await waitFor(() => {
      expect(screen.getByText('Local-first (Ollama / Model Pack)')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: UI_TEXT.en['settings.configPresetsExport'] }));
    await waitFor(() => {
      expect(configProfilesApi.exportProfile).toHaveBeenCalledTimes(1);
    });
    expect(vi.mocked(configProfilesApi.exportProfile).mock.calls[0]).toEqual([]);
    expect(click).toHaveBeenCalled();
    expect(vi.mocked(configProfilesApi.listPresets).mock.calls[0]).toEqual([]);
    click.mockRestore();
  });

  it('previews import, confirms, calls onApplied, then reloads', async () => {
    const onApplied = vi.fn(async (_updatedKeys: string[]) => undefined);
    vi.mocked(configProfilesApi.previewImport).mockResolvedValue({
      valid: true,
      configVersion: 'v1',
      name: 'imported',
      displayName: 'Imported profile',
      description: 'Imported profile YAML',
      features: {},
      changes: [{ key: 'GENERATION_BACKEND', fromValue: '', to: 'litellm' }],
      changeCount: 1,
      issues: [],
    });
    vi.mocked(configProfilesApi.applyImport).mockResolvedValue({
      applied: true,
      configVersion: 'v1',
      newConfigVersion: 'v3',
      updatedKeys: ['GENERATION_BACKEND'],
      changes: [{ key: 'GENERATION_BACKEND', fromValue: '', to: 'litellm' }],
      name: 'imported',
      features: {},
      message: 'Imported',
    });

    renderDefault({ onApplied });
    await waitFor(() => {
      expect(screen.getByText('Local-first (Ollama / Model Pack)')).toBeInTheDocument();
    });

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['name: imported'], 'profile.yaml', { type: 'text/yaml' });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(configProfilesApi.previewImport).toHaveBeenCalledWith({
        configVersion: 'v1',
        content: 'name: imported',
      });
    });
    expect(await screen.findByText(UI_TEXT.en['settings.configPresetsImportConfirmTitle'])).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: UI_TEXT.en['settings.configPresetsConfirmImport'] }));

    await waitFor(() => {
      expect(configProfilesApi.applyImport).toHaveBeenCalledWith({
        configVersion: 'v1',
        content: 'name: imported',
        reloadNow: true,
      });
    });
    await waitFor(() => {
      expect(onApplied).toHaveBeenCalledWith(['GENERATION_BACKEND']);
    });
    await waitFor(() => {
      expect(configProfilesApi.listPresets).toHaveBeenCalledTimes(2);
    });
  });
});
