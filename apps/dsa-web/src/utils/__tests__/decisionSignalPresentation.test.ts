import { describe, expect, it } from 'vitest';
import type { DecisionSignalItem } from '../../types/decisionSignals';
import { getDecisionSignalPresentation } from '../decisionSignalPresentation';

const item = {
  action: 'sell',
  actionLabel: 'Sell',
  confidence: 0.1,
  reason: 'Legacy summary',
  riskSummary: 'Legacy risk',
  createdAt: '2026-01-01T00:00:00',
  presentation: {
    action: 'buy',
    label: 'Buy',
    confidence: 0.91,
    summary: 'Canonical summary',
    risk: 'Canonical risk',
    timestamp: '2026-07-19T00:00:00',
  },
} as DecisionSignalItem;

describe('getDecisionSignalPresentation', () => {
  it('uses the canonical nested contract for every presentation field', () => {
    expect(getDecisionSignalPresentation(item, { buy: 'Localized Buy' })).toEqual({
      action: 'buy',
      label: 'Localized Buy',
      confidence: 0.91,
      summary: 'Canonical summary',
      risk: 'Canonical risk',
      timestamp: '2026-07-19T00:00:00',
    });
  });

  it('keeps flat fields as a rolling-upgrade fallback', () => {
    expect(getDecisionSignalPresentation({ ...item, presentation: undefined })).toEqual({
      action: 'sell',
      label: '卖出',
      confidence: 0.1,
      summary: 'Legacy summary',
      risk: 'Legacy risk',
      timestamp: '2026-01-01T00:00:00',
    });
  });
});
