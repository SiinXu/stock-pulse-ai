// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  applyPriceDirection,
  applyThemePack,
  bootstrapThemeAppearance,
  readDocumentPriceDirection,
  readDocumentThemePack,
} from '../themeRuntime';
import { THEME_STORAGE_KEYS } from '../../../design/theme';

describe('themeRuntime', () => {
  beforeEach(() => {
    document.documentElement.removeAttribute('data-theme-pack');
    document.documentElement.removeAttribute('data-price-direction');
    localStorage.removeItem(THEME_STORAGE_KEYS.pack);
    localStorage.removeItem(THEME_STORAGE_KEYS.priceDirection);
  });

  afterEach(() => {
    localStorage.removeItem(THEME_STORAGE_KEYS.pack);
    localStorage.removeItem(THEME_STORAGE_KEYS.priceDirection);
  });

  it('applies classic pack and CN price direction by default', () => {
    const applied = bootstrapThemeAppearance();
    expect(applied.pack).toBe('classic');
    expect(applied.priceDirection).toBe('cn');
    expect(document.documentElement.getAttribute('data-theme-pack')).toBe('classic');
    expect(document.documentElement.getAttribute('data-price-direction')).toBe('cn');
  });

  it('persists slate pack selection', () => {
    applyThemePack('slate');
    expect(readDocumentThemePack()).toBe('slate');
    expect(localStorage.getItem(THEME_STORAGE_KEYS.pack)).toBe('slate');
  });

  it('persists US price direction (green_up convention)', () => {
    applyPriceDirection('us');
    expect(readDocumentPriceDirection()).toBe('us');
    expect(localStorage.getItem(THEME_STORAGE_KEYS.priceDirection)).toBe('us');
  });

  it('restores pack and price direction from storage on bootstrap', () => {
    localStorage.setItem(THEME_STORAGE_KEYS.pack, 'slate');
    localStorage.setItem(THEME_STORAGE_KEYS.priceDirection, 'us');
    const applied = bootstrapThemeAppearance();
    expect(applied).toEqual({ pack: 'slate', priceDirection: 'us' });
  });
});
