// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { createContext, useContext } from 'react';
import type { PriceDirectionId, ThemePackId } from '../design/theme';

export type ThemeAppearanceContextValue = {
  pack: ThemePackId;
  priceDirection: PriceDirectionId;
  setPack: (pack: ThemePackId) => void;
  setPriceDirection: (direction: PriceDirectionId) => void;
  syncPriceDirectionFromChangeColorPref: (
    pref: string | null | undefined,
    persist?: boolean,
  ) => void;
};

export const ThemeAppearanceContext = createContext<ThemeAppearanceContextValue | null>(null);

export function useThemeAppearance(): ThemeAppearanceContextValue {
  const context = useContext(ThemeAppearanceContext);
  if (!context) throw new Error('useThemeAppearance must be used within ThemeAppearanceProvider');
  return context;
}

export function useThemeAppearanceOptional(): ThemeAppearanceContextValue | null {
  return useContext(ThemeAppearanceContext);
}

const ignorePriceDirectionSync: ThemeAppearanceContextValue['syncPriceDirectionFromChangeColorPref'] = () => {};

/** Stable no-op outside the app provider, for isolated Settings mounts. */
export function usePriceDirectionSync(): ThemeAppearanceContextValue['syncPriceDirectionFromChangeColorPref'] {
  return useContext(ThemeAppearanceContext)?.syncPriceDirectionFromChangeColorPref
    ?? ignorePriceDirectionSync;
}
