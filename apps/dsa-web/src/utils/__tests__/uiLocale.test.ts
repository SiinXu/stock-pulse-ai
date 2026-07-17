import { describe, expect, it } from 'vitest';
import { UI_LANGUAGES, UI_LANGUAGE_METADATA } from '../../i18n/uiLanguages';
import {
  formatUiCurrency,
  formatUiDateTime,
  formatUiList,
  formatUiNumber,
  getUiLocale,
} from '../uiLocale';

describe('UI locale formatting', () => {
  it.each(UI_LANGUAGES)('maps %s to its declared Intl locale', (language) => {
    expect(getUiLocale(language)).toBe(UI_LANGUAGE_METADATA[language].intlLocale);
  });

  it.each(UI_LANGUAGES)('formats dates, numbers, currency, and lists for %s', (language) => {
    expect(formatUiDateTime(new Date('2026-01-02T03:04:00Z'), language, { timeZone: 'UTC' })).not.toBe('—');
    expect(formatUiNumber(1234.5, language)).not.toBe('');
    expect(formatUiCurrency(1234.5, 'USD', language)).toContain('USD');
    expect(formatUiList(['Alpha', 'Beta'], language)).toContain('Alpha');
  });
});
