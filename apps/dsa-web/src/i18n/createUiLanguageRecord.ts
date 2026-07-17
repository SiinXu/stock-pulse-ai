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
      Object.entries(value).map(([key, item]) => [
        key,
        translateValue(item, translations, namespace, [...path, key], key),
      ]),
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
