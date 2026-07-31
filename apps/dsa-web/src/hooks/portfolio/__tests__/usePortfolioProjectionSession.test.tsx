// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Exercises the feature-private projection session through its public hook interface.

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { usePortfolioProjectionSession } from '../usePortfolioProjectionSession';

const {
  getSnapshot,
  getRisk,
  listTrades,
  listCashLedger,
  listCorporateActions,
  refreshFx,
} = vi.hoisted(() => ({
  getSnapshot: vi.fn(),
  getRisk: vi.fn(),
  listTrades: vi.fn(),
  listCashLedger: vi.fn(),
  listCorporateActions: vi.fn(),
  refreshFx: vi.fn(),
}));

vi.mock('../../../api/portfolio', () => ({
  portfolioApi: {
    getSnapshot,
    getRisk,
    listTrades,
    listCashLedger,
    listCorporateActions,
    refreshFx,
  },
}));

function deferredPromise<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

function makeSnapshot(accountId: number) {
  return {
    asOf: '2026-07-30',
    costMethod: 'fifo' as const,
    currency: 'CNY',
    accountCount: 1,
    totalCash: 1000,
    totalMarketValue: 2000,
    totalEquity: 3000,
    realizedPnl: 0,
    unrealizedPnl: 0,
    feeTotal: 0,
    taxTotal: 0,
    fxStale: false,
    dataQuality: 'ok',
    limitations: [],
    accounts: [{
      accountId,
      accountName: `Account ${accountId}`,
      ownerId: null,
      broker: 'Demo',
      market: 'us',
      baseCurrency: 'USD',
      asOf: '2026-07-30',
      costMethod: 'fifo' as const,
      totalCash: 1000,
      totalMarketValue: 2000,
      totalEquity: 3000,
      realizedPnl: 0,
      unrealizedPnl: 0,
      feeTotal: 0,
      taxTotal: 0,
      fxStale: false,
      positions: [],
    }],
  };
}

function makeRisk() {
  return {
    asOf: '2026-07-30',
    accountId: null,
    costMethod: 'fifo' as const,
    currency: 'CNY',
    thresholds: {},
    concentration: {
      totalMarketValue: 0,
      topWeightPct: 0,
      alert: false,
      topPositions: [],
    },
    sectorConcentration: {
      totalMarketValue: 0,
      topWeightPct: 0,
      alert: false,
      topSectors: [],
      coverage: {},
      errors: [],
    },
    drawdown: {
      seriesPoints: 0,
      maxDrawdownPct: 0,
      currentDrawdownPct: 0,
      alert: false,
      fxStale: false,
    },
    stopLoss: {
      nearAlert: false,
      triggeredCount: 0,
      nearCount: 0,
      items: [],
    },
  };
}

function makeTradePage(id: number, accountId = 1) {
  return {
    items: [{
      id,
      accountId,
      symbol: `STOCK-${id}`,
      market: 'us',
      currency: 'USD',
      tradeDate: '2026-07-30',
      side: 'buy' as const,
      quantity: 1,
      price: 10,
      fee: 0,
      tax: 0,
    }],
    total: 1,
    page: 1,
    pageSize: 20,
  };
}

function makeCashPage(id: number, page = 1) {
  return {
    items: [{
      id,
      accountId: 1,
      eventDate: '2026-07-30',
      direction: 'in' as const,
      amount: 100,
      currency: 'USD',
    }],
    total: 1,
    page,
    pageSize: 20,
  };
}

