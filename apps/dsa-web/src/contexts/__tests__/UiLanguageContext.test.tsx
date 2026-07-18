import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageToggle } from '../../components/i18n/UiLanguageToggle';
import { UI_LANGUAGES, UI_LANGUAGE_METADATA, type UiLanguage } from '../../i18n/uiLanguages';
import { UI_TEXT } from '../../i18n/uiText';
import {
  getRuntimeInitialLanguage,
  normalizeUiLanguage,
  persistUiLanguage,
  recoverFailedUiLanguageSwitch,
  resolveInitialUiLanguage,
  UI_LANGUAGE_STORAGE_KEY,
} from '../../utils/uiLanguage';
import { UiLanguageProvider } from '../UiLanguageContext';

function createStorage(value: string | null): Storage {
  const store = new Map<string, string>();
  if (value !== null) store.set(UI_LANGUAGE_STORAGE_KEY, value);

  return {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key: string) => store.get(key) ?? null,
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    removeItem: (key: string) => {
      store.delete(key);
    },
    setItem: (key: string, nextValue: string) => {
      store.set(key, nextValue);
    },
  };
}

describe('UiLanguageContext', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.lang = 'zh-CN';
  });

  it.each<[string, UiLanguage]>([
    ['zh-CN', 'zh'],
    ['zh_Hans_SG', 'zh'],
    ['zh-TW', 'zh-TW'],
    ['zh-Hant-HK', 'zh-TW'],
    ['zh_HK', 'zh-TW'],
    ['EN-gb', 'en'],
    ['ja-JP', 'ja'],
    ['ko-KR', 'ko'],
    ['de-AT', 'de'],
    ['es-MX', 'es'],
    ['ms-BN', 'ms'],
    ['fr-CA', 'fr'],
    ['id-ID', 'id'],
    ['in-ID', 'id'],
  ])('normalizes browser locale %s to %s', (locale, expected) => {
    expect(normalizeUiLanguage(` ${locale} `)).toBe(expected);
  });

  it('rejects unsupported locales', () => {
    expect(normalizeUiLanguage('pt-BR')).toBeNull();
    expect(normalizeUiLanguage('tr-TR')).toBeNull();
  });

  it('resolves explicit storage before the first supported browser language', () => {
    expect(resolveInitialUiLanguage({
      storage: createStorage('fr'),
      navigatorLike: { language: 'ja-JP', languages: ['ja-JP'] },
    })).toBe('fr');

    expect(resolveInitialUiLanguage({
      storage: createStorage('pt-BR'),
      navigatorLike: { language: 'en-US', languages: ['tr-TR', 'zh-HK', 'en-US'] },
    })).toBe('zh-TW');

    expect(resolveInitialUiLanguage({
      storage: createStorage(null),
      navigatorLike: { language: 'tr-TR', languages: ['tr-TR'] },
    })).toBe('zh');
  });

  it('handles unavailable storage without throwing', () => {
    const throwingStorage = createStorage('en');
    throwingStorage.getItem = () => {
      throw new Error('Storage getItem disabled');
    };
    throwingStorage.setItem = () => {
      throw new Error('Storage setItem disabled');
    };

    expect(resolveInitialUiLanguage({
      storage: throwingStorage,
      navigatorLike: { language: 'de-DE', languages: ['de-DE'] },
    })).toBe('de');
    expect(() => persistUiLanguage(throwingStorage, 'ja')).not.toThrow();
  });

  it('persists a failed lazy-language selection before reloading the document', () => {
    const storage = createStorage('zh');
    const reload = vi.fn();

    recoverFailedUiLanguageSwitch('de', storage, reload);

    expect(storage.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe('de');
    expect(reload).toHaveBeenCalledOnce();
  });

  it('falls back safely when the localStorage accessor itself throws', () => {
    const originalDescriptor = Object.getOwnPropertyDescriptor(window, 'localStorage');
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get: () => {
        throw new Error('localStorage disabled');
      },
    });

    try {
      expect(getRuntimeInitialLanguage()).toBe('en');
    } finally {
      if (originalDescriptor) Object.defineProperty(window, 'localStorage', originalDescriptor);
    }
  });

  it('renders all ten native-language options and persists explicit selections', async () => {
    localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'zh');
    render(
      <UiLanguageProvider>
        <UiLanguageToggle />
      </UiLanguageProvider>,
    );

    const selector = screen.getByTestId('ui-language-selector');
    fireEvent.click(within(selector).getByRole('combobox'));
    expect(screen.getAllByRole('option')).toHaveLength(UI_LANGUAGES.length);
    expect(screen.getByRole('option', { name: '繁體中文' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Bahasa Indonesia' })).toBeInTheDocument();
    fireEvent.keyDown(within(selector).getByRole('combobox'), { key: 'Escape' });

    for (const language of UI_LANGUAGES) {
      const combobox = within(selector).getByRole('combobox');
      fireEvent.click(combobox);
      fireEvent.click(screen.getByRole('option', { name: UI_LANGUAGE_METADATA[language].nativeLabel }));
      await waitFor(() => expect(localStorage.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe(language));
      expect(document.documentElement.lang).toBe(UI_LANGUAGE_METADATA[language].htmlLang);
      expect(within(selector).getByRole('combobox')).toHaveAttribute('data-value', language);
      expect(within(selector).getByRole('combobox')).toHaveAccessibleName(UI_TEXT[language]['language.toggle']);
    }
    expect(within(selector).getByRole('combobox')).toHaveAttribute('data-value', 'id');
  });
});
