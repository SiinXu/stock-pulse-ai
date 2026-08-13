// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Built-in Theme Pack registry (Theme Contract v1).
 * Display names are proper nouns — not i18n keys (no bilingual baseline growth).
 */

import type { PriceDirectionId, ThemePackId } from './theme';
import { THEME_PACK_IDS } from './theme';

export type ThemePackCore = Readonly<Partial<Record<string, string>>>;

export type ThemePackDefinition = {
  id: ThemePackId;
  version: 1;
  displayName: string;
  priceDirection: PriceDirectionId | 'inherit';
  modes: {
    light: ThemePackCore;
    dark: ThemePackCore;
  };
};

export const THEME_PACKS: Readonly<Record<ThemePackId, ThemePackDefinition>> = {
  classic: {
    id: 'classic',
    version: 1,
    displayName: 'Classic',
    priceDirection: 'inherit',
    modes: { light: {}, dark: {} },
  },
  slate: {
    id: 'slate',
    version: 1,
    displayName: 'Slate',
    priceDirection: 'inherit',
    modes: {
      light: {
        primary: '215 16% 42%',
        ring: '215 16% 42%',
        background: '210 12% 97%',
        secondary: '210 12% 95%',
        muted: '210 12% 95%',
        accent: '210 12% 94%',
        hover: '210 12% 95%',
        border: '210 10% 90%',
        input: '210 10% 90%',
        'color-success': '152 40% 38%',
      },
      dark: {
        primary: '215 18% 68%',
        ring: '215 18% 68%',
        background: '220 10% 8%',
        secondary: '220 8% 14%',
        muted: '220 8% 14%',
        accent: '220 8% 16%',
        hover: '220 8% 16%',
        border: '220 8% 20%',
        input: '220 8% 20%',
        'color-success': '152 36% 58%',
      },
    },
  },
};

export const DEFAULT_THEME_PACK_ID: ThemePackId = 'classic';
export const DEFAULT_PRICE_DIRECTION_ID: PriceDirectionId = 'cn';

export function listThemePacks(): readonly ThemePackDefinition[] {
  return THEME_PACK_IDS.map((id) => THEME_PACKS[id]);
}

export function resolveThemePack(id: string | null | undefined): ThemePackDefinition {
  if (id && id in THEME_PACKS) {
    return THEME_PACKS[id as ThemePackId];
  }
  return THEME_PACKS[DEFAULT_THEME_PACK_ID];
}
