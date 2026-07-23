import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../i18n/uiText';
import { normalizeUiLanguage } from '../utils/uiLanguage';
import settingsHelpEnUS from './settingsHelp.en';
import settingsHelpZhCN from './settingsHelp.zh';
import type { SettingsHelpContent, SettingsHelpMap } from './settingsHelpTypes';

export type { SettingsHelpContent } from './settingsHelpTypes';

const SETTINGS_HELP_MAPS: Record<UiLanguage, SettingsHelpMap> = createUiLanguageRecord(
  'locales.settingsHelp.SETTINGS_HELP_MAPS',
  { zh: settingsHelpZhCN, en: settingsHelpEnUS },
);

const SETTINGS_HELP_FALLBACK_TITLES: Record<UiLanguage, string> = createUiLanguageRecord(
  'locales.settingsHelp.SETTINGS_HELP_FALLBACK_TITLES',
  { zh: '配置说明', en: 'Configuration help' },
);

function getPreferredHelpLanguage(locale?: string | null): UiLanguage {
  return normalizeUiLanguage(locale) ?? 'zh';
}

export function getSettingsHelpContent(
  helpKey?: string | null,
  fallbackDescription?: string,
  locale?: string | null,
): SettingsHelpContent | null {
  if (!helpKey) {
    return null;
  }

  const language = getPreferredHelpLanguage(locale);
  const localized = SETTINGS_HELP_MAPS[language][helpKey];
  if (localized) {
    return localized;
  }

  if (fallbackDescription) {
    return {
      title: SETTINGS_HELP_FALLBACK_TITLES[language],
      summary: fallbackDescription,
    };
  }

  return null;
}
