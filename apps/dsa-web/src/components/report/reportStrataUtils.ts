// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type {
  ReportDetails as ReportDetailsType,
  ReportStrata as ReportStrataType,
  ReportStrataGapOrConflict,
  ReportStrataVerifiedFact,
} from '../../types/analysis';

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

const asStringList = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => (typeof item === 'string' ? item.trim() : String(item ?? '').trim()))
    .filter(Boolean);
};

const pickList = (record: Record<string, unknown>, camel: string, snake: string): unknown =>
  record[camel] ?? record[snake];

/** Normalize camelCase or snake_case strata payloads into the Web presentation shape. */
export const normalizeReportStrataPayload = (value: unknown): ReportStrataType | null => {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const frameworkRaw = asRecord(
    pickList(record, 'frameworkAlignment', 'framework_alignment'),
  );
  return {
    schemaVersion:
      typeof record.schemaVersion === 'string'
        ? record.schemaVersion
        : typeof record.schema_version === 'string'
          ? record.schema_version
          : undefined,
    verifiedFacts: Array.isArray(pickList(record, 'verifiedFacts', 'verified_facts'))
      ? (pickList(record, 'verifiedFacts', 'verified_facts') as ReportStrataVerifiedFact[])
      : [],
    missingOrConflicts: Array.isArray(
      pickList(record, 'missingOrConflicts', 'missing_or_conflicts'),
    )
      ? (pickList(record, 'missingOrConflicts', 'missing_or_conflicts') as ReportStrataGapOrConflict[])
      : [],
    modelInference: asStringList(pickList(record, 'modelInference', 'model_inference')),
    risksCounterEvidence: asStringList(
      pickList(record, 'risksCounterEvidence', 'risks_counter_evidence'),
    ),
    frameworkAlignment: frameworkRaw
      ? {
          status: (
            frameworkRaw.status === 'aligned'
            || frameworkRaw.status === 'partial'
            || frameworkRaw.status === 'conflict'
            || frameworkRaw.status === 'not_configured'
              ? frameworkRaw.status
              : 'not_configured'
          ),
          summary:
            typeof frameworkRaw.summary === 'string' ? frameworkRaw.summary : undefined,
          frameworkTitle:
            typeof frameworkRaw.frameworkTitle === 'string'
              ? frameworkRaw.frameworkTitle
              : typeof frameworkRaw.framework_title === 'string'
                ? frameworkRaw.framework_title
                : null,
          frameworkVersion:
            typeof frameworkRaw.frameworkVersion === 'number'
              ? frameworkRaw.frameworkVersion
              : typeof frameworkRaw.framework_version === 'number'
                ? frameworkRaw.framework_version
                : null,
          frameworkId:
            typeof frameworkRaw.frameworkId === 'string'
              ? frameworkRaw.frameworkId
              : typeof frameworkRaw.framework_id === 'string'
                ? frameworkRaw.framework_id
                : null,
        }
      : undefined,
    disclaimer:
      typeof record.disclaimer === 'string' ? record.disclaimer : undefined,
  };
};

/** Prefer projected details.reportStrata; fall back to rawResult.dashboard.report_strata. */
export const resolveReportStrataFromDetails = (
  details?: ReportDetailsType | null,
): ReportStrataType | null => {
  if (!details) {
    return null;
  }
  if (details.reportStrata && typeof details.reportStrata === 'object') {
    return normalizeReportStrataPayload(details.reportStrata);
  }
  const raw = details.rawResult;
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const dashboard = asRecord((raw as Record<string, unknown>).dashboard);
  const nested = dashboard?.reportStrata ?? dashboard?.report_strata;
  if (nested && typeof nested === 'object') {
    return normalizeReportStrataPayload(nested);
  }
  const top = (raw as Record<string, unknown>).reportStrata
    ?? (raw as Record<string, unknown>).report_strata;
  if (top && typeof top === 'object') {
    return normalizeReportStrataPayload(top);
  }
  return null;
};
