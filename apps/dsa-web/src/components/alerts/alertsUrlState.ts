// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Alerts workspace URL schema (UI-03A / issue #879 A1).
 *
 * Owns shareable filter, pagination, and rule-selection state for the Alerts
 * workspace embedded in Signal Center. Signal Center itself owns the primary
 * `tab`, history subtab, scope, and trigger-selection keys.
 *
 * History policy:
 * - Filters and pagination → replace
 * - Selected rule (`alert`) → push (Back closes)
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
import { SIGNAL_CENTER_ALERTS_ROUTE_QUERY_KEYS } from '../../routing/routes';

export type AlertsUrlView = 'rules' | 'history' | 'notifications';

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
  enabled: enumParam({
    name: SIGNAL_CENTER_ALERTS_ROUTE_QUERY_KEYS.rulesEnabled,
    values: ENABLED_FILTERS,
    default: 'all',
    history: 'replace',
  }),
  type: enumParam({
    name: SIGNAL_CENTER_ALERTS_ROUTE_QUERY_KEYS.rulesType,
    values: ALERT_TYPE_FILTERS,
    default: 'all',
    history: 'replace',
  }),
  page: numberParam({
    name: SIGNAL_CENTER_ALERTS_ROUTE_QUERY_KEYS.rulesPage,
    default: 1,
    history: 'replace',
    min: 1,
  }),
  historyPage: numberParam({
    name: SIGNAL_CENTER_ALERTS_ROUTE_QUERY_KEYS.triggerPage,
    default: 1,
    history: 'replace',
    min: 1,
  }),
  notificationsPage: numberParam({
    name: SIGNAL_CENTER_ALERTS_ROUTE_QUERY_KEYS.notificationPage,
    default: 1,
    history: 'replace',
    min: 1,
  }),
  channel: stringParam({
    name: SIGNAL_CENTER_ALERTS_ROUTE_QUERY_KEYS.notificationChannel,
    default: 'all',
    history: 'replace',
    omitEmpty: false,
  }),
  success: enumParam({
    name: SIGNAL_CENTER_ALERTS_ROUTE_QUERY_KEYS.notificationSuccess,
    values: NOTIFICATION_SUCCESS_FILTERS,
    default: 'all',
    history: 'replace',
  }),
  /** Selected rule id for the edit modal (push so Back closes). */
  alert: numberParam({
    name: SIGNAL_CENTER_ALERTS_ROUTE_QUERY_KEYS.alert,
    default: null,
    history: 'push',
    min: 1,
  }),
});

export type AlertsUrlState = InferUrlState<typeof alertsUrlSchema>;
export type AlertsUrlPatch = UrlStatePatch<typeof alertsUrlSchema>;
export type NotificationSuccessFilter = (typeof NOTIFICATION_SUCCESS_FILTERS)[number];
