// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { UiLanguage } from '../../i18n/uiText';
import { ALERT_TRIGGER_TEXT } from '../../locales/alerts';

/**
 * User-facing alert trigger status. Reuses ALERT_TRIGGER_TEXT.statuses.
 * Unknown values keep the raw code.
 */
export function formatAlertTriggerStatus(
  status: string | null | undefined,
  language: UiLanguage,
): string {
  if (status == null || status === '') {
    return '--';
  }
  const labels = ALERT_TRIGGER_TEXT[language].statuses;
  return labels[status as keyof typeof labels] ?? status;
}
