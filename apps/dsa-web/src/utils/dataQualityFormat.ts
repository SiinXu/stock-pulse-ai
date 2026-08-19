// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { UiLanguage } from '../i18n/uiText';
import { ALERT_TRIGGER_TEXT } from '../locales/alerts';
import { ANALYSIS_CONTEXT_CONTENT_TEXT } from '../locales/reportContent';
import { PORTFOLIO_LIMITATION_LABELS } from '../locales/portfolio';
import { PORTFOLIO_RISK_METRICS_TEXT } from '../locales/portfolioRiskMetrics';
import { getReportLanguageForUi } from './reportLanguage';

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

/**
 * User-facing label for AnalysisContextPack data-quality levels.
 * Reuses ANALYSIS_CONTEXT_CONTENT_TEXT.qualityLevel. Unknown values keep the raw code.
 */
export function formatDataQualityLevel(
  level: string | null | undefined,
  language: UiLanguage,
): string | null {
  if (!level) {
    return null;
  }
  const labels = ANALYSIS_CONTEXT_CONTENT_TEXT[getReportLanguageForUi(language)].qualityLevel;
  return labels[level as keyof typeof labels] ?? level;
}

/**
 * User-facing label for AnalysisContextPack limitation strings such as
 * `fundamentals: fetch_failed`. Reuses the existing report-content maps.
 * Unrecognized fragments stay visible.
 */
export function formatDataQualityLimitation(
  value: string,
  language: UiLanguage,
): string {
  const reportLanguage = getReportLanguageForUi(language);
  const text = ANALYSIS_CONTEXT_CONTENT_TEXT[reportLanguage];
  const [rawKey, ...statusParts] = value.split(':');
  if (!rawKey || statusParts.length === 0) {
    return value;
  }

  const key = rawKey.trim();
  const status = statusParts.join(':').trim();
  if (!key || !status) {
    return value;
  }

  const label = text.blockLabels[key] || key;
  const statusLabel = (text.status as Record<string, string>)[status] || status;
  return reportLanguage === 'zh' ? `${label}：${statusLabel}` : `${label}: ${statusLabel}`;
}

/**
 * User-facing alert trigger status. Reuses ALERT_TRIGGER_TEXT.statuses.
 * Unknown values keep the raw code.
 */
export function formatAlertTriggerStatus(
  status: string | null | undefined,
  language: UiLanguage,
): string {
  if (status == null || status === '') {
    return '--';
  }
  const labels = ALERT_TRIGGER_TEXT[language].statuses;
  return labels[status as keyof typeof labels] ?? status;
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
