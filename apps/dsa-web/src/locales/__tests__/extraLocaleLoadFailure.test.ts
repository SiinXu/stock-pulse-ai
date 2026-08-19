// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { afterEach, describe, expect, it, vi } from 'vitest';

describe('extra-locale catalog load failures', () => {
  afterEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
  });

  it('fails completeness when a non-English locale loader is deliberately broken', async () => {
    vi.resetModules();
    const translations = await import('../../i18n/translations');
    const restore = translations.replaceUiLanguageTranslationLoaderForTests('ja', async () => {
      throw new Error('deliberately broken ja locale loader');
    });
    try {
      await expect(translations.loadUiLanguageTranslations('ja')).rejects.toThrow(
        'deliberately broken ja locale loader',
      );
      expect(translations.isUiLanguageTranslationsLoaded('ja')).toBe(false);
      expect(translations.getLoadedUiLanguageTranslations('ja')).toBeNull();

      const { PORTFOLIO_INSIGHT_CODES } = await import('../portfolioInsightCodes');
      const { PERSONAL_PERFORMANCE_REASON_LABELS } = await import('../personalPerformanceReasons');
      expect(() => PORTFOLIO_INSIGHT_CODES.ja.reasonNegativeEquity).toThrow(
        /UI translation bundle is not loaded: ja/,
      );
      expect(() => PERSONAL_PERFORMANCE_REASON_LABELS.ja.no_analysis_support).toThrow(
        /UI translation bundle is not loaded: ja/,
      );
    } finally {
      restore();
    }
  });

  it('fails completeness when a loaded extra-locale bundle is missing catalog keys', async () => {
    vi.resetModules();
    const translations = await import('../../i18n/translations');
    await translations.loadUiLanguageTranslations('de');
    const loaded = translations.getLoadedUiLanguageTranslations('de');
    expect(loaded).not.toBeNull();
    if (!loaded) {
      throw new Error('expected de translations to load');
    }
    const incomplete = { ...loaded } as Record<string, string>;
    delete incomplete['locales.portfolioInsightCodes.PORTFOLIO_INSIGHT_CODES.reasonNegativeEquity'];
    translations.unloadUiLanguageTranslationsForTests('de');
    const restore = translations.replaceUiLanguageTranslationLoaderForTests('de', async () => ({
      translations: incomplete as NonNullable<ReturnType<typeof translations.getLoadedUiLanguageTranslations>>,
    }));
    try {
      await translations.loadUiLanguageTranslations('de');
      const { PORTFOLIO_INSIGHT_CODES } = await import('../portfolioInsightCodes');
      expect(() => PORTFOLIO_INSIGHT_CODES.de.reasonNegativeEquity).toThrow(/Missing UI translation/);
    } finally {
      restore();
    }
  });
});
