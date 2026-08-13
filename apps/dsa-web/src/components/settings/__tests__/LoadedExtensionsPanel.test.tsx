// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { pluginsApi } from '../../../api/plugins';
import { createParsedApiError } from '../../../api/error';
import { UI_TEXT } from '../../../i18n/uiText';
import LoadedExtensionsPanel from '../LoadedExtensionsPanel';

vi.mock('../../../api/plugins', () => ({
  pluginsApi: {
    list: vi.fn(),
    updateLifecycle: vi.fn(),
    getSettings: vi.fn(),
    updateSettings: vi.fn(),
  },
}));

const t = (key: keyof typeof UI_TEXT.en, params?: Record<string, string | number>) => {
  const template = UI_TEXT.en[key] ?? String(key);
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (
    params[name] === undefined ? match : String(params[name])
  ));
};

function renderPanel(initialEntry = '/settings?section=system_security&view=extensions') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <LoadedExtensionsPanel t={t} language="en" />
    </MemoryRouter>,
  );
}

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
          notificationChannels: [],
          description: 'Built-in forecasting tool',
          author: 'StockPulse',
          settingsCount: 0,
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
          notificationChannels: [],
          lastErrorCode: 'manifest_permissions_undeclared',
          description: '',
          author: 'Acme',
          settingsCount: 0,
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
          notificationChannels: [],
          description: '',
          author: '',
          settingsCount: 0,
        },
      ],
    });

    renderPanel();

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
    expect(screen.getByTestId('settings-loaded-extensions-management-note')).toHaveTextContent(
      /persisted/i,
    );
    // No marketplace / install affordance.
    expect(screen.queryByRole('button', { name: /install/i })).not.toBeInTheDocument();
    expect(screen.getByRole('switch', { name: /Disabled: Kronos/i })).toBeInTheDocument();
    expect(pluginsApi.list).toHaveBeenCalledTimes(1);
  });

  it('shows empty state when no plugins are registered', async () => {
    vi.mocked(pluginsApi.list).mockResolvedValue({ total: 0, items: [] });

    renderPanel();

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
          notificationChannels: [],
          description: '',
          author: '',
          settingsCount: 0,
        }],
      });

    renderPanel();

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
        notificationChannels: [],
        description: '',
        author: '',
        settingsCount: 0,
      }],
    });

    renderPanel();

    expect(await screen.findByTestId('loaded-extension-row-opt-out')).toBeInTheDocument();
    expect(screen.getByText('Opt Out')).toBeInTheDocument();
    expect(screen.getByText(/Persisted intent: disabled/i)).toBeInTheDocument();
    expect(screen.getByText(/not sandboxed/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /install|browse store|marketplace/i })).not.toBeInTheDocument();
  });

  it('persists an enable action through the lifecycle API', async () => {
    vi.mocked(pluginsApi.list)
      .mockResolvedValueOnce({
        total: 1,
        items: [{
          id: 'toggle-demo',
          name: 'Toggle Demo',
          version: '1.0.0',
          source: 'external',
          state: 'disabled',
          desiredEnabled: false,
          reloadable: true,
          packageRoot: '/opt/plugins/toggle-demo',
          extensionPoints: [],
          notificationChannels: [],
          description: '',
          author: '',
          settingsCount: 0,
        }],
      })
      .mockResolvedValue({
        total: 1,
        items: [{
          id: 'toggle-demo',
          name: 'Toggle Demo',
          version: '1.0.0',
          source: 'external',
          state: 'enabled',
          desiredEnabled: true,
          reloadable: true,
          packageRoot: '/opt/plugins/toggle-demo',
          extensionPoints: [],
          notificationChannels: [],
          description: '',
          author: '',
          settingsCount: 0,
        }],
      });
    vi.mocked(pluginsApi.updateLifecycle).mockResolvedValue({
      pluginId: 'toggle-demo',
      action: 'enable',
      success: true,
      state: 'enabled',
      reloaded: false,
      restartRequired: false,
      plugin: null,
    });

    renderPanel();
    const toggle = await screen.findByRole('switch', { name: /Enabled: Toggle Demo/i });
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(pluginsApi.updateLifecycle).toHaveBeenCalledWith('toggle-demo', 'enable');
      expect(toggle).toHaveAttribute('aria-checked', 'true');
    });
    await waitFor(() => {
      expect(pluginsApi.list).toHaveBeenCalledTimes(2);
    });
  });

  it('keeps the roster after a successful toggle when the follow-up refresh fails', async () => {
    vi.mocked(pluginsApi.list)
      .mockResolvedValueOnce({
        total: 1,
        items: [{
          id: 'toggle-demo',
          name: 'Toggle Demo',
          version: '1.0.0',
          source: 'external',
          state: 'disabled',
          desiredEnabled: false,
          reloadable: true,
          packageRoot: '/opt/plugins/toggle-demo',
          extensionPoints: [],
          notificationChannels: [],
          description: '',
          author: '',
          settingsCount: 0,
        }],
      })
      .mockRejectedValueOnce(
        createParsedApiError({
          title: 'Unavailable',
          message: 'Roster unavailable',
          status: 503,
          code: 'unavailable',
          category: 'http_error',
        }),
      );
    vi.mocked(pluginsApi.updateLifecycle).mockResolvedValue({
      pluginId: 'toggle-demo',
      action: 'enable',
      success: true,
      state: 'enabled',
      reloaded: false,
      restartRequired: false,
      plugin: null,
    });

    renderPanel();
    const toggle = await screen.findByRole('switch', { name: /Enabled: Toggle Demo/i });
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(pluginsApi.updateLifecycle).toHaveBeenCalledWith('toggle-demo', 'enable');
      expect(pluginsApi.list).toHaveBeenCalledTimes(2);
    });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Refresh extensions list' })).toBeEnabled();
    });
    expect(screen.getByTestId('loaded-extension-row-toggle-demo')).toBeInTheDocument();
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    expect(screen.queryByText('No extensions registered')).not.toBeInTheDocument();
  });

  it('generates a settings form from the plugin schema and saves typed values', async () => {
    vi.mocked(pluginsApi.list).mockResolvedValue({
      total: 1,
      items: [{
        id: 'configured-demo',
        name: 'Configured Demo',
        version: '1.0.0',
        source: 'external',
        state: 'enabled',
        desiredEnabled: true,
        reloadable: true,
        packageRoot: '/opt/plugins/configured-demo',
        extensionPoints: [],
        notificationChannels: [],
        description: '',
        author: '',
        settingsCount: 2,
      }],
    });
    vi.mocked(pluginsApi.getSettings).mockResolvedValue({
      pluginId: 'configured-demo',
      schema: [
        {
          key: 'threshold',
          title: 'Threshold',
          description: 'Finite score threshold.',
          dataType: 'number',
          uiControl: 'number',
          isSensitive: false,
          isRequired: true,
          defaultValue: 0.5,
          options: [],
          validation: { minimum: 0, maximum: 1 },
          displayOrder: 10,
        },
        {
          key: 'api_token',
          title: 'API token',
          description: '',
          dataType: 'string',
          uiControl: 'password',
          isSensitive: true,
          isRequired: true,
          defaultValue: null,
          options: [],
          validation: { minLength: 8 },
          displayOrder: 20,
        },
      ],
      values: { threshold: 0.5, api_token: '******' },
      maskedKeys: ['api_token'],
      maskToken: '******',
    });
    vi.mocked(pluginsApi.updateSettings).mockResolvedValue({
      pluginId: 'configured-demo',
      schema: [],
      values: { threshold: 0.75, api_token: '******' },
      maskedKeys: ['api_token'],
      maskToken: '******',
      changedKeys: ['threshold'],
      restartRequired: true,
    });

    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'View details: Configured Demo' }));

    expect(await screen.findByRole('dialog', { name: 'View details: Configured Demo' })).toBeInTheDocument();
    const threshold = await screen.findByLabelText(/^Threshold/);
    fireEvent.change(threshold, { target: { value: '0.75' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save configuration' }));

    await waitFor(() => {
      expect(pluginsApi.updateSettings).toHaveBeenCalledWith(
        'configured-demo',
        { threshold: 0.75, api_token: '******' },
        '******',
      );
    });
    expect(await screen.findByText('Restart to apply')).toBeInTheDocument();
  });

  it('deep-links an active notification adapter into Notifications and stays honest when inactive', async () => {
    vi.mocked(pluginsApi.list).mockResolvedValue({
      total: 2,
      items: [
        {
          id: 'example-notification-channel',
          name: 'Example Notification Channel',
          version: '1.0.0',
          source: 'external',
          state: 'enabled',
          desiredEnabled: true,
          reloadable: true,
          packageRoot: '/plugins/example-notification-channel',
          extensionPoints: ['notification_channel'],
          notificationChannels: ['example_log'],
          description: '',
          author: '',
          settingsCount: 0,
        },
        {
          id: 'dormant-notifier',
          name: 'Dormant Notifier',
          version: '1.0.0',
          source: 'external',
          state: 'disabled',
          desiredEnabled: false,
          reloadable: true,
          packageRoot: '/plugins/dormant-notifier',
          extensionPoints: ['notification_channel'],
          notificationChannels: [],
          description: '',
          author: '',
          settingsCount: 0,
        },
      ],
    });

    renderPanel();

    const link = await screen.findByTestId(
      'loaded-extension-notification-link-example-notification-channel-example_log',
    );
    expect(link).toHaveAttribute(
      'href',
      '/settings?section=notifications&view=channels&channel=example_log',
    );
    expect(screen.getByTestId('loaded-extension-notification-inactive-dormant-notifier'))
      .toHaveTextContent(/not active/i);
    expect(screen.queryByTestId('loaded-extension-notification-link-dormant-notifier-example_log'))
      .not.toBeInTheDocument();
  });
});
