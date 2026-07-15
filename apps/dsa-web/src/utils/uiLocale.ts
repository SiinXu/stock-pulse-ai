import type { UiLanguage } from '../i18n/uiText';

export type UiLocale = 'zh-CN' | 'en-US';

export function getUiLocale(language: UiLanguage): UiLocale {
  return language === 'en' ? 'en-US' : 'zh-CN';
}

export function formatUiDateTime(
  value: string | number | Date | null | undefined,
  language: UiLanguage,
  options: Intl.DateTimeFormatOptions = {},
): string {
  if (value === null || value === undefined || value === '') return '—';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(getUiLocale(language), options).format(date);
}

export function formatUiNumber(
  value: number,
  language: UiLanguage,
  options?: Intl.NumberFormatOptions,
): string {
  return new Intl.NumberFormat(getUiLocale(language), options).format(value);
}

export function formatUiCurrency(
  value: number,
  currency: string,
  language: UiLanguage,
  options?: Omit<Intl.NumberFormatOptions, 'style' | 'currency'>,
): string {
  return new Intl.NumberFormat(getUiLocale(language), {
    style: 'currency',
    currency,
    currencyDisplay: 'code',
    ...options,
  }).format(value);
}

export function formatUiList(values: string[], language: UiLanguage): string {
  return new Intl.ListFormat(getUiLocale(language), { style: 'long', type: 'conjunction' }).format(values);
}
