import { getUiLanguageStorage, persistUiLanguage } from '../utils/uiLanguage';
import { loadUiLanguageTranslations } from './translations';
import type { UiLanguage } from './uiLanguages';

type TranslationLoader = (language: UiLanguage) => Promise<void>;

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
