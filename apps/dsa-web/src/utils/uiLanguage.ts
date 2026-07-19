import type { UiLanguage } from '../i18n/uiText';
import { UI_LANGUAGE_METADATA } from '../i18n/uiLanguages';

export const UI_LANGUAGE_STORAGE_KEY = 'dsa.uiLanguage';

export function normalizeUiLanguage(value?: string | null): UiLanguage | null {
  const normalized = value?.trim().replaceAll('_', '-').toLowerCase();
  if (!normalized) return null;

  if (
    normalized === 'zh-cht'
    || normalized === 'zh-hant'
    || normalized.startsWith('zh-hant-')
    || normalized === 'zh-tw'
    || normalized.startsWith('zh-tw-')
    || normalized === 'zh-hk'
    || normalized.startsWith('zh-hk-')
    || normalized === 'zh-mo'
    || normalized.startsWith('zh-mo-')
  ) return 'zh-TW';

  if (normalized === 'zh' || normalized.startsWith('zh-')) return 'zh';
  if (normalized === 'en' || normalized.startsWith('en-')) return 'en';
  if (normalized === 'ja' || normalized.startsWith('ja-')) return 'ja';
  if (normalized === 'ko' || normalized.startsWith('ko-')) return 'ko';
  if (normalized === 'de' || normalized.startsWith('de-')) return 'de';
  if (normalized === 'es' || normalized.startsWith('es-')) return 'es';
  if (normalized === 'ms' || normalized.startsWith('ms-')) return 'ms';
  if (normalized === 'fr' || normalized.startsWith('fr-')) return 'fr';
  if (normalized === 'id' || normalized.startsWith('id-') || normalized === 'in' || normalized.startsWith('in-')) return 'id';
  return null;
}

function getStoredUiLanguage(storage?: Storage | null): UiLanguage | null {
  if (!storage) {
    return null;
  }

  try {
    return normalizeUiLanguage(storage.getItem(UI_LANGUAGE_STORAGE_KEY));
  } catch {
    return null;
  }
}

export function getUiLanguageStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function persistUiLanguage(storage: Storage | null, language: UiLanguage): void {
  if (!storage) {
    return;
  }

  try {
    storage.setItem(UI_LANGUAGE_STORAGE_KEY, language);
  } catch {
    // Ignore storage failures; in-memory language still updates.
  }
}

function getBrowserUiLanguage(navigatorLike?: Pick<Navigator, 'language' | 'languages'> | null): UiLanguage {
  const languageCandidates = [
    ...(Array.isArray(navigatorLike?.languages) ? navigatorLike?.languages ?? [] : []),
    navigatorLike?.language,
  ].filter((language): language is string => Boolean(language));

  for (const candidate of languageCandidates) {
    const normalized = normalizeUiLanguage(candidate);
    if (normalized) return normalized;
  }

  return 'zh';
}

export function resolveInitialUiLanguage({
  storage,
  navigatorLike,
}: {
  storage?: Storage | null;
  navigatorLike?: Pick<Navigator, 'language' | 'languages'> | null;
} = {}): UiLanguage {
  const stored = getStoredUiLanguage(storage);
  if (stored) {
    return stored;
  }

  return getBrowserUiLanguage(navigatorLike);
}

export function getRuntimeInitialLanguage(): UiLanguage {
  if (typeof window === 'undefined') {
    return 'zh';
  }

  return resolveInitialUiLanguage({
    storage: getUiLanguageStorage(),
    navigatorLike: window.navigator,
  });
}

export function applyUiLanguageToDocument(language: UiLanguage, documentLike: Pick<Document, 'documentElement'> = document): void {
  documentLike.documentElement.lang = UI_LANGUAGE_METADATA[language].htmlLang;
}

export function recoverFailedUiLanguageSwitch(
  language: UiLanguage,
  storage: Storage | null = getUiLanguageStorage(),
  reload: () => void = () => window.location.reload(),
): void {
  // Failed dynamic imports are cached for the lifetime of the document by
  // browsers. Persist the requested language and reload once so a transient
  // chunk failure can be retried in a fresh module map. Bootstrap falls back
  // to Simplified Chinese if the chunk is still unavailable.
  persistUiLanguage(storage, language);
  reload();
}
