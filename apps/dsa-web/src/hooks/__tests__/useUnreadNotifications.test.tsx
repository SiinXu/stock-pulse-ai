// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClient, QueryClientProvider, onlineManager } from '@tanstack/react-query';
import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import { StrictMode, type ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { notificationInboxApi } from '../../api/notificationInbox';
import { createDeferred } from '../../test-utils';
import type {
  NotificationInboxItem,
  NotificationInboxPage,
  NotificationInboxUnreadCount,
} from '../../types/notificationInbox';
import { useUnreadNotifications } from '../useUnreadNotifications';

const DEFAULT_POLL_MS = 60_000;
const DEFAULT_PAGE_SIZE = 10;

function previewQueryKey(pageSize: number) {
  return ['notifications', 'unread-preview', pageSize] as const;
}

vi.mock('../../api/notificationInbox', () => ({
  notificationInboxApi: {
    list: vi.fn(),
    unreadCount: vi.fn(),
    markAllRead: vi.fn(),
  },
}));

const listMock = vi.mocked(notificationInboxApi.list);
const countMock = vi.mocked(notificationInboxApi.unreadCount);
const markAllMock = vi.mocked(notificationInboxApi.markAllRead);

const ITEM: NotificationInboxItem = {
  id: 'v1:analysis_complete:1:1786320000000000',
  kind: 'analysis_complete',
  titleKey: 'analysisCompleteTitle',
  titleParams: { label: 'AAPL' },
  summary: 'Hold',
  severity: 'info',
  createdAt: '2026-08-10T00:00:00Z',
  isRead: false,
  href: '/research/analysis?segment=history&recordId=1',
  sourceId: '1',
};

const ITEM_B: NotificationInboxItem = {
  ...ITEM,
  id: 'v1:analysis_complete:2:1786320000000001',
  titleParams: { label: 'MSFT' },
};

function page(overrides: Partial<NotificationInboxPage> = {}): NotificationInboxPage {
  return {
    items: [ITEM],
    page: 1,
    pageSize: 10,
    total: 1,
    unreadTotal: 1,
    hasMore: false,
    sourceStatuses: [
      { source: 'analysis', available: true, itemCount: 1 },
      { source: 'alerts', available: true, itemCount: 0 },
      { source: 'scheduled_tasks', available: true, itemCount: 0 },
      { source: 'decision_signals', available: true, itemCount: 0 },
    ],
    retentionDays: 90,
    maxItems: 500,
    ...overrides,
  };
}

function count(overrides: Partial<NotificationInboxUnreadCount> = {}): NotificationInboxUnreadCount {
  return {
    unreadTotal: 1,
    sourceStatuses: page().sourceStatuses,
    retentionDays: 90,
    maxItems: 500,
    ...overrides,
  };
}

function createWrapper(client?: QueryClient) {
  const queryClient = client ?? new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return { client: queryClient, wrapper: Wrapper };
}

function queryOptions(client: QueryClient, pageSize = DEFAULT_PAGE_SIZE) {
  const query = client.getQueryCache().find({
    queryKey: previewQueryKey(pageSize),
  });
  return query?.options as Record<string, unknown> | undefined;
}

/** Flush microtasks so TanStack Query's initial queryFn can settle under fake timers. */
async function flushQueryMicrotasks(rounds = 2) {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
  }
}

type InboxPageDeferred = ReturnType<typeof createDeferred<NotificationInboxPage>>;
type InboxCountDeferred = ReturnType<typeof createDeferred<NotificationInboxUnreadCount>>;

function mockDeferredInbox() {
  const lists: InboxPageDeferred[] = [];
  const counts: InboxCountDeferred[] = [];
  listMock.mockImplementation(() => {
    const deferred = createDeferred<NotificationInboxPage>();
    lists.push(deferred);
    return deferred.promise;
  });
  countMock.mockImplementation(() => {
    const deferred = createDeferred<NotificationInboxUnreadCount>();
    counts.push(deferred);
    return deferred.promise;
  });
  return { lists, counts };
}

