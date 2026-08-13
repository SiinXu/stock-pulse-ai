// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import type { PluginInfo } from '../../../api/plugins';
import {
  buildExtensionsHref,
  buildExtensionsPluginHref,
  buildNotificationsChannelHref,
  collectPluginNotificationChannelLinks,
  getLinkableNotificationChannelIds,
  pluginClaimsNotificationAdapter,
} from '../extensionNotificationLinks';

function plugin(overrides: Partial<PluginInfo> = {}): PluginInfo {
  return {
    id: 'demo',
    name: 'Demo',
    version: '1.0.0',
    source: 'external',
    state: 'enabled',
    desiredEnabled: true,
    reloadable: true,
    packageRoot: '/plugins/demo',
    extensionPoints: ['notification_channel'],
    notificationChannels: ['example_log'],
    description: '',
    author: '',
    settingsCount: 0,
    ...overrides,
  };
}

describe('extensionNotificationLinks', () => {
  it('builds bidirectional settings deep links', () => {
    expect(buildNotificationsChannelHref('example_log')).toBe(
      '/settings?section=notifications&view=channels&channel=example_log',
    );
    expect(buildExtensionsPluginHref('example-notification-channel')).toBe(
      '/settings?section=system_security&view=extensions&plugin=example-notification-channel',
    );
    expect(buildExtensionsHref()).toBe(
      '/settings?section=system_security&view=extensions',
    );
  });

  it('only linkifies enabled plugins with active channel registrations', () => {
    expect(getLinkableNotificationChannelIds(plugin())).toEqual(['example_log']);
    expect(getLinkableNotificationChannelIds(plugin({ state: 'disabled' }))).toEqual([]);
    expect(getLinkableNotificationChannelIds(plugin({
      state: 'failed',
      notificationChannels: [],
    }))).toEqual([]);
    expect(pluginClaimsNotificationAdapter(plugin({
      extensionPoints: ['notification_channel'],
      notificationChannels: [],
      state: 'disabled',
    }))).toBe(true);
  });

  it('flattens multi-channel plugins without inventing unloaded adapters', () => {
    const links = collectPluginNotificationChannelLinks([
      plugin({
        id: 'multi',
        name: 'Multi',
        notificationChannels: ['alpha', 'beta'],
      }),
      plugin({
        id: 'dormant',
        name: 'Dormant',
        state: 'disabled',
        notificationChannels: ['ghost'],
      }),
      plugin({
        id: 'tool-only',
        name: 'Tool Only',
        extensionPoints: ['agent_tool'],
        notificationChannels: [],
      }),
    ]);
    expect(links).toEqual([
      {
        pluginId: 'multi',
        pluginName: 'Multi',
        channelId: 'alpha',
        pluginState: 'enabled',
      },
      {
        pluginId: 'multi',
        pluginName: 'Multi',
        channelId: 'beta',
        pluginState: 'enabled',
      },
    ]);
  });
});
