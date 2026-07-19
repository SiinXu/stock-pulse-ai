// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it, vi } from 'vitest';
import { UI_LANGUAGE_STORAGE_KEY } from '../../utils/uiLanguage';
import { prepareInitialUiLanguage } from '../prepareUiLanguage';

function createMemoryStorage(initialValues: Array<[string, string]> = []): Storage {
  const values = new Map<string, string>(initialValues);

  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => Array.from(values.keys())[index] ?? null,
    removeItem: (key) => values.delete(key),
    setItem: (key, value) => {
      values.set(key, value);
    },
  };
}

describe('prepareInitialUiLanguage', () => {
  it('keeps the requested language after its translation bundle loads', async () => {
    const loadTranslations = vi.fn(async () => undefined);
    const storageLike = createMemoryStorage();

    await expect(prepareInitialUiLanguage('de', loadTranslations, storageLike)).resolves.toBe('de');
    expect(loadTranslations).toHaveBeenCalledWith('de');
    expect(storageLike.getItem(UI_LANGUAGE_STORAGE_KEY)).toBeNull();
  });

  it('persists and returns the built-in fallback when a locale chunk fails', async () => {
    const loadTranslations = vi.fn(async () => {
      throw new TypeError('Failed to fetch dynamically imported module');
    });
    const storageLike = createMemoryStorage([[UI_LANGUAGE_STORAGE_KEY, 'fr']]);

    await expect(prepareInitialUiLanguage('fr', loadTranslations, storageLike)).resolves.toBe('zh');
    expect(storageLike.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe('zh');
  });
});
