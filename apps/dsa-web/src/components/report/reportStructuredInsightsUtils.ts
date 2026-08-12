// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type {
  ReportCommitteeConclusion,
  ReportCommitteeDeliberation,
  ReportCommitteeDivergence,
  ReportCommitteeMember,
  ReportCommitteeOpinion,
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


const normalizeCommitteeMember = (value: unknown): ReportCommitteeMember | null => {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const member: ReportCommitteeMember = {};
  const textFields = [
    ['personaId', 'persona_id'],
    ['displayName', 'display_name'],
    ['agentName', 'agent_name'],
    ['signal', 'signal'],
    ['lensVerdict', 'lens_verdict'],
    ['reasoningExcerpt', 'reasoning_excerpt'],
    ['invalidReason', 'invalid_reason'],
  ] as const;
  textFields.forEach(([camelKey, snakeKey]) => {
    const text = cleanText(pick(record, camelKey, snakeKey));
    if (text !== undefined) {
      member[camelKey] = text;
    }
  });
  const confidence = cleanNumber(pick(record, 'confidence', 'confidence'));
  if (confidence !== undefined) {
    member.confidence = confidence;
  }
  const invalid = pick(record, 'invalid', 'invalid');
  if (typeof invalid === 'boolean') {
    member.invalid = invalid;
  }
  const meaningful = Boolean(
    member.personaId || member.displayName || member.signal,
  );
  return meaningful ? member : null;
};

const normalizeCommitteeOpinion = (value: unknown): ReportCommitteeOpinion | null => {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const opinion: ReportCommitteeOpinion = {};
  const textFields = [
    ['personaId', 'persona_id'],
    ['displayName', 'display_name'],
    ['agentName', 'agent_name'],
    ['signal', 'signal'],
    ['reasoningExcerpt', 'reasoning_excerpt'],
  ] as const;
  textFields.forEach(([camelKey, snakeKey]) => {
    const text = cleanText(pick(record, camelKey, snakeKey));
    if (text !== undefined) {
      opinion[camelKey] = text;
    }
  });
  const confidence = cleanNumber(pick(record, 'confidence', 'confidence'));
  if (confidence !== undefined) {
    opinion.confidence = confidence;
  }
  const meaningful = Boolean(
    opinion.personaId || opinion.displayName || opinion.signal,
  );
  return meaningful ? opinion : null;
};

const normalizeCommitteeDivergence = (
  value: unknown,
): ReportCommitteeDivergence | null => {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const point: ReportCommitteeDivergence = {};
  const textFields = [
    ['source', 'source'],
    ['conflictType', 'conflict_type'],
    ['severity', 'severity'],
    ['descriptionKey', 'description_key'],
  ] as const;
  textFields.forEach(([camelKey, snakeKey]) => {
    const text = cleanText(pick(record, camelKey, snakeKey));
    if (text !== undefined) {
      point[camelKey] = text;
    }
  });
  const participants = cleanStringList(
    pick(record, 'participants', 'participants'),
  );
  if (participants.length > 0) {
    point.participants = participants;
  }
  if (!point.conflictType && !point.participants?.length) {
    return null;
  }
  return point;
};

export const normalizeCommitteeDeliberation = (
  value: unknown,
): ReportCommitteeDeliberation | undefined => {
  const record = asRecord(value);
  if (!record) {
    return undefined;
  }
  const deliberation: ReportCommitteeDeliberation = {};
  const textFields = [
    ['schemaVersion', 'schema_version'],
    ['mode', 'mode'],
    ['source', 'source'],
    ['status', 'status'],
    ['outcome', 'outcome'],
  ] as const;
  textFields.forEach(([camelKey, snakeKey]) => {
    const text = cleanText(pick(record, camelKey, snakeKey));
    if (text !== undefined) {
      deliberation[camelKey] = text;
    }
  });

  const rawMembers = pick(record, 'members', 'members');
  const members = Array.isArray(rawMembers)
    ? rawMembers
      .map(normalizeCommitteeMember)
      .filter((item): item is ReportCommitteeMember => item !== null)
      .slice(0, 30)
    : [];
  if (members.length > 0) {
    deliberation.members = members;
  }

  const conclusionRecord = asRecord(
    pick(record, 'conclusion', 'conclusion'),
  );
  if (conclusionRecord) {
    const conclusion: ReportCommitteeConclusion = {};
    const conclusionText = [
      ['finalSignal', 'final_signal'],
      ['consensusLevel', 'consensus_level'],
      ['conflictSeverity', 'conflict_severity'],
    ] as const;
    conclusionText.forEach(([camelKey, snakeKey]) => {
      const text = cleanText(pick(conclusionRecord, camelKey, snakeKey));
      if (text !== undefined) {
        conclusion[camelKey] = text;
      }
    });
    const conclusionNumbers = [
      ['confidence', 'confidence'],
      ['conflictCount', 'conflict_count'],
      ['weightedScore', 'weighted_score'],
    ] as const;
    conclusionNumbers.forEach(([camelKey, snakeKey]) => {
      const number = cleanNumber(pick(conclusionRecord, camelKey, snakeKey));
      if (number !== undefined) {
        conclusion[camelKey] = number;
      }
    });
    if (
      conclusion.finalSignal
      || conclusion.consensusLevel
      || conclusion.confidence !== undefined
    ) {
      deliberation.conclusion = conclusion;
    }
  }

  const opinionFields = [
    ['supportingOpinions', 'supporting_opinions'],
    ['dissentingOpinions', 'dissenting_opinions'],
  ] as const;
  opinionFields.forEach(([camelKey, snakeKey]) => {
    const rawItems = pick(record, camelKey, snakeKey);
    const items = Array.isArray(rawItems)
      ? rawItems
        .map(normalizeCommitteeOpinion)
        .filter((item): item is ReportCommitteeOpinion => item !== null)
        .slice(0, 30)
      : [];
    if (items.length > 0) {
      deliberation[camelKey] = items;
    }
  });

  const rawDivergences = pick(record, 'divergencePoints', 'divergence_points');
  const divergences = Array.isArray(rawDivergences)
    ? rawDivergences
      .map(normalizeCommitteeDivergence)
      .filter((item): item is ReportCommitteeDivergence => item !== null)
      .slice(0, 30)
    : [];
  if (divergences.length > 0) {
    deliberation.divergencePoints = divergences;
  }

  const invalid = cleanStringList(
    pick(record, 'personasInvalid', 'personas_invalid'),
  );
  if (invalid.length > 0) {
    deliberation.personasInvalid = invalid;
  }
  const truncated = cleanStringList(
    pick(record, 'personasTruncated', 'personas_truncated'),
  );
  if (truncated.length > 0) {
    deliberation.personasTruncated = truncated;
  }

  const meaningful = Boolean(
    deliberation.members?.length
      || deliberation.conclusion
      || deliberation.dissentingOpinions?.length
      || deliberation.divergencePoints?.length,
  );
  return meaningful ? deliberation : undefined;
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
  const committeeDeliberation = normalizeCommitteeDeliberation(
    pick(record, 'committeeDeliberation', 'committee_deliberation'),
  );
  if (
    !phaseDecision
    && !signalAttribution
    && !strategySynthesis
    && !committeeDeliberation
  ) {
    return null;
  }

  return {
    schemaVersion: SCHEMA_VERSION,
    ...(phaseDecision ? { phaseDecision } : {}),
    ...(signalAttribution ? { signalAttribution } : {}),
    ...(strategySynthesis ? { strategySynthesis } : {}),
    ...(committeeDeliberation ? { committeeDeliberation } : {}),
  };
};
