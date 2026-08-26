// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { DecisionSignalItem } from '../../../types/decisionSignals';
import { useDecisionSignalSelection } from '../useDecisionSignalSelection';

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

const first = makeItem({ id: 7 });
const second = makeItem({ id: 8, stockCode: 'AAPL', stockName: 'Apple', market: 'us' });

describe('useDecisionSignalSelection', () => {
  it('hydrates the URL signal by id when two list rows share a source', () => {
    const fetchSignalById = vi.fn();
    const updateSearchParams = vi.fn();
    const { result } = renderHook(() => useDecisionSignalSelection({
      routeSearch: '?signal=8',
      routeKey: 'k1',
      candidates: [{ source: 'list', items: [first, second] }],
      fetchSignalById,
      updateSearchParams,
      isMounted: () => true,
    }));

    expect(result.current.selectedSignalId).toBe(8);
    expect(result.current.selected?.item.stockCode).toBe('AAPL');
    expect(result.current.selected?.source).toBe('list');
    expect(fetchSignalById).not.toHaveBeenCalled();
  });

  it('keeps selectedSignalId authoritative when selecting siblings with the same source', () => {
    const updateSearchParams = vi.fn();
    const { result } = renderHook(() => useDecisionSignalSelection({
      routeSearch: '',
      routeKey: 'k1',
      candidates: [{ source: 'list', items: [first, second] }],
      fetchSignalById: vi.fn(),
      updateSearchParams,
      isMounted: () => true,
    }));

    act(() => result.current.selectSignal(first, 'list'));
    expect(result.current.selectedSignalId).toBe(7);
    act(() => result.current.selectSignal(second, 'list'));
    expect(result.current.selectedSignalId).toBe(8);
    expect(result.current.selected?.item.stockCode).toBe('AAPL');
    expect(updateSearchParams).toHaveBeenCalledWith({ signal: 8 }, false);
  });

  it('follows browser back/forward URL identity without aliasing source', async () => {
    const fetchSignalById = vi.fn();
    const updateSearchParams = vi.fn();
    const { result, rerender } = renderHook(
      ({ routeSearch, routeKey }: { routeSearch: string; routeKey: string }) => useDecisionSignalSelection({
        routeSearch,
        routeKey,
        candidates: [{ source: 'list', items: [first, second] }],
        fetchSignalById,
        updateSearchParams,
        isMounted: () => true,
      }),
      { initialProps: { routeSearch: '?signal=8', routeKey: 'fwd' } },
    );

    expect(result.current.selectedSignalId).toBe(8);
    rerender({ routeSearch: '?signal=7', routeKey: 'back' });
    await waitFor(() => expect(result.current.selectedSignalId).toBe(7));
    expect(result.current.selected?.item.stockCode).toBe('600519');
    expect(fetchSignalById).not.toHaveBeenCalled();
  });

  it('keeps selectedSignalId and URL identity when the detail drawer closes', () => {
    const updateSearchParams = vi.fn();
    const { result } = renderHook(() => useDecisionSignalSelection({
      routeSearch: '',
      routeKey: 'k1',
      candidates: [{ source: 'list', items: [first, second] }],
      fetchSignalById: vi.fn(),
      updateSearchParams,
      isMounted: () => true,
    }));

    act(() => result.current.selectSignal(first, 'list'));
    expect(result.current.detailOpen).toBe(true);
    expect(result.current.selectedSignalId).toBe(7);
    updateSearchParams.mockClear();

    act(() => result.current.closeDetail());
    expect(result.current.detailOpen).toBe(false);
    expect(result.current.selectedSignalId).toBe(7);
    expect(updateSearchParams).not.toHaveBeenCalled();

    act(() => result.current.openDetail());
    expect(result.current.detailOpen).toBe(true);
    expect(result.current.selectedSignalId).toBe(7);
    expect(updateSearchParams).not.toHaveBeenCalled();
  });

  it('adopts a persisted id without restoring a stale pending URL selection', () => {
    const updateSearchParams = vi.fn();
    const { result } = renderHook(() => useDecisionSignalSelection({
      routeSearch: '?signal=7',
      routeKey: 'k1',
      candidates: [{ source: 'list', items: [first, second] }],
      fetchSignalById: vi.fn(),
      updateSearchParams,
      isMounted: () => true,
    }));

    expect(result.current.selectedSignalId).toBe(7);
    updateSearchParams.mockClear();
    act(() => result.current.adoptSelected(second, 'persisted'));
    expect(result.current.selectedSignalId).toBe(8);
    expect(result.current.detailOpen).toBe(true);
    expect(updateSearchParams).toHaveBeenCalledWith({ signal: 8 }, true);
    expect(result.current.takePendingSelection('list', [first, second])).toBeNull();
  });
});
