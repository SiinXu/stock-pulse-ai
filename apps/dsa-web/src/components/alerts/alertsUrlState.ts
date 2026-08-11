// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Alerts workspace URL schema (UI-03A / issue #879 A1).
 *
 * Owns shareable filter, tab, pagination, and selection state for the
 * standalone Alerts surface (AlertsPage / non-embedded AlertsWorkspace).
 *
 * History policy:
 * - Filters, tabs, pagination → replace
 * - Selected rule (`alert`) / selected trigger (`trigger`) → push (Back closes)
 *
 * Embedded Signal Center mounts keep local React state for these fields so
 * Alerts does not fight Signal Center keys (`view` / `page` / `trigger` / `tab`).
 */
import type { AlertType } from '../../types/alerts';
import {
  defineUrlStateSchema,
  enumParam,
  numberParam,
  stringParam,
  type InferUrlState,
  type UrlStatePatch,
} from '../../utils/urlState';

export const ALERT_VIEWS = ['rules', 'history', 'notifications'] as const;
export type AlertsUrlView = (typeof ALERT_VIEWS)[number];

const ENABLED_FILTERS = ['all', 'enabled', 'disabled'] as const;

const ALERT_TYPES = [
  'price_cross',
  'price_change_percent',
  'volume_spike',
  'ma_price_cross',
  'rsi_threshold',
  'macd_cross',
  'kdj_cross',
  'cci_threshold',
  'portfolio_stop_loss',
  'portfolio_concentration',
  'portfolio_drawdown',
  'portfolio_price_stale',
  'market_light_status',
  'market_light_score_drop',
] as const satisfies readonly AlertType[];

const ALERT_TYPE_FILTERS = ['all', ...ALERT_TYPES] as const;

const NOTIFICATION_SUCCESS_FILTERS = ['all', 'success', 'failure'] as const;

export const alertsUrlSchema = defineUrlStateSchema({
  view: enumParam({
    name: 'view',
    values: ALERT_VIEWS,
    default: 'rules',
    history: 'replace',
  }),
  enabled: enumParam({
    name: 'enabled',
    values: ENABLED_FILTERS,
    default: 'all',
    history: 'replace',
  }),
  type: enumParam({
    name: 'type',
    values: ALERT_TYPE_FILTERS,
    default: 'all',
    history: 'replace',
  }),
  page: numberParam({
    name: 'page',
    default: 1,
    history: 'replace',
    min: 1,
  }),
  historyPage: numberParam({
    name: 'historyPage',
    default: 1,
    history: 'replace',
    min: 1,
  }),
  notificationsPage: numberParam({
    name: 'notificationsPage',
    default: 1,
    history: 'replace',
    min: 1,
  }),
  channel: stringParam({
    name: 'channel',
    default: 'all',
    history: 'replace',
    omitEmpty: false,
  }),
  success: enumParam({
    name: 'success',
    values: NOTIFICATION_SUCCESS_FILTERS,
    default: 'all',
    history: 'replace',
  }),
  /** Selected rule id for the edit modal (push so Back closes). */
  alert: numberParam({
    name: 'alert',
    default: null,
    history: 'push',
    min: 1,
  }),
  /** Selected trigger highlight on the history tab (push so Back clears). */
  trigger: numberParam({
    name: 'trigger',
    default: null,
    history: 'push',
    min: 1,
  }),
});

export type AlertsUrlState = InferUrlState<typeof alertsUrlSchema>;
export type AlertsUrlPatch = UrlStatePatch<typeof alertsUrlSchema>;
export type NotificationSuccessFilter = (typeof NOTIFICATION_SUCCESS_FILTERS)[number];
