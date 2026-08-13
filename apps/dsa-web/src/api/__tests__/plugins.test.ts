// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { pluginsApi } from '../plugins';

vi.mock('../index', () => ({
  __esModule: true,
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
  locallyRecoverableResourceConfig: () => ({ handleUnauthorizedLocally: true }),
}));

describe('pluginsApi', () => {
  beforeEach(() => vi.clearAllMocks());

  it('maps stable lifecycle failure codes from the list response', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: {
        total: 1,
        items: [{
          id: 'acme-plugin',
          name: 'Acme Plugin',
          version: '1.0.0',
          source: 'external',
          state: 'failed',
          desired_enabled: true,
          reloadable: true,
          package_root: '/opt/plugins/acme',
          extension_points: ['agent_tool'],
          notification_channels: [],
          last_error_code: 'manifest_permissions_undeclared',
          settings_count: 3,
        }],
      },
    });

    const result = await pluginsApi.list();

    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/v1/plugins',
      expect.objectContaining({ handleUnauthorizedLocally: true }),
    );
    expect(result.items[0]).toMatchObject({
      id: 'acme-plugin',
      desiredEnabled: true,
      packageRoot: '/opt/plugins/acme',
      extensionPoints: ['agent_tool'],
      notificationChannels: [],
      lastErrorCode: 'manifest_permissions_undeclared',
      settingsCount: 3,
    });
  });

  it('maps active notification channel registrations from the list response', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: {
        total: 1,
        items: [{
          id: 'example-notification-channel',
          name: 'Example Notification Channel',
          version: '1.0.0',
          source: 'external',
          state: 'enabled',
          desired_enabled: true,
          reloadable: true,
          package_root: '/opt/plugins/example-notification-channel',
          extension_points: ['notification_channel'],
          notification_channels: ['example_log'],
          settings_count: 0,
        }],
      },
    });

    const result = await pluginsApi.list();
    expect(result.items[0].notificationChannels).toEqual(['example_log']);
    expect(result.items[0].extensionPoints).toEqual(['notification_channel']);
  });

  it('parses generated settings and sends a full typed replacement', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        plugin_id: 'acme-plugin',
        schema: [{
          key: 'threshold',
          title: 'Threshold',
          data_type: 'number',
          ui_control: 'number',
          is_sensitive: false,
          is_required: true,
          default_value: 0.5,
          options: [],
          validation: { minimum: 0, maximum: 1 },
          display_order: 10,
        }],
        values: { threshold: 0.5 },
        masked_keys: [],
        mask_token: '******',
      },
    });

    const settings = await pluginsApi.getSettings('acme/plugin');
    expect(settings.schema[0]).toMatchObject({
      key: 'threshold',
      dataType: 'number',
      validation: { minimum: 0, maximum: 1 },
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/v1/plugins/acme%2Fplugin/settings',
      expect.objectContaining({ handleUnauthorizedLocally: true }),
    );

    vi.mocked(apiClient.put).mockResolvedValueOnce({
      data: {
        plugin_id: 'acme-plugin',
        schema: [],
        values: { threshold: 0.75 },
        masked_keys: [],
        mask_token: '******',
        changed_keys: ['threshold'],
        restart_required: true,
      },
    });
    const updated = await pluginsApi.updateSettings(
      'acme-plugin',
      { threshold: 0.75 },
      '******',
    );
    expect(apiClient.put).toHaveBeenCalledWith(
      '/api/v1/plugins/acme-plugin/settings',
      { values: { threshold: 0.75 }, mask_token: '******' },
      expect.objectContaining({ handleUnauthorizedLocally: true }),
    );
    expect(updated).toMatchObject({ changedKeys: ['threshold'], restartRequired: true });
  });

  it('rejects non-finite settings responses at the client boundary', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        plugin_id: 'acme-plugin',
        schema: [],
        values: { threshold: Number.POSITIVE_INFINITY },
        masked_keys: [],
        mask_token: '******',
      },
    });

    await expect(pluginsApi.getSettings('acme-plugin')).rejects.toBeDefined();
  });
});
