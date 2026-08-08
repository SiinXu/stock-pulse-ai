// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { SetupStatusCheck } from '../../types/systemConfig';
import type { UiTextKey } from '../../i18n/uiText';
import {
  SETTINGS_SECTION_IDS,
  SETTINGS_VIEW_IDS,
  buildSettingsHref,
} from '../../routing/routes';
import { legacyToSectionView } from '../settings/settingsInformationArchitecture';

/** Stable setup-status check keys known to the Web mapping layer. */
export const SETUP_CHECK_LABEL_KEYS: Record<string, UiTextKey> = {
  llm_primary: 'home.setupCheck.llm_primary',
  llm_agent: 'home.setupCheck.llm_agent',
  stock_list: 'home.setupCheck.stock_list',
  notification: 'home.setupCheck.notification',
  storage: 'home.setupCheck.storage',
};

/** Goal-language labels for the Home readiness card (prefer these over config jargon). */
export const SETUP_CHECK_GOAL_LABEL_KEYS: Record<string, UiTextKey> = {
  llm_primary: 'home.readiness.goal.llm_primary',
  llm_agent: 'home.readiness.goal.llm_agent',
  stock_list: 'home.readiness.goal.stock_list',
  notification: 'home.readiness.goal.notification',
  storage: 'home.readiness.goal.storage',
};

/** One primary CTA label key per check when action is needed. */
export const SETUP_CHECK_ACTION_LABEL_KEYS: Record<string, UiTextKey> = {
  llm_primary: 'home.readiness.action.llm_primary',
  llm_agent: 'home.readiness.action.llm_agent',
  stock_list: 'home.readiness.action.stock_list',
  notification: 'home.readiness.action.notification',
  storage: 'home.readiness.action.storage',
};

export type SetupCheckTone = 'success' | 'warning' | 'danger' | 'neutral';

export function resolveSetupCheckLabel(
  check: Pick<SetupStatusCheck, 'key' | 'title'>,
  t: (key: UiTextKey, params?: Record<string, string | number>) => string,
  options?: { goalLanguage?: boolean },
): string {
  if (options?.goalLanguage) {
    const goalKey = SETUP_CHECK_GOAL_LABEL_KEYS[check.key];
    if (goalKey) return t(goalKey);
  }
  const textKey = SETUP_CHECK_LABEL_KEYS[check.key];
  return textKey ? t(textKey) : check.title;
}

export function resolveSetupCheckTone(check: SetupStatusCheck): SetupCheckTone {
  if (check.status === 'configured' || check.status === 'inherited') {
    return 'success';
  }
  if (check.status === 'needs_action') {
    return check.required ? 'danger' : 'warning';
  }
  return 'neutral';
}

export function resolveSetupCheckStatusLabel(
  check: SetupStatusCheck,
  t: (key: UiTextKey, params?: Record<string, string | number>) => string,
): string {
  if (check.status === 'configured') return t('settings.setupStatusConfigured');
  if (check.status === 'inherited') return t('settings.setupStatusInherited');
  if (check.status === 'needs_action') return t('settings.setupStatusNeedsAction');
  return t('settings.setupStatusOptional');
}

/**
 * Exactly one primary fix surface per known check key.
 * Unknown keys fall back to the backend category → section/view mapping.
 */
export function resolveSetupCheckHref(check: Pick<SetupStatusCheck, 'key' | 'category'>): string {
  switch (check.key) {
    case 'llm_primary':
      return buildSettingsHref({
        section: SETTINGS_SECTION_IDS.aiModels,
        view: SETTINGS_VIEW_IDS.aiModels.connections,
        source: 'home_readiness',
      });
    case 'llm_agent':
      return buildSettingsHref({
        section: 'agent_behavior',
        view: 'execution',
        source: 'home_readiness',
      });
    case 'stock_list':
      return buildSettingsHref({
        section: 'overview',
        view: 'readiness',
        source: 'home_readiness',
      });
    case 'notification':
      return buildSettingsHref({
        section: 'notifications',
        view: 'channels',
        source: 'home_readiness',
      });
    case 'storage':
      return buildSettingsHref({
        section: 'system_security',
        view: 'general',
        source: 'home_readiness',
      });
    default: {
      const target = legacyToSectionView(check.category, null);
      return buildSettingsHref({
        section: target.section,
        view: target.view,
        source: 'home_readiness',
      });
    }
  }
}

export function resolveSetupCheckActionLabel(
  check: Pick<SetupStatusCheck, 'key'>,
  t: (key: UiTextKey, params?: Record<string, string | number>) => string,
): string {
  const key = SETUP_CHECK_ACTION_LABEL_KEYS[check.key];
  return key ? t(key) : t('home.readiness.action.generic');
}

/** Prefer the readiness signals called out by issue #797 when present. */
export const HOME_READINESS_PRIORITY_KEYS = [
  'llm_primary',
  'stock_list',
  'storage',
  'llm_agent',
  'notification',
] as const;

export function orderSetupChecksForHome(checks: SetupStatusCheck[]): SetupStatusCheck[] {
  const rank = new Map<string, number>(
    HOME_READINESS_PRIORITY_KEYS.map((key, index) => [key, index]),
  );
  return [...checks].sort((left, right) => {
    const leftRank = rank.get(left.key) ?? HOME_READINESS_PRIORITY_KEYS.length;
    const rightRank = rank.get(right.key) ?? HOME_READINESS_PRIORITY_KEYS.length;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return left.key.localeCompare(right.key);
  });
}
