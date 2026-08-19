// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { ADDITIONAL_UI_LANGUAGES, type UiLanguage } from '../uiLanguages';
import type { UiTranslationKey } from './en';

export { SOURCE_UI_TRANSLATIONS, UI_TRANSLATION_KEYS, type UiTranslationKey } from './en';

export type AdditionalUiLanguage = Exclude<UiLanguage, 'zh' | 'en'>;
export type UiTranslationBundle = Readonly<Record<UiTranslationKey, string>>;
type UiTranslationModule = { translations: UiTranslationBundle };
type ExtraLocaleCoreModule = { translations: Record<string, string> };
type PresentationCatalogModule = { SERVER_PRESENTATION_CATALOG: Record<string, string> };

const TRANSLATION_LOADERS: Record<AdditionalUiLanguage, () => Promise<ExtraLocaleCoreModule>> = {
  "zh-TW": () => import('./zh-TW'),
  "ja": () => import('./ja'),
  "ko": () => import('./ko'),
  "de": () => import('./de'),
  "es": () => import('./es'),
  "ms": () => import('./ms'),
  "fr": () => import('./fr'),
  "id": () => import('./id'),
};

const PRESENTATION_CATALOG_LOADERS: Record<AdditionalUiLanguage, () => Promise<PresentationCatalogModule>> = {
  "zh-TW": () => import('../serverPresentationCatalogs/zh-TW'),
  "ja": () => import('../serverPresentationCatalogs/ja'),
  "ko": () => import('../serverPresentationCatalogs/ko'),
  "de": () => import('../serverPresentationCatalogs/de'),
  "es": () => import('../serverPresentationCatalogs/es'),
  "ms": () => import('../serverPresentationCatalogs/ms'),
  "fr": () => import('../serverPresentationCatalogs/fr'),
  "id": () => import('../serverPresentationCatalogs/id'),
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
    pending = Promise.all([
      TRANSLATION_LOADERS[language](),
      PRESENTATION_CATALOG_LOADERS[language](),
    ]).then(([core, catalog]) => {
      loadedTranslations.set(language, {
        ...core.translations,
        ...catalog.SERVER_PRESENTATION_CATALOG,
      } as UiTranslationBundle);
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
  const previousCatalog = PRESENTATION_CATALOG_LOADERS[language];
  TRANSLATION_LOADERS[language] = loader;
  PRESENTATION_CATALOG_LOADERS[language] = async () => ({ SERVER_PRESENTATION_CATALOG: {} });
  loadedTranslations.delete(language);
  pendingTranslations.delete(language);
  return () => {
    TRANSLATION_LOADERS[language] = previous;
    PRESENTATION_CATALOG_LOADERS[language] = previousCatalog;
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