async function resolvePreviewPair(
  listDeferred: InboxPageDeferred,
  countDeferred: InboxCountDeferred,
  listValue: NotificationInboxPage,
  countValue: NotificationInboxUnreadCount,
) {
  await act(async () => {
    listDeferred.resolve(listValue);
    countDeferred.resolve(countValue);
    await listDeferred.promise;
    await countDeferred.promise;
  });
}

describe('useUnreadNotifications', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    onlineManager.setOnline(true);
    listMock.mockResolvedValue(page());
    countMock.mockResolvedValue(count());
    markAllMock.mockResolvedValue({ markedCount: 1, unreadTotal: 0 });
  });

  afterEach(() => {
    vi.useRealTimers();
    onlineManager.setOnline(true);
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    });
  });

  it('uses the inbox list and unread-count endpoints as one server authority', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(listMock).toHaveBeenCalledWith({ pageSize: 10 });
    expect(countMock).toHaveBeenCalledWith();
    expect(result.current.items).toEqual([ITEM]);
    expect(result.current.unreadCount).toBe(1);
    expect(window.localStorage.length).toBe(0);
  });

  it('marks the same server-side occurrences read when the Bell opens', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    await waitFor(() => expect(result.current.unreadCount).toBe(1));

    await act(async () => {
      await result.current.markAllSeen();
    });

    expect(markAllMock).toHaveBeenCalledWith();
    expect(result.current.unreadCount).toBe(0);
    expect(result.current.items[0]?.isRead).toBe(true);
    expect(result.current.markFailed).toBe(false);
  });

  it('keeps the count available when the preview list fails', async () => {
    listMock.mockRejectedValue(new Error('list down'));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.unreadCount).toBe(1);
    expect(result.current.listFailed).toBe(true);
    expect(result.current.countFailed).toBe(false);
    expect(result.current.hasPartialError).toBe(true);
    expect(result.current.hasError).toBe(false);
  });

  it('surfaces bounded source degradation returned by the inbox API', async () => {
    const degraded = page({
      sourceStatuses: [
        { source: 'analysis', available: true, itemCount: 1 },
        { source: 'alerts', available: false, itemCount: 0, errorCode: 'alerts_unavailable' },
      ],
    });
    listMock.mockResolvedValue(degraded);
    countMock.mockResolvedValue(count({ sourceStatuses: degraded.sourceStatuses }));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.hasPartialError).toBe(true);
    expect(result.current.hasError).toBe(false);
  });

  it('reports a hard error only when both inbox reads fail', async () => {
    listMock.mockRejectedValue(new Error('list down'));
    countMock.mockRejectedValue(new Error('count down'));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.hasError).toBe(true);
    expect(result.current.hasPartialError).toBe(false);
  });

  it('schedules the default 60s poll without window-focus refetch', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useUnreadNotifications(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    const options = queryOptions(client);
    expect(options?.retry).toBe(false);
    expect(options?.refetchOnWindowFocus).toBe(false);
    expect(options?.refetchInterval).toBe(DEFAULT_POLL_MS);
    expect(options?.refetchIntervalInBackground).toBe(true);
    expect(options?.networkMode).toBe('always');
    expect(options?.staleTime).toBe(0);
    expect(options?.queryKey).toEqual(previewQueryKey(DEFAULT_PAGE_SIZE));
  });

  it('keeps interval ticks while the document is hidden', async () => {
    vi.useFakeTimers();
    const { wrapper } = createWrapper();
    renderHook(() => useUnreadNotifications(), { wrapper });
    await flushQueryMicrotasks();
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(countMock).toHaveBeenCalledTimes(1);

    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEFAULT_POLL_MS);
    });
    await flushQueryMicrotasks();

    expect(listMock).toHaveBeenCalledTimes(2);
    expect(countMock).toHaveBeenCalledTimes(2);
  });

  it('does not refetch when the window regains focus', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(listMock).toHaveBeenCalledTimes(1);
    expect(countMock).toHaveBeenCalledTimes(1);
  });

  it('returns empty non-loading state when disabled and does not fetch', () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useUnreadNotifications({ enabled: false, pollMs: 0 }),
      { wrapper },
    );

    expect(result.current.items).toEqual([]);
    expect(result.current.unreadCount).toBe(0);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.hasError).toBe(false);
    expect(result.current.hasPartialError).toBe(false);
    expect(result.current.listFailed).toBe(false);
    expect(result.current.countFailed).toBe(false);
    expect(listMock).not.toHaveBeenCalled();
    expect(countMock).not.toHaveBeenCalled();
  });

  it('keeps refresh void-facing and waits for both settlements on manual refresh', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const listDeferred = createDeferred<NotificationInboxPage>();
    const countDeferred = createDeferred<NotificationInboxUnreadCount>();
    listMock.mockReturnValue(listDeferred.promise);
    countMock.mockReturnValue(countDeferred.promise);

    let refreshResult: unknown = 'unset';
    act(() => {
      refreshResult = result.current.refresh();
    });
    expect(refreshResult).toBeUndefined();
    await waitFor(() => expect(result.current.isLoading).toBe(true));
    expect(result.current.items).toEqual([ITEM]);
    expect(result.current.unreadCount).toBe(1);

    await act(async () => {
      listDeferred.resolve(page({ items: [ITEM_B] }));
      await listDeferred.promise;
    });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.items).toEqual([ITEM]);

    await act(async () => {
      countDeferred.resolve(count({ unreadTotal: 3 }));
      await countDeferred.promise;
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.items).toEqual([ITEM_B]);
    expect(result.current.unreadCount).toBe(3);
  });

  it('keeps last-good items when a later list refresh fails', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    await waitFor(() => expect(result.current.items).toEqual([ITEM]));

    listMock.mockRejectedValue(new Error('list down'));
    countMock.mockResolvedValue(count({ unreadTotal: 7 }));

    act(() => {
      result.current.refresh();
    });
    await waitFor(() => expect(result.current.listFailed).toBe(true));

    expect(result.current.items).toEqual([ITEM]);
    expect(result.current.unreadCount).toBe(7);
    expect(result.current.countFailed).toBe(false);
    expect(result.current.hasPartialError).toBe(true);
    expect(result.current.hasError).toBe(false);
  });

  it('keeps last-good values on both sides when a later refresh fails completely', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    await waitFor(() => expect(result.current.unreadCount).toBe(1));

    listMock.mockRejectedValue(new Error('list down'));
    countMock.mockRejectedValue(new Error('count down'));
    act(() => {
      result.current.refresh();
    });
    await waitFor(() => expect(result.current.hasError).toBe(true));

    expect(result.current.items).toEqual([ITEM]);
    expect(result.current.unreadCount).toBe(1);
    expect(result.current.hasPartialError).toBe(false);
  });

  it('does not let a slower overlapping generation overwrite a newer preview', async () => {
    const { wrapper } = createWrapper();
    const firstList = createDeferred<NotificationInboxPage>();
    const firstCount = createDeferred<NotificationInboxUnreadCount>();
    listMock.mockReturnValue(firstList.promise);
    countMock.mockReturnValue(firstCount.promise);

    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    await act(async () => {
      firstList.resolve(page());
      firstCount.resolve(count());
      await firstList.promise;
      await firstCount.promise;
    });
    await waitFor(() => expect(result.current.unreadCount).toBe(1));

    const staleList = createDeferred<NotificationInboxPage>();
    const staleCount = createDeferred<NotificationInboxUnreadCount>();
    listMock.mockReturnValue(staleList.promise);
    countMock.mockReturnValue(staleCount.promise);
    act(() => {
      result.current.refresh();
    });
    await waitFor(() => expect(result.current.isLoading).toBe(true));

    const freshList = createDeferred<NotificationInboxPage>();
    const freshCount = createDeferred<NotificationInboxUnreadCount>();
    listMock.mockReturnValue(freshList.promise);
    countMock.mockReturnValue(freshCount.promise);
    act(() => {
      result.current.refresh();
    });

    await act(async () => {
      staleList.resolve(page({ items: [ITEM], unreadTotal: 99 }));
      staleCount.resolve(count({ unreadTotal: 99 }));
      await staleList.promise;
      await staleCount.promise;
    });
    await waitFor(() => expect(result.current.isLoading).toBe(true));
    expect(result.current.unreadCount).toBe(1);
    expect(result.current.items).toEqual([ITEM]);

    await act(async () => {
      freshList.resolve(page({ items: [ITEM_B] }));
      freshCount.resolve(count({ unreadTotal: 2 }));
      await freshList.promise;
      await freshCount.promise;
    });
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
      expect(result.current.unreadCount).toBe(2);
    });
    expect(result.current.items).toEqual([ITEM_B]);
    expect(result.current.unreadCount).toBe(2);
  });

  it('rethrows mark-all failures without changing last-good preview state', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    await waitFor(() => expect(result.current.unreadCount).toBe(1));

    markAllMock.mockRejectedValue(new Error('mark down'));
    await act(async () => {
      await expect(result.current.markAllSeen()).rejects.toThrow('mark down');
    });

    expect(result.current.markFailed).toBe(true);
    expect(result.current.hasPartialError).toBe(true);
    expect(result.current.unreadCount).toBe(1);
    expect(result.current.items[0]?.isRead).toBe(false);
  });

  it('misses cache on remount instead of showing a hidden preview snapshot', async () => {
    const { client, wrapper } = createWrapper();
    const first = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    await waitFor(() => expect(first.result.current.items).toEqual([ITEM]));
    const callsAfterFirst = listMock.mock.calls.length;

    first.unmount();
    expect(client.getQueryData(previewQueryKey(10))).toBeUndefined();

    const second = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    expect(second.result.current.items).toEqual([]);
    expect(second.result.current.isLoading).toBe(true);

    await waitFor(() => expect(second.result.current.items).toEqual([ITEM]));
    expect(listMock.mock.calls.length).toBeGreaterThan(callsAfterFirst);
    expect(countMock.mock.calls.length).toBeGreaterThan(callsAfterFirst);
  });

  it('includes pageSize in the query key and list transport argument', async () => {
    const { wrapper, client } = createWrapper();
    const { result, rerender } = renderHook(
      ({ pageSize }: { pageSize: number }) => useUnreadNotifications({ pollMs: 0, pageSize }),
      { wrapper, initialProps: { pageSize: 10 } },
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listMock).toHaveBeenCalledWith({ pageSize: 10 });
    expect(queryOptions(client, 10)?.queryKey).toEqual(previewQueryKey(10));

    rerender({ pageSize: 5 });
    await waitFor(() => expect(listMock).toHaveBeenCalledWith({ pageSize: 5 }));
    expect(queryOptions(client, 5)?.queryKey).toEqual(previewQueryKey(5));
    expect(queryOptions(client, 5)?.queryKey).toHaveLength(3);
  });

  it('still fetches while Query reports the browser offline', async () => {
    onlineManager.setOnline(false);
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useUnreadNotifications({ pollMs: 0 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(listMock).toHaveBeenCalledWith({ pageSize: 10 });
    expect(countMock).toHaveBeenCalledWith();
    expect(result.current.items).toEqual([ITEM]);
  });

  it('does not start a poll interval when pollMs is 0', async () => {
    vi.useFakeTimers();
    const { wrapper } = createWrapper();
    renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    await flushQueryMicrotasks();
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(countMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DEFAULT_POLL_MS);
    });
    await flushQueryMicrotasks();

    expect(listMock).toHaveBeenCalledTimes(1);
    expect(countMock).toHaveBeenCalledTimes(1);
  });

  it('keeps last-good unread count when a later count refresh fails', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    await waitFor(() => expect(result.current.unreadCount).toBe(1));

    listMock.mockResolvedValue(page({ items: [ITEM_B] }));
    countMock.mockRejectedValue(new Error('count down'));
    act(() => {
      result.current.refresh();
    });
    await waitFor(() => expect(result.current.countFailed).toBe(true));

    expect(result.current.unreadCount).toBe(1);
    expect(result.current.items).toEqual([ITEM_B]);
    expect(result.current.listFailed).toBe(false);
    expect(result.current.hasPartialError).toBe(true);
    expect(result.current.hasError).toBe(false);
  });

  it('does not let a stale pageSize completion replace the active preview', async () => {
    const staleList = createDeferred<NotificationInboxPage>();
    const staleCount = createDeferred<NotificationInboxUnreadCount>();
    const freshList = createDeferred<NotificationInboxPage>();
    const freshCount = createDeferred<NotificationInboxUnreadCount>();
    const countDeferreds = [staleCount, freshCount];
    let countIndex = 0;

    listMock.mockImplementation(async (query = {}) => (
      query.pageSize === 5 ? freshList.promise : staleList.promise
    ));
    countMock.mockImplementation(() => countDeferreds[countIndex++]!.promise);

    const { wrapper, client } = createWrapper();
    const { result, rerender } = renderHook(
      ({ pageSize }: { pageSize: number }) => useUnreadNotifications({ pollMs: 0, pageSize }),
      { wrapper, initialProps: { pageSize: 10 } },
    );

    rerender({ pageSize: 5 });

    await act(async () => {
      staleList.resolve(page({ items: [ITEM], unreadTotal: 99 }));
      staleCount.resolve(count({ unreadTotal: 99 }));
      await staleList.promise;
      await staleCount.promise;
    });
    await waitFor(() => expect(listMock).toHaveBeenCalledWith({ pageSize: 5 }));
    expect(result.current.unreadCount).toBe(0);
    expect(result.current.items).toEqual([]);
    expect(client.getQueryData(previewQueryKey(10))).toBeUndefined();

    await act(async () => {
      freshList.resolve(page({ items: [ITEM_B], pageSize: 5 }));
      freshCount.resolve(count({ unreadTotal: 2 }));
      await freshList.promise;
      await freshCount.promise;
    });
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
      expect(result.current.unreadCount).toBe(2);
    });
    expect(result.current.items).toEqual([ITEM_B]);
    expect(listMock).toHaveBeenCalledWith({ pageSize: 5 });
    expect(client.getQueryData(previewQueryKey(10))).toBeUndefined();
  });

  it('keeps default gcTime and still misses cache on remount because cleanup removes the row', async () => {
    const { client, wrapper } = createWrapper();
    const first = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    await waitFor(() => expect(first.result.current.items).toEqual([ITEM]));

    const options = queryOptions(client);
    expect(options?.staleTime).toBe(0);
    expect(options?.gcTime ?? 5 * 60 * 1000).toBeGreaterThan(0);

    first.unmount();
    expect(client.getQueryData(previewQueryKey(10))).toBeUndefined();

    const second = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    expect(second.result.current.items).toEqual([]);
    expect(second.result.current.isLoading).toBe(true);
    await waitFor(() => expect(second.result.current.items).toEqual([ITEM]));
  });

  it('starts a paired fetch when enabled flips from false to true', async () => {
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useUnreadNotifications({ pollMs: 0, enabled }),
      { wrapper, initialProps: { enabled: false } },
    );

    expect(result.current.isLoading).toBe(false);
    expect(listMock).not.toHaveBeenCalled();
    expect(countMock).not.toHaveBeenCalled();

    rerender({ enabled: true });
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
      expect(result.current.unreadCount).toBe(1);
    });
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(countMock).toHaveBeenCalledTimes(1);
    expect(result.current.items).toEqual([ITEM]);
  });

  it('discards an initial in-flight fetch on disable and fetches fresh on re-enable', async () => {
    const { lists, counts } = mockDeferredInbox();
    const { client, wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useUnreadNotifications({ pollMs: 0, enabled }),
      { wrapper, initialProps: { enabled: true } },
    );

    await waitFor(() => expect(lists).toHaveLength(1));
    rerender({ enabled: false });
    expect(result.current.items).toEqual([]);
    expect(result.current.unreadCount).toBe(0);
    expect(result.current.isLoading).toBe(false);

    await resolvePreviewPair(
      lists[0]!,
      counts[0]!,
      page({ items: [ITEM_B] }),
      count({ unreadTotal: 9 }),
    );
    expect(client.getQueryData(previewQueryKey(10))).toBeUndefined();
    expect(result.current.items).toEqual([]);
    expect(result.current.unreadCount).toBe(0);
    expect(result.current.isLoading).toBe(false);

    rerender({ enabled: true });
    expect(result.current.items).toEqual([]);
    expect(result.current.unreadCount).toBe(0);
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(lists).toHaveLength(2));

    await resolvePreviewPair(lists[1]!, counts[1]!, page(), count());
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
      expect(result.current.unreadCount).toBe(1);
    });
    expect(result.current.items).toEqual([ITEM]);
  });

  it('discards a manual in-flight fetch on disable and fetches fresh on re-enable', async () => {
    const { wrapper, client } = createWrapper();
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useUnreadNotifications({ pollMs: 0, enabled }),
      { wrapper, initialProps: { enabled: true } },
    );
    await waitFor(() => expect(result.current.unreadCount).toBe(1));

    const { lists, counts } = mockDeferredInbox();
    act(() => {
      result.current.refresh();
    });
    await waitFor(() => expect(result.current.isLoading).toBe(true));
    expect(lists).toHaveLength(1);

    rerender({ enabled: false });
    expect(result.current.items).toEqual([]);
    expect(result.current.isLoading).toBe(false);

    await resolvePreviewPair(
      lists[0]!,
      counts[0]!,
      page({ items: [ITEM_B] }),
      count({ unreadTotal: 9 }),
    );
    expect(client.getQueryData(previewQueryKey(10))).toBeUndefined();

    rerender({ enabled: true });
    expect(result.current.unreadCount).toBe(0);
    expect(result.current.items).toEqual([]);
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(lists).toHaveLength(2));

    await resolvePreviewPair(lists[1]!, counts[1]!, page(), count());
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
      expect(result.current.unreadCount).toBe(1);
    });
    expect(result.current.items).toEqual([ITEM]);
  });

  it('discards a background in-flight fetch on disable and fetches fresh on re-enable', async () => {
    const { lists, counts } = mockDeferredInbox();
    const { client, wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) =>
        useUnreadNotifications({ pollMs: 50, enabled }),
      { wrapper, initialProps: { enabled: true } },
    );

    await waitFor(() => expect(lists).toHaveLength(1));
    await resolvePreviewPair(lists[0]!, counts[0]!, page(), count());
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
      expect(result.current.unreadCount).toBe(1);
    });

    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });

    await waitFor(() => expect(lists.length).toBeGreaterThanOrEqual(2));
    const inflightIndex = lists.length - 1;
    expect(result.current.isLoading).toBe(true);

    rerender({ enabled: false });
    expect(result.current.items).toEqual([]);
    expect(result.current.isLoading).toBe(false);

    for (let index = 1; index <= inflightIndex; index += 1) {
      await resolvePreviewPair(
        lists[index]!,
        counts[index]!,
        page({ items: [ITEM_B] }),
        count({ unreadTotal: 9 }),
      );
    }
    expect(client.getQueryData(previewQueryKey(10))).toBeUndefined();

    rerender({ enabled: true });
    expect(result.current.items).toEqual([]);
    expect(result.current.unreadCount).toBe(0);
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(lists.length).toBeGreaterThan(inflightIndex));

    const freshIndex = lists.length - 1;
    await resolvePreviewPair(lists[freshIndex]!, counts[freshIndex]!, page(), count());
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
      expect(result.current.unreadCount).toBe(1);
    });
    expect(result.current.items).toEqual([ITEM]);
  });

  it('starts a new paired schedule when refresh runs during the initial pending fetch', async () => {
    const { lists, counts } = mockDeferredInbox();
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });

    await waitFor(() => expect(lists).toHaveLength(1));
    expect(counts).toHaveLength(1);

    act(() => {
      result.current.refresh();
    });
    await waitFor(() => expect(lists).toHaveLength(2));
    expect(counts).toHaveLength(2);
    expect(result.current.isLoading).toBe(true);

    await resolvePreviewPair(
      lists[0]!,
      counts[0]!,
      page({ items: [ITEM], unreadTotal: 99 }),
      count({ unreadTotal: 99 }),
    );
    await waitFor(() => expect(result.current.isLoading).toBe(true));
    expect(result.current.unreadCount).toBe(0);
    expect(result.current.items).toEqual([]);

    await resolvePreviewPair(
      lists[1]!,
      counts[1]!,
      page({ items: [ITEM_B] }),
      count({ unreadTotal: 2 }),
    );
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
      expect(result.current.unreadCount).toBe(2);
    });
    expect(result.current.items).toEqual([ITEM_B]);
    expect(listMock).toHaveBeenCalledTimes(2);
    expect(countMock).toHaveBeenCalledTimes(2);
  });

  it('keeps the latest pageSize generation across a rapid 10 to 5 to 10 change', async () => {
    const { lists, counts } = mockDeferredInbox();
    const { client, wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ pageSize }: { pageSize: number }) => useUnreadNotifications({ pollMs: 0, pageSize }),
      { wrapper, initialProps: { pageSize: 10 } },
    );

    await waitFor(() => expect(listMock).toHaveBeenCalledWith({ pageSize: 10 }));
    rerender({ pageSize: 5 });
    await waitFor(() => expect(listMock).toHaveBeenCalledWith({ pageSize: 5 }));
    rerender({ pageSize: 10 });
    await waitFor(() => {
      expect(listMock.mock.calls.filter((call) => call[0]?.pageSize === 10)).toHaveLength(2);
    });
    expect(lists).toHaveLength(3);
    expect(counts).toHaveLength(3);

    await resolvePreviewPair(
      lists[0]!,
      counts[0]!,
      page({ items: [ITEM], unreadTotal: 99 }),
      count({ unreadTotal: 99 }),
    );
    await resolvePreviewPair(
      lists[1]!,
      counts[1]!,
      page({ items: [ITEM_B], pageSize: 5, unreadTotal: 7 }),
      count({ unreadTotal: 7 }),
    );
    await waitFor(() => expect(result.current.isLoading).toBe(true));
    expect(result.current.unreadCount).toBe(0);
    expect(result.current.items).toEqual([]);
    expect(client.getQueryData(previewQueryKey(5))).toBeUndefined();

    await resolvePreviewPair(
      lists[2]!,
      counts[2]!,
      page({ items: [ITEM_B] }),
      count({ unreadTotal: 2 }),
    );
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
      expect(result.current.unreadCount).toBe(2);
    });
    expect(result.current.items).toEqual([ITEM_B]);
    expect(client.getQueryData(previewQueryKey(5))).toBeUndefined();
  });

  it('discards an in-flight generation when StrictMode remounts', async () => {
    const { lists, counts } = mockDeferredInbox();
    const { client } = createWrapper();

    function Probe() {
      const state = useUnreadNotifications({ pollMs: 0 });
      return (
        <div
          data-testid="unread-preview"
          data-count={String(state.unreadCount)}
          data-loading={state.isLoading ? 'true' : 'false'}
        />
      );
    }

    render(
      <StrictMode>
        <QueryClientProvider client={client}>
          <Probe />
        </QueryClientProvider>
      </StrictMode>,
    );

    await waitFor(() => expect(lists.length).toBeGreaterThanOrEqual(2));
    expect(counts.length).toBe(lists.length);

    const lastIndex = lists.length - 1;
    for (let index = 0; index < lastIndex; index += 1) {
      await resolvePreviewPair(
        lists[index]!,
        counts[index]!,
        page({ items: [ITEM], unreadTotal: 99 }),
        count({ unreadTotal: 99 }),
      );
    }
    await waitFor(() => expect(screen.getByTestId('unread-preview')).toHaveAttribute('data-loading', 'true'));
    expect(screen.getByTestId('unread-preview')).toHaveAttribute('data-count', '0');
    expect(client.getQueryData(previewQueryKey(10))).toBeUndefined();

    await resolvePreviewPair(
      lists[lastIndex]!,
      counts[lastIndex]!,
      page({ items: [ITEM_B] }),
      count({ unreadTotal: 2 }),
    );
    await waitFor(() => {
      expect(screen.getByTestId('unread-preview')).toHaveAttribute('data-loading', 'false');
      expect(screen.getByTestId('unread-preview')).toHaveAttribute('data-count', '2');
    });
    expect(client.getQueryData(previewQueryKey(10))).toMatchObject({ unreadCount: 2 });
  });

  it('does not write cache when unmounted while both inbox reads are pending', async () => {
    const { lists, counts } = mockDeferredInbox();
    const { client, wrapper } = createWrapper();
    const { unmount } = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });

    await waitFor(() => expect(lists).toHaveLength(1));
    unmount();
    expect(client.getQueryData(previewQueryKey(10))).toBeUndefined();

    await resolvePreviewPair(
      lists[0]!,
      counts[0]!,
      page({ items: [ITEM_B] }),
      count({ unreadTotal: 9 }),
    );
    expect(client.getQueryData(previewQueryKey(10))).toBeUndefined();
  });

  it('clears markFailed after a later successful markAllSeen and calls markAllRead once per attempt', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    await waitFor(() => expect(result.current.unreadCount).toBe(1));

    markAllMock.mockRejectedValueOnce(new Error('mark down'));
    await act(async () => {
      await expect(result.current.markAllSeen()).rejects.toThrow('mark down');
    });
    expect(result.current.markFailed).toBe(true);
    expect(markAllMock).toHaveBeenCalledTimes(1);

    markAllMock.mockResolvedValueOnce({ markedCount: 1, unreadTotal: 0 });
    await act(async () => {
      await result.current.markAllSeen();
    });
    expect(result.current.markFailed).toBe(false);
    expect(result.current.unreadCount).toBe(0);
    expect(result.current.items[0]?.isRead).toBe(true);
    expect(markAllMock).toHaveBeenCalledTimes(2);
  });

  it('keeps a concurrent markAllSeen result when the overlapping preview generation fails', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }), { wrapper });
    await waitFor(() => expect(result.current.unreadCount).toBe(1));

    const { lists, counts } = mockDeferredInbox();
    act(() => {
      result.current.refresh();
    });
    await waitFor(() => expect(result.current.isLoading).toBe(true));

    const markDeferred = createDeferred<{ markedCount: number; unreadTotal: number }>();
    markAllMock.mockReturnValue(markDeferred.promise);
    const markPromise = result.current.markAllSeen();

    await act(async () => {
      markDeferred.resolve({ markedCount: 1, unreadTotal: 0 });
      await markPromise;
    });
    expect(result.current.items[0]?.isRead).toBe(true);
    expect(result.current.unreadCount).toBe(0);

    await act(async () => {
      lists[0]!.reject(new Error('list down'));
      counts[0]!.reject(new Error('count down'));
    });
    await waitFor(() => expect(result.current.hasError).toBe(true));
    expect(result.current.items[0]?.isRead).toBe(true);
    expect(result.current.unreadCount).toBe(0);
  });
});
