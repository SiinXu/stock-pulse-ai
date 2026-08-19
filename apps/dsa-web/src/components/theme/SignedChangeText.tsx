// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useThemeAppearanceOptional } from '../../contexts/ThemeAppearanceContext';
import { changeColorPrefFromPriceDirection } from '../../design/theme';
import { cn } from '../../utils/cn';
import { changeColorStyle, coerceMarketId } from '../../utils/marketFormat';
import { readDocumentPriceDirection } from './themeRuntime';

type SignedChangeTextProps = {
  value: number | null | undefined;
  /**
   * Market id or stock code. When provided but unresolvable, the value stays
   * unpainted (unknown/neutral). Omit this prop for non-instrument figures
   * such as calculator gain so document preference can still apply.
   */
  market?: string | null;
  children: React.ReactNode;
  className?: string;
  /** Applied when the value is zero, missing, unknown, or non-finite (no price paint). */
  fallbackClassName?: string;
};

/**
 * Paint a signed price / gain / loss with the canonical marketFormat tokens.
 * Neutral, unknown-market, and non-finite values stay unpainted; callers must
 * also show sign or wording. Preference comes from ThemeAppearance /
 * `data-price-direction` (Settings MARKET_REVIEW_COLOR_SCHEME).
 */
export const SignedChangeText: React.FC<SignedChangeTextProps> = ({
  value,
  market,
  children,
  className,
  fallbackClassName,
}) => {
  const appearance = useThemeAppearanceOptional();
  const userPref = changeColorPrefFromPriceDirection(
    appearance?.priceDirection ?? readDocumentPriceDirection(),
  );
  const marketProvided = market !== undefined;
  const resolved = marketProvided ? coerceMarketId(market) : null;
  const style = marketProvided && resolved === null
    ? undefined
    : changeColorStyle(value, resolved, userPref);
  return (
    <span className={cn(style ? className : fallbackClassName)} style={style}>
      {children}
    </span>
  );
};
