export const UI_LANGUAGES = [
  'zh',
  'zh-TW',
  'en',
  'ja',
  'ko',
  'de',
  'es',
  'ms',
  'fr',
  'id',
] as const;

export type UiLanguage = (typeof UI_LANGUAGES)[number];

export type UiLanguageMetadata = {
  htmlLang: string;
  intlLocale: string;
  nativeLabel: string;
  shortLabel: string;
};

export const UI_LANGUAGE_METADATA = {
  zh: { htmlLang: 'zh-CN', intlLocale: 'zh-CN', nativeLabel: '简体中文', shortLabel: '简' },
  'zh-TW': { htmlLang: 'zh-TW', intlLocale: 'zh-TW', nativeLabel: '繁體中文', shortLabel: '繁' },
  en: { htmlLang: 'en', intlLocale: 'en-US', nativeLabel: 'English', shortLabel: 'EN' },
  ja: { htmlLang: 'ja', intlLocale: 'ja-JP', nativeLabel: '日本語', shortLabel: '日' },
  ko: { htmlLang: 'ko', intlLocale: 'ko-KR', nativeLabel: '한국어', shortLabel: '한' },
  de: { htmlLang: 'de', intlLocale: 'de-DE', nativeLabel: 'Deutsch', shortLabel: 'DE' },
  es: { htmlLang: 'es', intlLocale: 'es-ES', nativeLabel: 'Español', shortLabel: 'ES' },
  ms: { htmlLang: 'ms', intlLocale: 'ms-MY', nativeLabel: 'Bahasa Melayu', shortLabel: 'MS' },
  fr: { htmlLang: 'fr', intlLocale: 'fr-FR', nativeLabel: 'Français', shortLabel: 'FR' },
  id: { htmlLang: 'id', intlLocale: 'id-ID', nativeLabel: 'Bahasa Indonesia', shortLabel: 'ID' },
} as const satisfies Record<UiLanguage, UiLanguageMetadata>;

export const ADDITIONAL_UI_LANGUAGES = UI_LANGUAGES.filter(
  (language): language is Exclude<UiLanguage, 'zh' | 'en'> => language !== 'zh' && language !== 'en',
);

export function prefersChineseContent(language: UiLanguage): boolean {
  return language === 'zh' || language === 'zh-TW';
}

export function localeIndependent<T>(value: T): Record<UiLanguage, T> {
  return Object.fromEntries(UI_LANGUAGES.map((language) => [language, value])) as Record<UiLanguage, T>;
}
