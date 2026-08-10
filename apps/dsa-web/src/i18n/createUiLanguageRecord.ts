// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { ADDITIONAL_UI_LANGUAGES, type UiLanguage } from './uiLanguages';
import {
  getLoadedUiLanguageTranslations,
  SOURCE_UI_TRANSLATIONS,
  type AdditionalUiLanguage,
  type UiTranslationKey,
} from './translations';

type BaseUiLanguageRecord = {
  zh: unknown;
  en: unknown;
};

const NON_TRANSLATABLE_PROPERTIES = new Set([
  'value',
  'filename',
  'id',
  'key',
  'href',
  'url',
  'route',
  'path',
]);

/** Settings-help config sample arrays are machine literals, not localized UI copy. */
export const SETTINGS_HELP_MAPS_NAMESPACE = 'locales.settingsHelp.SETTINGS_HELP_MAPS';

/**
 * Skip the `examples` container for settings-help only, before array recursion.
 * Array children do not retain the parent property name, so this must run on the
 * object key — not on string leaves — and must not treat every registry `examples`
 * field as non-translatable.
 */
export function shouldSkipSettingsHelpExamplesContainer(
  namespace: string,
  propertyName: string | undefined,
): boolean {
  return namespace === SETTINGS_HELP_MAPS_NAMESPACE && propertyName === 'examples';
}

type WidenLocalizedValue<T, PropertyName extends PropertyKey = never> =
  T extends string ? PropertyName extends 'value' | 'filename' | 'id' | 'key' | 'href' | 'url' | 'route' | 'path' ? T : string
    : T extends number ? number
      : T extends boolean ? boolean
        : T extends readonly (infer U)[] ? Array<WidenLocalizedValue<U>>
          : T extends object ? { -readonly [K in keyof T]: WidenLocalizedValue<T[K], K> }
            : T;

type LocalizedValue<B extends BaseUiLanguageRecord> = WidenLocalizedValue<B['zh'] | B['en']>;

const registeredTranslationKeys = new Set<UiTranslationKey>();

export const getRegisteredUiTranslationKeys = (): readonly UiTranslationKey[] =>
  [...registeredTranslationKeys];

function assertExampleLiteralArraysEqual(
  english: unknown,
  chinese: unknown,
  path: string,
): void {
  if (!Array.isArray(english) || !Array.isArray(chinese)) {
    throw new Error(`Settings-help examples parity failed at ${path}: both sides must be arrays`);
  }
  if (english.length !== chinese.length) {
    throw new Error(
      `Settings-help examples parity failed at ${path}: length ${english.length} !== ${chinese.length}`,
    );
  }
  english.forEach((item, index) => {
    if (item !== chinese[index]) {
      throw new Error(
        `Settings-help examples parity failed at ${path}.${index}: English and Chinese literals must match byte-for-byte`,
      );
    }
  });
}

/** Walk settings-help maps and enforce parity only on `examples` arrays. Exported for unit tests. */
export function assertSettingsHelpExamplesParity(english: unknown, chinese: unknown, path: string[] = []): void {
  if (!english || typeof english !== 'object' || Array.isArray(english)) {
    return;
  }
  if (!chinese || typeof chinese !== 'object' || Array.isArray(chinese)) {
    return;
  }

  const englishRecord = english as Record<string, unknown>;
  const chineseRecord = chinese as Record<string, unknown>;
  for (const [key, child] of Object.entries(englishRecord)) {
    const nextPath = [...path, key];
    if (key === 'examples') {
      assertExampleLiteralArraysEqual(child, chineseRecord[key], nextPath.join('.'));
      continue;
    }
    assertSettingsHelpExamplesParity(child, chineseRecord[key], nextPath);
  }
  if (Object.prototype.hasOwnProperty.call(chineseRecord, 'examples')
    && !Object.prototype.hasOwnProperty.call(englishRecord, 'examples')) {
    throw new Error(
      `Settings-help examples parity failed at ${[...path, 'examples'].join('.')}: present in Chinese only`,
    );
  }
}
function validateSourceValue(
  value: unknown,
  namespace: string,
  path: string[] = [],
  propertyName?: string,
): void {
  if (typeof value === 'string') {
    if (propertyName && NON_TRANSLATABLE_PROPERTIES.has(propertyName)) return;
    const key = [namespace, ...path].join('.') as UiTranslationKey;
    registeredTranslationKeys.add(key);
    if (SOURCE_UI_TRANSLATIONS[key] !== value) {
      throw new Error(`Stale UI translation source: ${key}`);
    }
    return;
  }

  if (Array.isArray(value)) {
    value.forEach((item, index) => validateSourceValue(item, namespace, [...path, String(index)]));
    return;
  }

  if (value && typeof value === 'object') {
    Object.entries(value).forEach(([key, item]) => {
      if (shouldSkipSettingsHelpExamplesContainer(namespace, key)) {
        return;
      }
      validateSourceValue(item, namespace, [...path, key], key);
    });
  }
}

function translateValue<T>(
  value: T,
  translations: Readonly<Record<UiTranslationKey, string>>,
  namespace: string,
  path: string[] = [],
  propertyName?: string,
): T {
  if (typeof value === 'string') {
    if (propertyName && NON_TRANSLATABLE_PROPERTIES.has(propertyName)) {
      return value;
    }
    const key = [namespace, ...path].join('.') as UiTranslationKey;
    const translated = translations[key];
    if (translated === undefined) {
      throw new Error(`Missing UI translation: ${key}`);
    }
    return translated as T;
  }

  if (Array.isArray(value)) {
    return value.map((item, index) => translateValue(item, translations, namespace, [...path, String(index)])) as T;
  }

  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => {
        if (shouldSkipSettingsHelpExamplesContainer(namespace, key)) {
          // Additional languages keep the canonical English source literals.
          return [key, item];
        }
        return [key, translateValue(item, translations, namespace, [...path, key], key)];
      }),
    ) as T;
  }

  return value;
}

export function createUiLanguageRecord<const B extends BaseUiLanguageRecord>(
  namespace: string,
  base: B,
  overrides: Partial<Record<Exclude<UiLanguage, 'zh' | 'en'>, LocalizedValue<B>>> = {},
): Record<UiLanguage, LocalizedValue<B>> & Omit<B, 'zh' | 'en'> {
  // Source inventory validation is intentionally limited to development and
  // tests. Production builds can then tree-shake the duplicated English
  // inventory while CI still catches stale or missing translation keys.
  if (import.meta.env?.DEV || import.meta.env?.MODE === 'test') {
    if (namespace === SETTINGS_HELP_MAPS_NAMESPACE) {
      assertSettingsHelpExamplesParity(base.en, base.zh);
    }
    validateSourceValue(base.en, namespace);
  }
  const record: Record<PropertyKey, unknown> = { ...base };
  const localizedCache = new Map<AdditionalUiLanguage, LocalizedValue<B>>();

  for (const language of ADDITIONAL_UI_LANGUAGES) {
    const override = overrides[language];
    if (override !== undefined) {
      record[language] = override;
      continue;
    }
    Object.defineProperty(record, language, {
      enumerable: true,
      get: () => {
        const cached = localizedCache.get(language);
        if (cached !== undefined) return cached;
        const translations = getLoadedUiLanguageTranslations(language);
        if (!translations) {
          throw new Error(`UI translation bundle is not loaded: ${language}`);
        }
        const localized = translateValue(base.en, translations, namespace) as LocalizedValue<B>;
        localizedCache.set(language, localized);
        return localized;
      },
    });
  }

  return record as Record<UiLanguage, LocalizedValue<B>> & Omit<B, 'zh' | 'en'>;
}
