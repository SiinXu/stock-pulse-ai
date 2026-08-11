// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Presentation-only Decision Card assembly (Issue #874 / #861 Phase 1 web view).
 * Mirrors templates/_macros.j2 decision_card field selection and missing-field
 * omission. Does not invent backend fields.
 */
import type {
  AnalysisReport,
  ReportDetails,
  ReportMeta,
  ReportStrategy,
  ReportSummary as ReportSummaryType,
} from '../../types/analysis';

export interface ReportDecisionCardModel {
  signalLabel?: string;
  score?: number;
  oneSentence?: string;
  trendPrediction?: string;
  confidenceLevel?: string;
  confidenceReason?: string;
  immediateAction?: string;
  timeSensitivity?: string;
  positionNoPosition?: string;
  positionHasPosition?: string;
  keyRisks: string[];
  riskWarning?: string;
  watchConditions: string[];
  stopLoss?: string;
  takeProfit?: string;
}

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

const asTrimmedString = (value: unknown): string | undefined => {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || undefined;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value);
  }
  return undefined;
};

const asStringList = (value: unknown, limit = 3): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => asTrimmedString(item))
    .filter((item): item is string => Boolean(item))
    .slice(0, limit);
};

const pick = (
  record: Record<string, unknown> | null | undefined,
  camel: string,
  snake: string,
): unknown => {
  if (!record) {
    return undefined;
  }
  return record[camel] ?? record[snake];
};

const nestedRecord = (
  parent: Record<string, unknown> | null | undefined,
  camel: string,
  snake: string,
): Record<string, unknown> | null => asRecord(pick(parent, camel, snake));

const resolveDashboard = (details?: ReportDetails | null): Record<string, unknown> | null => {
  const raw = details?.rawResult;
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  return asRecord((raw as Record<string, unknown>).dashboard);
};

const cleanLevel = (value: unknown): string | undefined => {
  const text = asTrimmedString(value);
  if (!text) {
    return undefined;
  }
  const lower = text.toLowerCase();
  if (['unknown', 'n/a', 'na', 'none', 'null', '-'].includes(lower)) {
    return undefined;
  }
  return text;
};

export const buildReportDecisionCardModel = (input: {
  meta?: ReportMeta | null;
  summary?: ReportSummaryType | null;
  strategy?: ReportStrategy | null;
  details?: ReportDetails | null;
  signalLabel?: string | null;
}): ReportDecisionCardModel => {
  const { summary, strategy, details, signalLabel } = input;
  const raw = asRecord(details?.rawResult);
  const dashboard = resolveDashboard(details);
  const core = nestedRecord(dashboard, 'coreConclusion', 'core_conclusion');
  const intel = nestedRecord(dashboard, 'intelligence', 'intelligence');
  const battle = nestedRecord(dashboard, 'battlePlan', 'battle_plan');
  const sniper = nestedRecord(battle, 'sniperPoints', 'sniper_points');
  const posAdvice = nestedRecord(core, 'positionAdvice', 'position_advice');
  const phaseFromDashboard = nestedRecord(dashboard, 'phaseDecision', 'phase_decision');
  const phaseFromInsights = details?.structuredInsights?.phaseDecision;

  const oneSentence =
    asTrimmedString(pick(core, 'oneSentence', 'one_sentence'))
    || asTrimmedString(summary?.analysisSummary);

  const riskAlerts = asStringList(pick(intel, 'riskAlerts', 'risk_alerts'), 3);
  const riskWarning =
    asTrimmedString(pick(raw, 'riskWarning', 'risk_warning'))
    || asTrimmedString(pick(dashboard, 'riskWarning', 'risk_warning'));

  const watchFromDashboard = asStringList(
    pick(phaseFromDashboard, 'watchConditions', 'watch_conditions'),
    3,
  );
  const watchFromInsights = (phaseFromInsights?.watchConditions ?? [])
    .map((item) => asTrimmedString(item))
    .filter((item): item is string => Boolean(item))
    .slice(0, 3);
  const watchConditions = watchFromDashboard.length > 0 ? watchFromDashboard : watchFromInsights;

  const confidenceLevel =
    cleanLevel(pick(raw, 'confidenceLevel', 'confidence_level'))
    || cleanLevel(pick(dashboard, 'confidenceLevel', 'confidence_level'));

  const confidenceReason =
    asTrimmedString(pick(phaseFromDashboard, 'confidenceReason', 'confidence_reason'))
    || asTrimmedString(phaseFromInsights?.confidenceReason);

  const immediateAction =
    asTrimmedString(pick(phaseFromDashboard, 'immediateAction', 'immediate_action'))
    || asTrimmedString(phaseFromInsights?.immediateAction);

  const timeSensitivity = asTrimmedString(
    pick(core, 'timeSensitivity', 'time_sensitivity'),
  );

  const stopLoss =
    asTrimmedString(strategy?.stopLoss)
    || asTrimmedString(pick(sniper, 'stopLoss', 'stop_loss'));
  const takeProfit =
    asTrimmedString(strategy?.takeProfit)
    || asTrimmedString(pick(sniper, 'takeProfit', 'take_profit'));

  const score =
    typeof summary?.sentimentScore === 'number' && Number.isFinite(summary.sentimentScore)
      ? summary.sentimentScore
      : undefined;

  const trendPrediction = asTrimmedString(summary?.trendPrediction);

  return {
    signalLabel: asTrimmedString(signalLabel) || undefined,
    score,
    oneSentence,
    trendPrediction,
    confidenceLevel,
    confidenceReason,
    immediateAction,
    timeSensitivity,
    positionNoPosition: asTrimmedString(pick(posAdvice, 'noPosition', 'no_position')),
    positionHasPosition: asTrimmedString(pick(posAdvice, 'hasPosition', 'has_position')),
    keyRisks: riskAlerts,
    riskWarning: riskAlerts.length === 0 ? riskWarning : undefined,
    watchConditions,
    stopLoss,
    takeProfit,
  };
};

export const hasReportDecisionCardContent = (model: ReportDecisionCardModel): boolean => {
  if (model.signalLabel || model.oneSentence || model.trendPrediction) {
    return true;
  }
  if (model.confidenceLevel || model.confidenceReason || model.immediateAction) {
    return true;
  }
  if (model.timeSensitivity || model.positionNoPosition || model.positionHasPosition) {
    return true;
  }
  if (model.keyRisks.length > 0 || model.riskWarning || model.watchConditions.length > 0) {
    return true;
  }
  if (model.stopLoss || model.takeProfit) {
    return true;
  }
  if (typeof model.score === 'number') {
    return true;
  }
  return false;
};

export const buildReportDecisionCardModelFromReport = (
  report: Pick<AnalysisReport, 'meta' | 'summary' | 'strategy' | 'details'>,
  signalLabel?: string | null,
): ReportDecisionCardModel =>
  buildReportDecisionCardModel({
    meta: report.meta,
    summary: report.summary,
    strategy: report.strategy,
    details: report.details,
    signalLabel,
  });
