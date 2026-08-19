// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { UiLanguage } from '../../i18n/uiText';
import {
  ALERT_HISTORY_CONTROLS_TEXT,
  ALERT_LIST_TEXT,
  ALERT_METRIC_LABELS,
  ALERT_NOTIFICATION_CHANNEL_LABELS,
  ALERT_NOTIFICATION_STATUS_LABELS,
  ALERT_TRIGGER_TEXT,
} from '../../locales/alerts';
import type { AlertNotificationItem } from '../../types/alerts';
import {
  formatEmptyDisplay,
  formatLabeledDiagnostic,
  formatUnknownMachineCode,
  formatUnknownStatusCode,
} from './unknownCode';

/**
 * User-facing alert trigger status. Reuses ALERT_TRIGGER_TEXT.statuses.
 * Unknown values use a localized diagnostic that keeps a sanitized code.
 */
export function formatAlertTriggerStatus(
  status: string | null | undefined,
  language: UiLanguage,
): string {
  if (status == null || status === '') {
    return '--';
  }
  const labels = ALERT_TRIGGER_TEXT[language].statuses;
  return labels[status as keyof typeof labels] ?? formatUnknownStatusCode(status, language);
}

export function formatAlertTriggerReason(
  reason: string | null | undefined,
  diagnostics: string | null | undefined,
  language: UiLanguage,
): string {
  const text = ALERT_TRIGGER_TEXT[language];
  const primary = String(reason ?? '').trim();
  if (primary) {
    const statusLabel = text.statuses[primary as keyof typeof text.statuses];
    if (statusLabel) return statusLabel;
    return formatLabeledDiagnostic(primary, language);
  }
  const fallback = String(diagnostics ?? '').trim();
  if (fallback) return formatLabeledDiagnostic(fallback, language);
  return '--';
}

export function formatAlertParameterMetric(
  metric: string,
  language: UiLanguage,
): string {
  return ALERT_METRIC_LABELS[language][metric] ?? formatUnknownMachineCode(metric, language);
}

export function formatAlertWatchlistTarget(
  target: string,
  language: UiLanguage,
): string {
  if (target === 'default') return ALERT_LIST_TEXT[language].defaultWatchlist;
  return target;
}

export function formatAlertNotificationChannel(
  channel: string | null | undefined,
  language: UiLanguage,
): string {
  if (channel == null || channel === '') return '--';
  return ALERT_NOTIFICATION_CHANNEL_LABELS[language][channel]
    ?? formatUnknownMachineCode(channel, language);
}

export function formatAlertNotificationStatus(
  notification: Pick<AlertNotificationItem, 'success' | 'errorCode'>,
  language: UiLanguage,
): string {
  const labels = ALERT_NOTIFICATION_STATUS_LABELS[language];
  if (notification.success) return labels.success;
  if (notification.errorCode && labels[notification.errorCode]) {
    return labels[notification.errorCode];
  }
  return labels.failure;
}

export function formatAlertNotificationErrorCode(
  errorCode: string | null | undefined,
  language: UiLanguage,
): string {
  if (errorCode == null || errorCode === '') return '--';
  const labels = ALERT_NOTIFICATION_STATUS_LABELS[language];
  return labels[errorCode] ?? formatUnknownMachineCode(errorCode, language);
}

export function formatAlertTestMessage(
  message: string | null | undefined,
  language: UiLanguage,
): string {
  if (message == null || String(message).trim() === '') {
    return formatEmptyDisplay();
  }
  return formatLabeledDiagnostic(message, language);
}

export function formatAlertNotificationDiagnostics(
  diagnostics: string | null | undefined,
  language: UiLanguage,
): string {
  if (diagnostics == null || diagnostics === '') return '--';
  return formatLabeledDiagnostic(diagnostics, language);
}

export function formatAlertTestStatus(
  status: string | null | undefined,
  language: UiLanguage,
): string {
  if (status == null || status === '') return '--';
  const labels = ALERT_HISTORY_CONTROLS_TEXT[language].testStatuses;
  return labels[status as keyof typeof labels] ?? formatUnknownStatusCode(status, language);
}
