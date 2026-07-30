// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type {
  ReportPhaseContext,
  ReportPhaseDecision,
  ReportSignalAttribution,
  ReportStrategySynthesis,
  ReportStrategySynthesisConflict,
  ReportStrategySynthesisSkill,
  ReportStrategySynthesisSummaryParams,
  ReportStructuredInsights,
} from '../../types/analysis';

const SCHEMA_VERSION = 'report-structured-insights-v1';

const asRecord = (value: unknown): Record<string, unknown> | null => {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
};

const pick = (
  record: Record<string, unknown>,
  camelKey: string,
  snakeKey: string,
): unknown => record[camelKey] ?? record[snakeKey];

const cleanText = (value: unknown): string | undefined => {
  if (typeof value !== 'string') {
    return undefined;
  }
  const cleaned = value.trim();
  return cleaned || undefined;
};

const cleanNumber = (value: unknown): number | undefined => {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return undefined;
  }
  return value;
};

const cleanStringList = (value: unknown): string[] => {
  const values = typeof value === 'string' ? [value] : Array.isArray(value) ? value : [];
  return values
    .map(cleanText)
    .filter((item): item is string => Boolean(item))
    .filter((item, index, items) => items.indexOf(item) === index)
    .slice(0, 30);
};

const normalizePhaseContext = (value: unknown): ReportPhaseContext | undefined => {
  const record = asRecord(value);
  if (!record) {
    return undefined;
  }

  const context: ReportPhaseContext = {};
  const textFields = [
    ['phase', 'phase'],
    ['market', 'market'],
    ['marketLocalTime', 'market_local_time'],
    ['sessionDate', 'session_date'],
    ['effectiveDailyBarDate', 'effective_daily_bar_date'],
    ['triggerSource', 'trigger_source'],
    ['analysisIntent', 'analysis_intent'],
  ] as const;
  textFields.forEach(([camelKey, snakeKey]) => {
    const text = cleanText(pick(record, camelKey, snakeKey));
    if (text !== undefined) {
      context[camelKey] = text;
    }
  });

  const booleanFields = [
    ['isTradingDay', 'is_trading_day'],
    ['isMarketOpenNow', 'is_market_open_now'],
    ['isPartialBar', 'is_partial_bar'],
  ] as const;
  booleanFields.forEach(([camelKey, snakeKey]) => {
    const flag = pick(record, camelKey, snakeKey);
    if (typeof flag === 'boolean') {
      context[camelKey] = flag;
    }
  });

  const numberFields = [
    ['minutesToOpen', 'minutes_to_open'],
    ['minutesToClose', 'minutes_to_close'],
  ] as const;
  numberFields.forEach(([camelKey, snakeKey]) => {
    const number = cleanNumber(pick(record, camelKey, snakeKey));
    if (number !== undefined) {
      context[camelKey] = number;
    }
  });

  const warnings = cleanStringList(record.warnings);
  if (warnings.length > 0) {
    context.warnings = warnings;
  }

  return Object.keys(context).length > 0 ? context : undefined;
};

const normalizePhaseDecision = (value: unknown): ReportPhaseDecision | undefined => {
  const record = asRecord(value);
  if (!record) {
    return undefined;
  }

  const decision: ReportPhaseDecision = {};
  const phaseContext = normalizePhaseContext(pick(record, 'phaseContext', 'phase_context'));
  if (phaseContext) {
    decision.phaseContext = phaseContext;
  }
  const textFields = [
    ['actionWindow', 'action_window'],
    ['immediateAction', 'immediate_action'],
    ['nextCheckTime', 'next_check_time'],
    ['confidenceReason', 'confidence_reason'],
  ] as const;
  textFields.forEach(([camelKey, snakeKey]) => {
    const text = cleanText(pick(record, camelKey, snakeKey));
    if (text !== undefined) {
      decision[camelKey] = text;
    }
  });
  const watchConditions = cleanStringList(
    pick(record, 'watchConditions', 'watch_conditions'),
  );
  if (watchConditions.length > 0) {
    decision.watchConditions = watchConditions;
  }
  const dataLimitations = cleanStringList(
    pick(record, 'dataLimitations', 'data_limitations'),
  );
  if (dataLimitations.length > 0) {
    decision.dataLimitations = dataLimitations;
  }
  return Object.keys(decision).length > 0 ? decision : undefined;
};

