import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../api/history';
import type { HistoryListResponse, StockBarItem } from '../../types/analysis';
import { useWatchlistAnalysisCoverage } from '../useWatchlistAnalysisCoverage';

vi.mock('../../api/history', () => ({
  historyApi: {
    getList: vi.fn(),
  },
}));

function deferredPromise<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

function historyResponse(createdAt: string): HistoryListResponse {
  return {
    total: 1,
    page: 1,
    limit: 1,
    items: [{
      id: 1,
      queryId: 'query-1',
      stockCode: 'AAPL',
      stockName: 'Apple',
      reportType: 'detailed',
      createdAt,
    }],
  };
}

function stockBarItem(lastAnalysisTime: string): StockBarItem {
  return {
    id: 2,
    stockCode: 'AAPL',
    stockName: 'Apple',
    reportType: 'detailed',
    analysisCount: 1,
    lastAnalysisTime,
  };
}

describe('useWatchlistAnalysisCoverage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('blocks a repeated missing-symbol signature until its new fallback lookup settles', async () => {
    const repeatedLookup = deferredPromise<HistoryListResponse>();
    const watchlistCodes = ['AAPL'];
    vi.mocked(historyApi.getList)
      .mockResolvedValueOnce(historyResponse('2020-01-01T00:00:00Z'))
      .mockReturnValueOnce(repeatedLookup.promise);

    const { result, rerender } = renderHook(
      ({ stockBarItems }: { stockBarItems: StockBarItem[] }) => (
        useWatchlistAnalysisCoverage({
          watchlistCodes,
          stockBarItems,
          isLoadingStockBar: false,
          isInitialStockBarLoadSettled: true,
          stockBarRefreshFailed: false,
          activeTasks: [],
        })
      ),
      { initialProps: { stockBarItems: [] as StockBarItem[] } },
    );

    await waitFor(() => expect(result.current.pendingCodes).toEqual(['AAPL']));

    rerender({ stockBarItems: [stockBarItem(new Date().toISOString())] });
    await waitFor(() => expect(result.current.analyzedTodayCount).toBe(1));

    rerender({ stockBarItems: [] });
    await waitFor(() => expect(historyApi.getList).toHaveBeenCalledTimes(2));
    expect(result.current.isTodayStatusBlocked).toBe(true);
    expect(result.current.pendingCodes).toEqual([]);

    await act(async () => {
      repeatedLookup.resolve(historyResponse('2020-01-01T00:00:00Z'));
      await repeatedLookup.promise;
    });
    await waitFor(() => expect(result.current.pendingCodes).toEqual(['AAPL']));
  });
});
