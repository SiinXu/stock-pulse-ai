// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { reportVersionCompareApi } from '../../api/reportVersionCompare';
import type {
  ReportVersionCompareResponse,
  ReportVersionRunItem,
  ReportVersionRunListResponse,
} from '../../api/reportVersionCompare';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import {
  REPORT_VERSION_COMPARE_CANCEL,
  REPORT_VERSION_COMPARE_QUERY_SCHEDULE,
  REPORT_VERSION_COMPARE_RUN_PAGE_SIZE,
  buildReportVersionCompareQueryKey,
  buildReportVersionRunsQueryKey,
  fetchReportVersionCompare,
  fetchReportVersionRuns,
  useReportVersionCompareQueries,
} from '../useReportVersionCompareQueries';

vi.mock('../../api/reportVersionCompare', () => ({
  reportVersionCompareApi: {
    listRuns: vi.fn(),
    compare: vi.fn(),
  },
}));

const listRuns = vi.mocked(reportVersionCompareApi.listRuns);
const compareApi = vi.mocked(reportVersionCompareApi.compare);

const STOCK = '600519';
const PAGE = 1;
const LIMIT = 50;

function runItem(runId: string): ReportVersionRunItem {
  return {
    runId,
    queryId: `q-${runId}`,
    stockCode: STOCK,
    createdAt: '2026-08-01T00:00:00',
    action: 'buy',
    actionLabel: 'Buy',
    sentimentScore: 80,
    modelUsed: 'm1',
    configFingerprint: `fp-${runId}`,
    configComponents: {},
    configComplete: true,
    configMissingKeys: [],
  };
}

function listPayload(
  items: ReportVersionRunItem[],
  extras: Partial<ReportVersionRunListResponse> = {},
): ReportVersionRunListResponse {
  return {
    stockCode: STOCK,
    total: items.length,
    page: PAGE,
    limit: LIMIT,
    items,
    ...extras,
  };
}

function comparePayload(
  baseRunId = '1',
  targetRunId = '2',
): ReportVersionCompareResponse {
  return {
    status: 'ok',
    stockCode: STOCK,
    baseRun: runItem(baseRunId),
    targetRun: runItem(targetRunId),
    configDiff: {
      baseFingerprint: 'fp-1',
      targetFingerprint: 'fp-2',
      identical: false,
      hasDifferences: true,
      comparisonStatus: 'different',
      baseComplete: true,
      targetComplete: true,
      baseMissingKeys: [],
      targetMissingKeys: [],
      components: [],
    },
    fieldDiffs: [],
    optionalSections: [],
    delta: null,
    engineStatus: 'ok',
  };
}

function createWrapper(client?: QueryClient) {
  const queryClient = client ?? createAppQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
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

function assertNoReportVersionComparePrefixOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'report-version-compare' && key.length === 1).toBe(false);
    if (key[0] === 'report-version-compare') {
      expect(filters?.exact).toBe(true);
      expect(key[1] === 'runs' || key[1] === 'compare').toBe(true);
      expect(key).toHaveLength(5);
    }
  }
}

