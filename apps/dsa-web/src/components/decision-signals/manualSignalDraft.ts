import type { DecisionAction, MarketPhaseValue } from '../../types/analysis';
import type {
  DecisionProfile,
  DecisionSignalCreateRequest,
  DecisionSignalHorizon,
  DecisionSignalMarket,
} from '../../types/decisionSignals';
import { normalizeStockCode } from '../../utils/stockCode';

// Manual web signals are always fixed to this identity so they can never be
// presented as analysis / agent / alert / market-review output downstream.
export const MANUAL_SIGNAL_SOURCE_TYPE = 'manual' as const;
export const MANUAL_SIGNAL_TRIGGER_SOURCE = 'web_manual' as const;

export const MANUAL_MARKET_OPTIONS: readonly DecisionSignalMarket[] = ['cn', 'hk', 'us', 'jp', 'kr', 'tw'];
export const MANUAL_ACTION_OPTIONS: readonly DecisionAction[] = ['buy', 'add', 'hold', 'reduce', 'sell', 'watch', 'avoid', 'alert'];
export const MANUAL_HORIZON_OPTIONS: readonly DecisionSignalHorizon[] = ['intraday', '1d', '3d', '5d', '10d', 'swing', 'long'];
export const MANUAL_PHASE_OPTIONS: readonly MarketPhaseValue[] = ['premarket', 'intraday', 'lunch_break', 'closing_auction', 'postmarket', 'non_trading', 'unknown'];
export const MANUAL_PROFILE_OPTIONS: readonly DecisionProfile[] = ['conservative', 'balanced', 'aggressive'];

export interface ManualSignalDraft {
  stockCode: string;
  stockName: string;
  market: '' | DecisionSignalMarket;
  action: '' | DecisionAction;
  confidence: string;
  horizon: '' | DecisionSignalHorizon;
  marketPhase: '' | MarketPhaseValue;
  decisionProfile: '' | DecisionProfile;
  entryLow: string;
  entryHigh: string;
  stopLoss: string;
  targetPrice: string;
  invalidation: string;
  expiresAt: string;
  reason: string;
  riskSummary: string;
  catalystSummary: string;
  watchConditions: string;
  evidence: string;
}

export const EMPTY_MANUAL_SIGNAL_DRAFT: ManualSignalDraft = {
  stockCode: '',
  stockName: '',
  market: '',
  action: '',
  confidence: '',
  horizon: '',
  marketPhase: '',
  decisionProfile: '',
  entryLow: '',
  entryHigh: '',
  stopLoss: '',
  targetPrice: '',
  invalidation: '',
  expiresAt: '',
  reason: '',
  riskSummary: '',
  catalystSummary: '',
  watchConditions: '',
  evidence: '',
};

export type ManualSignalErrorCode =
  | 'required'
  | 'confidenceRange'
  | 'positive'
  | 'entryOrder'
  | 'invalidDate';

export type ManualSignalErrorField =
  | 'stockCode'
  | 'market'
  | 'action'
  | 'confidence'
  | 'entryLow'
  | 'entryHigh'
  | 'stopLoss'
  | 'targetPrice'
  | 'expiresAt';

export type ManualSignalErrors = Partial<Record<ManualSignalErrorField, ManualSignalErrorCode>>;

function parseNumeric(raw: string): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

// Optional positive-price field: empty means "not provided". A non-empty value
// that is not a finite number > 0 is invalid (mirrors the backend gt=0 rule).
function validatePositiveOptional(raw: string): { provided: boolean; value: number | null; valid: boolean } {
  if (!raw.trim()) return { provided: false, value: null, valid: true };
  const value = parseNumeric(raw);
  if (value === null || value <= 0) return { provided: true, value: null, valid: false };
  return { provided: true, value, valid: true };
}

function isValidDate(raw: string): boolean {
  const trimmed = raw.trim();
  if (!trimmed) return true;
  const time = new Date(`${trimmed}T00:00:00Z`).getTime();
  return Number.isFinite(time);
}

export function toManualSignalExpiresAt(raw: string): string | undefined {
  const trimmed = raw.trim();
  if (!trimmed) return undefined;
  const date = new Date(`${trimmed}T00:00:00Z`);
  const time = date.getTime();
  if (!Number.isFinite(time)) return undefined;
  return date.toISOString();
}

