// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import type { DecisionSignalItem } from '../../../types/decisionSignals';
import {
  findSignalInCandidates,
  refreshOwnedSelectionFromItems,
  refreshLatestSelection,
  type SelectedSignal,
} from '../decisionSignalsPageModel';

function makeItem(overrides: Partial<DecisionSignalItem> = {}): DecisionSignalItem {
  return {
    id: 7,
    stockCode: '600519',
    stockName: 'Kweichow Moutai',
    market: 'cn',
    sourceType: 'analysis',
    sourceReportId: 3001,
    triggerSource: 'web',
    action: 'hold',
    planQuality: 'complete',
    status: 'active',
    ...overrides,
  };
}

describe('Decision Signals selection identity', () => {
  it('resolves candidates by signal id when multiple rows share the same source', () => {
    const first = makeItem({ id: 7, stockCode: '600519' });
    const second = makeItem({ id: 8, stockCode: 'AAPL', stockName: 'Apple', market: 'us' });
    const found = findSignalInCandidates(8, [
      { source: 'list', items: [first, second] },
      { source: 'latest', items: [first] },
    ]);

    expect(found?.item.id).toBe(8);
    expect(found?.item.stockCode).toBe('AAPL');
    expect(found?.source).toBe('list');
  });

  it('does not alias an owned refresh to a sibling signal with the same source', () => {
    const current: SelectedSignal = {
      source: 'latest',
      item: makeItem({ id: 7, sourceType: 'analysis' }),
    };
    const sibling = makeItem({ id: 8, stockCode: 'AAPL', sourceType: 'analysis' });
    const refreshed = makeItem({ id: 7, sourceType: 'analysis', status: 'closed' });

    expect(refreshOwnedSelectionFromItems(current, [sibling, refreshed], 'latest')?.item.id).toBe(7);
    expect(refreshOwnedSelectionFromItems(current, [sibling, refreshed], 'latest')?.item.status).toBe('closed');
    expect(refreshLatestSelection(current, [sibling])).toBeNull();
    expect(refreshLatestSelection({ source: 'list', item: current.item }, [sibling])?.item.id).toBe(7);
  });
});