function flags(result: {
  current: {
    loadingRuns: boolean;
    loadingMore: boolean;
    comparing: boolean;
  };
}) {
  return {
    loadingRuns: result.current.loadingRuns,
    loadingMore: result.current.loadingMore,
    comparing: result.current.comparing,
  };
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

describe('useReportVersionCompareQueries', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    listRuns.mockResolvedValue(listPayload([runItem('1'), runItem('2')]));
    compareApi.mockResolvedValue(comparePayload());
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

  it('pins exact list/compare keys, schedule, and { signal } transport', async () => {
    expect(buildReportVersionRunsQueryKey(STOCK, PAGE, LIMIT)).toEqual([
      'report-version-compare', 'runs', STOCK, PAGE, LIMIT,
    ]);
    expect(buildReportVersionCompareQueryKey(STOCK, '1', '2')).toEqual([
      'report-version-compare', 'compare', STOCK, '1', '2',
    ]);
    expect(REPORT_VERSION_COMPARE_RUN_PAGE_SIZE).toBe(50);
    expect(REPORT_VERSION_COMPARE_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });

    const signal = new AbortController().signal;
    await fetchReportVersionRuns({ stockCode: STOCK, page: PAGE, limit: LIMIT, signal });
    expect(listRuns).toHaveBeenCalledTimes(1);
    expect(listRuns).toHaveBeenCalledWith({
      stockCode: STOCK,
      page: PAGE,
      limit: LIMIT,
      signal,
    });

    await fetchReportVersionCompare({
      stockCode: STOCK,
      baseRunId: '1',
      targetRunId: '2',
      signal,
    });
    expect(compareApi).toHaveBeenCalledTimes(1);
    expect(compareApi).toHaveBeenCalledWith({
      stockCode: STOCK,
      baseRunId: '1',
      targetRunId: '2',
      signal,
    });
  });

  it('does not auto-fetch on mount', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await flushQueryMicrotasks();
    expect(listRuns).not.toHaveBeenCalled();
    expect(compareApi).not.toHaveBeenCalled();
    expect(result.current.loadingRuns).toBe(false);
    expect(result.current.loadingMore).toBe(false);
    expect(result.current.comparing).toBe(false);
    expect(result.current.hasLoadedRuns).toBe(false);
  });

  it('does not auto-retry a 5xx load when the QueryClient default would retry', async () => {
    listRuns.mockRejectedValue(Object.assign(new Error('server'), { response: { status: 500 } }));
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      await result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });

    expect(result.current.error).not.toBeNull();
    expect(listRuns).toHaveBeenCalledTimes(1);
    expect(queryOptions(client, buildReportVersionRunsQueryKey(STOCK, PAGE, LIMIT))?.retry).toBe(false);
    expect(result.current.runs).toEqual([]);
    expect(result.current.hasLoadedRuns).toBe(true);
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      await result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });
    const key = buildReportVersionRunsQueryKey(STOCK, PAGE, LIMIT);
    expect(queryOptions(client, key)?.refetchOnWindowFocus).toBe(false);
    expect(queryOptions(client, key)?.retry).toBe(false);
    expect(queryOptions(client, key)?.staleTime).toBe(0);
    expect(listRuns).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(listRuns).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call the API again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });
    await act(async () => {
      await result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });
    expect(listRuns).toHaveBeenCalledTimes(1);
    expect(
      queryOptions(client, buildReportVersionRunsQueryKey(STOCK, PAGE, LIMIT))?.refetchInterval,
    ).toBeUndefined();

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

    expect(listRuns).toHaveBeenCalledTimes(1);
    expect(compareApi).not.toHaveBeenCalled();
  });

  it('issues the GET while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      await result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });
    expect(listRuns).toHaveBeenCalledTimes(1);
    expect(
      queryOptions(client, buildReportVersionRunsQueryKey(STOCK, PAGE, LIMIT))?.networkMode,
    ).toBe('always');
    expect(result.current.runs.map((run) => run.runId)).toEqual(['1', '2']);
  });

  it('schedules through fetchQuery with no live observer', async () => {
    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      await result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });
    expect(
      client.getQueryCache().find({
        queryKey: buildReportVersionRunsQueryKey(STOCK, PAGE, LIMIT),
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);

    await act(async () => {
      await result.current.compare({ stockCode: STOCK, baseRunId: '1', targetRunId: '2' });
    });

    expect(fetchSpy).toHaveBeenCalled();
    const keys = fetchSpy.mock.calls.map(([options]) => options.queryKey);
    expect(keys).toContainEqual(['report-version-compare', 'runs', STOCK, PAGE, LIMIT]);
    expect(keys).toContainEqual(['report-version-compare', 'compare', STOCK, '1', '2']);
    for (const key of keys) {
      expect(key).not.toContain('reportType');
      expect(key).not.toContain(true);
      expect(key).not.toContain(false);
    }
    expect(
      client.getQueryCache().find({
        queryKey: buildReportVersionCompareQueryKey(STOCK, '1', '2'),
        exact: true,
      })?.getObserversCount(),
    ).toBe(0);
  });

  it('cancels an in-flight list when compare starts and converges loading flags', async () => {
    const first = createDeferred<ReportVersionRunListResponse>();
    listRuns.mockReturnValueOnce(first.promise);
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const listKey = buildReportVersionRunsQueryKey(STOCK, PAGE, LIMIT);
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      void result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });
    await waitFor(() => expect(listRuns).toHaveBeenCalledTimes(1));
    expect(flags(result)).toEqual({ loadingRuns: true, loadingMore: false, comparing: false });

    await act(async () => {
      void result.current.compare({ stockCode: STOCK, baseRunId: '1', targetRunId: '2' });
    });
    await waitFor(() => expect(result.current.result?.stockCode).toBe(STOCK));

    expect(flags(result)).toEqual({ loadingRuns: false, loadingMore: false, comparing: false });
    expect(result.current.runs).toEqual([]);
    expect(listRuns.mock.calls[0][0]?.signal?.aborted).toBe(true);
    expect(client.getQueryState(listKey)).toBeUndefined();

    await act(async () => {
      first.resolve(listPayload([runItem('stale')]));
      await first.promise.catch(() => undefined);
    });
    expect(result.current.runs).toEqual([]);
    expect(result.current.error).toBeNull();
    expect(flags(result)).toEqual({ loadingRuns: false, loadingMore: false, comparing: false });
    assertNoReportVersionComparePrefixOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertNoReportVersionComparePrefixOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('cancels an in-flight compare when list starts and converges loading flags', async () => {
    const first = createDeferred<ReportVersionCompareResponse>();
    compareApi.mockReturnValueOnce(first.promise);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      void result.current.compare({ stockCode: STOCK, baseRunId: '1', targetRunId: '2' });
    });
    await waitFor(() => expect(compareApi).toHaveBeenCalledTimes(1));
    expect(flags(result)).toEqual({ loadingRuns: false, loadingMore: false, comparing: true });

    await act(async () => {
      void result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });
    await waitFor(() => expect(result.current.runs.map((run) => run.runId)).toEqual(['1', '2']));

    expect(flags(result)).toEqual({ loadingRuns: false, loadingMore: false, comparing: false });
    expect(result.current.result).toBeNull();
    expect(compareApi.mock.calls[0][0]?.signal?.aborted).toBe(true);

    await act(async () => {
      first.resolve(comparePayload());
      await first.promise.catch(() => undefined);
    });
    expect(result.current.result).toBeNull();
    expect(result.current.error).toBeNull();
    expect(flags(result)).toEqual({ loadingRuns: false, loadingMore: false, comparing: false });
  });

  it('same-key list refresh cancel+remove then fetchQuery', async () => {
    const first = createDeferred<ReportVersionRunListResponse>();
    listRuns
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(listPayload([runItem('newest')]));
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const key = buildReportVersionRunsQueryKey(STOCK, PAGE, LIMIT);
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      void result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });
    await waitFor(() => expect(listRuns).toHaveBeenCalledTimes(1));
    const firstSignal = listRuns.mock.calls[0][0]?.signal;

    await act(async () => {
      void result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });
    await waitFor(() => expect(result.current.runs.map((run) => run.runId)).toEqual(['newest']));

    expect(firstSignal?.aborted).toBe(true);
    expect(cancelSpy).toHaveBeenCalledWith(
      { queryKey: key, exact: true },
      REPORT_VERSION_COMPARE_CANCEL,
    );
    expect(removeSpy).toHaveBeenCalledWith({ queryKey: key, exact: true });
    expect(fetchSpy.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(queryFetchStatus(client, key)).toBe('idle');

    await act(async () => {
      first.resolve(listPayload([runItem('stale')]));
      await first.promise.catch(() => undefined);
    });
    expect(result.current.runs.map((run) => run.runId)).toEqual(['newest']);
    assertNoReportVersionComparePrefixOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('append merges by runId and does not clear result', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      await result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
      await result.current.compare({ stockCode: STOCK, baseRunId: '1', targetRunId: '2' });
    });
    expect(result.current.result?.stockCode).toBe(STOCK);

    listRuns.mockResolvedValueOnce(listPayload(
      [{ ...runItem('1'), actionLabel: 'Updated' }, runItem('3')],
      { page: 2, total: 3 },
    ));
    await act(async () => {
      await result.current.loadRuns({ stockCode: STOCK, page: 2, append: true });
    });

    expect(result.current.runs.map((run) => run.runId)).toEqual(['1', '2', '3']);
    expect(result.current.runs[0]?.actionLabel).toBe('Updated');
    expect(result.current.result?.stockCode).toBe(STOCK);
    expect(result.current.runPage).toBe(2);
    expect(flags(result)).toEqual({ loadingRuns: false, loadingMore: false, comparing: false });
  });

  it('replace list (append: false) clears result', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      await result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
      await result.current.compare({ stockCode: STOCK, baseRunId: '1', targetRunId: '2' });
    });
    expect(result.current.result).not.toBeNull();

    await act(async () => {
      await result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });
    expect(result.current.result).toBeNull();
    expect(result.current.runs.map((run) => run.runId)).toEqual(['1', '2']);
  });

  it('equal base/target IDs clear result without HTTP', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      await result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
      await result.current.compare({ stockCode: STOCK, baseRunId: '1', targetRunId: '2' });
    });
    expect(result.current.result).not.toBeNull();
    compareApi.mockClear();

    await act(async () => {
      await result.current.compare({ stockCode: STOCK, baseRunId: '1', targetRunId: '1' });
    });
    expect(compareApi).not.toHaveBeenCalled();
    expect(result.current.result).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('validation-only empty list stock does not cancel a deferred valid request', async () => {
    const first = createDeferred<ReportVersionRunListResponse>();
    listRuns.mockReturnValueOnce(first.promise);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      void result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });
    await waitFor(() => expect(listRuns).toHaveBeenCalledTimes(1));
    const firstSignal = listRuns.mock.calls[0][0]?.signal;

    await act(async () => {
      await result.current.loadRuns({ stockCode: '   ', page: PAGE, append: false });
      await result.current.loadRuns({ stockCode: '', page: PAGE, append: false });
    });

    expect(firstSignal?.aborted).toBe(false);
    expect(listRuns).toHaveBeenCalledTimes(1);
    expect(flags(result)).toEqual({ loadingRuns: true, loadingMore: false, comparing: false });

    await act(async () => {
      first.resolve(listPayload([runItem('kept')]));
    });
    await waitFor(() => expect(result.current.runs.map((run) => run.runId)).toEqual(['kept']));
    expect(flags(result)).toEqual({ loadingRuns: false, loadingMore: false, comparing: false });
  });

  it('validation-only missing compare inputs do not cancel a deferred valid request', async () => {
    const first = createDeferred<ReportVersionRunListResponse>();
    listRuns.mockReturnValueOnce(first.promise);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      void result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });
    await waitFor(() => expect(listRuns).toHaveBeenCalledTimes(1));
    const firstSignal = listRuns.mock.calls[0][0]?.signal;

    await act(async () => {
      await result.current.compare({ stockCode: '', baseRunId: '1', targetRunId: '2' });
      await result.current.compare({ stockCode: STOCK, baseRunId: '', targetRunId: '2' });
      await result.current.compare({ stockCode: STOCK, baseRunId: '1', targetRunId: '' });
    });

    expect(firstSignal?.aborted).toBe(false);
    expect(compareApi).not.toHaveBeenCalled();
    expect(flags(result)).toEqual({ loadingRuns: true, loadingMore: false, comparing: false });

    await act(async () => {
      first.resolve(listPayload([runItem('kept')]));
    });
    await waitFor(() => expect(result.current.runs.map((run) => run.runId)).toEqual(['kept']));
  });

  it('equal-id compare does not cancel a deferred valid request and may still commit', async () => {
    const first = createDeferred<ReportVersionRunListResponse>();
    listRuns.mockReturnValueOnce(first.promise);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      void result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });
    await waitFor(() => expect(listRuns).toHaveBeenCalledTimes(1));
    const firstSignal = listRuns.mock.calls[0][0]?.signal;

    await act(async () => {
      await result.current.compare({ stockCode: STOCK, baseRunId: '9', targetRunId: '9' });
    });

    expect(firstSignal?.aborted).toBe(false);
    expect(compareApi).not.toHaveBeenCalled();
    expect(result.current.result).toBeNull();
    expect(flags(result)).toEqual({ loadingRuns: true, loadingMore: false, comparing: false });

    await act(async () => {
      first.resolve(listPayload([runItem('kept')]));
    });
    await waitFor(() => expect(result.current.runs.map((run) => run.runId)).toEqual(['kept']));
    expect(flags(result)).toEqual({ loadingRuns: false, loadingMore: false, comparing: false });
  });

  it('does not setError when listRuns settles as CancelledError', async () => {
    listRuns.mockRejectedValue(new CancelledError(REPORT_VERSION_COMPARE_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      await result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });

    expect(result.current.error).toBeNull();
    expect(result.current.runs).toEqual([]);
    expect(result.current.hasLoadedRuns).toBe(false);
    expect(flags(result)).toEqual({ loadingRuns: false, loadingMore: false, comparing: false });
  });

  it('unmount removes exact live keys and ignores a late failure', async () => {
    const pending = createDeferred<ReportVersionRunListResponse>();
    listRuns.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const key = buildReportVersionRunsQueryKey(STOCK, PAGE, LIMIT);
    const { result, unmount } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      void result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });
    await waitFor(() => expect(listRuns).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(Object.assign(new Error('server'), { response: { status: 500 } }));
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.error).toBeNull();
    expect(client.getQueryState(key)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['report-version-compare', 'runs'] })).toHaveLength(0);
    expect(queryFetchStatus(client, key)).toBeUndefined();
  });

  it('cancelInFlight clears hook-owned loaded state and ignores a late success', async () => {
    const pending = createDeferred<ReportVersionRunListResponse>();
    listRuns.mockReturnValueOnce(pending.promise);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      void result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });
    await waitFor(() => expect(listRuns).toHaveBeenCalledTimes(1));
    expect(flags(result)).toEqual({ loadingRuns: true, loadingMore: false, comparing: false });

    await act(async () => {
      result.current.cancelInFlight();
    });

    expect(result.current.runs).toEqual([]);
    expect(result.current.totalRuns).toBe(0);
    expect(result.current.runPage).toBe(1);
    expect(result.current.loadedStockCode).toBeNull();
    expect(result.current.hasLoadedRuns).toBe(false);
    expect(result.current.result).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.failedOperation).toBeNull();
    expect(flags(result)).toEqual({ loadingRuns: false, loadingMore: false, comparing: false });

    await act(async () => {
      pending.resolve(listPayload([runItem('late')]));
      await pending.promise.catch(() => undefined);
    });
    expect(result.current.runs).toEqual([]);
    expect(result.current.hasLoadedRuns).toBe(false);
    expect(flags(result)).toEqual({ loadingRuns: false, loadingMore: false, comparing: false });
  });

  it('append failure keeps existing runs and a live-generation list replace failure clears them', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReportVersionCompareQueries(), { wrapper });

    await act(async () => {
      await result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });
    expect(result.current.runs).toHaveLength(2);

    listRuns.mockRejectedValueOnce(Object.assign(new Error('append failed'), { response: { status: 500 } }));
    await act(async () => {
      await result.current.loadRuns({ stockCode: STOCK, page: 2, append: true });
    });
    expect(result.current.runs).toHaveLength(2);
    expect(result.current.error).not.toBeNull();
    expect(result.current.failedOperation).toEqual({
      kind: 'list',
      stockCode: STOCK,
      page: 2,
      append: true,
    });

    listRuns.mockRejectedValueOnce(Object.assign(new Error('replace failed'), { response: { status: 500 } }));
    await act(async () => {
      await result.current.loadRuns({ stockCode: STOCK, page: PAGE, append: false });
    });
    expect(result.current.runs).toEqual([]);
    expect(result.current.loadedStockCode).toBeNull();
    expect(result.current.hasLoadedRuns).toBe(true);
    expect(result.current.failedOperation).toMatchObject({ kind: 'list', append: false });
  });
});