describe('usePortfolioProjectionSession', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    getRisk.mockResolvedValue(makeRisk());
    listTrades.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });
    listCashLedger.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });
    listCorporateActions.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });
  });

  it('rejects stale scope responses and resolves stable refresh calls against the active scope', async () => {
    const accountOneSnapshot = deferredPromise<ReturnType<typeof makeSnapshot>>();
    const accountOneTrades = deferredPromise<ReturnType<typeof makeTradePage>>();
    getSnapshot.mockImplementation(({ accountId }: { accountId?: number } = {}) => (
      accountId === 1
        ? accountOneSnapshot.promise
        : Promise.resolve(makeSnapshot(accountId ?? 2))
    ));
    listTrades.mockImplementation(({ accountId }: { accountId?: number } = {}) => (
      accountId === 1
        ? accountOneTrades.promise
        : Promise.resolve(makeTradePage(accountId ?? 2, accountId ?? 2))
    ));
    const setError = vi.fn();
    const loadAccounts = vi.fn().mockResolvedValue(true);
    const hook = renderHook(
      ({ accountId }) => usePortfolioProjectionSession({
        accountId,
        costMethod: 'fifo',
        hasAccounts: true,
        language: 'zh',
        riskFallbackMessage: 'risk unavailable',
        loadAccounts,
        setError,
      }),
      { initialProps: { accountId: 1 } },
    );
    const refreshFromAccountOneRender = hook.result.current.refreshPortfolioData;

    await waitFor(() => expect(getSnapshot).toHaveBeenCalledWith({
      accountId: 1,
      costMethod: 'fifo',
      includeRealtime: false,
    }));

    hook.rerender({ accountId: 2 });
    await waitFor(() => expect(
      hook.result.current.snapshot?.accounts[0]?.accountId,
    ).toBe(2));
    await waitFor(() => expect(hook.result.current.tradeEvents[0]?.accountId).toBe(2));

    await act(async () => {
      accountOneSnapshot.resolve(makeSnapshot(1));
      accountOneTrades.resolve(makeTradePage(1));
      await accountOneSnapshot.promise;
      await accountOneTrades.promise;
    });
    expect(hook.result.current.snapshot?.accounts[0]?.accountId).toBe(2);
    expect(hook.result.current.tradeEvents[0]?.accountId).toBe(2);

    getSnapshot.mockClear();
    listTrades.mockClear();
    await act(async () => {
      await refreshFromAccountOneRender();
    });
    expect(getSnapshot).toHaveBeenLastCalledWith({
      accountId: 2,
      costMethod: 'fifo',
      includeRealtime: false,
    });
    expect(listTrades).toHaveBeenLastCalledWith(expect.objectContaining({ accountId: 2 }));
  });

  it('invalidates an in-flight event response as soon as filters are applied', async () => {
    const staleTrades = deferredPromise<ReturnType<typeof makeTradePage>>();
    const filteredTrades = deferredPromise<ReturnType<typeof makeTradePage>>();
    getSnapshot.mockResolvedValue(makeSnapshot(1));
    listTrades
      .mockReturnValueOnce(staleTrades.promise)
      .mockReturnValueOnce(filteredTrades.promise);
    const hook = renderHook(() => usePortfolioProjectionSession({
      accountId: 1,
      costMethod: 'fifo',
      hasAccounts: true,
      language: 'zh',
      riskFallbackMessage: 'risk unavailable',
      loadAccounts: vi.fn().mockResolvedValue(true),
      setError: vi.fn(),
    }));

    await waitFor(() => expect(listTrades).toHaveBeenCalledTimes(1));
    act(() => hook.result.current.setEventSymbol('AAPL'));
    act(() => {
      hook.result.current.applyEventFilters();
      staleTrades.resolve(makeTradePage(1));
    });
    await staleTrades.promise;

    await waitFor(() => expect(hook.result.current.tradeEvents).toEqual([]));
    await waitFor(() => expect(listTrades).toHaveBeenCalledTimes(2));
    expect(listTrades).toHaveBeenLastCalledWith(expect.objectContaining({ symbol: 'AAPL' }));
    expect(hook.result.current.eventLoading).toBe(true);
    hook.unmount();
  });

  it('invalidates an in-flight event response as soon as ledger type changes', async () => {
    const staleTrades = deferredPromise<ReturnType<typeof makeTradePage>>();
    getSnapshot.mockResolvedValue(makeSnapshot(1));
    listTrades.mockReturnValueOnce(staleTrades.promise);
    listCashLedger.mockReturnValueOnce(new Promise(() => {}));
    const hook = renderHook(() => usePortfolioProjectionSession({
      accountId: 1,
      costMethod: 'fifo',
      hasAccounts: true,
      language: 'zh',
      riskFallbackMessage: 'risk unavailable',
      loadAccounts: vi.fn().mockResolvedValue(true),
      setError: vi.fn(),
    }));

    await waitFor(() => expect(listTrades).toHaveBeenCalledTimes(1));
    act(() => {
      hook.result.current.setEventType('cash');
      staleTrades.resolve(makeTradePage(1));
    });
    await staleTrades.promise;

    await waitFor(() => expect(hook.result.current.tradeEvents).toEqual([]));
    await waitFor(() => expect(listCashLedger).toHaveBeenCalledTimes(1));
    expect(hook.result.current.eventType).toBe('cash');
    expect(hook.result.current.cashEvents).toEqual([]);
    expect(hook.result.current.eventLoading).toBe(true);
    hook.unmount();
  });

  it('invalidates an in-flight event response as soon as the page changes', async () => {
    const staleTrades = deferredPromise<ReturnType<typeof makeTradePage>>();
    const nextPageTrades = deferredPromise<ReturnType<typeof makeTradePage>>();
    getSnapshot.mockResolvedValue(makeSnapshot(1));
    listTrades
      .mockReturnValueOnce(staleTrades.promise)
      .mockReturnValueOnce(nextPageTrades.promise);
    const hook = renderHook(() => usePortfolioProjectionSession({
      accountId: 1,
      costMethod: 'fifo',
      hasAccounts: true,
      language: 'zh',
      riskFallbackMessage: 'risk unavailable',
      loadAccounts: vi.fn().mockResolvedValue(true),
      setError: vi.fn(),
    }));

    await waitFor(() => expect(listTrades).toHaveBeenCalledTimes(1));
    act(() => {
      hook.result.current.setEventPage(2);
      staleTrades.resolve(makeTradePage(1));
    });
    await staleTrades.promise;

    await waitFor(() => expect(hook.result.current.tradeEvents).toEqual([]));
    await waitFor(() => expect(listTrades).toHaveBeenCalledTimes(2));
    expect(listTrades).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
    expect(hook.result.current.eventLoading).toBe(true);
    hook.unmount();
  });

  it('releases loading when an FX follow-up supersedes a loading projection', async () => {
    const fxResult = deferredPromise<{
      asOf: string;
      accountCount: number;
      refreshEnabled: boolean;
      pairCount: number;
      updatedCount: number;
      staleCount: number;
      errorCount: number;
    }>();
    const committedRefreshSnapshot = deferredPromise<ReturnType<typeof makeSnapshot>>();
    getSnapshot
      .mockResolvedValueOnce(makeSnapshot(1))
      .mockReturnValueOnce(committedRefreshSnapshot.promise)
      .mockResolvedValueOnce(makeSnapshot(1));
    refreshFx.mockReturnValueOnce(fxResult.promise);
    const loadAccounts = vi.fn().mockResolvedValue(true);
    const setError = vi.fn();
    const hook = renderHook(() => usePortfolioProjectionSession({
      accountId: 1,
      costMethod: 'fifo',
      hasAccounts: true,
      language: 'zh',
      riskFallbackMessage: 'risk unavailable',
      loadAccounts,
      setError,
    }));

    await waitFor(() => expect(hook.result.current.isLoading).toBe(false));
    let fxRefreshPromise!: Promise<void>;
    act(() => {
      fxRefreshPromise = hook.result.current.handleRefreshFx();
    });
    await waitFor(() => expect(refreshFx).toHaveBeenCalledTimes(1));

    let committedRefreshPromise!: Promise<void>;
    act(() => {
      committedRefreshPromise = hook.result.current.refreshPortfolioData();
    });
    await waitFor(() => expect(hook.result.current.isLoading).toBe(true));
    await waitFor(() => expect(getSnapshot).toHaveBeenCalledTimes(2));

    await act(async () => {
      fxResult.resolve({
        asOf: '2026-07-30',
        accountCount: 1,
        refreshEnabled: true,
        pairCount: 1,
        updatedCount: 1,
        staleCount: 0,
        errorCount: 0,
      });
      await fxRefreshPromise;
    });

    expect(getSnapshot).toHaveBeenCalledTimes(3);
    expect(hook.result.current.isLoading).toBe(false);

    await act(async () => {
      committedRefreshSnapshot.resolve(makeSnapshot(1));
      await committedRefreshPromise;
    });
    expect(hook.result.current.isLoading).toBe(false);
  });

  it('rejects a later ledger response when paper refresh forces trade page one', async () => {
    const accountsRefresh = deferredPromise<boolean>();
    const paperSnapshot = deferredPromise<ReturnType<typeof makeSnapshot>>();
    const laterCashPage = deferredPromise<ReturnType<typeof makeCashPage>>();
    const correctedTradePage = deferredPromise<ReturnType<typeof makeTradePage>>();
    getSnapshot
      .mockResolvedValueOnce(makeSnapshot(1))
      .mockReturnValueOnce(paperSnapshot.promise);
    listTrades
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, pageSize: 20 })
      .mockResolvedValueOnce(makeTradePage(10))
      .mockReturnValueOnce(correctedTradePage.promise);
    listCashLedger
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, pageSize: 20 })
      .mockReturnValueOnce(laterCashPage.promise);
    const loadAccounts = vi.fn().mockReturnValue(accountsRefresh.promise);
    const setError = vi.fn();
    const hook = renderHook(() => usePortfolioProjectionSession({
      accountId: 1,
      costMethod: 'fifo',
      hasAccounts: true,
      language: 'zh',
      riskFallbackMessage: 'risk unavailable',
      loadAccounts,
      setError,
    }));

    await waitFor(() => expect(hook.result.current.isLoading).toBe(false));
    let paperRefreshPromise!: Promise<boolean>;
    act(() => {
      paperRefreshPromise = hook.result.current.refreshPaperTradeSurfaces();
    });
    await waitFor(() => expect(loadAccounts).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(listTrades).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(hook.result.current.tradeEvents[0]?.id).toBe(10));

    act(() => hook.result.current.setEventType('cash'));
    await waitFor(() => expect(listCashLedger).toHaveBeenCalledTimes(1));
    act(() => hook.result.current.setEventPage(2));
    await waitFor(() => expect(listCashLedger).toHaveBeenCalledTimes(2));
    expect(hook.result.current.eventType).toBe('cash');
    expect(hook.result.current.eventPage).toBe(2);

    await act(async () => {
      accountsRefresh.resolve(true);
      paperSnapshot.resolve(makeSnapshot(1));
      await paperRefreshPromise;
      laterCashPage.resolve(makeCashPage(77, 2));
      await laterCashPage.promise;
      await Promise.resolve();
    });

    expect(hook.result.current.eventType).toBe('trade');
    expect(hook.result.current.eventPage).toBe(1);
    expect(hook.result.current.cashEvents).toEqual([]);
    await waitFor(() => expect(listTrades).toHaveBeenCalledTimes(3));
    hook.unmount();
  });

  it('keeps a successful snapshot when risk projection partially fails', async () => {
    getSnapshot.mockResolvedValue(makeSnapshot(1));
    getRisk.mockRejectedValue(new Error('risk timeout'));
    const setError = vi.fn();
    const hook = renderHook(() => usePortfolioProjectionSession({
      accountId: 1,
      costMethod: 'fifo',
      hasAccounts: true,
      language: 'zh',
      riskFallbackMessage: 'risk unavailable',
      loadAccounts: vi.fn().mockResolvedValue(true),
      setError,
    }));

    await waitFor(() => expect(hook.result.current.riskWarning).not.toBeNull());
    expect(hook.result.current.snapshot?.accounts[0]?.accountId).toBe(1);
    expect(hook.result.current.risk).toBeNull();
    expect(setError).toHaveBeenCalledWith(null);
  });

  it('keeps FX success feedback when only the follow-up risk projection fails', async () => {
    getSnapshot.mockResolvedValue(makeSnapshot(1));
    getRisk.mockResolvedValue(makeRisk());
    refreshFx.mockResolvedValue({
      asOf: '2026-07-30',
      accountCount: 1,
      refreshEnabled: true,
      pairCount: 1,
      updatedCount: 1,
      staleCount: 0,
      errorCount: 0,
    });
    const hook = renderHook(() => usePortfolioProjectionSession({
      accountId: 1,
      costMethod: 'fifo',
      hasAccounts: true,
      language: 'zh',
      riskFallbackMessage: 'risk unavailable',
      loadAccounts: vi.fn().mockResolvedValue(true),
      setError: vi.fn(),
    }));

    await waitFor(() => expect(hook.result.current.isLoading).toBe(false));
    expect(hook.result.current.risk).not.toBeNull();
    getRisk.mockReset();
    getRisk.mockRejectedValue(new Error('risk timeout'));
    act(() => {
      void hook.result.current.handleRefreshFx();
    });

    await waitFor(() => expect(hook.result.current.fxRefreshFeedback?.tone).toBe('success'));
    expect(hook.result.current.snapshot?.accounts[0]?.accountId).toBe(1);
    expect(hook.result.current.risk).toBeNull();
    expect(hook.result.current.riskWarning).not.toBeNull();
  });
});
