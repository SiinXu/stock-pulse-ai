// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  buildNotificationEventBindingUpdates,
  buildNotificationEventRoutes,
  eventsForRoutingChannel,
  parseNotificationRouteChannelList,
} from '../notificationEventRoutes';
import { NOTIFICATION_ROUTING_VALUES } from '../notificationChannels';

describe('notificationEventRoutes', () => {
  it('keeps the built-in card, test, and route registry at the 14 backend IDs', () => {
    expect(NOTIFICATION_ROUTING_VALUES).toEqual([
      'wechat', 'feishu', 'telegram', 'dingtalk', 'email', 'discord', 'slack',
      'pushplus', 'pushover', 'ntfy', 'gotify', 'serverchan3', 'astrbot', 'custom',
    ]);
  });

  it('matches backend trim and lowercase parsing', () => {
    expect(parseNotificationRouteChannelList(' EMAIL , feishu, email ')).toEqual([
      'email',
      'feishu',
      'email',
    ]);
    expect(parseNotificationRouteChannelList('')).toEqual([]);
    expect(parseNotificationRouteChannelList(null)).toEqual([]);
  });

  it('deduplicates routes and diagnoses invalid or unconfigured targets', () => {
    const routes = buildNotificationEventRoutes({
      NOTIFICATION_REPORT_CHANNELS: ' EMAIL ,feishu,email,unknown ',
      NOTIFICATION_ALERT_CHANNELS: 'telegram',
      NOTIFICATION_SYSTEM_ERROR_CHANNELS: '',
    }, ['email', 'telegram']);

    expect(routes.report).toEqual({
      configured: ['email', 'feishu'],
      invalid: ['unknown'],
      unconfigured: ['feishu'],
      effective: ['email'],
      usesDefaultFanout: false,
    });
    expect(routes.alert.effective).toEqual(['telegram']);
    expect(routes.system_error).toEqual({
      configured: [],
      invalid: [],
      unconfigured: [],
      effective: ['email', 'telegram'],
      usesDefaultFanout: true,
    });
  });

  it('uses empty-as-all-configured for cards and keeps older-server authority unknown', () => {
    const effective = buildNotificationEventRoutes({}, ['wechat', 'custom']);
    expect(eventsForRoutingChannel(effective, 'custom')).toEqual(['report', 'alert', 'system_error']);

    const unknown = buildNotificationEventRoutes({}, null);
    expect(unknown.report.effective).toBeNull();
    expect(eventsForRoutingChannel(unknown, 'custom')).toEqual([]);
  });

  it('adds verified channels only to explicit routes', () => {
    expect(buildNotificationEventBindingUpdates({
      NOTIFICATION_REPORT_CHANNELS: 'email',
      NOTIFICATION_ALERT_CHANNELS: '',
      NOTIFICATION_SYSTEM_ERROR_CHANNELS: ' EMAIL,feishu ',
    }, 'custom', ['report', 'alert', 'system_error'])).toEqual([
      { key: 'NOTIFICATION_REPORT_CHANNELS', value: 'email,custom' },
      { key: 'NOTIFICATION_SYSTEM_ERROR_CHANNELS', value: 'email,feishu,custom' },
    ]);
  });
});
