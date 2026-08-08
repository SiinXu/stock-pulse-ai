// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  buildNotificationEventRoutes,
  eventsForRoutingChannel,
  parseNotificationRouteChannelList,
} from '../notificationEventRoutes';

describe('notificationEventRoutes', () => {
  it('parses comma-separated routing lists', () => {
    expect(parseNotificationRouteChannelList('email, feishu, custom')).toEqual([
      'email',
      'feishu',
      'custom',
    ]);
    expect(parseNotificationRouteChannelList('')).toEqual([]);
    expect(parseNotificationRouteChannelList(null)).toEqual([]);
  });

  it('builds the event matrix from config values', () => {
    const routes = buildNotificationEventRoutes({
      NOTIFICATION_REPORT_CHANNELS: 'email,feishu',
      NOTIFICATION_ALERT_CHANNELS: 'telegram',
      NOTIFICATION_SYSTEM_ERROR_CHANNELS: '',
    });
    expect(routes.report).toEqual(['email', 'feishu']);
    expect(routes.alert).toEqual(['telegram']);
    expect(routes.system_error).toEqual([]);
  });

  it('lists events for a routing channel value', () => {
    const routes = buildNotificationEventRoutes({
      NOTIFICATION_REPORT_CHANNELS: 'email,custom',
      NOTIFICATION_ALERT_CHANNELS: 'custom',
      NOTIFICATION_SYSTEM_ERROR_CHANNELS: 'wechat',
    });
    expect(eventsForRoutingChannel(routes, 'custom')).toEqual(['report', 'alert']);
    expect(eventsForRoutingChannel(routes, 'wechat')).toEqual(['system_error']);
    expect(eventsForRoutingChannel(routes, 'dingtalk')).toEqual([]);
  });
});
