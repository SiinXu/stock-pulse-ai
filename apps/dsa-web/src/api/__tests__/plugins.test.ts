// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { pluginsApi } from '../plugins';

vi.mock('../index', () => ({
  __esModule: true,
  default: { get: vi.fn() },
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
          last_error_code: 'manifest_permissions_undeclared',
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
      lastErrorCode: 'manifest_permissions_undeclared',
    });
  });
});
