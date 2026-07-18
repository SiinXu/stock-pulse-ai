// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiTextKey } from '../../i18n/uiText';

export interface NotificationFieldGroup {
  id: string;
  titleKey: UiTextKey;
  keys: string[];
}

export const NOTIFICATION_FIELD_GROUPS: NotificationFieldGroup[] = [
  {
    id: 'routing',
    titleKey: 'settings.notificationGroupRouting',
    keys: [
      'NOTIFICATION_REPORT_CHANNELS',
      'NOTIFICATION_ALERT_CHANNELS',
      'NOTIFICATION_SYSTEM_ERROR_CHANNELS',
      'MERGE_EMAIL_NOTIFICATION',
    ],
  },
  {
    id: 'report',
    titleKey: 'settings.notificationGroupReport',
    keys: [
      'REPORT_TYPE',
      'REPORT_LANGUAGE',
      'REPORT_TEMPLATES_DIR',
      'REPORT_SUMMARY_ONLY',
      'REPORT_SHOW_LLM_MODEL',
      'REPORT_INTEGRITY_ENABLED',
      'REPORT_INTEGRITY_RETRY',
      'REPORT_RENDERER_ENABLED',
      'REPORT_HISTORY_COMPARE_N',
    ],
  },
  {
    id: 'behavior',
    titleKey: 'settings.notificationGroupBehavior',
    keys: [
      'SINGLE_STOCK_NOTIFY',
      'WEBHOOK_VERIFY_SSL',
      'NOTIFICATION_DEDUP_TTL_SECONDS',
      'NOTIFICATION_COOLDOWN_SECONDS',
      'NOTIFICATION_QUIET_HOURS',
      'NOTIFICATION_TIMEZONE',
      'NOTIFICATION_MIN_SEVERITY',
      'NOTIFICATION_DAILY_DIGEST_ENABLED',
    ],
  },
];

const OTHER_GROUP_ID = 'other';

export const NOTIFICATION_FIELD_GROUP_ORDER: Array<{ id: string; titleKey: UiTextKey }> = [
  ...NOTIFICATION_FIELD_GROUPS.map((group) => ({ id: group.id, titleKey: group.titleKey })),
  { id: OTHER_GROUP_ID, titleKey: 'settings.notificationGroupOther' },
];

const KEY_TO_GROUP = new Map<string, string>();
const KEY_ORDER = new Map<string, number>();
for (const group of NOTIFICATION_FIELD_GROUPS) {
  for (const key of group.keys) {
    KEY_TO_GROUP.set(key, group.id);
    KEY_ORDER.set(key, KEY_ORDER.size);
  }
}

export function getNotificationFieldGroupId(key: string): string {
  return KEY_TO_GROUP.get(key) ?? OTHER_GROUP_ID;
}

export function getNotificationFieldOrder(key: string): number {
  return KEY_ORDER.get(key) ?? Number.MAX_SAFE_INTEGER;
}
