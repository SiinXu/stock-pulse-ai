// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import {
  useCallback,
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
import {
  ThemeAppearanceContext,
} from '../../contexts/ThemeAppearanceContext';

export const ThemeAppearanceProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [pack, setPackState] = useState<ThemePackId>(() => {
    if (typeof document === 'undefined') return 'classic';
    bootstrapThemeAppearance();
    return readDocumentThemePack();
  });
  const [priceDirection, setPriceDirectionState] = useState<PriceDirectionId>(() => {
    if (typeof document === 'undefined') return 'cn';
    return readDocumentPriceDirection();
  });

  const setPack = useCallback((next: ThemePackId) => {
    setPackState(applyThemePack(next));
  }, []);

  const setPriceDirection = useCallback((next: PriceDirectionId) => {
    setPriceDirectionState(applyPriceDirection(next));
  }, []);

  const syncPriceDirectionFromChangeColorPref = useCallback(
    (pref: string | null | undefined, persist = true) => {
      if (pref === null || pref === undefined || String(pref).trim() === '') return;
      const applied = applyPriceDirection(
        priceDirectionFromChangeColorPref(pref),
        { persist },
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
