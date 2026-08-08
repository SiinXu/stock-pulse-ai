// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/** Backend routing keys that select delivery channels per event class. */
export const NOTIFICATION_EVENT_ROUTE_KEYS = [
  'NOTIFICATION_REPORT_CHANNELS',
  'NOTIFICATION_ALERT_CHANNELS',
  'NOTIFICATION_SYSTEM_ERROR_CHANNELS',
] as const;

export type NotificationEventRouteKey = (typeof NOTIFICATION_EVENT_ROUTE_KEYS)[number];

export type NotificationEventKind = 'report' | 'alert' | 'system_error';

export type NotificationEventRoutes = {
  report: readonly string[];
  alert: readonly string[];
  system_error: readonly string[];
};

const KEY_TO_EVENT: Record<NotificationEventRouteKey, NotificationEventKind> = {
  NOTIFICATION_REPORT_CHANNELS: 'report',
  NOTIFICATION_ALERT_CHANNELS: 'alert',
  NOTIFICATION_SYSTEM_ERROR_CHANNELS: 'system_error',
};

/** Split comma-separated multi-select routing values. */
export function parseNotificationRouteChannelList(value: unknown): string[] {
  return String(value ?? '')
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
}

/**
 * Build the event→channel matrix from a flat config value map.
 * Empty lists mean “not explicitly set” (backend may fan out to all configured).
 */
export function buildNotificationEventRoutes(
  valuesByKey: Readonly<Record<string, string | undefined | null>>,
): NotificationEventRoutes {
  const routes: NotificationEventRoutes = {
    report: [],
    alert: [],
    system_error: [],
  };
  for (const key of NOTIFICATION_EVENT_ROUTE_KEYS) {
    const event = KEY_TO_EVENT[key];
    routes[event] = parseNotificationRouteChannelList(valuesByKey[key]);
  }
  return routes;
}

/** Events that currently list the given routing channel value. */
export function eventsForRoutingChannel(
  routes: NotificationEventRoutes | null | undefined,
  routingValue: string,
): NotificationEventKind[] {
  if (!routes) return [];
  const kinds: NotificationEventKind[] = [];
  if (routes.report.includes(routingValue)) kinds.push('report');
  if (routes.alert.includes(routingValue)) kinds.push('alert');
  if (routes.system_error.includes(routingValue)) kinds.push('system_error');
  return kinds;
}
