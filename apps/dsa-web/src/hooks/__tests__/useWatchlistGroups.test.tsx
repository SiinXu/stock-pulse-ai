// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { StrictMode, type ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { WatchlistGroupState } from '../../types/watchlist';
import {
  WATCHLIST_GROUPS_QUERY_KEY,
  WATCHLIST_GROUPS_QUERY_SCHEDULE,
  useWatchlistGroups,
} from '../useWatchlistGroups';

const { mockList, mockCreate, mockRestore } = vi.hoisted(() => ({
  mockList: vi.fn(),
  mockCreate: vi.fn(),
  mockRestore: vi.fn(),
}));

vi.mock('../../api/watchlistGroups', () => ({
  watchlistGroupsApi: {
    list: mockList,
    create: mockCreate,
    remove: vi.fn(),
    restore: mockRestore,
    reorderGroups: vi.fn(),
    reorderMembers: vi.fn(),
    moveMember: vi.fn(),
  },
}));

const state = (revision: number, groups: WatchlistGroupState['groups'] = []): WatchlistGroupState => ({
  revision,
  groups,
});

function apiError(message: string) {
  return Object.assign(new Error(message), {
    parsedError: {
      title: 'Error',
      message,
      rawMessage: message,
      category: 'http_error',
    },
  });
}

const CODES_KEY = ['watchlist', 'codes'] as const;
const SCORES_KEY = ['watchlist', 'scores', '[]', ''] as const;

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
  const query = client.getQueryCache().find({ queryKey: WATCHLIST_GROUPS_QUERY_KEY, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function groupsFetchStatus(client: QueryClient) {
  return client.getQueryState(WATCHLIST_GROUPS_QUERY_KEY)?.fetchStatus;
}

function seedSiblingWatchlistQueries(client: QueryClient) {
  client.setQueryData(CODES_KEY, ['AAPL']);
  client.setQueryData(SCORES_KEY, { items: [] });
}

function assertNoWatchlistPrefixOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'watchlist' && key.length === 1).toBe(false);
    if (key[0] === 'watchlist') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['watchlist', 'groups']);
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

