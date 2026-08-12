// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { useEffect, useRef } from 'react';
import { systemConfigApi } from '../../api/systemConfig';
import { useThemeAppearanceOptional } from './ThemeAppearanceProvider';

const COLOR_SCHEME_KEY = 'MARKET_REVIEW_COLOR_SCHEME';

/** Mirror MARKET_REVIEW_COLOR_SCHEME onto data-price-direction when config loads. */
export function PriceDirectionSync(): null {
  const appearance = useThemeAppearanceOptional();
  const ranRef = useRef(false);

  useEffect(() => {
    if (!appearance || ranRef.current) return;
    let cancelled = false;

    void systemConfigApi
      .getConfig(false)
      .then((config) => {
        if (cancelled || !config?.items) return;
        const item = config.items.find((entry) => entry.key === COLOR_SCHEME_KEY);
        const value = item?.value;
        if (value === undefined || value === null || String(value).trim() === '') return;
        ranRef.current = true;
        appearance.syncPriceDirectionFromChangeColorPref(String(value));
      })
      .catch(() => {
        // offline / unauthenticated
      });

    return () => {
      cancelled = true;
    };
  }, [appearance]);

  return null;
}
