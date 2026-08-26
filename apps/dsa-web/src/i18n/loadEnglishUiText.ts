// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiTextKey } from './uiTextZh';

type EnglishUiText = Record<UiTextKey, string>;
let loadedEnglishUiText: EnglishUiText | null = null;
let pendingEnglishUiText: Promise<void> | null = null;

// Keep this factory in an entry-side module that vite manualChunks isolates
// from the BacktestPage/backtest-support family. translations/index.ts is
// imported by createUiLanguageRecord (used by locales/backtest), so an
// import() there is emitted from already-preloaded backtest-support.
const ENGLISH_UI_TEXT_LOADER = () => import('./uiTextEn');

export function getLoadedEnglishUiText(): EnglishUiText | null {
  return loadedEnglishUiText;
}

export async function loadEnglishUiTextPayload(): Promise<void> {
  if (loadedEnglishUiText) return;
  if (!pendingEnglishUiText) {
    pendingEnglishUiText = ENGLISH_UI_TEXT_LOADER().then(({ en }) => {
      loadedEnglishUiText = en;
    }).finally(() => {
      pendingEnglishUiText = null;
    });
  }
  await pendingEnglishUiText;
}

export function unloadEnglishUiTextForTests(): void {
  if (import.meta.env.MODE !== 'test') {
    throw new Error('test-only');
  }
  loadedEnglishUiText = null;
  pendingEnglishUiText = null;
}
