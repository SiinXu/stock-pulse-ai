// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { NOTIFICATION_ROUTING_VALUES } from './notificationChannels';

/** Backend routing keys that select delivery channels per event class. */
export const NOTIFICATION_EVENT_ROUTE_KEYS = [
  'NOTIFICATION_REPORT_CHANNELS',
  'NOTIFICATION_ALERT_CHANNELS',
  'NOTIFICATION_SYSTEM_ERROR_CHANNELS',
] as const;

export type NotificationEventRouteKey = (typeof NOTIFICATION_EVENT_ROUTE_KEYS)[number];

export type NotificationEventKind = 'report' | 'alert' | 'system_error';

export type NotificationEventRouteResolution = {
  /** Explicit valid route tokens after backend-equivalent normalization. */
  configured: readonly string[];
  /** Tokens rejected by the backend routing registry. */
  invalid: readonly string[];
  /** Valid route tokens that do not currently identify a configured channel. */
  unconfigured: readonly string[];
  /** Effective live targets. Null means an older backend did not expose authority. */
  effective: readonly string[] | null;
  /** Empty persisted value uses the backend's all-configured fan-out behavior. */
  usesDefaultFanout: boolean;
};

export type NotificationEventRoutes = Record<
  NotificationEventKind,
  NotificationEventRouteResolution
>;

const EVENT_TO_KEY: Record<NotificationEventKind, NotificationEventRouteKey> = {
  report: 'NOTIFICATION_REPORT_CHANNELS',
  alert: 'NOTIFICATION_ALERT_CHANNELS',
  system_error: 'NOTIFICATION_SYSTEM_ERROR_CHANNELS',
};

/** Match route_config.py: trim, lowercase, drop blanks, and preserve input order. */
export function parseNotificationRouteChannelList(value: unknown): string[] {
  return String(value ?? '')
    .split(',')
    .map((entry) => entry.trim().toLowerCase())
    .filter(Boolean);
}

function unique(values: readonly string[]): string[] {
  return values.filter((value, index) => values.indexOf(value) === index);
}

/**
 * Resolve persisted route strings against the backend's live configured-channel
 * snapshot. Draft values must be resolved separately and labelled pending.
 */
export function buildNotificationEventRoutes(
  valuesByKey: Readonly<Record<string, string | undefined | null>>,
  configuredChannels: readonly string[] | null = null,
): NotificationEventRoutes {
  const allowed = new Set(NOTIFICATION_ROUTING_VALUES);
  const normalizedConfigured = configuredChannels === null
    ? null
    : unique(parseNotificationRouteChannelList(configuredChannels.join(',')))
      .filter((channel) => allowed.has(channel));
  const configuredSet = normalizedConfigured === null ? null : new Set(normalizedConfigured);

  const resolve = (key: NotificationEventRouteKey): NotificationEventRouteResolution => {
    const rawTokens = parseNotificationRouteChannelList(valuesByKey[key]);
    const usesDefaultFanout = rawTokens.length === 0;
    const configured = unique(rawTokens.filter((channel) => allowed.has(channel)));
    const invalid = unique(rawTokens.filter((channel) => !allowed.has(channel)));
    const unconfigured = configuredSet === null
      ? []
      : configured.filter((channel) => !configuredSet.has(channel));
    const effective = configuredSet === null
      ? null
      : usesDefaultFanout
        ? normalizedConfigured
        : configured.filter((channel) => configuredSet.has(channel));
    return { configured, invalid, unconfigured, effective, usesDefaultFanout };
  };

  return {
    report: resolve('NOTIFICATION_REPORT_CHANNELS'),
    alert: resolve('NOTIFICATION_ALERT_CHANNELS'),
    system_error: resolve('NOTIFICATION_SYSTEM_ERROR_CHANNELS'),
  };
}

/** Events that currently deliver to the given routing channel value. */
export function eventsForRoutingChannel(
  routes: NotificationEventRoutes | null | undefined,
  routingValue: string,
): NotificationEventKind[] {
  if (!routes) return [];
  const kinds: NotificationEventKind[] = [];
  if (routes.report.effective?.includes(routingValue)) kinds.push('report');
  if (routes.alert.effective?.includes(routingValue)) kinds.push('alert');
  if (routes.system_error.effective?.includes(routingValue)) kinds.push('system_error');
  return kinds;
}

/** Add a verified channel to explicit routes; empty routes already fan out to it. */
export function buildNotificationEventBindingUpdates(
  valuesByKey: Readonly<Record<string, string | undefined | null>>,
  routingValue: string,
  kinds: readonly NotificationEventKind[],
): Array<{ key: NotificationEventRouteKey; value: string }> {
  const updates: Array<{ key: NotificationEventRouteKey; value: string }> = [];
  for (const kind of kinds) {
    const key = EVENT_TO_KEY[kind];
    const current = unique(parseNotificationRouteChannelList(valuesByKey[key]));
    if (!current.length || current.includes(routingValue)) continue;
    updates.push({ key, value: [...current, routingValue].join(',') });
  }
  return updates;
}
