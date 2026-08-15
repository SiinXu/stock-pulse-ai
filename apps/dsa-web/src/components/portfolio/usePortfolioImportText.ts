// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { useEffect, useState } from 'react';
import type { UiLanguage } from '../../i18n/uiLanguages';
import {
  getPortfolioImportText,
  loadPortfolioImportText,
  SOURCE_PORTFOLIO_IMPORT_TEXT,
  type PortfolioImportText,
} from '../../locales/portfolioImport';

type LoadedText = {
  language: UiLanguage;
  text: PortfolioImportText;
};

export function usePortfolioImportText(language: UiLanguage): PortfolioImportText {
  const synchronous = getPortfolioImportText(language);
  const [loaded, setLoaded] = useState<LoadedText | null>(null);

  useEffect(() => {
    if (synchronous) return undefined;
    let active = true;
    void loadPortfolioImportText(language).then((text) => {
      if (active) setLoaded({ language, text });
    });
    return () => {
      active = false;
    };
  }, [language, synchronous]);

  if (synchronous) return synchronous;
  if (loaded?.language === language) return loaded.text;
  return SOURCE_PORTFOLIO_IMPORT_TEXT.en;
}
