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
  it('keeps top-level action authoritative while using nested presentation details', () => {
    expect(getDecisionSignalPresentation(item, { sell: 'Localized Sell' })).toEqual({
      action: 'sell',
      label: 'Localized Sell',
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
