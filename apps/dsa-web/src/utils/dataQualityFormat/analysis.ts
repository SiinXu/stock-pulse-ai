// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { UiLanguage } from '../../i18n/uiText';
import {
  ANALYSIS_CONTEXT_BLOCK_LABELS,
  ANALYSIS_CONTEXT_QUALITY_LEVEL_LABELS,
  ANALYSIS_CONTEXT_STATUS_LABELS,
} from '../../locales/analysisContextQuality';
import { getReportLanguageForUi } from '../reportLanguage';

import {
  formatLabeledDiagnostic,
  formatUnknownMachineCode,
  isStableMachineCode,
} from './unknownCode';

/**
 * User-facing label for AnalysisContextPack data-quality levels.
 * Reuses ANALYSIS_CONTEXT_QUALITY_LEVEL_LABELS. Unknown values become
 * localized diagnostics with a sanitized code, not raw snake_case.
 */
export function formatDataQualityLevel(
  level: string | null | undefined,
  language: UiLanguage,
): string | null {
  if (!level) {
    return null;
  }
  const labels = ANALYSIS_CONTEXT_QUALITY_LEVEL_LABELS[getReportLanguageForUi(language)];
  return labels[level as keyof typeof labels] ?? formatUnknownMachineCode(level, language);
}

function formatLimitationFragment(
  value: string,
  known: string | undefined,
  language: UiLanguage,
): string {
  if (known) return known;
  if (isStableMachineCode(value)) return formatUnknownMachineCode(value, language);
  return formatLabeledDiagnostic(value, language);
}

/**
 * User-facing label for AnalysisContextPack limitation strings such as
 * `fundamentals: fetch_failed`. Reuses the existing report-content maps.
 * Unrecognized fragments stay visible as localized diagnostics.
 */
export function formatDataQualityLimitation(
  value: string,
  language: UiLanguage,
): string {
  const reportLanguage = getReportLanguageForUi(language);
  const [rawKey, ...statusParts] = value.split(':');
  if (!rawKey || statusParts.length === 0) {
    return formatLimitationFragment(value, undefined, language);
  }

  const key = rawKey.trim();
  const status = statusParts.join(':').trim();
  if (!key || !status) {
    return formatLimitationFragment(value, undefined, language);
  }

  const label = formatLimitationFragment(
    key,
    ANALYSIS_CONTEXT_BLOCK_LABELS[reportLanguage][key] || undefined,
    language,
  );
  const statusLabel = formatLimitationFragment(
    status,
    ANALYSIS_CONTEXT_STATUS_LABELS[reportLanguage][status as keyof typeof ANALYSIS_CONTEXT_STATUS_LABELS.en] || undefined,
    language,
  );
  return reportLanguage === 'zh' ? `${label}：${statusLabel}` : `${label}: ${statusLabel}`;
}
