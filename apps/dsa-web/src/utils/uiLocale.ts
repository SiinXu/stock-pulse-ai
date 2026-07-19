// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiLanguage } from '../i18n/uiText';
import { UI_LANGUAGE_METADATA } from '../i18n/uiLanguages';

export type UiLocale = (typeof UI_LANGUAGE_METADATA)[UiLanguage]['intlLocale'];

export function getUiLocale(language: UiLanguage): UiLocale {
  return UI_LANGUAGE_METADATA[language].intlLocale;
}

export function getUiListSeparator(language: UiLanguage): string {
  return language === 'zh' || language === 'zh-TW' || language === 'ja' ? '、' : ', ';
}

export function getUiClauseSeparator(language: UiLanguage): string {
  return language === 'zh' || language === 'zh-TW' ? '；' : '; ';
}

export function getUiColon(language: UiLanguage): string {
  return language === 'zh' || language === 'zh-TW' || language === 'ja' ? '：' : ': ';
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
