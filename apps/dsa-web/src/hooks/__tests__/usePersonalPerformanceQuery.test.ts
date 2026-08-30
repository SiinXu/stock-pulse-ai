// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { portfolioApi } from '../../api/portfolio';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type {
  PaperDecisionQualityResponse,
  PortfolioAccountItem,
  PortfolioAccountListResponse,
} from '../../types/portfolio';
import {
  PERSONAL_PERFORMANCE_ACCOUNTS_QUERY_KEY,
  PERSONAL_PERFORMANCE_CANCEL,
  PERSONAL_PERFORMANCE_QUALITY_LIMIT,
  PERSONAL_PERFORMANCE_QUERY_SCHEDULE,
  buildPersonalPerformanceQualityQueryKey,
  fetchPersonalPerformanceAccounts,
  fetchPersonalPerformanceQuality,
  usePersonalPerformanceQuery,
} from '../usePersonalPerformanceQuery';

vi.mock('../../api/portfolio', () => ({
  portfolioApi: {
    getAccounts: vi.fn(),
    getPaperDecisionQuality: vi.fn(),
  },
}));

const getAccounts = vi.mocked(portfolioApi.getAccounts);
const getPaperDecisionQuality = vi.mocked(portfolioApi.getPaperDecisionQuality);

function paperAccount(
  id: number,
  name = `Paper ${id}`,
): PortfolioAccountItem {
  return {
    id,
    name,
    market: 'us',
    baseCurrency: 'USD',
    isActive: true,
    accountType: 'paper',
  };
}

function realAccount(id: number): PortfolioAccountItem {
  return {
    id,
    name: `Real ${id}`,
    market: 'us',
    baseCurrency: 'USD',
    isActive: true,
    accountType: 'real',
  };
}

function accountList(
  accounts: PortfolioAccountItem[],
): PortfolioAccountListResponse {
  return { accounts };
}

function qualityReport(
  accountId: number,
  processScore: number,
): PaperDecisionQualityResponse {
  return {
    scoreKind: 'process',
    formulaVersion: 'v1',
    disclaimer: 'Process score only.',
    accountId,
    accountType: 'paper',
    asOf: '2026-08-19',
    sampleSize: 1,
    totalTradeCount: 1,
    truncated: false,
    aggregate: {
      sampleSize: 1,
      processScore,
      status: 'ok',
      dimensions: {
        analysis_support: { score: processScore, status: 'ok', sampleSize: 1 },
        risk_gate_compliance: { score: processScore, status: 'ok', sampleSize: 1 },
        position_discipline: { score: processScore, status: 'ok', sampleSize: 1 },
      },
    },
    items: [{
      tradeId: accountId,
      symbol: `SYM${accountId}`,
      market: 'us',
      side: 'buy',
      tradeDate: '2026-08-01',
      processScore,
      dimensions: {},
      formulaVersion: 'v1',
      reasons: [],
    }],
    divisionOfLabor: {
      thisIssue: 986,
      owns: 'process',
      doesNotOwn: 'outcome',
      outcomeOwnerIssue: 987,
    },
  };
}

function createWrapper(client?: QueryClient) {
  const queryClient = client ?? createAppQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  }
  return { client: queryClient, wrapper: Wrapper };
}

function queryOptions(client: QueryClient, queryKey: readonly unknown[]) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertExactPerformanceKeysOnly(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'portfolio' && key.length === 1).toBe(false);
    expect(key[0] === 'portfolio' && key.length === 2).toBe(false);
    if (key[0] === 'portfolio') {
      expect(filters?.exact).toBe(true);
      expect(key[1]).toBe('performance');
      if (key[2] === 'accounts') {
        expect([...key]).toEqual(['portfolio', 'performance', 'accounts']);
      } else {
        expect([...key]).toEqual([
          'portfolio',
          'performance',
          'quality',
          key[3],
          PERSONAL_PERFORMANCE_QUALITY_LIMIT,
        ]);
        expect(key).toHaveLength(5);
      }
    }
  }
}

async function flushQueryMicrotasks(rounds = 2) {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
  }
}