const normalizeSignalAttribution = (value: unknown): ReportSignalAttribution | undefined => {
  const record = asRecord(value);
  if (!record) {
    return undefined;
  }

  const attribution: ReportSignalAttribution = {};
  const numberFields = [
    ['technicalIndicators', 'technical_indicators'],
    ['newsSentiment', 'news_sentiment'],
    ['fundamentals', 'fundamentals'],
    ['marketConditions', 'market_conditions'],
  ] as const;
  numberFields.forEach(([camelKey, snakeKey]) => {
    const number = cleanNumber(pick(record, camelKey, snakeKey));
    if (number !== undefined) {
      attribution[camelKey] = Math.min(100, Math.max(0, number));
    }
  });
  const textFields = [
    ['strongestBullishSignal', 'strongest_bullish_signal'],
    ['strongestBearishSignal', 'strongest_bearish_signal'],
  ] as const;
  textFields.forEach(([camelKey, snakeKey]) => {
    const text = cleanText(pick(record, camelKey, snakeKey));
    if (text !== undefined) {
      attribution[camelKey] = text;
    }
  });

  const hasWeight = numberFields.some(([camelKey]) => (attribution[camelKey] ?? 0) !== 0);
  return hasWeight || attribution.strongestBullishSignal || attribution.strongestBearishSignal
    ? attribution
    : undefined;
};

const normalizeStrategySkill = (value: unknown): ReportStrategySynthesisSkill | null => {
  const record = asRecord(value);
  if (!record) {
    return null;
  }

  const skill: ReportStrategySynthesisSkill = {};
  const textFields = [
    ['skillId', 'skill_id'],
    ['agentName', 'agent_name'],
    ['signal', 'signal'],
    ['reasoning', 'reasoning'],
  ] as const;
  textFields.forEach(([camelKey, snakeKey]) => {
    const text = cleanText(pick(record, camelKey, snakeKey));
    if (text !== undefined) {
      skill[camelKey] = text;
    }
  });
  const confidence = cleanNumber(record.confidence);
  if (confidence !== undefined) {
    skill.confidence = confidence;
  }
  const scoreAdjustment = cleanNumber(
    pick(record, 'scoreAdjustment', 'score_adjustment'),
  );
  if (scoreAdjustment !== undefined) {
    skill.scoreAdjustment = scoreAdjustment;
  }
  const conditionsMet = cleanStringList(pick(record, 'conditionsMet', 'conditions_met'));
  if (conditionsMet.length > 0) {
    skill.conditionsMet = conditionsMet;
  }
  const invalidSignal = pick(record, 'invalidSignal', 'invalid_signal');
  if (typeof invalidSignal === 'boolean') {
    skill.invalidSignal = invalidSignal;
  }
  return Object.keys(skill).length > 0 ? skill : null;
};

const normalizeStrategyConflict = (
  value: unknown,
): ReportStrategySynthesisConflict | null => {
  const record = asRecord(value);
  if (!record) {
    return null;
  }

  const conflict: ReportStrategySynthesisConflict = {};
  const textFields = [
    ['conflictType', 'conflict_type'],
    ['severity', 'severity'],
    ['descriptionKey', 'description_key'],
  ] as const;
  textFields.forEach(([camelKey, snakeKey]) => {
    const text = cleanText(pick(record, camelKey, snakeKey));
    if (text !== undefined) {
      conflict[camelKey] = text;
    }
  });
  const participants = cleanStringList(record.participants);
  if (participants.length > 0) {
    conflict.participants = participants;
  }
  return Object.keys(conflict).length > 0 ? conflict : null;
};

