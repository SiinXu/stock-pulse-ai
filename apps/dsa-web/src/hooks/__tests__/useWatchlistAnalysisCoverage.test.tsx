import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../api/history';
import type { HistoryListResponse, StockBarItem } from '../../types/analysis';
import {
  WATCHLIST_HISTORY_LOOKUP_CONCURRENCY,
  useWatchlistAnalysisCoverage,
} from '../useWatchlistAnalysisCoverage';
import { createDeferred } from '../../test-utils';

vi.mock('../../api/history', () => ({
  historyApi: {
    getList: vi.fn(),
  },
}));

function historyResponse(
  stockCode: string,
  createdAt: string,
): HistoryListResponse {
  return {
    total: 1,
    page: 1,
    limit: 1,
    items: [{
      id: 1,
      queryId: `query-${stockCode}`,
      stockCode,
      stockName: stockCode,
      reportType: 'detailed',
      createdAt,
    }],
  };
}

function stockBarItem(stockCode: string, lastAnalysisTime: string): StockBarItem {
  return {
    id: 2,
    stockCode,
    stockName: stockCode,
    reportType: 'detailed',
    analysisCount: 1,
    lastAnalysisTime,
  };
}

function abortError(): Error {
  return Object.assign(new Error('Aborted'), { name: 'AbortError' });
}

const EMPTY_STOCK_BAR: StockBarItem[] = [];
const EMPTY_TASKS: never[] = [];
const DEFAULT_WATCHLIST = ['AAPL'];

function coverageProps(overrides: {
  watchlistCodes?: string[];
  stockBarItems?: StockBarItem[];
  isLoadingStockBar?: boolean;
  isInitialStockBarLoadSettled?: boolean;
  stockBarRefreshFailed?: boolean;
} = {}) {
  return {
    watchlistCodes: overrides.watchlistCodes ?? DEFAULT_WATCHLIST,
    stockBarItems: overrides.stockBarItems ?? EMPTY_STOCK_BAR,
    isLoadingStockBar: overrides.isLoadingStockBar ?? false,
    isInitialStockBarLoadSettled: overrides.isInitialStockBarLoadSettled ?? true,
    stockBarRefreshFailed: overrides.stockBarRefreshFailed ?? false,
    activeTasks: EMPTY_TASKS,
  };
}

