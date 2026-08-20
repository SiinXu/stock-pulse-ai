// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen, waitFor } from '@testing-library/react';
import { useEffect } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { UI_LANGUAGE_STORAGE_KEY } from '../../utils/uiLanguage';
import { UI_TEXT } from '../uiText';
import { InitialUiLanguageGate } from '../InitialUiLanguageGate';
import { beginInitialUiLanguage } from '../prepareUiLanguage';

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

const WRONG_LANGUAGE_CHROME = [
  UI_TEXT.zh['layout.nav.home'],
  UI_TEXT.en['layout.nav.home'],
  UI_TEXT.zh['layout.nav.settings'],
  UI_TEXT.en['layout.nav.settings'],
  UI_TEXT.zh['layout.nav.research'],
  UI_TEXT.en['layout.nav.research'],
  UI_TEXT.zh['common.loading'],
  UI_TEXT.en['common.loading'],
] as const;

describe('InitialUiLanguageGate', () => {
  it('paints built-in English immediately when English is requested', () => {
    const { shell, catalog } = beginInitialUiLanguage(
      'en',
      vi.fn(async () => undefined),
      createMemoryStorage(),
    );

    const { container } = render(
      <InitialUiLanguageGate shell={shell} catalog={catalog}>
        {(language) => (
          <div data-testid="app-language">
            {language}:{UI_TEXT[language]['layout.nav.home']}
          </div>
        )}
      </InitialUiLanguageGate>,
    );

    expect(screen.getByTestId('app-language')).toHaveTextContent('en:Today');
    expect(container.querySelector('[data-locale-neutral-shell]')).toBeNull();
  });

  it('paints built-in zh immediately when Simplified Chinese is requested', () => {
    const { shell, catalog } = beginInitialUiLanguage(
      'zh',
      vi.fn(async () => undefined),
      createMemoryStorage(),
    );

    render(
      <InitialUiLanguageGate shell={shell} catalog={catalog}>
        {(language) => (
          <div data-testid="app-language">
            {language}:{UI_TEXT[language]['layout.nav.home']}
          </div>
        )}
      </InitialUiLanguageGate>,
    );

    expect(screen.getByTestId('app-language')).toHaveTextContent(`zh:${UI_TEXT.zh['layout.nav.home']}`);
  });

  it('does not paint zh or en navigation chrome while a de catalog is pending', async () => {
    let settle!: () => void;
    const loadTranslations = vi.fn(() => new Promise<void>((resolve) => {
      settle = resolve;
    }));
    const { shell, catalog } = beginInitialUiLanguage('de', loadTranslations, createMemoryStorage());

    const { container } = render(
      <InitialUiLanguageGate shell={shell} catalog={catalog}>
        {(language) => (
          <nav data-shell-sidebar="">
            <div data-testid="app-language">{language}</div>
            <span>{UI_TEXT.zh['layout.nav.home']}</span>
            <span>{UI_TEXT.en['layout.nav.home']}</span>
            <span>{UI_TEXT.zh['layout.nav.settings']}</span>
            <span>{UI_TEXT.en['layout.nav.settings']}</span>
          </nav>
        )}
      </InitialUiLanguageGate>,
    );

    expect(container.querySelector('[data-locale-neutral-shell]')).not.toBeNull();
    expect(container.querySelector('[data-shell-sidebar]')).toBeNull();
    expect(screen.queryByTestId('app-language')).toBeNull();
    const pendingText = container.textContent ?? '';
    for (const chrome of WRONG_LANGUAGE_CHROME) {
      expect(pendingText).not.toContain(chrome);
    }

    settle();
    await waitFor(() => expect(screen.getByTestId('app-language')).toHaveTextContent('de'));
    expect(container.querySelector('[data-locale-neutral-shell]')).toBeNull();
  });

  it('hydrates the real extra locale without remounting the app tree twice', async () => {
    let settle!: () => void;
    const loadTranslations = vi.fn(() => new Promise<void>((resolve) => {
      settle = resolve;
    }));
    const { shell, catalog } = beginInitialUiLanguage('fr', loadTranslations, createMemoryStorage());
    let mounts = 0;

    function Child({ language }: { language: string }) {
      useEffect(() => {
        mounts += 1;
      }, []);
      return <div data-testid="app-language">{language}</div>;
    }

    render(
      <InitialUiLanguageGate shell={shell} catalog={catalog}>
        {(language) => <Child language={language} />}
      </InitialUiLanguageGate>,
    );

    expect(mounts).toBe(0);
    expect(screen.queryByTestId('app-language')).toBeNull();

    settle();
    await waitFor(() => expect(screen.getByTestId('app-language')).toHaveTextContent('fr'));
    expect(mounts).toBe(1);
  });

  it('hydrates persisted zh after a failed extra-locale catalog without painting zh chrome first', async () => {
    let rejectLoad!: (reason?: unknown) => void;
    const loadTranslations = vi.fn(() => new Promise<void>((_resolve, reject) => {
      rejectLoad = reject;
    }));
    const storageLike = createMemoryStorage([[UI_LANGUAGE_STORAGE_KEY, 'fr']]);
    const applied: string[] = [];
    const { shell, catalog } = beginInitialUiLanguage('fr', loadTranslations, storageLike);

    const { container } = render(
      <InitialUiLanguageGate
        shell={shell}
        catalog={catalog}
        onLanguage={(language) => applied.push(language)}
      >
        {(language) => (
          <div data-testid="app-language">
            {language}:{UI_TEXT[language]['layout.nav.home']}
          </div>
        )}
      </InitialUiLanguageGate>,
    );

    expect(container.querySelector('[data-locale-neutral-shell]')).not.toBeNull();
    expect(screen.queryByText(UI_TEXT.zh['layout.nav.home'])).toBeNull();
    expect(storageLike.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe('fr');

    rejectLoad(new TypeError('Failed to fetch dynamically imported module'));
    await waitFor(() => expect(screen.getByTestId('app-language')).toHaveTextContent(`zh:${UI_TEXT.zh['layout.nav.home']}`));
    expect(storageLike.getItem(UI_LANGUAGE_STORAGE_KEY)).toBe('zh');
    expect(applied).toEqual(['zh']);
  });
});
