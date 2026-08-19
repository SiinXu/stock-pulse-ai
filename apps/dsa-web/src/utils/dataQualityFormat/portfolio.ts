// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { UiLanguage } from '../../i18n/uiText';
import { PORTFOLIO_LIMITATION_LABELS } from '../../locales/portfolio';
import { PORTFOLIO_RISK_METRICS_TEXT } from '../../locales/portfolioRiskMetrics';

const PORTFOLIO_STATUS_KEYS = {
  ok: 'statusOk',
  empty_portfolio: 'statusEmpty',
  insufficient_history: 'statusInsufficient',
  partial: 'statusPartial',
  unavailable: 'statusUnavailable',
} as const satisfies Record<string, keyof (typeof PORTFOLIO_RISK_METRICS_TEXT)['en']>;

function resolveRiskMetricsText(language: UiLanguage) {
  return PORTFOLIO_RISK_METRICS_TEXT[language] ?? PORTFOLIO_RISK_METRICS_TEXT.en;
}

/**
 * User-facing label for portfolio/risk data-quality and status codes.
 * Reuses PORTFOLIO_RISK_METRICS_TEXT. Unknown values keep the raw code.
 */
export function formatDataQualityStatus(
  status: string | null | undefined,
  language: UiLanguage,
): string {
  const text = resolveRiskMetricsText(language);
  if (status == null || status === '') {
    return text.statusUnknown;
  }
  const key = PORTFOLIO_STATUS_KEYS[status as keyof typeof PORTFOLIO_STATUS_KEYS];
  if (key) {
    return text[key];
  }
  return `${text.statusUnknown} (${status})`;
}

export function formatPortfolioStressQualityCell(
  row: {
    dataQuality?: string | null;
    priceStale?: boolean;
    limitations?: string[] | null;
  },
  language: UiLanguage,
  staleLabel: string,
  separator = ' · ',
): string {
  return [
    formatDataQualityStatus(row.dataQuality, language),
    row.priceStale ? staleLabel : null,
    ...(row.limitations ?? []).map((item) => PORTFOLIO_LIMITATION_LABELS[language][item] ?? item),
  ].filter(Boolean).join(separator);
}
