// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { UiLanguage } from '../../i18n/uiText';
import {
  ANALYSIS_CONTEXT_BLOCK_LABELS,
  ANALYSIS_CONTEXT_QUALITY_LEVEL_LABELS,
  ANALYSIS_CONTEXT_STATUS_LABELS,
} from '../../locales/analysisContextQuality';
import { getReportLanguageForUi } from '../reportLanguage';

/**
 * User-facing label for AnalysisContextPack data-quality levels.
 * Reuses ANALYSIS_CONTEXT_QUALITY_LEVEL_LABELS. Unknown values keep the raw code.
 */
export function formatDataQualityLevel(
  level: string | null | undefined,
  language: UiLanguage,
): string | null {
  if (!level) {
    return null;
  }
  const labels = ANALYSIS_CONTEXT_QUALITY_LEVEL_LABELS[getReportLanguageForUi(language)];
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
  const [rawKey, ...statusParts] = value.split(':');
  if (!rawKey || statusParts.length === 0) {
    return value;
  }

  const key = rawKey.trim();
  const status = statusParts.join(':').trim();
  if (!key || !status) {
    return value;
  }

  const label = ANALYSIS_CONTEXT_BLOCK_LABELS[reportLanguage][key] || key;
  const statusLabel = ANALYSIS_CONTEXT_STATUS_LABELS[reportLanguage][status as keyof typeof ANALYSIS_CONTEXT_STATUS_LABELS.en] || status;
  return reportLanguage === 'zh' ? `${label}：${statusLabel}` : `${label}: ${statusLabel}`;
}
