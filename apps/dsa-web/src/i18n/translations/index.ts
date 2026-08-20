// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { ADDITIONAL_UI_LANGUAGES, type UiLanguage } from '../uiLanguages';
import type { UiTranslationKey } from './en';

export { SOURCE_UI_TRANSLATIONS, UI_TRANSLATION_KEYS, type UiTranslationKey } from './en';

export type AdditionalUiLanguage = Exclude<UiLanguage, 'zh' | 'en'>;
export type UiTranslationBundle = Readonly<Record<UiTranslationKey, string>>;
type UiTranslationModule = { translations: UiTranslationBundle };

async function loadExtraLocaleBundle(
  loadCore: () => Promise<{ translations: Record<string, string> }>,
  loadExtra: () => Promise<{ EXTRA_UI_TRANSLATIONS: Record<string, string> }>,
  loadOptionalSections: () => Promise<{ OPTIONAL_SECTION_HONESTY_TRANSLATIONS: Record<string, string> }>,
): Promise<UiTranslationModule> {
  const [core, extra, optionalSections] = await Promise.all([
    loadCore(),
    loadExtra(),
    loadOptionalSections(),
  ]);
  return {
    translations: {
      ...core.translations,
      ...extra.EXTRA_UI_TRANSLATIONS,
      ...optionalSections.OPTIONAL_SECTION_HONESTY_TRANSLATIONS,
    } as UiTranslationBundle,
  };
}

const TRANSLATION_LOADERS: Record<AdditionalUiLanguage, () => Promise<UiTranslationModule>> = {
  "zh-TW": () => loadExtraLocaleBundle(
    () => import('./zh-TW'),
    () => import('./extra/zh-TW'),
    () => import('./optionalSections/zh-TW'),
  ),
  "ja": () => loadExtraLocaleBundle(
    () => import('./ja'),
    () => import('./extra/ja'),
    () => import('./optionalSections/ja'),
  ),
  "ko": () => loadExtraLocaleBundle(
    () => import('./ko'),
    () => import('./extra/ko'),
    () => import('./optionalSections/ko'),
  ),
  "de": () => loadExtraLocaleBundle(
    () => import('./de'),
    () => import('./extra/de'),
    () => import('./optionalSections/de'),
  ),
  "es": () => loadExtraLocaleBundle(
    () => import('./es'),
    () => import('./extra/es'),
    () => import('./optionalSections/es'),
  ),
  "ms": () => loadExtraLocaleBundle(
    () => import('./ms'),
    () => import('./extra/ms'),
    () => import('./optionalSections/ms'),
  ),
  "fr": () => loadExtraLocaleBundle(
    () => import('./fr'),
    () => import('./extra/fr'),
    () => import('./optionalSections/fr'),
  ),
  "id": () => loadExtraLocaleBundle(
    () => import('./id'),
    () => import('./extra/id'),
    () => import('./optionalSections/id'),
  ),
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

export function replaceUiLanguageTranslationLoaderForTests(
  language: AdditionalUiLanguage,
  loader: () => Promise<UiTranslationModule>,
): () => void {
  if (import.meta.env.MODE !== 'test') {
    throw new Error('replaceUiLanguageTranslationLoaderForTests is test-only');
  }
  const previous = TRANSLATION_LOADERS[language];
  TRANSLATION_LOADERS[language] = loader;
  loadedTranslations.delete(language);
  pendingTranslations.delete(language);
  return () => {
    TRANSLATION_LOADERS[language] = previous;
    loadedTranslations.delete(language);
    pendingTranslations.delete(language);
  };
}

export function unloadUiLanguageTranslationsForTests(language?: AdditionalUiLanguage): void {
  if (import.meta.env.MODE !== 'test') {
    throw new Error('unloadUiLanguageTranslationsForTests is test-only');
  }
  if (language) {
    loadedTranslations.delete(language);
    pendingTranslations.delete(language);
    return;
  }
  loadedTranslations.clear();
  pendingTranslations.clear();
}
