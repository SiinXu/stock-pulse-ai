// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiLanguage } from '../../i18n/uiLanguages';
import { getLoadedUiLanguageTranslations } from '../../i18n/translations';
import { buildSettingsHref } from '../../routing/routes';
import { SETTINGS_FIELD_QUERY_KEY } from '../settings/settingsFieldGroupDisclosure';

export const LOCAL_ONLY_MODE_FIELD_KEY = 'LOCAL_ONLY_MODE';

const LOCAL_ONLY_FIELD_TITLE_KEY = 'utils.systemConfigI18n.fieldTitleMaps.LOCAL_ONLY_MODE';

export function localOnlyModeFieldTitle(language: UiLanguage): string {
  if (language === 'zh') {
    return '仅本地模式';
  }
  if (language === 'en') {
    return 'Local Only Mode';
  }
  const translated = getLoadedUiLanguageTranslations(language)?.[
    LOCAL_ONLY_FIELD_TITLE_KEY as keyof NonNullable<ReturnType<typeof getLoadedUiLanguageTranslations>>
  ];
  return translated && translated.trim() !== '' ? translated : 'Local Only Mode';
}

/** Settings → Auth & Security, focusing the Local Only Mode field. */
export function buildLocalOnlyModeSettingsHref(): string {
  const href = buildSettingsHref({
    section: 'system_security',
    view: 'security',
  });
  const separator = href.includes('?') ? '&' : '?';
  return `${href}${separator}${SETTINGS_FIELD_QUERY_KEY}=${encodeURIComponent(LOCAL_ONLY_MODE_FIELD_KEY)}`;
}
