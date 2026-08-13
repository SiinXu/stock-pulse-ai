// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { EVENT_CALENDAR_TEXT } from '../eventCalendar';
import { ADDITIONAL_UI_LANGUAGES, UI_LANGUAGES } from '../../i18n/uiLanguages';

function flatten(value: unknown, path: string[] = []): Array<[string, string]> {
  if (typeof value === 'string') return [[path.join('.'), value]];
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
  return Object.entries(value).flatMap(([key, child]) => flatten(child, [...path, key]));
}

function placeholders(value: string): string[] {
  return [...value.matchAll(/\{([^{}]+)\}/g)].map((match) => match[1]).sort();
}

describe('event calendar localized copy', () => {
  it('keeps the complete key and placeholder contract for every UI locale', () => {
    const english = new Map(flatten(EVENT_CALENDAR_TEXT.en));
    expect(english.size).toBe(41);

    for (const language of UI_LANGUAGES) {
      const localized = new Map(flatten(EVENT_CALENDAR_TEXT[language]));
      expect([...localized.keys()].sort(), language).toEqual([...english.keys()].sort());
      for (const [key, source] of english) {
        expect(placeholders(localized.get(key) ?? ''), `${language}:${key}`)
          .toEqual(placeholders(source));
      }
    }
  });

  it('does not copy English values into non-English event-calendar locales', () => {
    const english = new Map(flatten(EVENT_CALENDAR_TEXT.en));
    const identical: string[] = [];
    for (const language of ADDITIONAL_UI_LANGUAGES) {
      for (const [key, value] of flatten(EVENT_CALENDAR_TEXT[language])) {
        if (value === english.get(key)) identical.push(`${language}:${key}`);
      }
    }
    expect(identical).toEqual([]);
  });
});
