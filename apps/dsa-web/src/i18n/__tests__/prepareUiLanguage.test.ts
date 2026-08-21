// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it, vi } from 'vitest';
import { UI_LANGUAGE_STORAGE_KEY } from '../../utils/uiLanguage';
import { beginInitialUiLanguage, prepareInitialUiLanguage, resolveInitialUiLanguageShell } from '../prepareUiLanguage';

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

describe('beginInitialUiLanguage', () => {
  it('is app-ready immediately only for requested zh', () => {
    const loadTranslations = vi.fn(() => new Promise<void>(() => undefined));

    expect(beginInitialUiLanguage('zh', loadTranslations, createMemoryStorage()).shell).toEqual({
      status: 'app-ready',
      language: 'zh',
    });
    expect(resolveInitialUiLanguageShell('zh')).toEqual({ status: 'app-ready', language: 'zh' });
    expect(resolveInitialUiLanguageShell('en')).toEqual({ status: 'locale-neutral', requested: 'en' });
  });

  it('reports locale-neutral shell before a deferred en catalog settles', async () => {
    let settle!: () => void;
    const loadTranslations = vi.fn(() => new Promise<void>((resolve) => {
      settle = resolve;
    }));
    const storageLike = createMemoryStorage([[UI_LANGUAGE_STORAGE_KEY, 'en']]);

    const { shell, catalog } = beginInitialUiLanguage('en', loadTranslations, storageLike);
    expect(shell).toEqual({ status: 'locale-neutral', requested: 'en' });
    expect(loadTranslations).toHaveBeenCalledWith('en');

    let catalogLanguage: string | undefined;
    void catalog.then((language) => {
      catalogLanguage = language;
    });
    await Promise.resolve();
    expect(catalogLanguage).toBeUndefined();
    expect(storageLike.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe('en');

    settle();
    await expect(catalog).resolves.toBe('en');
    expect(storageLike.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe('en');
  });

  it('reports locale-neutral shell before a deferred de catalog settles', async () => {
    let settle!: () => void;
    const loadTranslations = vi.fn(() => new Promise<void>((resolve) => {
      settle = resolve;
    }));
    const storageLike = createMemoryStorage([[UI_LANGUAGE_STORAGE_KEY, 'de']]);

    const { shell, catalog } = beginInitialUiLanguage('de', loadTranslations, storageLike);
    expect(shell).toEqual({ status: 'locale-neutral', requested: 'de' });
    expect(loadTranslations).toHaveBeenCalledWith('de');

    let catalogLanguage: string | undefined;
    void catalog.then((language) => {
      catalogLanguage = language;
    });
    await Promise.resolve();
    expect(catalogLanguage).toBeUndefined();
    expect(storageLike.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe('de');

    settle();
    await expect(catalog).resolves.toBe('de');
    expect(storageLike.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe('de');
  });

  it('reports locale-neutral shell before a deferred fr catalog settles', async () => {
    let settle!: () => void;
    const loadTranslations = vi.fn(() => new Promise<void>((resolve) => {
      settle = resolve;
    }));
    const storageLike = createMemoryStorage();

    const { shell, catalog } = beginInitialUiLanguage('fr', loadTranslations, storageLike);
    expect(shell).toEqual({ status: 'locale-neutral', requested: 'fr' });
    expect(storageLike.getItem(UI_LANGUAGE_STORAGE_KEY)).toBeNull();

    let catalogSettled = false;
    void catalog.then(() => {
      catalogSettled = true;
    });
    await Promise.resolve();
    expect(catalogSettled).toBe(false);

    settle();
    await expect(catalog).resolves.toBe('fr');
    expect(storageLike.getItem(UI_LANGUAGE_STORAGE_KEY)).toBeNull();
  });

  it('still persists zh honestly when a deferred en catalog fails', async () => {
    let rejectLoad!: (reason?: unknown) => void;
    const loadTranslations = vi.fn(() => new Promise<void>((_resolve, reject) => {
      rejectLoad = reject;
    }));
    const storageLike = createMemoryStorage([[UI_LANGUAGE_STORAGE_KEY, 'en']]);

    const { shell, catalog } = beginInitialUiLanguage('en', loadTranslations, storageLike);
    expect(shell).toEqual({ status: 'locale-neutral', requested: 'en' });
    expect(storageLike.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe('en');

    rejectLoad(new TypeError('Failed to fetch dynamically imported module'));
    await expect(catalog).resolves.toBe('zh');
    expect(storageLike.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe('zh');
  });

  it('still persists zh honestly when a deferred fr catalog fails', async () => {
    let rejectLoad!: (reason?: unknown) => void;
    const loadTranslations = vi.fn(() => new Promise<void>((_resolve, reject) => {
      rejectLoad = reject;
    }));
    const storageLike = createMemoryStorage([[UI_LANGUAGE_STORAGE_KEY, 'fr']]);

    const { shell, catalog } = beginInitialUiLanguage('fr', loadTranslations, storageLike);
    expect(shell).toEqual({ status: 'locale-neutral', requested: 'fr' });
    expect(storageLike.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe('fr');

    rejectLoad(new TypeError('Failed to fetch dynamically imported module'));
    await expect(catalog).resolves.toBe('zh');
    expect(storageLike.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe('zh');
  });
});
