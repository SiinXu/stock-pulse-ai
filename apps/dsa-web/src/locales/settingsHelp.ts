import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../i18n/uiText';
import { getFieldTitle } from '../utils/systemConfigI18n';
import { normalizeUiLanguage } from '../utils/uiLanguage';
import settingsHelpEnUS from './settingsHelp.en';
import settingsHelpZhCN from './settingsHelp.zh';
import type { SettingsHelpDefinition, SettingsHelpSourceMap } from './settingsHelpSourceTypes';
import type { SettingsHelpContent } from './settingsHelpTypes';
import {
  getSkillRetrievalSettingsHelp,
  isSkillRetrievalHelpKey,
} from './skillRetrievalSettingsHelp';

export type { SettingsHelpContent } from './settingsHelpTypes';

const SETTINGS_HELP_MAPS: Record<UiLanguage, SettingsHelpSourceMap> = createUiLanguageRecord(
  'locales.settingsHelp.SETTINGS_HELP_MAPS',
  { zh: settingsHelpZhCN, en: settingsHelpEnUS },
);

const SETTINGS_HELP_SCHEMA_DESCRIPTION_ONLY: SettingsHelpSourceMap = {
  'settings.agent.multi_model_consensus': {},
};

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
  const localized = isSkillRetrievalHelpKey(helpKey)
    ? getSkillRetrievalSettingsHelp(language)
    : SETTINGS_HELP_SCHEMA_DESCRIPTION_ONLY[helpKey]
      ?? SETTINGS_HELP_MAPS[language][helpKey]
      ?? (!helpKey.includes('.') ? findSettingsHelpByFieldKey(helpKey, language) : null);
  if (localized && Object.keys(localized).length > 0) {
    const fieldKey = helpKey.split('.').pop() ?? helpKey;
    return {
      ...localized,
      title: localized.title
        ?? getFieldTitle(fieldKey, SETTINGS_HELP_FALLBACK_TITLES[language], language),
    };
  }

  if (fallbackDescription) {
    return {
      title: SETTINGS_HELP_FALLBACK_TITLES[language],
      summary: fallbackDescription,
    };
  }

  return null;
}

function findSettingsHelpByFieldKey(
  fieldKey: string,
  language: UiLanguage,
): SettingsHelpDefinition | null {
  const suffix = `.${fieldKey}`;
  let match: SettingsHelpDefinition | null = null;

  for (const [helpKey, content] of Object.entries(SETTINGS_HELP_MAPS[language])) {
    if (!helpKey.endsWith(suffix)) {
      continue;
    }
    if (match) {
      return null;
    }
    match = content;
  }

  return match;
}
