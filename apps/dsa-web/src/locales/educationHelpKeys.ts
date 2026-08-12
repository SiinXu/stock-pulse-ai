// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Stable help keys for plain-language risk levels and indicator explanations (Issue #201).
 * Content lives in settingsHelp.en.ts / settingsHelp.zh.ts and is resolved via getSettingsHelpContent.
 */

export const EDUCATION_HELP_KEYS = {
  riskLevelLow: 'education.risk.level.low',
  riskLevelMedium: 'education.risk.level.medium',
  riskLevelHigh: 'education.risk.level.high',
  riskLevelCritical: 'education.risk.level.critical',
  beginnerRiskElevated: 'education.risk.beginner.elevated',
  beginnerRiskModerate: 'education.risk.beginner.moderate',
  beginnerRiskUnrated: 'education.risk.beginner.unrated',
  riskSection: 'education.risk.section',
  riskGatePass: 'education.risk.gate.pass',
  riskGateDowngrade: 'education.risk.gate.downgrade',
  riskGateReject: 'education.risk.gate.reject',
  riskGateNotEvaluated: 'education.risk.gate.not_evaluated',
  riskGateError: 'education.risk.gate.error',
  riskGateLoading: 'education.risk.gate.loading',
  portfolioHealth: 'education.portfolio.health',
  portfolioVar: 'education.portfolio.var',
  portfolioConcentration: 'education.portfolio.concentration',
  portfolioDiversification: 'education.portfolio.diversification',
  indicatorMa: 'education.indicator.ma',
  indicatorMacd: 'education.indicator.macd',
  indicatorRsi: 'education.indicator.rsi',
} as const;

export type EducationHelpKey = (typeof EDUCATION_HELP_KEYS)[keyof typeof EDUCATION_HELP_KEYS];

export type RiskScoreLevel = 'low' | 'medium' | 'high' | 'critical' | 'missing';

export function riskScoreLevelHelpKey(level: RiskScoreLevel): EducationHelpKey | null {
  switch (level) {
    case 'low':
      return EDUCATION_HELP_KEYS.riskLevelLow;
    case 'medium':
      return EDUCATION_HELP_KEYS.riskLevelMedium;
    case 'high':
      return EDUCATION_HELP_KEYS.riskLevelHigh;
    case 'critical':
      return EDUCATION_HELP_KEYS.riskLevelCritical;
    default:
      return null;
  }
}

export type BeginnerRiskKind = 'elevated' | 'moderate' | 'unrated';

export function beginnerRiskHelpKey(risk: BeginnerRiskKind): EducationHelpKey {
  switch (risk) {
    case 'elevated':
      return EDUCATION_HELP_KEYS.beginnerRiskElevated;
    case 'moderate':
      return EDUCATION_HELP_KEYS.beginnerRiskModerate;
    case 'unrated':
    default:
      return EDUCATION_HELP_KEYS.beginnerRiskUnrated;
  }
}

export type RiskGateHelpStatus =
  | 'pass'
  | 'downgrade'
  | 'reject'
  | 'not_evaluated'
  | 'error'
  | 'loading';

export function riskGateStatusHelpKey(status: RiskGateHelpStatus): EducationHelpKey {
  switch (status) {
    case 'pass':
      return EDUCATION_HELP_KEYS.riskGatePass;
    case 'downgrade':
      return EDUCATION_HELP_KEYS.riskGateDowngrade;
    case 'reject':
      return EDUCATION_HELP_KEYS.riskGateReject;
    case 'error':
      return EDUCATION_HELP_KEYS.riskGateError;
    case 'loading':
      return EDUCATION_HELP_KEYS.riskGateLoading;
    case 'not_evaluated':
    default:
      return EDUCATION_HELP_KEYS.riskGateNotEvaluated;
  }
}
