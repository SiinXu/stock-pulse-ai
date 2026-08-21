// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { getUiLanguageStorage, persistUiLanguage } from '../utils/uiLanguage';
import { loadUiLanguageTranslations } from './translations';
import type { UiLanguage } from './uiLanguages';

type TranslationLoader = (language: UiLanguage) => Promise<void>;

// Only Simplified Chinese stays in the render-blocking entry chunk. English
// uses the same loadUiLanguageTranslations path as extra locales so the unused
// language payload is not downloaded on first paint.
export type BuiltinUiLanguage = Extract<UiLanguage, 'zh'>;
export type ExtraUiLanguage = Exclude<UiLanguage, BuiltinUiLanguage>;

export function isBuiltinUiLanguage(language: UiLanguage): language is BuiltinUiLanguage {
  return language === 'zh';
}

export type InitialUiLanguageShell =
  | { status: 'app-ready'; language: BuiltinUiLanguage }
  | { status: 'locale-neutral'; requested: ExtraUiLanguage };

export type InitialUiLanguageBootstrap = {
  shell: InitialUiLanguageShell;
  catalog: Promise<UiLanguage>;
};

export function resolveInitialUiLanguageShell(requestedLanguage: UiLanguage): InitialUiLanguageShell {
  if (isBuiltinUiLanguage(requestedLanguage)) {
    return { status: 'app-ready', language: requestedLanguage };
  }
  return { status: 'locale-neutral', requested: requestedLanguage };
}

export async function prepareInitialUiLanguage(
  requestedLanguage: UiLanguage,
  loadTranslations: TranslationLoader = loadUiLanguageTranslations,
  storage: Storage | null = getUiLanguageStorage(),
): Promise<UiLanguage> {
  try {
    await loadTranslations(requestedLanguage);
    return requestedLanguage;
  } catch {
    // zh is built into the initial bundle and remains available even when a
    // lazily loaded locale chunk is missing or a deployment is mid-rollout.
    const fallbackLanguage: UiLanguage = 'zh';
    persistUiLanguage(storage, fallbackLanguage);
    return fallbackLanguage;
  }
}

export function beginInitialUiLanguage(
  requestedLanguage: UiLanguage,
  loadTranslations: TranslationLoader = loadUiLanguageTranslations,
  storage: Storage | null = getUiLanguageStorage(),
): InitialUiLanguageBootstrap {
  return {
    shell: resolveInitialUiLanguageShell(requestedLanguage),
    catalog: prepareInitialUiLanguage(requestedLanguage, loadTranslations, storage),
  };
}
