// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { UiLanguage } from '../i18n/uiLanguages';

export type ServerPresentationText = {
  personalPerformanceReasons: Record<string, string>;
  portfolioInsightCodes: Record<string, string>;
};

type AdditionalLanguage = Exclude<UiLanguage, 'zh' | 'en'>;

const TRANSLATION_LOADERS = {
  de: () => import('./serverPresentationTranslations/de'),
  es: () => import('./serverPresentationTranslations/es'),
  fr: () => import('./serverPresentationTranslations/fr'),
  id: () => import('./serverPresentationTranslations/id'),
  ja: () => import('./serverPresentationTranslations/ja'),
  ko: () => import('./serverPresentationTranslations/ko'),
  ms: () => import('./serverPresentationTranslations/ms'),
  'zh-TW': () => import('./serverPresentationTranslations/zh-TW'),
} satisfies Record<AdditionalLanguage, () => Promise<{ default: ServerPresentationText }>>;

const cache = new Map<AdditionalLanguage, ServerPresentationText>();

export function getServerPresentationText(language: UiLanguage): ServerPresentationText | null {
  if (language === 'zh' || language === 'en') return null;
  return cache.get(language) ?? null;
}

export async function loadServerPresentationText(language: UiLanguage): Promise<ServerPresentationText> {
  if (language === 'zh' || language === 'en') {
    throw new Error('zh/en server presentation catalogs are source-owned');
  }
  const cached = cache.get(language);
  if (cached) return cached;
  const loaded = (await TRANSLATION_LOADERS[language]()).default;
  cache.set(language, loaded);
  return loaded;
}
