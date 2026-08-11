// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { pluginsApi } from '../../../api/plugins';
import { createParsedApiError } from '../../../api/error';
import { UI_TEXT } from '../../../i18n/uiText';
import LoadedExtensionsPanel from '../LoadedExtensionsPanel';

vi.mock('../../../api/plugins', () => ({
  pluginsApi: {
    list: vi.fn(),
  },
}));

const t = (key: keyof typeof UI_TEXT.en, params?: Record<string, string | number>) => {
  const template = UI_TEXT.en[key] ?? String(key);
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (
    params[name] === undefined ? match : String(params[name])
  ));
};

describe('LoadedExtensionsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists loaded extensions with source path and states from GET /api/v1/plugins', async () => {
    vi.mocked(pluginsApi.list).mockResolvedValue({
      total: 3,
      items: [
        {
          id: 'kronos',
          name: 'Kronos',
          version: '1.0.0',
          source: 'builtin',
          state: 'enabled',
          desiredEnabled: true,
          reloadable: false,
          packageRoot: null,
          extensionPoints: ['agent_tool'],
          description: 'Built-in forecasting tool',
          author: 'StockPulse',
        },
        {
          id: 'acme-notify',
          name: 'Acme Notify',
          version: '0.3.1',
          source: 'external',
          state: 'failed',
          desiredEnabled: true,
          reloadable: true,
          packageRoot: '/var/plugins/acme-notify',
          extensionPoints: [],
          lastErrorCode: 'manifest_permissions_undeclared',
          description: '',
          author: 'Acme',
        },
        {
          id: 'legacy-failed',
          name: 'Legacy Failed',
          version: '0.1.0',
          source: 'external',
          state: 'failed',
          desiredEnabled: true,
          reloadable: false,
          packageRoot: null,
          extensionPoints: [],
          description: '',
          author: '',
        },
      ],
    });

    render(<LoadedExtensionsPanel t={t} language="en" />);

    expect(await screen.findByText('Kronos')).toBeInTheDocument();
    expect(screen.getByText('kronos')).toBeInTheDocument();
    expect(screen.getByText('1.0.0')).toBeInTheDocument();
    expect(screen.getByText('Built-in package (in-process)')).toBeInTheDocument();
    expect(screen.getByText('Enabled')).toBeInTheDocument();
    expect(screen.getByText('agent_tool')).toBeInTheDocument();

    expect(screen.getByText('Acme Notify')).toBeInTheDocument();
    expect(screen.getByText('/var/plugins/acme-notify')).toBeInTheDocument();
    expect(screen.getAllByText('Failed')).toHaveLength(2);
    expect(screen.getByTestId('loaded-extension-failure-acme-notify')).toHaveTextContent(
      'Failure code: manifest_permissions_undeclared',
    );
    expect(screen.getByTestId('loaded-extension-failure-legacy-failed')).toHaveTextContent(
      /no stable failure code is currently available/i,
    );

    expect(screen.getByTestId('settings-loaded-extensions-trust')).toHaveTextContent(
      /not sandboxed/i,
    );
    expect(screen.getByTestId('settings-loaded-extensions-readonly')).toHaveTextContent(
      /Read-only/i,
    );
    // No marketplace / install affordance.
    expect(screen.queryByRole('button', { name: /install/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /enable/i })).not.toBeInTheDocument();
    expect(pluginsApi.list).toHaveBeenCalledTimes(1);
  });

  it('shows empty state when no plugins are registered', async () => {
    vi.mocked(pluginsApi.list).mockResolvedValue({ total: 0, items: [] });

    render(<LoadedExtensionsPanel t={t} language="en" />);

    expect(await screen.findByText('No extensions registered')).toBeInTheDocument();
    expect(screen.getByText(/Add trusted plugins to PLUGINS_DIR/i)).toBeInTheDocument();
  });

  it('retries after a load failure on refresh', async () => {
    vi.mocked(pluginsApi.list)
      .mockRejectedValueOnce(
        createParsedApiError({
          title: 'Unauthorized',
          message: 'Login required',
          status: 401,
          code: 'unauthorized',
          category: 'http_error',
        }),
      )
      .mockResolvedValueOnce({
        total: 1,
        items: [{
          id: 'demo',
          name: 'Demo',
          version: '0.0.1',
          source: 'builtin',
          state: 'registered',
          desiredEnabled: true,
          reloadable: false,
          packageRoot: null,
          extensionPoints: [],
          description: '',
          author: '',
        }],
      });

    render(<LoadedExtensionsPanel t={t} language="en" />);

    // ApiErrorAlert is toast-based; assert the list stayed empty after the failure.
    await waitFor(() => {
      expect(pluginsApi.list).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByTestId('settings-loaded-extensions-list')).not.toBeInTheDocument();
    expect(screen.queryByText('Demo')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Refresh extensions list' }));
    expect(await screen.findByText('Demo')).toBeInTheDocument();
    expect(screen.getByTestId('loaded-extension-row-demo')).toBeInTheDocument();
    expect(pluginsApi.list).toHaveBeenCalledTimes(2);
  });

  it('shows desired-disabled intent without offering install actions', async () => {
    vi.mocked(pluginsApi.list).mockResolvedValue({
      total: 1,
      items: [{
        id: 'opt-out',
        name: 'Opt Out',
        version: '2.0.0',
        source: 'external',
        state: 'disabled',
        desiredEnabled: false,
        reloadable: true,
        packageRoot: '/opt/plugins/opt-out',
        extensionPoints: ['notification_channel'],
        description: '',
        author: '',
      }],
    });

    render(<LoadedExtensionsPanel t={t} language="en" />);

    expect(await screen.findByTestId('loaded-extension-row-opt-out')).toBeInTheDocument();
    expect(screen.getByText('Opt Out')).toBeInTheDocument();
    expect(screen.getByText(/Persisted intent: disabled/i)).toBeInTheDocument();
    expect(screen.getByText(/not sandboxed/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /install|browse store|marketplace/i })).not.toBeInTheDocument();
  });
});
