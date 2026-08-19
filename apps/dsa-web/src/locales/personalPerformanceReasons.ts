// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../i18n/uiText';
import { loadUiLanguageTranslations } from '../i18n/translations';

const zh = {
  no_analysis_support: '这笔成交没有关联的 DecisionSignal 或分析计划。',
  signal_linked: '在回看窗口内找到了关联的 DecisionSignal。',
  action_aligned: '信号动作与成交方向一致。',
  action_misaligned: '信号动作不支持该成交方向。',
  reason_present: '信号包含可读理由。',
  reason_missing: '信号没有理由文本。',
  plan_quality_adequate: '计划质量足够（完整或部分）。',
  plan_quality_weak: '计划质量偏弱或未知。',
  analysis_or_evidence: '存在分析或证据支撑。',
  risk_gate_unverifiable: '风险门无法核验。',
  risk_gate_unverifiable_sell: '卖出成交的风险门无法核验。',
  missing_invalidation_or_stop_loss: '缺少失效条件或止损。',
  invalidation_or_stop_present: '包含失效条件或止损。',
  missing_confidence: '缺少置信度。',
  confidence_below_threshold: '置信度低于可执行阈值。',
  confidence_ok: '置信度达到可执行阈值。',
  insufficient_data_quality: '数据质量不足。',
  elevated_data_gaps: '数据缺口偏高。',
  data_quality_ok: '数据质量可接受。',
  trade_against_risk_gate: '成交方向与风险门冲突。',
  defensive_action_aligned: '防御性动作与信号一致。',
  sell_against_bullish_signal: '卖出与看多信号冲突。',
  exit_plan_thin: '退出计划偏薄。',
  risk_notes_present: '包含风险说明。',
  position_size_unavailable: '无法核验仓位大小。',
  size_within_ideal: '仓位位于理想区间。',
  size_exceeds_poor_band: '仓位超过较差区间。',
  size_elevated: '仓位偏高。',
  size_not_reduced_for_gaps: '数据缺口下仓位未收敛。',
  size_restrained_for_gaps: '数据缺口下仓位已收敛。',
  sell_resulting_exposure_evaluated: '已评估卖出后的剩余敞口。',
} as const;

const en: Record<keyof typeof zh, string> = {
  no_analysis_support: 'No DecisionSignal or analysis plan was linked to this trade.',
  signal_linked: 'A DecisionSignal was found within the lookback window.',
  action_aligned: 'Signal action aligns with the trade side.',
  action_misaligned: 'Signal action does not support the trade side.',
  reason_present: 'The signal includes a human-readable reason.',
  reason_missing: 'The signal has no reason text.',
  plan_quality_adequate: 'Plan quality is complete or partial.',
  plan_quality_weak: 'Plan quality is weak or unknown.',
  analysis_or_evidence: 'Analysis or evidence support is present.',
  risk_gate_unverifiable: 'The risk gate could not be verified.',
  risk_gate_unverifiable_sell: 'The risk gate could not be verified for this sell.',
  missing_invalidation_or_stop_loss: 'Invalidation or stop-loss is missing.',
  invalidation_or_stop_present: 'Invalidation or stop-loss is present.',
  missing_confidence: 'Confidence is missing.',
  confidence_below_threshold: 'Confidence is below the actionable threshold.',
  confidence_ok: 'Confidence meets the actionable threshold.',
  insufficient_data_quality: 'Data quality is insufficient.',
  elevated_data_gaps: 'Data gaps are elevated.',
  data_quality_ok: 'Data quality is acceptable.',
  trade_against_risk_gate: 'The trade conflicts with the risk gate.',
  defensive_action_aligned: 'The defensive action aligns with the signal.',
  sell_against_bullish_signal: 'The sell conflicts with a bullish signal.',
  exit_plan_thin: 'The exit plan is thin.',
  risk_notes_present: 'Risk notes are present.',
  position_size_unavailable: 'Position size could not be verified.',
  size_within_ideal: 'Position size is inside the ideal band.',
  size_exceeds_poor_band: 'Position size exceeds the poor band.',
  size_elevated: 'Position size is elevated.',
  size_not_reduced_for_gaps: 'Position size was not reduced for data gaps.',
  size_restrained_for_gaps: 'Position size was restrained for data gaps.',
  sell_resulting_exposure_evaluated: 'Remaining exposure after the sell was evaluated.',
};

export type PersonalPerformanceReasonText = Record<keyof typeof zh, string>;

export const PERSONAL_PERFORMANCE_REASON_LABELS = createUiLanguageRecord(
  'locales.personalPerformanceReasons.PERSONAL_PERFORMANCE_REASON_LABELS',
  { zh, en },
);

export function getPersonalPerformanceReasonLabels(language: UiLanguage): PersonalPerformanceReasonText {
  return PERSONAL_PERFORMANCE_REASON_LABELS[language];
}

export async function loadPersonalPerformanceReasonLabels(
  language: UiLanguage,
): Promise<PersonalPerformanceReasonText> {
  await loadUiLanguageTranslations(language);
  return PERSONAL_PERFORMANCE_REASON_LABELS[language];
}
