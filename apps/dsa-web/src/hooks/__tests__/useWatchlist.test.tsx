// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { StrictMode, type ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import {
  WATCHLIST_QUERY_KEY,
  WATCHLIST_QUERY_SCHEDULE,
  useWatchlist,
} from '../useWatchlist';

const {
  mockGetWatchlist,
  mockAddToWatchlist,
  mockRemoveFromWatchlist,
} = vi.hoisted(() => ({
  mockGetWatchlist: vi.fn(),
  mockAddToWatchlist: vi.fn(),
  mockRemoveFromWatchlist: vi.fn(),
}));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getWatchlist: mockGetWatchlist,
    addToWatchlist: mockAddToWatchlist,
    removeFromWatchlist: mockRemoveFromWatchlist,
  },
}));

function createWrapper(client?: QueryClient) {
  const queryClient = client ?? createAppQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return { client: queryClient, wrapper: Wrapper };
}

function createHostWrapper(client?: QueryClient) {
  const queryClient = client ?? createAppQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <StrictMode>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </StrictMode>
    );
  }
  return { client: queryClient, wrapper: Wrapper };
}

function loadQueryOptions(client: QueryClient) {
  const query = client.getQueryCache().find({ queryKey: WATCHLIST_QUERY_KEY, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function assertNoWatchlistPrefixOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'watchlist' && key.length === 1).toBe(false);
    if (key[0] === 'watchlist') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['watchlist', 'codes']);
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

describe('useWatchlist', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    mockGetWatchlist.mockResolvedValue([]);
    mockAddToWatchlist.mockResolvedValue([]);
    mockRemoveFromWatchlist.mockResolvedValue([]);
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

  it('pins the exact watchlist GET key and schedule around getWatchlist()', async () => {
    expect(WATCHLIST_QUERY_KEY).toEqual(['watchlist', 'codes']);
    expect(WATCHLIST_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlist(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockGetWatchlist).toHaveBeenCalledTimes(1);
    expect(mockGetWatchlist).toHaveBeenCalledWith();
    expect(loadQueryOptions(client)?.retry).toBe(false);
    expect(loadQueryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(loadQueryOptions(client)?.staleTime).toBe(0);
    expect(loadQueryOptions(client)?.networkMode).toBe('always');
    expect(loadQueryOptions(client)?.refetchInterval).toBeUndefined();
  });

  it('defers the initial request until the consumer enables watchlist scope', async () => {
    mockGetWatchlist.mockResolvedValue(['AAPL']);
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ enabled }) => useWatchlist({ enabled }),
      { wrapper, initialProps: { enabled: false } },
    );

    expect(result.current.isLoading).toBe(false);
    expect(result.current.watchlistCodes).toEqual([]);
    expect(mockGetWatchlist).not.toHaveBeenCalled();

    rerender({ enabled: true });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockGetWatchlist).toHaveBeenCalledOnce();
    expect(result.current.watchlistCodes).toEqual(['AAPL']);
  });

  it('issues one getWatchlist under host-faithful StrictMode', async () => {
    const pending = createDeferred<string[]>();
    mockGetWatchlist.mockReturnValue(pending.promise);
    const { wrapper } = createHostWrapper();
    const { result } = renderHook(() => useWatchlist(), { wrapper });

    await waitFor(() => expect(mockGetWatchlist).toHaveBeenCalledTimes(1));
    await act(async () => {
      pending.resolve(['AAPL']);
    });
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
      expect(result.current.watchlistCodes).toEqual(['AAPL']);
    });
    expect(mockGetWatchlist).toHaveBeenCalledTimes(1);
  });

  it('keeps the newest watchlist result when an older refresh resolves last', async () => {
    const older = createDeferred<string[]>();
    const newer = createDeferred<string[]>();
    mockGetWatchlist
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise);
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const { result, rerender } = renderHook(
      ({ enabled }) => useWatchlist({ enabled }),
      { wrapper, initialProps: { enabled: true } },
    );

    await waitFor(() => expect(mockGetWatchlist).toHaveBeenCalledTimes(1));
    rerender({ enabled: false });
    rerender({ enabled: true });
    await waitFor(() => expect(mockGetWatchlist).toHaveBeenCalledTimes(2));

    await act(async () => newer.resolve(['NEW']));
    await waitFor(() => expect(result.current.watchlistCodes).toEqual(['NEW']));
    await act(async () => {
      older.resolve(['OLD']);
      await older.promise.catch(() => undefined);
    });

    expect(result.current.watchlistCodes).toEqual(['NEW']);
    expect(result.current.loadError).toBeNull();
    expect(result.current.isLoading).toBe(false);
    assertNoWatchlistPrefixOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('ignores an older watchlist error after a newer refresh succeeds', async () => {
    const older = createDeferred<string[]>();
    const newer = createDeferred<string[]>();
    mockGetWatchlist
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise);
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ enabled }) => useWatchlist({ enabled }),
      { wrapper, initialProps: { enabled: true } },
    );

    await waitFor(() => expect(mockGetWatchlist).toHaveBeenCalledTimes(1));
    rerender({ enabled: false });
    rerender({ enabled: true });
    await waitFor(() => expect(mockGetWatchlist).toHaveBeenCalledTimes(2));

    await act(async () => newer.resolve(['NEW']));
    await waitFor(() => expect(result.current.watchlistCodes).toEqual(['NEW']));
    await act(async () => {
      older.reject(new Error('stale watchlist failure'));
      await older.promise.catch(() => undefined);
    });

    expect(result.current.watchlistCodes).toEqual(['NEW']);
    expect(result.current.loadError).toBeNull();
    expect(result.current.isLoading).toBe(false);
  });

  it('keeps the newest watchlist error when an older refresh succeeds later', async () => {
    const older = createDeferred<string[]>();
    const newer = createDeferred<string[]>();
    mockGetWatchlist
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise);
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ enabled }) => useWatchlist({ enabled }),
      { wrapper, initialProps: { enabled: true } },
    );

    await waitFor(() => expect(mockGetWatchlist).toHaveBeenCalledTimes(1));
    rerender({ enabled: false });
    rerender({ enabled: true });
    await waitFor(() => expect(mockGetWatchlist).toHaveBeenCalledTimes(2));

    await act(async () => {
      newer.reject(new Error('current watchlist failure'));
      await newer.promise.catch(() => undefined);
    });
    await waitFor(() => expect(result.current.loadError).not.toBeNull());
    const latestError = result.current.loadError;
    await act(async () => {
      older.resolve(['OLD']);
      await older.promise.catch(() => undefined);
    });

    expect(result.current.watchlistCodes).toEqual([]);
    expect(result.current.loadError).toBe(latestError);
    expect(result.current.isLoading).toBe(false);
  });

  it('does not auto-retry a failed GET when the QueryClient default would retry', async () => {
    mockGetWatchlist.mockRejectedValue(
      Object.assign(new Error('server'), { response: { status: 500 } }),
    );
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useWatchlist(), { wrapper });

    await waitFor(() => expect(result.current.loadError).not.toBeNull());
    expect(mockGetWatchlist).toHaveBeenCalledTimes(1);
    expect(loadQueryOptions(client)?.retry).toBe(false);
    expect(result.current.watchlistCodes).toEqual([]);
    expect(result.current.isLoading).toBe(false);
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useWatchlist(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockGetWatchlist).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(mockGetWatchlist).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call getWatchlist again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useWatchlist(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockGetWatchlist).toHaveBeenCalledTimes(1);
    expect(loadQueryOptions(client)?.refetchInterval).toBeUndefined();

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

    expect(mockGetWatchlist).toHaveBeenCalledTimes(1);
  });

  it('issues getWatchlist while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlist(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockGetWatchlist).toHaveBeenCalledTimes(1);
  });

  it('shares one in-flight GET across concurrent observers of the exact key', async () => {
    const pending = createDeferred<string[]>();
    mockGetWatchlist.mockReturnValue(pending.promise);
    const { wrapper } = createWrapper();
    const first = renderHook(() => useWatchlist(), { wrapper });
    const second = renderHook(() => useWatchlist(), { wrapper });

    await waitFor(() => expect(mockGetWatchlist).toHaveBeenCalledTimes(1));
    await act(async () => {
      pending.resolve(['AAPL']);
    });
    await waitFor(() => {
      expect(first.result.current.watchlistCodes).toEqual(['AAPL']);
      expect(second.result.current.watchlistCodes).toEqual(['AAPL']);
    });
    expect(mockGetWatchlist).toHaveBeenCalledTimes(1);
  });

  it('updates the exact query after a successful mutation so sibling observers converge without another GET', async () => {
    mockGetWatchlist.mockResolvedValue(['AAPL']);
    mockAddToWatchlist.mockResolvedValue(['AAPL', 'MSFT']);
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const { result } = renderHook(() => ({
      first: useWatchlist(),
      second: useWatchlist(),
    }), { wrapper });

    await waitFor(() => {
      expect(result.current.first.watchlistCodes).toEqual(['AAPL']);
      expect(result.current.second.watchlistCodes).toEqual(['AAPL']);
    });
    expect(mockGetWatchlist).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.first.addToWatchlist('MSFT');
    });

    expect(mockAddToWatchlist).toHaveBeenCalledWith('MSFT');
    expect(mockGetWatchlist).toHaveBeenCalledTimes(1);
    expect(client.getQueryData(WATCHLIST_QUERY_KEY)).toEqual(['AAPL', 'MSFT']);
    expect(result.current.first.watchlistCodes).toEqual(['AAPL', 'MSFT']);
    expect(result.current.second.watchlistCodes).toEqual(['AAPL', 'MSFT']);
    expect(result.current.first.loadError).toBeNull();
    expect(result.current.second.loadError).toBeNull();
    expect(result.current.first.isLoading).toBe(false);
    expect(result.current.second.isLoading).toBe(false);
    assertNoWatchlistPrefixOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('does not let a stale in-flight GET overwrite a successful mutation result', async () => {
    const pendingGet = createDeferred<string[]>();
    mockGetWatchlist.mockReturnValueOnce(pendingGet.promise);
    mockAddToWatchlist.mockResolvedValue(['MSFT']);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlist(), { wrapper });

    await waitFor(() => expect(mockGetWatchlist).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(result.current.isLoading).toBe(true));

    await act(async () => {
      await result.current.addToWatchlist('MSFT');
    });
    expect(result.current.watchlistCodes).toEqual(['MSFT']);
    expect(result.current.isLoading).toBe(false);

    await act(async () => {
      pendingGet.resolve(['STALE']);
      await pendingGet.promise.catch(() => undefined);
    });

    expect(result.current.watchlistCodes).toEqual(['MSFT']);
    expect(result.current.loadError).toBeNull();
    expect(mockGetWatchlist).toHaveBeenCalledTimes(1);
  });

  it('matches raw HK watchlist entries against prefixed and suffixed variants', async () => {
    mockGetWatchlist.mockResolvedValue(['00700']);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlist(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.isInWatchlist('00700')).toBe(true);
    expect(result.current.isInWatchlist('HK00700')).toBe(true);
    expect(result.current.isInWatchlist('00700.HK')).toBe(true);
    expect(result.current.isInWatchlist('HK01810')).toBe(false);
  });

  it('removes the matched raw watchlist entry instead of adding a duplicate variant', async () => {
    mockGetWatchlist.mockResolvedValue(['00700']);
    mockRemoveFromWatchlist.mockResolvedValue([]);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlist(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    await act(async () => {
      await result.current.toggleWatchlist('HK00700');
    });

    expect(mockRemoveFromWatchlist).toHaveBeenCalledWith('00700');
    expect(mockAddToWatchlist).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(result.current.watchlistCodes).toEqual([]);
    });
  });

  it('compares submitted and stored US tickers case-insensitively', async () => {
    mockGetWatchlist.mockResolvedValue(['aapl']);
    mockRemoveFromWatchlist.mockResolvedValue([]);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlist(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.isInWatchlist('AAPL')).toBe(true);

    await act(async () => {
      await result.current.toggleWatchlist('AAPL');
    });

    expect(mockRemoveFromWatchlist).toHaveBeenCalledWith('aapl');
    expect(mockAddToWatchlist).not.toHaveBeenCalled();
  });
});
