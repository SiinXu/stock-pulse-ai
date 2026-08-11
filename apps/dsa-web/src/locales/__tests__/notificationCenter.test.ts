// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { UI_LANGUAGES } from '../../i18n/uiLanguages';
import { NOTIFICATION_CENTER_TEXT } from '../notificationCenter';

function placeholders(value: string): string[] {
  return [...value.matchAll(/\{([^{}]+)\}/g)]
    .map((match) => match[1])
    .sort();
}

describe('notification center localized copy', () => {
  it('keeps the complete key and placeholder contract for every UI locale', () => {
    const english = NOTIFICATION_CENTER_TEXT.en;
    const keys = Object.keys(english) as Array<keyof typeof english>;
    expect(keys).toHaveLength(23);

    for (const language of UI_LANGUAGES) {
      const localized = NOTIFICATION_CENTER_TEXT[language];
      expect(Object.keys(localized).sort(), language).toEqual([...keys].sort());
      for (const key of keys) {
        expect(placeholders(localized[key]), `${language}:${key}`)
          .toEqual(placeholders(english[key]));
      }
    }
  });

  it('does not copy English values into non-English locales', () => {
    const english = NOTIFICATION_CENTER_TEXT.en;
    const keys = Object.keys(english) as Array<keyof typeof english>;
    const identical: string[] = [];

    for (const language of UI_LANGUAGES.filter((value) => value !== 'en')) {
      for (const key of keys) {
        if (NOTIFICATION_CENTER_TEXT[language][key] === english[key]) {
          identical.push(`${language}:${key}`);
        }
      }
    }

    expect(identical).toEqual([]);
  });
});
