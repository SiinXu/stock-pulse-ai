import { describe, expect, it } from 'vitest';
import {
  EMPTY_MANUAL_SIGNAL_DRAFT,
  buildManualSignalPayload,
  computeManualSignalTraceId,
  manualSignalMayInvalidateOpposite,
  toManualSignalExpiresAt,
  validateManualSignalDraft,
  type ManualSignalDraft,
} from '../manualSignalDraft';

function draft(overrides: Partial<ManualSignalDraft> = {}): ManualSignalDraft {
  return { ...EMPTY_MANUAL_SIGNAL_DRAFT, ...overrides };
}

const validMinimal = draft({ stockCode: '600519', market: 'cn', action: 'buy' });

describe('validateManualSignalDraft', () => {
  it('requires stock code, market, and action', () => {
    const errors = validateManualSignalDraft(EMPTY_MANUAL_SIGNAL_DRAFT);
    expect(errors.stockCode).toBe('required');
    expect(errors.market).toBe('required');
    expect(errors.action).toBe('required');
  });

  it('accepts a valid minimal draft', () => {
    expect(validateManualSignalDraft(validMinimal)).toEqual({});
  });

  it('rejects confidence outside 0..1', () => {
    expect(validateManualSignalDraft(draft({ ...validMinimal, confidence: '1.5' })).confidence).toBe('confidenceRange');
    expect(validateManualSignalDraft(draft({ ...validMinimal, confidence: '-0.1' })).confidence).toBe('confidenceRange');
    expect(validateManualSignalDraft(draft({ ...validMinimal, confidence: 'abc' })).confidence).toBe('confidenceRange');
    expect(validateManualSignalDraft(draft({ ...validMinimal, confidence: '0.7' })).confidence).toBeUndefined();
  });

  it('rejects non-positive prices', () => {
    expect(validateManualSignalDraft(draft({ ...validMinimal, entryLow: '0' })).entryLow).toBe('positive');
    expect(validateManualSignalDraft(draft({ ...validMinimal, stopLoss: '-3' })).stopLoss).toBe('positive');
    expect(validateManualSignalDraft(draft({ ...validMinimal, targetPrice: '12.5' })).targetPrice).toBeUndefined();
  });

  it('rejects an inverted entry range', () => {
    const errors = validateManualSignalDraft(draft({ ...validMinimal, entryLow: '20', entryHigh: '10' }));
    expect(errors.entryHigh).toBe('entryOrder');
  });

  it('rejects an unparseable expiry date', () => {
    expect(validateManualSignalDraft(draft({ ...validMinimal, expiresAt: 'not-a-date' })).expiresAt).toBe('invalidDate');
    expect(validateManualSignalDraft(draft({ ...validMinimal, expiresAt: '2026-08-01' })).expiresAt).toBeUndefined();
  });
});

