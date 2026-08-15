// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { useEffect, useState } from 'react';
import type { UiLanguage } from '../../i18n/uiLanguages';
import {
  getPortfolioInsightsText,
  loadPortfolioInsightsText,
  SOURCE_PORTFOLIO_INSIGHTS_TEXT,
  type PortfolioInsightsText,
} from '../../locales/portfolioInsights';

type LoadedText = {
  language: UiLanguage;
  text: PortfolioInsightsText;
};

export function usePortfolioInsightsText(language: UiLanguage): PortfolioInsightsText {
  const synchronous = getPortfolioInsightsText(language);
  const [loaded, setLoaded] = useState<LoadedText | null>(null);

  useEffect(() => {
    if (synchronous) return undefined;
    let active = true;
    void loadPortfolioInsightsText(language).then((text) => {
      if (active) setLoaded({ language, text });
    });
    return () => {
      active = false;
    };
  }, [language, synchronous]);

  if (synchronous) return synchronous;
  if (loaded?.language === language) return loaded.text;
  return SOURCE_PORTFOLIO_INSIGHTS_TEXT.en;
}
