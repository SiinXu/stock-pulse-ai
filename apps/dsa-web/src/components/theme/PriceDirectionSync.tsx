// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { useEffect, useRef } from 'react';
import { systemConfigApi } from '../../api/systemConfig';
import { useThemeAppearanceOptional } from '../../contexts/ThemeAppearanceContext';
import {
  readDocumentPriceDirection,
  readStoredPriceDirection,
} from './themeRuntime';

const COLOR_SCHEME_KEY = 'MARKET_REVIEW_COLOR_SCHEME';

/** Session-only Settings preview: document attr changed without writing storage. */
function hasUnpersistedPriceDirectionPreview(): boolean {
  return readDocumentPriceDirection() !== readStoredPriceDirection();
}

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
        // A Settings draft may have already previewed a different convention
        // with persist: false; do not revert the document or write storage.
        if (hasUnpersistedPriceDirectionPreview()) return;
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
