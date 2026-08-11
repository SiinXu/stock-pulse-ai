// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { pluginsApi, type PluginInfo } from '../../../api/plugins';
import { createParsedApiError } from '../../../api/error';
import { UI_TEXT } from '../../../i18n/uiText';
import PluginsPanel from '../plugins/PluginsPanel';

vi.mock('../../../api/plugins', () => ({
  pluginsApi: {
    list: vi.fn(),
    updateLifecycle: vi.fn(),
  },
}));

const t = (key: keyof typeof UI_TEXT.en, params?: Record<string, string | number>) => {
  const template = UI_TEXT.en[key] ?? String(key);
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (
    params[name] === undefined ? match : String(params[name])
  ));
};

function samplePlugin(overrides: Partial<PluginInfo> = {}): PluginInfo {
  return {
    id: 'example_provider',
    name: 'Example Provider',
    version: '1.0.0',
    source: 'external',
    state: 'enabled',
    desiredEnabled: true,
    reloadable: true,
    packageRoot: '/plugins/example-provider',
    extensionPoints: ['data_provider'],
    description: 'Example',
    author: 'ops',
    ...overrides,
  };
}

describe('PluginsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists plugins with name, version, hooks, source path, and state', async () => {
    vi.mocked(pluginsApi.list).mockResolvedValue({
      total: 1,
      items: [samplePlugin()],
    });

    render(<PluginsPanel t={t} language="en" />);

    expect(await screen.findByText('Example Provider')).toBeInTheDocument();
    expect(screen.getByText('v1.0.0')).toBeInTheDocument();
    expect(screen.getByText(/data_provider/)).toBeInTheDocument();
    expect(screen.getByText('/plugins/example-provider')).toBeInTheDocument();
    expect(screen.getByText('Enabled')).toBeInTheDocument();
    expect(screen.getByTestId('settings-plugins-trust-banner')).toHaveTextContent(
      /full process privileges|code you have reviewed and trust/i,
    );
    expect(pluginsApi.list).toHaveBeenCalledTimes(1);
  });

  it('toggles enable/disable through the plugins API boundary', async () => {
    vi.mocked(pluginsApi.list).mockResolvedValue({
      total: 1,
      items: [samplePlugin({ desiredEnabled: true, state: 'enabled' })],
    });
    vi.mocked(pluginsApi.updateLifecycle).mockResolvedValue({
      pluginId: 'example_provider',
      action: 'disable',
      success: true,
      state: 'disabled',
      reloaded: false,
      restartRequired: false,
      errorCode: null,
      message: 'Plugin disabled; will not be loaded or invoked',
      plugin: samplePlugin({ desiredEnabled: false, state: 'disabled' }),
    });

    render(<PluginsPanel t={t} language="en" />);
    expect(await screen.findByText('Example Provider')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('settings-plugin-toggle-example_provider'));

    await waitFor(() => {
      expect(pluginsApi.updateLifecycle).toHaveBeenCalledWith('example_provider', 'disable');
    });
    expect(await screen.findByText('Disabled')).toBeInTheDocument();
  });

  it('renders failed state and lifecycle diagnostic when enable fails', async () => {
    vi.mocked(pluginsApi.list).mockResolvedValue({
      total: 1,
      items: [samplePlugin({
        state: 'failed',
        desiredEnabled: true,
        extensionPoints: [],
      })],
    });
    vi.mocked(pluginsApi.updateLifecycle).mockResolvedValue({
      pluginId: 'example_provider',
      action: 'enable',
      success: false,
      state: 'failed',
      reloaded: false,
      restartRequired: false,
      errorCode: 'plugin_onload_failed',
      message: 'onload raised ValueError: boom',
      plugin: samplePlugin({
        state: 'failed',
        desiredEnabled: true,
        extensionPoints: [],
      }),
    });

    render(<PluginsPanel t={t} language="en" />);
    expect(await screen.findByTestId('settings-plugin-failed-example_provider')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('settings-plugin-toggle-example_provider'));

    expect(
      await screen.findByText(/plugin_onload_failed|onload raised ValueError/i),
    ).toBeInTheDocument();
  });

  it('shows honest restart-required copy after reload of a built-in plugin', async () => {
    vi.mocked(pluginsApi.list).mockResolvedValue({
      total: 1,
      items: [samplePlugin({
        id: 'kronos',
        name: 'Kronos',
        source: 'builtin',
        reloadable: false,
        packageRoot: null,
        extensionPoints: ['agent_tools'],
      })],
    });
    vi.mocked(pluginsApi.updateLifecycle).mockResolvedValue({
      pluginId: 'kronos',
      action: 'reload',
      success: false,
      state: 'enabled',
      reloaded: false,
      restartRequired: true,
      errorCode: 'plugin_reload_restart_required',
      message: 'Built-in plugins require a process restart',
      plugin: samplePlugin({
        id: 'kronos',
        name: 'Kronos',
        source: 'builtin',
        reloadable: false,
        packageRoot: null,
        extensionPoints: ['agent_tools'],
      }),
    });

    render(<PluginsPanel t={t} language="en" />);
    expect(await screen.findByText('Kronos')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('settings-plugin-reload-kronos'));

    expect(await screen.findByTestId('settings-plugin-restart-kronos')).toBeInTheDocument();
    expect(screen.getByTestId('settings-plugins-restart-banner')).toBeInTheDocument();
  });

  it('shows empty state when no plugins are registered', async () => {
    vi.mocked(pluginsApi.list).mockResolvedValue({ total: 0, items: [] });

    render(<PluginsPanel t={t} language="en" />);

    expect(await screen.findByText('No plugins registered')).toBeInTheDocument();
  });

  it('surfaces list load errors', async () => {
    vi.mocked(pluginsApi.list).mockRejectedValue(
      createParsedApiError({
        title: 'Request failed',
        message: 'Network down',
        status: 500,
        code: 'http_error',
        category: 'http_error',
      }),
    );

    render(<PluginsPanel t={t} language="en" />);

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(/Request failed/i);
    expect(screen.getByRole('alert')).toHaveTextContent(/Network down/i);
  });
});
