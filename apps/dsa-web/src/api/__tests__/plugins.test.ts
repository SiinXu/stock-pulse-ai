// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { pluginsApi } from '../plugins';

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('../index', () => ({
  default: { get, post },
}));

describe('pluginsApi', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it('lists plugins and camel-cases the payload', async () => {
    get.mockResolvedValueOnce({
      data: {
        items: [{
          id: 'example_provider',
          name: 'Example Provider',
          version: '1.0.0',
          source: 'external',
          state: 'enabled',
          desired_enabled: true,
          reloadable: true,
          package_root: '/plugins/example-provider',
          extension_points: ['data_provider'],
          description: 'Example',
          author: 'ops',
        }],
        total: 1,
      },
    });

    const page = await pluginsApi.list();
    expect(get).toHaveBeenCalledWith('/api/v1/plugins');
    expect(page.total).toBe(1);
    expect(page.items[0]).toMatchObject({
      id: 'example_provider',
      desiredEnabled: true,
      packageRoot: '/plugins/example-provider',
      extensionPoints: ['data_provider'],
    });
  });

  it('posts lifecycle actions with snake-case response camel-cased', async () => {
    post.mockResolvedValueOnce({
      data: {
        plugin_id: 'example_provider',
        action: 'disable',
        success: true,
        state: 'disabled',
        reloaded: false,
        restart_required: false,
        error_code: null,
        message: 'Plugin disabled',
        plugin: {
          id: 'example_provider',
          name: 'Example Provider',
          version: '1.0.0',
          source: 'external',
          state: 'disabled',
          desired_enabled: false,
          reloadable: true,
          package_root: '/plugins/example-provider',
          extension_points: [],
          description: '',
          author: '',
        },
      },
    });

    const result = await pluginsApi.updateLifecycle('example_provider', 'disable');
    expect(post).toHaveBeenCalledWith(
      '/api/v1/plugins/example_provider/lifecycle',
      { action: 'disable' },
    );
    expect(result).toMatchObject({
      pluginId: 'example_provider',
      action: 'disable',
      success: true,
      restartRequired: false,
      plugin: { desiredEnabled: false, state: 'disabled' },
    });
  });
});