describe('useWatchlistAnalysisCoverage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('passes an AbortSignal as the second getList argument', async () => {
    vi.mocked(historyApi.getList).mockResolvedValue(
      historyResponse('AAPL', '2020-01-01T00:00:00Z'),
    );

    renderHook(() => useWatchlistAnalysisCoverage(coverageProps()));

    await waitFor(() => expect(historyApi.getList).toHaveBeenCalled());
    expect(historyApi.getList).toHaveBeenCalledWith(
      { stockCode: 'AAPL', limit: 1 },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    const options = vi.mocked(historyApi.getList).mock.calls[0][1];
    expect(options?.signal).toBeInstanceOf(AbortSignal);
  });

  it('aborts in-flight lookups when the missing-symbol signature changes', async () => {
    const firstLookup = createDeferred<HistoryListResponse>();
    const secondLookup = createDeferred<HistoryListResponse>();
    const signals: AbortSignal[] = [];
    vi.mocked(historyApi.getList).mockImplementation((params, options) => {
      expect(options?.signal).toBeInstanceOf(AbortSignal);
      signals.push(options!.signal!);
      if (signals.length === 1) {
        options!.signal!.addEventListener('abort', () => {
          firstLookup.reject(abortError());
        });
        return firstLookup.promise;
      }
      void params;
      return secondLookup.promise;
    });

    const { result, rerender } = renderHook(
      ({ watchlistCodes }: { watchlistCodes: string[] }) => (
        useWatchlistAnalysisCoverage(coverageProps({ watchlistCodes }))
      ),
      { initialProps: { watchlistCodes: ['AAPL'] } },
    );

    await waitFor(() => expect(historyApi.getList).toHaveBeenCalledTimes(1));
    expect(result.current.isTodayStatusBlocked).toBe(true);
    expect(result.current.pendingCodes).toEqual([]);

    rerender({ watchlistCodes: ['AAPL', 'MSFT'] });
    await waitFor(() => expect(signals[0]?.aborted).toBe(true));
    await waitFor(() => expect(historyApi.getList).toHaveBeenCalledTimes(3));

    await act(async () => {
      firstLookup.resolve(historyResponse('AAPL', new Date().toISOString()));
    });
    expect(result.current.rows.find((row) => row.code === 'AAPL')?.analyzedToday).not.toBe(true);
    expect(result.current.pendingCodes).toEqual([]);

    await act(async () => {
      secondLookup.resolve(historyResponse('MSFT', '2020-01-01T00:00:00Z'));
      await secondLookup.promise;
    });
    await waitFor(() => expect(result.current.isTodayStatusBlocked).toBe(false));
    expect(result.current.pendingCodes.sort()).toEqual(['AAPL', 'MSFT']);
  });

  it('does not apply an aborted result as failed or unknown', async () => {
    const lookup = createDeferred<HistoryListResponse>();
    let capturedSignal: AbortSignal | undefined;
    vi.mocked(historyApi.getList).mockImplementation((_params, options) => {
      capturedSignal = options?.signal;
      return lookup.promise;
    });

    const { result, unmount } = renderHook(() => (
      useWatchlistAnalysisCoverage(coverageProps())
    ));

    await waitFor(() => expect(historyApi.getList).toHaveBeenCalledTimes(1));
    expect(result.current.rows[0]?.isTodayStatusLoading).toBe(true);
    unmount();
    expect(capturedSignal?.aborted).toBe(true);

    await act(async () => {
      lookup.reject(abortError());
    });
    expect(capturedSignal?.aborted).toBe(true);
  });

  it('aborts fallback lookups when a newer stock-bar load supersedes them', async () => {
    const lookup = createDeferred<HistoryListResponse>();
    let capturedSignal: AbortSignal | undefined;
    vi.mocked(historyApi.getList).mockImplementation((_params, options) => {
      capturedSignal = options?.signal;
      return lookup.promise;
    });

    const { result, rerender } = renderHook(
      ({ isLoadingStockBar }: { isLoadingStockBar: boolean }) => (
        useWatchlistAnalysisCoverage(coverageProps({ isLoadingStockBar }))
      ),
      { initialProps: { isLoadingStockBar: false } },
    );

    await waitFor(() => expect(historyApi.getList).toHaveBeenCalledTimes(1));
    rerender({ isLoadingStockBar: true });
    await waitFor(() => expect(capturedSignal?.aborted).toBe(true));
    expect(result.current.isTodayStatusBlocked).toBe(true);
    expect(result.current.pendingCodes).toEqual([]);

    await act(async () => {
      lookup.resolve(historyResponse('AAPL', new Date().toISOString()));
    });
    expect(result.current.analyzedTodayCount).toBe(0);
    expect(result.current.pendingCodes).toEqual([]);
  });

  it('caps concurrent fallback history lookups for large watchlists', async () => {
    const watchlistCodes = Array.from({ length: 8 }, (_, index) => `T${index}`);
    const deferreds = watchlistCodes.map(() => createDeferred<HistoryListResponse>());
    let started = 0;
    let inFlight = 0;
    let maxInFlight = 0;
    vi.mocked(historyApi.getList).mockImplementation((_params, options) => {
      expect(options?.signal).toBeInstanceOf(AbortSignal);
      const index = started;
      started += 1;
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      return deferreds[index].promise.finally(() => {
        inFlight -= 1;
      });
    });

    renderHook(() => useWatchlistAnalysisCoverage(coverageProps({ watchlistCodes })));

    await waitFor(() => (
      expect(historyApi.getList).toHaveBeenCalledTimes(WATCHLIST_HISTORY_LOOKUP_CONCURRENCY)
    ));
    expect(maxInFlight).toBe(WATCHLIST_HISTORY_LOOKUP_CONCURRENCY);
    expect(historyApi.getList).toHaveBeenCalledTimes(WATCHLIST_HISTORY_LOOKUP_CONCURRENCY);

    await act(async () => {
      deferreds[0].resolve(historyResponse('T0', '2020-01-01T00:00:00Z'));
      await deferreds[0].promise;
    });
    await waitFor(() => (
      expect(historyApi.getList).toHaveBeenCalledTimes(WATCHLIST_HISTORY_LOOKUP_CONCURRENCY + 1)
    ));
    expect(maxInFlight).toBe(WATCHLIST_HISTORY_LOOKUP_CONCURRENCY);
  });

  it('keeps in-flight fallback lookups blocked instead of pending', async () => {
    const lookup = createDeferred<HistoryListResponse>();
    vi.mocked(historyApi.getList).mockReturnValue(lookup.promise);

    const { result } = renderHook(() => useWatchlistAnalysisCoverage(coverageProps()));

    await waitFor(() => expect(historyApi.getList).toHaveBeenCalled());
    expect(result.current.isTodayStatusBlocked).toBe(true);
    expect(result.current.pendingCodes).toEqual([]);
    expect(result.current.rows[0]?.isTodayStatusLoading).toBe(true);
    expect(result.current.rows[0]?.isTodayStatusUnknown).toBe(false);
  });

  it('marks a failed per-code lookup unknown instead of pending or analyzed', async () => {
    vi.mocked(historyApi.getList).mockRejectedValue(new Error('lookup failed'));

    const { result } = renderHook(() => useWatchlistAnalysisCoverage(coverageProps()));

    await waitFor(() => expect(result.current.rows[0]?.isTodayStatusUnknown).toBe(true));
    expect(result.current.isTodayStatusBlocked).toBe(true);
    expect(result.current.pendingCodes).toEqual([]);
    expect(result.current.analyzedTodayCount).toBe(0);
  });

  it('does not let stale fallback success clear a newer unknown refresh failure', async () => {
    const lookup = createDeferred<HistoryListResponse>();
    vi.mocked(historyApi.getList).mockReturnValue(lookup.promise);

    const { result, rerender } = renderHook(
      ({ stockBarRefreshFailed }: { stockBarRefreshFailed: boolean }) => (
        useWatchlistAnalysisCoverage(coverageProps({ stockBarRefreshFailed }))
      ),
      { initialProps: { stockBarRefreshFailed: false } },
    );

    await waitFor(() => expect(historyApi.getList).toHaveBeenCalledTimes(1));
    rerender({ stockBarRefreshFailed: true });
    expect(result.current.isTodayStatusBlocked).toBe(true);
    expect(result.current.pendingCodes).toEqual([]);

    await act(async () => {
      lookup.resolve(historyResponse('AAPL', new Date().toISOString()));
      await lookup.promise;
    });
    expect(result.current.analyzedTodayCount).toBe(0);
    expect(result.current.rows[0]?.isTodayStatusUnknown).toBe(true);
    expect(result.current.pendingCodes).toEqual([]);
  });

  it('blocks a repeated missing-symbol signature until its new fallback lookup settles', async () => {
    const repeatedLookup = createDeferred<HistoryListResponse>();
    const watchlistCodes = ['AAPL'];
    vi.mocked(historyApi.getList)
      .mockResolvedValueOnce(historyResponse('AAPL', '2020-01-01T00:00:00Z'))
      .mockReturnValueOnce(repeatedLookup.promise);

    const { result, rerender } = renderHook(
      ({ stockBarItems }: { stockBarItems: StockBarItem[] }) => (
        useWatchlistAnalysisCoverage(coverageProps({ watchlistCodes, stockBarItems }))
      ),
      { initialProps: { stockBarItems: [] as StockBarItem[] } },
    );

    await waitFor(() => expect(result.current.pendingCodes).toEqual(['AAPL']));

    rerender({ stockBarItems: [stockBarItem('AAPL', new Date().toISOString())] });
    await waitFor(() => expect(result.current.analyzedTodayCount).toBe(1));

    rerender({ stockBarItems: [] });
    await waitFor(() => expect(historyApi.getList).toHaveBeenCalledTimes(2));
    expect(result.current.isTodayStatusBlocked).toBe(true);
    expect(result.current.pendingCodes).toEqual([]);

    await act(async () => {
      repeatedLookup.resolve(historyResponse('AAPL', '2020-01-01T00:00:00Z'));
      await repeatedLookup.promise;
    });
    await waitFor(() => expect(result.current.pendingCodes).toEqual(['AAPL']));
  });
});
