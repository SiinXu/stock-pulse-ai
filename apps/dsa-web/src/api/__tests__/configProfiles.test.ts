// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { configProfilesApi } from '../configProfiles';
import apiClient from '../index';

vi.mock('../index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('configProfilesApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists presets and camelCases the response', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: {
        recommended_preset_id: 'local-first',
        detection: {
          ollama_healthy: true,
          model_pack_present: false,
          cli_detected: [],
          cloud_ready: false,
        },
        presets: [
          {
            id: 'local-first',
            display_name: 'Local-first',
            description: 'desc',
            tags: ['local'],
            preference_order: ['ollama'],
            config_values: { GENERATION_BACKEND: 'litellm' },
            strategies: { enabled: ['bull_trend'] },
            features: { beginner_mode: true },
            requirements: {},
            recommended: true,
            score: 100,
            meets_requirements: true,
          },
        ],
      },
    });
    const result = await configProfilesApi.listPresets();
    expect(apiClient.get).toHaveBeenCalledWith('/api/v1/config-profiles/presets');
    expect(result.recommendedPresetId).toBe('local-first');
    expect(result.detection.ollamaHealthy).toBe(true);
    expect(result.presets[0].displayName).toBe('Local-first');
  });

  it('previews and applies a preset with snake_case body', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        preset_id: 'local-first',
        display_name: 'Local-first',
        config_version: 'v1',
        features: {},
        changes: [{ key: 'GENERATION_BACKEND', from_value: '', to: 'litellm' }],
        change_count: 1,
      },
    });
    const preview = await configProfilesApi.previewPreset('local-first', { configVersion: 'v1' });
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/config-profiles/presets/local-first/preview',
      { config_version: 'v1' },
    );
    expect(preview.changes[0].fromValue).toBe('');

    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        preset_id: 'local-first',
        display_name: 'Local-first',
        applied: true,
        config_version: 'v1',
        new_config_version: 'v2',
        updated_keys: ['GENERATION_BACKEND'],
        changes: [],
        features: {},
        message: 'ok',
      },
    });
    const applied = await configProfilesApi.applyPreset('local-first', {
      configVersion: 'v1',
      reloadNow: true,
    });
    expect(applied.applied).toBe(true);
    expect(applied.newConfigVersion).toBe('v2');
  });

  it('exports profile content without client-side secret injection', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: {
        content: 'apiVersion: stockpulse/v1\n',
        config_version: 'v1',
        filename: 'stockpulse-profile-current.yaml',
        keys_exported: ['GENERATION_BACKEND'],
        keys_redacted: 3,
      },
    });
    const exported = await configProfilesApi.exportProfile();
    expect(exported.keysRedacted).toBe(3);
    expect(exported.content).not.toContain('API_KEY');
  });
});
