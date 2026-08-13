// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiLanguage } from '../i18n/uiText';
import { normalizeUiLanguage } from '../utils/uiLanguage';
import educationHelpEnUS from './educationHelp.en';
import type { EducationHelpTranslationMap } from './educationHelpTranslationTypes';
import type { EducationHelpKey } from './educationHelpKeys';
import educationHelpZhCN from './educationHelp.zh';
import type { SettingsHelpContent, SettingsHelpMap } from './settingsHelpTypes';

type AdditionalEducationLanguage = Exclude<UiLanguage, 'zh' | 'en'>;

const SOURCE_EDUCATION_HELP_MAPS = {
  zh: educationHelpZhCN,
  en: educationHelpEnUS,
} satisfies Record<'zh' | 'en', SettingsHelpMap>;

const TRANSLATION_LOADERS = {
  de: () => import('./educationHelpTranslations/de'),
  es: () => import('./educationHelpTranslations/es'),
  fr: () => import('./educationHelpTranslations/fr'),
  id: () => import('./educationHelpTranslations/id'),
  ja: () => import('./educationHelpTranslations/ja'),
  ko: () => import('./educationHelpTranslations/ko'),
  ms: () => import('./educationHelpTranslations/ms'),
  'zh-TW': () => import('./educationHelpTranslations/zh-TW'),
} satisfies Record<AdditionalEducationLanguage, () => Promise<{ default: EducationHelpTranslationMap }>>;

const translationCache = new Map<AdditionalEducationLanguage, EducationHelpTranslationMap>();

function translatedContent(
  translations: EducationHelpTranslationMap,
  helpKey: EducationHelpKey,
): SettingsHelpContent {
  const value = (field: string): string | undefined => translations[`${helpKey}.${field}`];
  const list = (field: string): string[] | undefined => {
    const values: string[] = [];
    for (let index = 0; ; index += 1) {
      const item = value(`${field}.${index}`);
      if (item === undefined) break;
      values.push(item);
    }
    return values.length > 0 ? values : undefined;
  };

  return {
    title: value('title') ?? helpKey,
    summary: value('summary'),
    usage: value('usage'),
    impact: list('impact'),
    notes: list('notes'),
  };
}

export function getEducationHelpContent(
  helpKey: EducationHelpKey,
  locale?: string | null,
): SettingsHelpContent | null {
  const language = normalizeUiLanguage(locale) ?? 'zh';
  if (language === 'zh' || language === 'en') {
    return SOURCE_EDUCATION_HELP_MAPS[language][helpKey];
  }
  const translations = translationCache.get(language);
  return translations ? translatedContent(translations, helpKey) : null;
}

export async function loadEducationHelpContent(
  helpKey: EducationHelpKey,
  locale?: string | null,
): Promise<SettingsHelpContent> {
  const language = normalizeUiLanguage(locale) ?? 'zh';
  if (language === 'zh' || language === 'en') {
    return SOURCE_EDUCATION_HELP_MAPS[language][helpKey];
  }
  let translations = translationCache.get(language);
  if (!translations) {
    translations = (await TRANSLATION_LOADERS[language]()).default;
    translationCache.set(language, translations);
  }
  return translatedContent(translations, helpKey);
}
