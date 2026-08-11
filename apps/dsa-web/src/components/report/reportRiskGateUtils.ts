// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Presentation-only Risk Manager gate projection for Web report / decision surfaces.
 *
 * Reads the backend canonical `risk-manager-result/v1` payload only.
 * Never invents a pass verdict when the field is missing or malformed —
 * missing evaluation must surface as `not_evaluated` (fail-closed presentation).
 */
import type { ReportDetails, ReportSummary } from '../../types/analysis';

export const RISK_MANAGER_SCHEMA_VERSION = 'risk-manager-result/v1' as const;

export type RiskGateVerdict = 'pass' | 'downgrade' | 'reject';

export type RiskGatePresentationStatus =
  | 'loading'
  | 'error'
  | 'not_evaluated'
  | RiskGateVerdict;

export interface RiskGatePresentation {
  status: RiskGatePresentationStatus;
  verdict?: RiskGateVerdict;
  originalAction?: string;
  finalAction?: string;
  profile?: string;
  reasonCodes: string[];
  evidenceCodes: string[];
  adjustment?: string;
  failClosed?: boolean;
  authorizedBypassId?: string;
  evaluationId?: string;
  /** Stable machine key for error presentation; not user-facing copy. */
  errorCode?: string;
}

const EMPTY_CODES: string[] = [];

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

const asTrimmedString = (value: unknown): string | undefined => {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || undefined;
  }
  return undefined;
};

const asStringList = (value: unknown, limit = 20): string[] => {
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

const normalizeVerdict = (value: unknown): RiskGateVerdict | undefined => {
  const raw = asTrimmedString(value)?.toLowerCase();
  if (raw === 'pass' || raw === 'downgrade' || raw === 'reject') {
    return raw;
  }
  return undefined;
};

/**
 * Locate the backend risk-gate payload without inventing defaults.
 * Preference order mirrors production consumers:
 * 1. `summary.riskManager` (analysis_service projection)
 * 2. `details.rawResult.riskGateResult` / `risk_gate_result`
 * 3. `details.rawResult.dashboard.riskManager` / `risk_manager`
 */
export const extractRiskGateSource = (input: {
  summary?: Pick<ReportSummary, 'riskManager'> | null;
  details?: Pick<ReportDetails, 'rawResult'> | null;
  /** Direct metadata blob (DecisionSignal.metadata.riskManager). */
  metadata?: Record<string, unknown> | null;
}): unknown => {
  const fromSummary = input.summary?.riskManager;
  if (fromSummary !== undefined && fromSummary !== null) {
    return fromSummary;
  }

  const metadata = asRecord(input.metadata);
  if (metadata) {
    const fromMeta = pick(metadata, 'riskManager', 'risk_manager');
    if (fromMeta !== undefined && fromMeta !== null) {
      return fromMeta;
    }
  }

  const raw = asRecord(input.details?.rawResult);
  if (!raw) {
    return undefined;
  }

  const fromRaw = pick(raw, 'riskGateResult', 'risk_gate_result');
  if (fromRaw !== undefined && fromRaw !== null) {
    return fromRaw;
  }

  const dashboard = asRecord(pick(raw, 'dashboard', 'dashboard'));
  const fromDashboard = pick(dashboard, 'riskManager', 'risk_manager');
  if (fromDashboard !== undefined && fromDashboard !== null) {
    return fromDashboard;
  }

  return undefined;
};

/**
 * Parse a risk-manager payload into a presentation model.
 * Missing / null → `not_evaluated` (never pass).
 * Wrong shape / unknown schema / missing verdict → never defaults to pass.
 */
export const parseRiskGateResult = (raw: unknown): RiskGatePresentation => {
  if (raw === undefined || raw === null) {
    return {
      status: 'not_evaluated',
      reasonCodes: EMPTY_CODES,
      evidenceCodes: EMPTY_CODES,
    };
  }

  const record = asRecord(raw);
  if (!record) {
    return {
      status: 'error',
      reasonCodes: EMPTY_CODES,
      evidenceCodes: EMPTY_CODES,
      errorCode: 'invalid_shape',
    };
  }

  const schemaVersion = asTrimmedString(
    pick(record, 'schemaVersion', 'schema_version'),
  );
  if (schemaVersion !== RISK_MANAGER_SCHEMA_VERSION) {
    // Present payload that is not the canonical schema: treat as unevaluated
    // for presentation (fail-closed), not as pass.
    return {
      status: 'not_evaluated',
      reasonCodes: EMPTY_CODES,
      evidenceCodes: EMPTY_CODES,
      errorCode: schemaVersion ? 'unsupported_schema' : 'missing_schema',
    };
  }

  const verdict = normalizeVerdict(pick(record, 'verdict', 'verdict'));
  const originalAction = asTrimmedString(
    pick(record, 'originalAction', 'original_action'),
  );
  const finalAction = asTrimmedString(
    pick(record, 'finalAction', 'final_action'),
  );
  const profile = asTrimmedString(pick(record, 'profile', 'profile'));
  const reasonCodes = asStringList(
    pick(record, 'reasonCodes', 'reason_codes'),
  );
  const evidenceCodes = asStringList(
    pick(record, 'evidenceCodes', 'evidence_codes'),
  );
  const adjustment = asTrimmedString(pick(record, 'adjustment', 'adjustment'));
  const failClosedRaw = pick(record, 'failClosed', 'fail_closed');
  const failClosed = typeof failClosedRaw === 'boolean' ? failClosedRaw : undefined;
  const authorizedBypassId = asTrimmedString(
    pick(record, 'authorizedBypassId', 'authorized_bypass_id'),
  );
  const evaluationId = asTrimmedString(
    pick(record, 'evaluationId', 'evaluation_id'),
  );

  if (!verdict) {
    // Canonical schema present but verdict missing: never imply pass.
    return {
      status: 'not_evaluated',
      originalAction,
      finalAction,
      profile,
      reasonCodes,
      evidenceCodes,
      adjustment,
      failClosed,
      authorizedBypassId,
      evaluationId,
      errorCode: 'missing_verdict',
    };
  }

  return {
    status: verdict,
    verdict,
    originalAction,
    finalAction,
    profile,
    reasonCodes,
    evidenceCodes,
    adjustment,
    failClosed,
    authorizedBypassId,
    evaluationId,
  };
};

export const buildRiskGatePresentation = (input: {
  summary?: Pick<ReportSummary, 'riskManager'> | null;
  details?: Pick<ReportDetails, 'rawResult'> | null;
  metadata?: Record<string, unknown> | null;
  loading?: boolean;
  error?: boolean;
}): RiskGatePresentation => {
  if (input.loading) {
    return {
      status: 'loading',
      reasonCodes: EMPTY_CODES,
      evidenceCodes: EMPTY_CODES,
    };
  }
  if (input.error) {
    return {
      status: 'error',
      reasonCodes: EMPTY_CODES,
      evidenceCodes: EMPTY_CODES,
      errorCode: 'load_failed',
    };
  }
  return parseRiskGateResult(extractRiskGateSource(input));
};

export const isRiskGateReject = (presentation: RiskGatePresentation): boolean =>
  presentation.status === 'reject';

export const isRiskGateNotEvaluated = (
  presentation: RiskGatePresentation,
): boolean => presentation.status === 'not_evaluated';
