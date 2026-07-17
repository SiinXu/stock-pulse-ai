import { ADDITIONAL_UI_LANGUAGES, type UiLanguage } from '../uiLanguages';
import type { UiTranslationKey } from './en';

export { SOURCE_UI_TRANSLATIONS, UI_TRANSLATION_KEYS, type UiTranslationKey } from './en';

export type AdditionalUiLanguage = Exclude<UiLanguage, 'zh' | 'en'>;
export type UiTranslationBundle = Readonly<Record<UiTranslationKey, string>>;
type UiTranslationModule = { translations: UiTranslationBundle };

const TRANSLATION_LOADERS: Record<AdditionalUiLanguage, () => Promise<UiTranslationModule>> = {
  "zh-TW": () => import('./zh-TW'),
  "ja": () => import('./ja'),
  "ko": () => import('./ko'),
  "de": () => import('./de'),
  "es": () => import('./es'),
  "ms": () => import('./ms'),
  "fr": () => import('./fr'),
  "id": () => import('./id'),
};

const loadedTranslations = new Map<AdditionalUiLanguage, UiTranslationBundle>();
const pendingTranslations = new Map<AdditionalUiLanguage, Promise<void>>();

function isAdditionalUiLanguage(language: UiLanguage): language is AdditionalUiLanguage {
  return language !== 'zh' && language !== 'en';
}

export async function loadUiLanguageTranslations(language: UiLanguage): Promise<void> {
  if (!isAdditionalUiLanguage(language) || loadedTranslations.has(language)) return;
  let pending = pendingTranslations.get(language);
  if (!pending) {
    pending = TRANSLATION_LOADERS[language]().then(({ translations }) => {
      loadedTranslations.set(language, translations);
    }).finally(() => {
      pendingTranslations.delete(language);
    });
    pendingTranslations.set(language, pending);
  }
  await pending;
}

export async function loadAllUiLanguageTranslations(): Promise<void> {
  await Promise.all(ADDITIONAL_UI_LANGUAGES.map(loadUiLanguageTranslations));
}

export function isUiLanguageTranslationsLoaded(language: UiLanguage): boolean {
  return !isAdditionalUiLanguage(language) || loadedTranslations.has(language);
}

export function getLoadedUiLanguageTranslations(language: AdditionalUiLanguage): UiTranslationBundle | null {
  return loadedTranslations.get(language) ?? null;
}
