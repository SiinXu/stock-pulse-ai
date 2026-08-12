// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import type { PriceDirectionId, ThemePackId } from '../../design/theme';
import { priceDirectionFromChangeColorPref } from '../../design/theme';
import {
  applyPriceDirection,
  applyThemePack,
  bootstrapThemeAppearance,
  readDocumentPriceDirection,
  readDocumentThemePack,
} from './themeRuntime';

export type SyncPriceDirectionOptions = {
  /**
   * When true (default), write localStorage. Draft Settings edits should pass
   * false so uncommitted values do not outlive a cancelled settings session.
   */
  persist?: boolean;
};

type ThemeAppearanceContextValue = {
  pack: ThemePackId;
  priceDirection: PriceDirectionId;
  setPack: (pack: ThemePackId) => void;
  setPriceDirection: (direction: PriceDirectionId) => void;
  syncPriceDirectionFromChangeColorPref: (
    pref: string | null | undefined,
    options?: SyncPriceDirectionOptions,
  ) => void;
};

const ThemeAppearanceContext = createContext<ThemeAppearanceContextValue | null>(null);

export const ThemeAppearanceProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [pack, setPackState] = useState<ThemePackId>(() => {
    if (typeof document === 'undefined') return 'classic';
    bootstrapThemeAppearance({ persist: false });
    return readDocumentThemePack();
  });
  const [priceDirection, setPriceDirectionState] = useState<PriceDirectionId>(() => {
    if (typeof document === 'undefined') return 'cn';
    return readDocumentPriceDirection();
  });

  useEffect(() => {
    const applied = bootstrapThemeAppearance();
    setPackState(applied.pack);
    setPriceDirectionState(applied.priceDirection);
  }, []);

  const setPack = useCallback((next: ThemePackId) => {
    setPackState(applyThemePack(next));
  }, []);

  const setPriceDirection = useCallback((next: PriceDirectionId) => {
    setPriceDirectionState(applyPriceDirection(next));
  }, []);

  const syncPriceDirectionFromChangeColorPref = useCallback(
    (pref: string | null | undefined, options?: SyncPriceDirectionOptions) => {
      if (pref === null || pref === undefined || String(pref).trim() === '') return;
      const applied = applyPriceDirection(
        priceDirectionFromChangeColorPref(pref),
        { persist: options?.persist !== false },
      );
      setPriceDirectionState(applied);
    },
    [],
  );

  const value = useMemo(
    () => ({
      pack,
      priceDirection,
      setPack,
      setPriceDirection,
      syncPriceDirectionFromChangeColorPref,
    }),
    [pack, priceDirection, setPack, setPriceDirection, syncPriceDirectionFromChangeColorPref],
  );

  return (
    <ThemeAppearanceContext.Provider value={value}>
      {children}
    </ThemeAppearanceContext.Provider>
  );
};

export function useThemeAppearance(): ThemeAppearanceContextValue {
  const ctx = useContext(ThemeAppearanceContext);
  if (!ctx) throw new Error('useThemeAppearance must be used within ThemeAppearanceProvider');
  return ctx;
}

export function useThemeAppearanceOptional(): ThemeAppearanceContextValue | null {
  return useContext(ThemeAppearanceContext);
}
