// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Extra-locale catalogs are a merged overflow bucket, not a per-locale
 * classifier. i18n:resources only asserts the union of core+extra+optional
 * is complete. UI_TEXT keys that live in extra/ must therefore be present
 * in every additional locale's extra file — never a one-locale hand move.
 */
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { ADDITIONAL_UI_LANGUAGES } from '../uiLanguages';
import { UI_TRANSLATION_KEYS } from '../translations/en';

const translationsRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../translations');
const UI_TEXT_KEY_PATTERN = /^\s*"((?:i18n\.uiText\.UI_TEXT\.)[^"]+)"/gm;

function uiTextKeysInFile(filename: string): string[] {
  const source = fs.readFileSync(filename, 'utf8');
  return [...source.matchAll(UI_TEXT_KEY_PATTERN)].map((match) => match[1]).sort();
}

describe('extra-locale UI_TEXT placement', () => {
  it('keeps extra-catalog UI_TEXT keys identical across every additional locale', () => {
    const extraKeys = Object.fromEntries(
      ADDITIONAL_UI_LANGUAGES.map((language) => [
        language,
        uiTextKeysInFile(path.join(translationsRoot, 'extra', `${language}.ts`)),
      ]),
    ) as Record<(typeof ADDITIONAL_UI_LANGUAGES)[number], string[]>;
    const baseline = extraKeys[ADDITIONAL_UI_LANGUAGES[0]];
    for (const language of ADDITIONAL_UI_LANGUAGES) {
      expect(extraKeys[language], language).toEqual(baseline);
    }
  });

  it('does not inventory a dedicated shell Local Only UI_TEXT key', () => {
    expect(UI_TRANSLATION_KEYS).not.toContain('i18n.uiText.UI_TEXT.layout.localOnlyModeOpenSettings');
  });
});
