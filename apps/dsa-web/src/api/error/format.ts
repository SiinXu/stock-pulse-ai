// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiLanguage } from '../../i18n/uiText';
import { GENERIC_ERROR_TEXT, STABLE_ERROR_TEXT } from './catalog';
import type { ParsedApiError } from './types';

export function formatErrorTemplate(template: string, params?: Record<string, unknown>): string {
  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (_, key: string) => {
    const value = params?.[key];
    return value === undefined || value === null || value === '' ? '—' : String(value);
  });
}

export function localizeParsedApiError(error: ParsedApiError, language: UiLanguage): ParsedApiError {
  const stable = error.code ? STABLE_ERROR_TEXT[error.code] : undefined;
  if (stable) {
    const localized = stable[language];
    return {
      ...error,
      title: formatErrorTemplate(localized.title, error.params),
      message: formatErrorTemplate(localized.message, error.params),
      category: stable.category ?? error.category,
    };
  }
  if (language === 'zh') return error;
  const localized = GENERIC_ERROR_TEXT[language][error.category] ?? GENERIC_ERROR_TEXT[language].unknown;
  return {
    ...error,
    title: localized.title,
    message: localized.message,
  };
}

export function formatParsedApiError(parsed: ParsedApiError): string {
  if (!parsed.title.trim()) {
    return parsed.message;
  }
  if (parsed.title === parsed.message) {
    return parsed.title;
  }
  return `${parsed.title}：${parsed.message}`;
}
