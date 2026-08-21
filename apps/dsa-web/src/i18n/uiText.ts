// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from './createUiLanguageRecord';
import { getLoadedEnglishUiText } from './translations';
import { zh, type UiTextKey } from './uiTextZh';
import type { UiLanguage } from './uiLanguages';

export type { UiLanguage } from './uiLanguages';
export type { UiTextKey } from './uiTextZh';

function englishUiText() {
  const loaded = getLoadedEnglishUiText();
  if (!loaded) {
    throw new Error('UI translation bundle is not loaded: en');
  }
  return loaded;
}

export const UI_TEXT: Record<UiLanguage, Record<UiTextKey, string>> = createUiLanguageRecord(
  'i18n.uiText.UI_TEXT',
  {
    zh,
    get en() {
      return englishUiText();
    },
  },
);

export type UiTextParams = Record<string, string | number>;

export function formatUiText(template: string, params?: UiTextParams): string {
  if (!params) {
    return template;
  }

  return template.replace(/\{(\w+)\}/g, (match, key: string) => {
    const value = params[key];
    return value === undefined ? match : String(value);
  });
}