describe('useWatchlistGroups', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    mockList.mockResolvedValue(state(1));
    mockCreate.mockResolvedValue(state(2));
    mockRestore.mockResolvedValue(state(3));
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

  it('pins the exact groups GET key and schedule around list()', async () => {
    expect(WATCHLIST_GROUPS_QUERY_KEY).toEqual(['watchlist', 'groups']);
    expect(WATCHLIST_GROUPS_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlistGroups(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockList).toHaveBeenCalledTimes(1);
    expect(mockList).toHaveBeenCalledWith();
    expect(loadQueryOptions(client)?.retry).toBe(false);
    expect(loadQueryOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(loadQueryOptions(client)?.staleTime).toBe(0);
    expect(loadQueryOptions(client)?.networkMode).toBe('always');
    expect(loadQueryOptions(client)?.refetchInterval).toBeUndefined();
  });

  it('defers the initial request until the consumer enables groups', async () => {
    mockList.mockResolvedValue(state(4));
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ enabled }) => useWatchlistGroups({ enabled }),
      { wrapper, initialProps: { enabled: false } },
    );

    expect(result.current.isLoading).toBe(false);
    expect(result.current.groups).toEqual([]);
    expect(result.current.revision).toBeNull();
    expect(mockList).not.toHaveBeenCalled();

    rerender({ enabled: true });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockList).toHaveBeenCalledOnce();
    expect(result.current.revision).toBe(4);
  });

  it('issues one list() under host-faithful StrictMode', async () => {
    const pending = createDeferred<WatchlistGroupState>();
    mockList.mockReturnValue(pending.promise);
    const { client, wrapper } = createHostWrapper();
    const { result } = renderHook(() => useWatchlistGroups(), { wrapper });

    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(1));
    await act(async () => {
      pending.resolve(state(1));
    });
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
      expect(result.current.revision).toBe(1);
      expect(groupsFetchStatus(client)).not.toBe('fetching');
    });
    expect(mockList).toHaveBeenCalledTimes(1);
  });

  it('returns false from refresh when the GET fails and keeps the current revision', async () => {
    mockList
      .mockResolvedValueOnce(state(1))
      .mockRejectedValueOnce(new Error('groups down'));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlistGroups(), { wrapper });
    await waitFor(() => expect(result.current.revision).toBe(1));

    let refreshed!: boolean;
    await act(async () => {
      refreshed = await result.current.refresh();
    });

    expect(refreshed).toBe(false);
    expect(result.current.revision).toBe(1);
    expect(result.current.errorMessage).toBeTruthy();
    expect(result.current.isLoading).toBe(false);
  });

  it('returns true from refresh and clears a prior load error', async () => {
    mockList
      .mockRejectedValueOnce(new Error('groups down'))
      .mockResolvedValueOnce(state(2));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlistGroups(), { wrapper });
    await waitFor(() => expect(result.current.errorMessage).toBeTruthy());

    let refreshed!: boolean;
    await act(async () => {
      refreshed = await result.current.refresh();
    });

    expect(refreshed).toBe(true);
    expect(result.current.revision).toBe(2);
    expect(result.current.errorMessage).toBeNull();
  });

  it('keeps the newest groups result when an older refresh resolves last', async () => {
    const older = createDeferred<WatchlistGroupState>();
    const newer = createDeferred<WatchlistGroupState>();
    mockList
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise);
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const { result, rerender } = renderHook(
      ({ enabled }) => useWatchlistGroups({ enabled }),
      { wrapper, initialProps: { enabled: true } },
    );

    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(1));
    rerender({ enabled: false });
    rerender({ enabled: true });
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(2));

    await act(async () => newer.resolve(state(3)));
    await waitFor(() => expect(result.current.revision).toBe(3));
    await act(async () => {
      older.resolve(state(1));
      await older.promise.catch(() => undefined);
    });

    expect(result.current.revision).toBe(3);
    expect(result.current.errorMessage).toBeNull();
    expect(result.current.isLoading).toBe(false);
    assertNoWatchlistPrefixOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('settles disable cancellation before its re-enabled successor completes', async () => {
    const cancelledGet = createDeferred<WatchlistGroupState>();
    const successorGet = createDeferred<WatchlistGroupState>();
    mockList
      .mockReturnValueOnce(cancelledGet.promise)
      .mockReturnValueOnce(successorGet.promise);
    const { client, wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ enabled }) => useWatchlistGroups({ enabled }),
      { wrapper, initialProps: { enabled: true } },
    );

    await waitFor(() => expect(groupsFetchStatus(client)).toBe('fetching'));
    rerender({ enabled: false });
    await waitFor(() => expect(groupsFetchStatus(client)).not.toBe('fetching'));
    rerender({ enabled: true });
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(2));
    await act(async () => successorGet.resolve(state(8)));
    await waitFor(() => {
      expect(result.current.revision).toBe(8);
      expect(result.current.isLoading).toBe(false);
      expect(groupsFetchStatus(client)).not.toBe('fetching');
    });

    await act(async () => cancelledGet.resolve(state(1)));
    expect(result.current.revision).toBe(8);
  });

  it('does not auto-retry a failed GET when the QueryClient default would retry', async () => {
    mockList.mockRejectedValue(
      Object.assign(new Error('server'), { response: { status: 500 } }),
    );
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useWatchlistGroups(), { wrapper });

    await waitFor(() => expect(result.current.errorMessage).not.toBeNull());
    expect(mockList).toHaveBeenCalledTimes(1);
    expect(loadQueryOptions(client)?.retry).toBe(false);
    expect(result.current.revision).toBeNull();
    expect(result.current.isLoading).toBe(false);
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useWatchlistGroups(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockList).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(mockList).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call list() again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useWatchlistGroups(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockList).toHaveBeenCalledTimes(1);
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

    expect(mockList).toHaveBeenCalledTimes(1);
  });

  it('issues list() while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlistGroups(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockList).toHaveBeenCalledTimes(1);
  });

  it('shares one in-flight GET across concurrent observers of the exact key', async () => {
    const pending = createDeferred<WatchlistGroupState>();
    mockList.mockReturnValue(pending.promise);
    const { wrapper } = createWrapper();
    const first = renderHook(() => useWatchlistGroups(), { wrapper });
    const second = renderHook(() => useWatchlistGroups(), { wrapper });

    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(1));
    await act(async () => {
      pending.resolve(state(1));
    });
    await waitFor(() => {
      expect(first.result.current.revision).toBe(1);
      expect(second.result.current.revision).toBe(1);
    });
    expect(mockList).toHaveBeenCalledTimes(1);
  });

  it('does not remove the shared row when one co-mounted observer unmounts', async () => {
    const pending = createDeferred<WatchlistGroupState>();
    mockList.mockReturnValue(pending.promise);
    const { client, wrapper } = createWrapper();
    const first = renderHook(() => useWatchlistGroups(), { wrapper });
    const second = renderHook(() => useWatchlistGroups(), { wrapper });

    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(1));
    first.unmount();
    await flushQueryMicrotasks();

    expect(client.getQueryState(WATCHLIST_GROUPS_QUERY_KEY)).toBeDefined();
    expect(client.getQueryCache()
      .find({ queryKey: WATCHLIST_GROUPS_QUERY_KEY, exact: true })
      ?.getObserversCount()).toBe(1);
    await act(async () => pending.resolve(state(1)));
    await waitFor(() => expect(second.result.current.revision).toBe(1));
    expect(groupsFetchStatus(client)).not.toBe('fetching');
  });

  it('removes the exact groups key on last-observer unmount and ignores a late list()', async () => {
    const pending = createDeferred<WatchlistGroupState>();
    mockList.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    seedSiblingWatchlistQueries(client);
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');
    const { unmount } = renderHook(() => useWatchlistGroups(), { wrapper });

    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(1));
    unmount();
    await flushQueryMicrotasks();

    await act(async () => {
      pending.resolve(state(9));
      await pending.promise.catch(() => undefined);
    });

    expect(client.getQueryState(WATCHLIST_GROUPS_QUERY_KEY)).toBeUndefined();
    expect(client.getQueryData(CODES_KEY)).toEqual(['AAPL']);
    expect(client.getQueryData(SCORES_KEY)).toEqual({ items: [] });
    expect(invalidateSpy).not.toHaveBeenCalled();
    assertNoWatchlistPrefixOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
    assertNoWatchlistPrefixOps(
      removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('returns false from mutations before revision has loaded', async () => {
    const pending = createDeferred<WatchlistGroupState>();
    mockList.mockReturnValue(pending.promise);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlistGroups(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(true));

    let succeeded!: boolean;
    await act(async () => {
      succeeded = await result.current.createGroup('Core');
    });

    expect(succeeded).toBe(false);
    expect(mockCreate).not.toHaveBeenCalled();
    expect(result.current.revision).toBeNull();
  });

  it('does not let a stale in-flight GET overwrite a successful mutation result', async () => {
    const pendingRefresh = createDeferred<WatchlistGroupState>();
    mockList
      .mockResolvedValueOnce(state(1))
      .mockReturnValueOnce(pendingRefresh.promise);
    mockCreate.mockResolvedValue(state(4));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlistGroups(), { wrapper });
    await waitFor(() => expect(result.current.revision).toBe(1));

    act(() => {
      void result.current.refresh();
    });
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(2));

    await act(async () => {
      await result.current.createGroup('Core');
    });
    expect(result.current.revision).toBe(4);
    expect(mockCreate).toHaveBeenCalledWith('Core', 1);

    await act(async () => {
      pendingRefresh.resolve(state(99));
      await pendingRefresh.promise.catch(() => undefined);
    });

    expect(result.current.revision).toBe(4);
    expect(result.current.errorMessage).toBeNull();
  });

  it('updates the exact query after a successful mutation so sibling observers converge without another GET', async () => {
    mockList.mockResolvedValue(state(1));
    mockCreate.mockResolvedValue(state(2));
    const { client, wrapper } = createWrapper();
    seedSiblingWatchlistQueries(client);
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const { result } = renderHook(() => ({
      first: useWatchlistGroups(),
      second: useWatchlistGroups(),
    }), { wrapper });

    await waitFor(() => {
      expect(result.current.first.revision).toBe(1);
      expect(result.current.second.revision).toBe(1);
    });
    expect(mockList).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.first.createGroup('Core');
    });

    expect(mockCreate).toHaveBeenCalledWith('Core', 1);
    expect(mockList).toHaveBeenCalledTimes(1);
    expect(client.getQueryData(WATCHLIST_GROUPS_QUERY_KEY)).toEqual(state(2));
    expect(result.current.first.revision).toBe(2);
    expect(result.current.second.revision).toBe(2);
    expect(result.current.first.errorMessage).toBeNull();
    expect(result.current.second.errorMessage).toBeNull();
    expect(result.current.first.isLoading).toBe(false);
    expect(result.current.second.isLoading).toBe(false);
    expect(client.getQueryData(CODES_KEY)).toEqual(['AAPL']);
    expect(client.getQueryData(SCORES_KEY)).toEqual({ items: [] });
    assertNoWatchlistPrefixOps(
      cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
    );
  });

  it('acquires an action lease synchronously so same-render double submit runs once', async () => {
    const pending = createDeferred<WatchlistGroupState>();
    mockCreate.mockReturnValue(pending.promise);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlistGroups(), { wrapper });
    await waitFor(() => expect(result.current.revision).toBe(1));

    let first!: Promise<boolean>;
    let second!: Promise<boolean>;
    act(() => {
      first = result.current.createGroup('Core');
      second = result.current.createGroup('Duplicate');
    });
    expect(mockCreate).toHaveBeenCalledOnce();
    await expect(second).resolves.toBe(false);
    await act(async () => pending.resolve(state(2)));
    await expect(first).resolves.toBe(true);
    expect(result.current.revision).toBe(2);
  });

  it('does not let an older action response overwrite a newer refresh', async () => {
    const pendingAction = createDeferred<WatchlistGroupState>();
    const pendingRefresh = createDeferred<WatchlistGroupState>();
    mockCreate.mockReturnValue(pendingAction.promise);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlistGroups(), { wrapper });
    await waitFor(() => expect(result.current.revision).toBe(1));

    let action!: Promise<boolean>;
    act(() => { action = result.current.createGroup('Core'); });
    mockList.mockReturnValueOnce(pendingRefresh.promise);
    let refresh!: Promise<boolean>;
    act(() => { refresh = result.current.refresh(); });
    await act(async () => pendingRefresh.resolve(state(3)));
    await expect(refresh).resolves.toBe(true);
    await act(async () => pendingAction.resolve(state(2)));
    await expect(action).resolves.toBe(false);

    expect(result.current.revision).toBe(3);
    expect(result.current.isActioning).toBe(false);
  });

  it('returns false through the public callback when a mutation fails', async () => {
    mockCreate.mockRejectedValue(new Error('create failed'));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlistGroups(), { wrapper });
    await waitFor(() => expect(result.current.revision).toBe(1));

    let succeeded!: boolean;
    await act(async () => {
      succeeded = await result.current.createGroup('Core');
    });

    expect(succeeded).toBe(false);
    expect(result.current.errorMessage).toBeTruthy();
    expect(mockList).toHaveBeenCalledTimes(2);
  });

  it('keeps the original mutation error when recovery list restores revisioned state', async () => {
    mockCreate.mockRejectedValue(apiError('create failed'));
    mockList
      .mockResolvedValueOnce(state(1))
      .mockResolvedValueOnce(state(7));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlistGroups(), { wrapper });
    await waitFor(() => expect(result.current.revision).toBe(1));

    let succeeded!: boolean;
    await act(async () => {
      succeeded = await result.current.createGroup('Core');
    });

    expect(succeeded).toBe(false);
    expect(result.current.revision).toBe(7);
    expect(result.current.errorMessage).toBe('create failed');
    expect(mockList).toHaveBeenCalledTimes(2);
  });

  it('keeps the original mutation error when recovery list also fails', async () => {
    mockCreate.mockRejectedValue(apiError('create failed'));
    mockList
      .mockResolvedValueOnce(state(1))
      .mockRejectedValueOnce(apiError('recovery list failed'));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlistGroups(), { wrapper });
    await waitFor(() => expect(result.current.revision).toBe(1));

    await act(async () => {
      await result.current.createGroup('Core');
    });

    expect(result.current.revision).toBe(1);
    expect(result.current.errorMessage).toBe('create failed');
    expect(result.current.errorMessage).not.toContain('recovery list failed');
  });

  it('restores a deleted group through the revisioned restore API', async () => {
    mockRestore.mockResolvedValue(state(3));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useWatchlistGroups(), { wrapper });
    await waitFor(() => expect(result.current.revision).toBe(1));

    let succeeded!: boolean;
    await act(async () => {
      succeeded = await result.current.restoreGroup({
        groupId: 'growth',
        name: 'Growth',
        memberCodes: ['600519'],
        exclusiveMemberCodes: ['600519'],
        orderedGroupIds: ['default', 'growth'],
      });
    });

    expect(succeeded).toBe(true);
    expect(mockRestore).toHaveBeenCalledWith({
      groupId: 'growth',
      name: 'Growth',
      memberCodes: ['600519'],
      exclusiveMemberCodes: ['600519'],
      orderedGroupIds: ['default', 'growth'],
    }, 1);
    expect(result.current.revision).toBe(3);
  });
});
