// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { buildSettingsHref } from '../../routing/routes';
import type { PluginInfo } from '../../api/plugins';

/** Canonical plugin extension point for outbound notification adapters. */
export const NOTIFICATION_CHANNEL_EXTENSION_POINT = 'notification_channel';

export type PluginNotificationChannelLink = {
  pluginId: string;
  pluginName: string;
  channelId: string;
  pluginState: PluginInfo['state'];
};

/** Active channel IDs exposed by one plugin list row (never invents IDs). */
export function getActiveNotificationChannelIds(plugin: PluginInfo): string[] {
  return plugin.notificationChannels.filter((channelId) => channelId.trim().length > 0);
}

/** True when the roster claims a notification adapter contribution. */
export function pluginClaimsNotificationAdapter(plugin: PluginInfo): boolean {
  return (
    plugin.extensionPoints.includes(NOTIFICATION_CHANNEL_EXTENSION_POINT)
    || getActiveNotificationChannelIds(plugin).length > 0
  );
}

/**
 * Channels that are safe to deep-link into Notifications.
 * Disabled/failed/registered plugins stay unlinkable so the UI cannot pretend
 * the adapter is connected.
 */
export function getLinkableNotificationChannelIds(plugin: PluginInfo): string[] {
  if (plugin.state !== 'enabled') return [];
  return getActiveNotificationChannelIds(plugin);
}

/** Flatten enabled plugins into Notifications hub cards. */
export function collectPluginNotificationChannelLinks(
  plugins: readonly PluginInfo[],
): PluginNotificationChannelLink[] {
  const links: PluginNotificationChannelLink[] = [];
  for (const plugin of plugins) {
    for (const channelId of getLinkableNotificationChannelIds(plugin)) {
      links.push({
        pluginId: plugin.id,
        pluginName: plugin.name || plugin.id,
        channelId,
        pluginState: plugin.state,
      });
    }
  }
  return links;
}

export function buildNotificationsChannelHref(channelId: string): string {
  return buildSettingsHref({
    section: 'notifications',
    view: 'channels',
    channel: channelId,
  });
}

export function buildExtensionsPluginHref(pluginId: string): string {
  return buildSettingsHref({
    section: 'system_security',
    view: 'extensions',
    plugin: pluginId,
  });
}

export function buildExtensionsHref(): string {
  return buildSettingsHref({
    section: 'system_security',
    view: 'extensions',
  });
}