export function validateManualSignalDraft(draft: ManualSignalDraft): ManualSignalErrors {
  const errors: ManualSignalErrors = {};

  if (!normalizeStockCode(draft.stockCode.trim())) errors.stockCode = 'required';
  if (!MANUAL_MARKET_OPTIONS.includes(draft.market as DecisionSignalMarket)) errors.market = 'required';
  if (!MANUAL_ACTION_OPTIONS.includes(draft.action as DecisionAction)) errors.action = 'required';

  if (draft.confidence.trim()) {
    const confidence = parseNumeric(draft.confidence);
    if (confidence === null || confidence < 0 || confidence > 1) errors.confidence = 'confidenceRange';
  }

  const entryLow = validatePositiveOptional(draft.entryLow);
  const entryHigh = validatePositiveOptional(draft.entryHigh);
  const stopLoss = validatePositiveOptional(draft.stopLoss);
  const targetPrice = validatePositiveOptional(draft.targetPrice);
  if (!entryLow.valid) errors.entryLow = 'positive';
  if (!entryHigh.valid) errors.entryHigh = 'positive';
  if (!stopLoss.valid) errors.stopLoss = 'positive';
  if (!targetPrice.valid) errors.targetPrice = 'positive';

  if (
    !errors.entryLow
    && !errors.entryHigh
    && entryLow.value !== null
    && entryHigh.value !== null
    && entryLow.value > entryHigh.value
  ) {
    errors.entryHigh = 'entryOrder';
  }

  if (!isValidDate(draft.expiresAt)) errors.expiresAt = 'invalidDate';

  return errors;
}

export function hasManualSignalErrors(errors: ManualSignalErrors): boolean {
  return Object.keys(errors).length > 0;
}

function trimmedOrUndefined(raw: string): string | undefined {
  const trimmed = raw.trim();
  return trimmed ? trimmed : undefined;
}

// FNV-1a over the canonical payload string, run with two offset bases to widen
// the digest. Stable across runs so an identical draft always yields the same
// trace_id, giving the backend a dedup key for otherwise source-less manual
// signals (any field change produces a new signal).
function stableDigest(input: string): string {
  const round = (basis: number): string => {
    let hash = basis;
    for (let index = 0; index < input.length; index += 1) {
      hash ^= input.charCodeAt(index);
      hash = Math.imul(hash, 0x01000193);
    }
    return (hash >>> 0).toString(16).padStart(8, '0');
  };
  return `${round(0x811c9dc5)}${round(0x84222325)}`;
}

export function computeManualSignalTraceId(fields: Array<string | number | undefined>): string {
  // JSON-encode the field array so boundaries between adjacent free-text
  // fields are unambiguous; a plain join lets e.g. ["ab","c"] and ["a","bc"]
  // hash identically and wrongly dedup two distinct drafts.
  const canonical = JSON.stringify(fields.map((value) => (value === undefined ? '' : String(value))));
  return `${MANUAL_SIGNAL_TRIGGER_SOURCE}:${stableDigest(canonical)}`;
}

export function buildManualSignalPayload(draft: ManualSignalDraft): DecisionSignalCreateRequest {
  const stockCode = normalizeStockCode(draft.stockCode.trim());
  const market = draft.market as DecisionSignalMarket;
  const action = draft.action as DecisionAction;
  const confidence = draft.confidence.trim() ? parseNumeric(draft.confidence) ?? undefined : undefined;
  const horizon = draft.horizon || undefined;
  const marketPhase = draft.marketPhase || undefined;
  const decisionProfile = draft.decisionProfile || undefined;
  const entryLow = validatePositiveOptional(draft.entryLow).value ?? undefined;
  const entryHigh = validatePositiveOptional(draft.entryHigh).value ?? undefined;
  const stopLoss = validatePositiveOptional(draft.stopLoss).value ?? undefined;
  const targetPrice = validatePositiveOptional(draft.targetPrice).value ?? undefined;
  const expiresAt = toManualSignalExpiresAt(draft.expiresAt);
  const invalidation = trimmedOrUndefined(draft.invalidation);
  const watchConditions = trimmedOrUndefined(draft.watchConditions);
  const reason = trimmedOrUndefined(draft.reason);
  const riskSummary = trimmedOrUndefined(draft.riskSummary);
  const catalystSummary = trimmedOrUndefined(draft.catalystSummary);
  const evidence = trimmedOrUndefined(draft.evidence);
  const stockName = trimmedOrUndefined(draft.stockName);

  const traceId = computeManualSignalTraceId([
    stockCode,
    market,
    action,
    confidence,
    horizon,
    marketPhase,
    decisionProfile,
    entryLow,
    entryHigh,
    stopLoss,
    targetPrice,
    expiresAt,
    invalidation,
    watchConditions,
    reason,
    riskSummary,
    catalystSummary,
    evidence,
    stockName,
  ]);

  return {
    stockCode,
    stockName,
    market,
    sourceType: MANUAL_SIGNAL_SOURCE_TYPE,
    triggerSource: MANUAL_SIGNAL_TRIGGER_SOURCE,
    traceId,
    action,
    confidence,
    horizon,
    marketPhase,
    decisionProfile,
    entryLow,
    entryHigh,
    stopLoss,
    targetPrice,
    invalidation,
    watchConditions,
    reason,
    riskSummary,
    catalystSummary,
    evidence,
    expiresAt,
  };
}

const DIRECTIONAL_ACTIONS: ReadonlySet<DecisionAction> = new Set(['buy', 'add', 'reduce', 'sell', 'avoid']);

// Creating an active directional signal may invalidate an opposing active
// signal server-side; surface that possibility after a successful create.
export function manualSignalMayInvalidateOpposite(action: '' | DecisionAction): boolean {
  return DIRECTIONAL_ACTIONS.has(action as DecisionAction);
}