describe('buildManualSignalPayload', () => {
  it('fixes source_type=manual and trigger_source=web_manual', () => {
    const payload = buildManualSignalPayload(validMinimal);
    expect(payload.sourceType).toBe('manual');
    expect(payload.triggerSource).toBe('web_manual');
  });

  it('canonicalizes the stock code and parses numeric fields', () => {
    const payload = buildManualSignalPayload(draft({
      stockCode: '00700',
      market: 'hk',
      action: 'add',
      confidence: '0.6',
      entryLow: '10.5',
      entryHigh: '11',
      stopLoss: '9',
      targetPrice: '13',
    }));
    expect(payload.stockCode).toBe('HK00700');
    expect(payload.confidence).toBe(0.6);
    expect(payload.entryLow).toBe(10.5);
    expect(payload.entryHigh).toBe(11);
    expect(payload.stopLoss).toBe(9);
    expect(payload.targetPrice).toBe(13);
  });

  it('omits blank optional fields', () => {
    const payload = buildManualSignalPayload(validMinimal);
    expect(payload.confidence).toBeUndefined();
    expect(payload.horizon).toBeUndefined();
    expect(payload.marketPhase).toBeUndefined();
    expect(payload.decisionProfile).toBeUndefined();
    expect(payload.entryLow).toBeUndefined();
    expect(payload.reason).toBeUndefined();
    expect(payload.expiresAt).toBeUndefined();
  });

  it('serializes the expiry date to an ISO timestamp', () => {
    const payload = buildManualSignalPayload(draft({ ...validMinimal, expiresAt: '2026-08-01' }));
    expect(payload.expiresAt).toBe('2026-08-01T00:00:00.000Z');
  });

  it('derives a deterministic web_manual trace id used for dedup', () => {
    const first = buildManualSignalPayload(validMinimal);
    const second = buildManualSignalPayload(draft({ stockCode: '600519', market: 'cn', action: 'buy' }));
    expect(first.traceId).toBe(second.traceId);
    expect(first.traceId?.startsWith('web_manual:')).toBe(true);
    expect((first.traceId ?? '').length).toBeLessThanOrEqual(64);
  });

  it('changes the trace id when any meaningful field changes', () => {
    const base = buildManualSignalPayload(validMinimal);
    const changedAction = buildManualSignalPayload(draft({ ...validMinimal, action: 'sell' }));
    const changedPrice = buildManualSignalPayload(draft({ ...validMinimal, entryLow: '10' }));
    const changedReason = buildManualSignalPayload(draft({ ...validMinimal, reason: 'note' }));
    expect(changedAction.traceId).not.toBe(base.traceId);
    expect(changedPrice.traceId).not.toBe(base.traceId);
    expect(changedReason.traceId).not.toBe(base.traceId);
  });

  it('keeps distinct signals distinct when free-text field boundaries shift', () => {
    const a = buildManualSignalPayload(draft({ ...validMinimal, reason: 'ab', riskSummary: 'c' }));
    const b = buildManualSignalPayload(draft({ ...validMinimal, reason: 'a', riskSummary: 'bc' }));
    expect(a.traceId).not.toBe(b.traceId);
  });

  it('treats equivalent stock-code spellings as the same signal identity', () => {
    const canonical = buildManualSignalPayload(draft({ stockCode: 'HK00700', market: 'hk', action: 'buy' }));
    const shorthand = buildManualSignalPayload(draft({ stockCode: '00700', market: 'hk', action: 'buy' }));
    expect(canonical.traceId).toBe(shorthand.traceId);
  });
});

describe('computeManualSignalTraceId', () => {
  it('is stable and prefixed', () => {
    expect(computeManualSignalTraceId(['a', 'b'])).toBe(computeManualSignalTraceId(['a', 'b']));
    expect(computeManualSignalTraceId(['a', 'b'])).not.toBe(computeManualSignalTraceId(['a', 'c']));
    expect(computeManualSignalTraceId(['a']).startsWith('web_manual:')).toBe(true);
  });

  it('treats undefined and empty consistently but distinguishes field boundaries', () => {
    expect(computeManualSignalTraceId([undefined, 'x'])).toBe(computeManualSignalTraceId(['', 'x']));
  });

  it('does not collide when a boundary between adjacent fields shifts', () => {
    expect(computeManualSignalTraceId(['ab', 'c'])).not.toBe(computeManualSignalTraceId(['a', 'bc']));
  });
});

describe('toManualSignalExpiresAt', () => {
  it('converts a date to an ISO timestamp and passes through blanks', () => {
    expect(toManualSignalExpiresAt('2026-08-01')).toBe('2026-08-01T00:00:00.000Z');
    expect(toManualSignalExpiresAt('')).toBeUndefined();
    expect(toManualSignalExpiresAt('nope')).toBeUndefined();
  });
});

describe('manualSignalMayInvalidateOpposite', () => {
  it('is true for directional actions only', () => {
    expect(manualSignalMayInvalidateOpposite('buy')).toBe(true);
    expect(manualSignalMayInvalidateOpposite('sell')).toBe(true);
    expect(manualSignalMayInvalidateOpposite('avoid')).toBe(true);
    expect(manualSignalMayInvalidateOpposite('hold')).toBe(false);
    expect(manualSignalMayInvalidateOpposite('watch')).toBe(false);
    expect(manualSignalMayInvalidateOpposite('')).toBe(false);
  });
});
