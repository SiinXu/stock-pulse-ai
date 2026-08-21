// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiTextKey } from './uiTextZh';

type EnglishUiText = Record<UiTextKey, string>;

let loadedEnglishUiText: EnglishUiText | null = null;
let pendingEnglishUiText: Promise<void> | null = null;

export function getLoadedEnglishUiText(): EnglishUiText | null {
  return loadedEnglishUiText;
}

export async function loadEnglishUiTextPayload(): Promise<void> {
  if (loadedEnglishUiText) return;
  if (!pendingEnglishUiText) {
    pendingEnglishUiText = import('./uiTextEn').then(({ en }) => {
      loadedEnglishUiText = en;
    }).finally(() => {
      pendingEnglishUiText = null;
    });
  }
  await pendingEnglishUiText;
}

export function unloadEnglishUiTextForTests(): void {
  if (import.meta.env.MODE !== 'test') {
    throw new Error('unloadEnglishUiTextForTests is test-only');
  }
  loadedEnglishUiText = null;
  pendingEnglishUiText = null;
}

// Dev, tests, and the i18n resource checker need synchronous English source
// text. Production keeps this payload off the entry chunk and loads it through
// loadUiLanguageTranslations.
if (!import.meta.env || import.meta.env.DEV || import.meta.env.MODE === 'test') {
  await loadEnglishUiTextPayload();
}
