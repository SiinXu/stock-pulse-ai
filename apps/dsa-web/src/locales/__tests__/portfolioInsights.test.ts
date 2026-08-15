// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, it } from 'vitest';
import { ADDITIONAL_UI_LANGUAGES } from '../../i18n/uiLanguages';
import {
  loadPortfolioImportText,
  SOURCE_PORTFOLIO_IMPORT_TEXT,
} from '../portfolioImport';
import {
  loadPortfolioInsightsText,
  SOURCE_PORTFOLIO_INSIGHTS_TEXT,
} from '../portfolioInsights';

const SOURCE_KEYS = Object.keys(SOURCE_PORTFOLIO_INSIGHTS_TEXT.en).sort();
const IMPORT_SOURCE_KEYS = Object.keys(SOURCE_PORTFOLIO_IMPORT_TEXT.en).sort();

describe('portfolio insights text inventory', () => {
  it('keeps the Chinese and English source inventories in parity', () => {
    expect(Object.keys(SOURCE_PORTFOLIO_INSIGHTS_TEXT.zh).sort()).toEqual(SOURCE_KEYS);
    expect(Object.keys(SOURCE_PORTFOLIO_IMPORT_TEXT.zh).sort()).toEqual(IMPORT_SOURCE_KEYS);
  });

  it.each(ADDITIONAL_UI_LANGUAGES)(
    'lazy-loads complete, non-English portfolio insights copy for %s',
    async (language) => {
      const translated = await loadPortfolioInsightsText(language);
      expect(Object.keys(translated).sort()).toEqual(SOURCE_KEYS);
      expect(Object.values(translated).every((value) => value.trim().length > 0)).toBe(true);
      expect(translated).not.toEqual(SOURCE_PORTFOLIO_INSIGHTS_TEXT.en);

      const importText = await loadPortfolioImportText(language);
      expect(Object.keys(importText).sort()).toEqual(IMPORT_SOURCE_KEYS);
      expect(Object.values(importText).every((value) => value.trim().length > 0)).toBe(true);
      expect(importText).not.toEqual(SOURCE_PORTFOLIO_IMPORT_TEXT.en);
    },
  );
});