const normalizeSummaryParams = (
  value: unknown,
): ReportStrategySynthesisSummaryParams | undefined => {
  const record = asRecord(value);
  if (!record) {
    return undefined;
  }

  const params: ReportStrategySynthesisSummaryParams = {};
  const textFields = [
    ['finalSignal', 'final_signal'],
    ['consensusLevel', 'consensus_level'],
    ['conflictSeverity', 'conflict_severity'],
  ] as const;
  textFields.forEach(([camelKey, snakeKey]) => {
    const text = cleanText(pick(record, camelKey, snakeKey));
    if (text !== undefined) {
      params[camelKey] = text;
    }
  });
  const numberFields = [
    ['opinionCount', 'opinion_count'],
    ['totalOpinionCount', 'total_opinion_count'],
    ['invalidOpinionCount', 'invalid_opinion_count'],
    ['conflictCount', 'conflict_count'],
  ] as const;
  numberFields.forEach(([camelKey, snakeKey]) => {
    const number = cleanNumber(pick(record, camelKey, snakeKey));
    if (number !== undefined) {
      params[camelKey] = number;
    }
  });
  return Object.keys(params).length > 0 ? params : undefined;
};

const normalizeStrategySynthesis = (value: unknown): ReportStrategySynthesis | undefined => {
  const record = asRecord(value);
  if (!record) {
    return undefined;
  }

  const synthesis: ReportStrategySynthesis = {};
  const textFields = [
    ['finalSignal', 'final_signal'],
    ['conflictSeverity', 'conflict_severity'],
    ['consensusLevel', 'consensus_level'],
    ['summaryKey', 'summary_key'],
  ] as const;
  textFields.forEach(([camelKey, snakeKey]) => {
    const text = cleanText(pick(record, camelKey, snakeKey));
    if (text !== undefined) {
      synthesis[camelKey] = text;
    }
  });
  const numberFields = [
    ['weightedScore', 'weighted_score'],
    ['confidence', 'confidence'],
    ['originalConfidence', 'original_confidence'],
    ['conflictCount', 'conflict_count'],
  ] as const;
  numberFields.forEach(([camelKey, snakeKey]) => {
    const number = cleanNumber(pick(record, camelKey, snakeKey));
    if (number !== undefined) {
      synthesis[camelKey] = number;
    }
  });

  const listFields = [
    ['supportingSkills', 'supporting_skills'],
    ['opposingSkills', 'opposing_skills'],
  ] as const;
  listFields.forEach(([camelKey, snakeKey]) => {
    const rawItems = pick(record, camelKey, snakeKey);
    const items = Array.isArray(rawItems)
      ? rawItems
        .map(normalizeStrategySkill)
        .filter((item): item is ReportStrategySynthesisSkill => item !== null)
        .slice(0, 30)
      : [];
    if (items.length > 0) {
      synthesis[camelKey] = items;
    }
  });

  const rawConflicts = record.conflicts;
  const conflicts = Array.isArray(rawConflicts)
    ? rawConflicts
      .map(normalizeStrategyConflict)
      .filter((item): item is ReportStrategySynthesisConflict => item !== null)
      .slice(0, 30)
    : [];
  if (conflicts.length > 0) {
    synthesis.conflicts = conflicts;
  }
  const summaryParams = normalizeSummaryParams(
    pick(record, 'summaryParams', 'summary_params'),
  );
  if (summaryParams) {
    synthesis.summaryParams = summaryParams;
  }

  const meaningful = Boolean(
    synthesis.finalSignal
      || synthesis.consensusLevel
      || synthesis.supportingSkills?.length
      || synthesis.opposingSkills?.length
      || synthesis.conflicts?.length,
  );
  return meaningful ? synthesis : undefined;
};

export const normalizeReportStructuredInsights = (
  value: unknown,
): ReportStructuredInsights | null => {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const schemaVersion = cleanText(pick(record, 'schemaVersion', 'schema_version'));
  if (schemaVersion !== SCHEMA_VERSION) {
    return null;
  }

  const phaseDecision = normalizePhaseDecision(
    pick(record, 'phaseDecision', 'phase_decision'),
  );
  const signalAttribution = normalizeSignalAttribution(
    pick(record, 'signalAttribution', 'signal_attribution'),
  );
  const strategySynthesis = normalizeStrategySynthesis(
    pick(record, 'strategySynthesis', 'strategy_synthesis'),
  );
  if (!phaseDecision && !signalAttribution && !strategySynthesis) {
    return null;
  }

  return {
    schemaVersion: SCHEMA_VERSION,
    ...(phaseDecision ? { phaseDecision } : {}),
    ...(signalAttribution ? { signalAttribution } : {}),
    ...(strategySynthesis ? { strategySynthesis } : {}),
  };
};
