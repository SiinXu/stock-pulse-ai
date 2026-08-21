// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it } from 'vitest';
import { UI_LANGUAGES } from '../uiLanguages';
import { UI_TEXT } from '../uiText';
import { zh } from '../uiTextZh';
import {
  getLoadedEnglishUiText,
  isUiLanguageTranslationsLoaded,
  loadEnglishUiTextPayload,
  loadUiLanguageTranslations,
  unloadEnglishUiTextForTests,
} from '../translations';

const i18nRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

describe('English UI_TEXT entry split (Refs #883)', () => {
  afterEach(async () => {
    if (!getLoadedEnglishUiText()) {
      await loadEnglishUiTextPayload();
    }
  });

  it('does not statically import the English payload from the entry uiText module', () => {
    const uiTextSource = fs.readFileSync(path.join(i18nRoot, 'uiText.ts'), 'utf8');
    const extraLocaleLoaderSource = fs.readFileSync(path.join(i18nRoot, 'translations/index.ts'), 'utf8');
    const englishLoaderSource = fs.readFileSync(path.join(i18nRoot, 'loadEnglishUiText.ts'), 'utf8');
    const viteConfigSource = fs.readFileSync(path.resolve(i18nRoot, '../../vite.config.ts'), 'utf8');

    expect(uiTextSource).not.toMatch(/from ['"]\.\/uiTextEn['"]/);
    expect(uiTextSource).not.toMatch(/import\(\s*['"]\.\/uiTextEn['"]\s*\)/);
    expect(extraLocaleLoaderSource).not.toMatch(/import\(\s*['"]\.\.\/uiTextEn['"]\s*\)/);
    expect(englishLoaderSource).toContain("import('./uiTextEn')");
    expect(englishLoaderSource).toContain('ENGLISH_UI_TEXT_LOADER');
    expect(englishLoaderSource).toContain('loadEnglishUiTextPayload');
    expect(viteConfigSource).toContain("endsWith('/src/i18n/loadEnglishUiText.ts')");
    expect(viteConfigSource).toContain("return 'englishUiTextLoader'");
  });

  it('keeps Simplified Chinese readable without the English catalog', () => {
    expect(UI_TEXT.zh['layout.nav.home']).toBe(zh['layout.nav.home']);
    expect(isUiLanguageTranslationsLoaded('zh')).toBe(true);
  });

  it('loads English through the same locale loader used by extra languages', async () => {
    unloadEnglishUiTextForTests();
    expect(getLoadedEnglishUiText()).toBeNull();
    expect(isUiLanguageTranslationsLoaded('en')).toBe(false);
    expect(() => UI_TEXT.en['layout.nav.home']).toThrow(/UI translation bundle is not loaded: en/);

    await loadUiLanguageTranslations('en');
    expect(isUiLanguageTranslationsLoaded('en')).toBe(true);
    expect(UI_TEXT.en['layout.nav.home']).toBe('Today');
  });

  it('projects every locale from the same UI_TEXT key set after the loader settles', async () => {
    const expectedKeys = Object.keys(UI_TEXT.zh).sort();
    for (const language of UI_LANGUAGES) {
      await loadUiLanguageTranslations(language);
      expect(isUiLanguageTranslationsLoaded(language)).toBe(true);
      expect(Object.keys(UI_TEXT[language]).sort()).toEqual(expectedKeys);
      expect(UI_TEXT[language]['layout.nav.home']).toBeTruthy();
    }
  });
});