describe('usePersonalPerformanceQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    getAccounts.mockResolvedValue(accountList([paperAccount(7)]));
    getPaperDecisionQuality.mockResolvedValue(qualityReport(7, 80));
  });

  afterEach(() => {
    vi.useRealTimers();
    onlineManager.setOnline(true);
    focusManager.setFocused(true);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    });
  });

  it('pins frozen keys, schedule, getAccounts(false), and quality limit 50', async () => {
    expect([...PERSONAL_PERFORMANCE_ACCOUNTS_QUERY_KEY]).toEqual([
      'portfolio',
      'performance',
      'accounts',
    ]);
    expect(buildPersonalPerformanceQualityQueryKey(7)).toEqual([
      'portfolio',
      'performance',
      'quality',
      7,
      50,
    ]);
    expect(PERSONAL_PERFORMANCE_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    expect(PERSONAL_PERFORMANCE_QUALITY_LIMIT).toBe(50);
    await fetchPersonalPerformanceAccounts();
    await fetchPersonalPerformanceQuality({ accountId: 7 });
    expect(getAccounts).toHaveBeenCalledTimes(1);
    expect(getAccounts).toHaveBeenCalledWith(false);
    expect(getPaperDecisionQuality).toHaveBeenCalledTimes(1);
    expect(getPaperDecisionQuality).toHaveBeenCalledWith(7, { limit: 50 });
  });

  it('is not barrel-exported and does not mount a live useQuery observer', async () => {
    const barrel = await import('../index');
    expect(Object.keys(barrel)).not.toContain('usePersonalPerformanceQuery');

    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => usePersonalPerformanceQuery(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(fetchSpy).toHaveBeenCalled();
    const keys = fetchSpy.mock.calls.map(([options]) => options.queryKey);
    expect(keys).toContainEqual(['portfolio', 'performance', 'accounts']);
    expect(keys).toContainEqual(['portfolio', 'performance', 'quality', 7, 50]);
    expect(
      client.getQueryCache().find({
        queryKey: PERSONAL_PERFORMANCE_ACCOUNTS_QUERY_KEY,
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
    expect(
      client.getQueryCache().find({
        queryKey: buildPersonalPerformanceQualityQueryKey(7),
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
  });

  it('does not auto-retry a 5xx load when the QueryClient default would retry', async () => {
    getAccounts.mockRejectedValue(Object.assign(new Error('server'), { response: { status: 500 } }));
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => usePersonalPerformanceQuery(), { wrapper });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(getAccounts).toHaveBeenCalledTimes(1);
    expect(getPaperDecisionQuality).not.toHaveBeenCalled();
    expect(queryOptions(client, PERSONAL_PERFORMANCE_ACCOUNTS_QUERY_KEY)?.retry).toBe(false);
    expect(result.current.report).toBeNull();
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => usePersonalPerformanceQuery(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(queryOptions(client, PERSONAL_PERFORMANCE_ACCOUNTS_QUERY_KEY)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client, buildPersonalPerformanceQualityQueryKey(7))?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client, PERSONAL_PERFORMANCE_ACCOUNTS_QUERY_KEY)?.retry).toBe(false);
    expect(queryOptions(client, PERSONAL_PERFORMANCE_ACCOUNTS_QUERY_KEY)?.staleTime).toBe(0);
    expect(getAccounts).toHaveBeenCalledTimes(1);
    expect(getPaperDecisionQuality).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(getAccounts).toHaveBeenCalledTimes(1);
    expect(getPaperDecisionQuality).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call the APIs again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => usePersonalPerformanceQuery(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getAccounts).toHaveBeenCalledTimes(1);
    expect(queryOptions(client, PERSONAL_PERFORMANCE_ACCOUNTS_QUERY_KEY)?.refetchInterval).toBeUndefined();

    vi.useFakeTimers();
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    await flushQueryMicrotasks();

    expect(getAccounts).toHaveBeenCalledTimes(1);
    expect(getPaperDecisionQuality).toHaveBeenCalledTimes(1);
  });

  it('issues both GETs while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => usePersonalPerformanceQuery(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getAccounts).toHaveBeenCalledTimes(1);
    expect(getPaperDecisionQuality).toHaveBeenCalledTimes(1);
    expect(queryOptions(client, PERSONAL_PERFORMANCE_ACCOUNTS_QUERY_KEY)?.networkMode).toBe('always');
    expect(queryOptions(client, buildPersonalPerformanceQualityQueryKey(7))?.networkMode).toBe('always');
    expect(result.current.report?.aggregate?.processScore).toBe(80);
  });

  it('skips quality when the paper-account list is empty', async () => {
    getAccounts.mockResolvedValue(accountList([realAccount(1)]));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePersonalPerformanceQuery(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getAccounts).toHaveBeenCalledTimes(1);
    expect(getPaperDecisionQuality).not.toHaveBeenCalled();
    expect(result.current.accountId).toBeNull();
    expect(result.current.report).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.accounts).toHaveLength(1);
  });

  it('account change fetches quality only and discards older quality', async () => {
    getAccounts.mockResolvedValue(accountList([paperAccount(7), paperAccount(8)]));
    const firstQuality = createDeferred<PaperDecisionQualityResponse>();
    getPaperDecisionQuality
      .mockReturnValueOnce(firstQuality.promise)
      .mockResolvedValueOnce(qualityReport(8, 90));
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => usePersonalPerformanceQuery(), { wrapper });

    await waitFor(() => expect(getPaperDecisionQuality).toHaveBeenCalledTimes(1));
    expect(getAccounts).toHaveBeenCalledTimes(1);

    await act(async () => {
      void result.current.onAccountChange(8);
    });
    await waitFor(() => expect(result.current.report?.accountId).toBe(8));

    expect(getAccounts).toHaveBeenCalledTimes(1);
    expect(getPaperDecisionQuality).toHaveBeenCalledTimes(2);
    expect(getPaperDecisionQuality).toHaveBeenLastCalledWith(8, { limit: 50 });
    expect(result.current.accountId).toBe(8);
    expect(client.getQueryState(buildPersonalPerformanceQualityQueryKey(7))).toBeUndefined();
    expect(client.getQueryState(buildPersonalPerformanceQualityQueryKey(8))).toBeDefined();
    expect(client.getQueryState(PERSONAL_PERFORMANCE_ACCOUNTS_QUERY_KEY)).toBeDefined();

    await act(async () => {
      firstQuality.resolve(qualityReport(7, 80));
      await firstQuality.promise.catch(() => undefined);
    });

    expect(result.current.report?.aggregate?.processScore).toBe(90);
    expect(result.current.error).toBeNull();
    assertExactPerformanceKeysOnly(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertExactPerformanceKeysOnly(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('refresh fetches accounts then quality and latest-wins against a stale predecessor', async () => {
    const firstAccounts = createDeferred<PortfolioAccountListResponse>();
    const successorAccounts = createDeferred<PortfolioAccountListResponse>();
    getAccounts
      .mockReturnValueOnce(firstAccounts.promise)
      .mockReturnValueOnce(successorAccounts.promise);
    getPaperDecisionQuality.mockResolvedValue(qualityReport(7, 95));
    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => usePersonalPerformanceQuery(), { wrapper });

    await waitFor(() => expect(getAccounts).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(getAccounts).toHaveBeenCalledTimes(2));

    await act(async () => {
      successorAccounts.resolve(accountList([paperAccount(7)]));
    });
    await waitFor(() => expect(result.current.report?.aggregate?.processScore).toBe(95));

    await act(async () => {
      firstAccounts.resolve(accountList([paperAccount(7, 'Stale')]));
      await firstAccounts.promise.catch(() => undefined);
    });

    expect(result.current.accounts[0]?.name).toBe('Paper 7');
    expect(result.current.report?.aggregate?.processScore).toBe(95);
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(queryFetchStatus(client, PERSONAL_PERFORMANCE_ACCOUNTS_QUERY_KEY)).toBe('idle');
    for (const [options] of fetchSpy.mock.calls) {
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
    }
  });

  it('hard error clears report instead of keeping last-good', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePersonalPerformanceQuery(), { wrapper });
    await waitFor(() => expect(result.current.report?.aggregate?.processScore).toBe(80));

    getPaperDecisionQuality.mockRejectedValueOnce(
      Object.assign(new Error('server'), { response: { status: 500 } }),
    );
    await act(async () => {
      await result.current.load('refresh');
    });

    expect(result.current.error).not.toBeNull();
    expect(result.current.report).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.refreshing).toBe(false);
  });

  it('does not setError when a GET settles as CancelledError', async () => {
    getAccounts.mockRejectedValue(new CancelledError(PERSONAL_PERFORMANCE_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePersonalPerformanceQuery(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.report).toBeNull();
    expect(getPaperDecisionQuality).not.toHaveBeenCalled();
  });

  it('does not setError or clear newer data when an aborted predecessor fails', async () => {
    const firstQuality = createDeferred<PaperDecisionQualityResponse>();
    getPaperDecisionQuality
      .mockReturnValueOnce(firstQuality.promise)
      .mockResolvedValueOnce(qualityReport(7, 90));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => usePersonalPerformanceQuery(), { wrapper });

    await waitFor(() => expect(getPaperDecisionQuality).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(result.current.report?.aggregate?.processScore).toBe(90));

    await act(async () => {
      firstQuality.reject(Object.assign(new Error('server'), { response: { status: 500 } }));
      await firstQuality.promise.catch(() => undefined);
    });

    expect(result.current.error).toBeNull();
    expect(result.current.report?.aggregate?.processScore).toBe(90);
  });

  it('removes exact keys on unmount and ignores a late failure without setState', async () => {
    const pending = createDeferred<PortfolioAccountListResponse>();
    getAccounts.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const accountsKey = PERSONAL_PERFORMANCE_ACCOUNTS_QUERY_KEY;
    const qualityKey = buildPersonalPerformanceQualityQueryKey(7);
    const { result, unmount } = renderHook(() => usePersonalPerformanceQuery(), { wrapper });

    await waitFor(() => expect(getAccounts).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(Object.assign(new Error('server'), { response: { status: 500 } }));
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.error).toBeNull();
    expect(client.getQueryState(accountsKey)).toBeUndefined();
    expect(client.getQueryState(qualityKey)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['portfolio', 'performance'] })).toHaveLength(0);
    expect(queryFetchStatus(client, accountsKey)).toBeUndefined();
  });
});
