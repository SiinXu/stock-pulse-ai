// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiLanguage } from '../i18n/uiText';
import { getFieldTitle } from '../utils/systemConfigI18n';
import { getSettingsHelpContent } from './settingsHelp';

interface SettingsFieldTitleInput {
  itemKey: string;
  schemaKey?: string | null;
  fallbackTitle?: string | null;
  language: UiLanguage;
}

export function resolveSettingsFieldTitle({
  itemKey,
  schemaKey,
  fallbackTitle,
  language,
}: SettingsFieldTitleInput): string {
  const fallback = fallbackTitle ?? itemKey;

  // The backend owns the live English schema title. Every other supported
  // language resolves known fields through the per-key catalog; only dynamic
  // fields absent from that catalog fall back to the backend title.
  if (language === 'en') {
    return fallback;
  }

  const localizedTitle = getFieldTitle(
    schemaKey ?? itemKey,
    getFieldTitle(itemKey, fallback, language),
    language,
  );
  if (localizedTitle !== fallback) {
    return localizedTitle;
  }

  return getSettingsHelpContent(schemaKey ?? itemKey, undefined, language)?.title
    ?? getSettingsHelpContent(itemKey, undefined, language)?.title
    ?? localizedTitle;
}
