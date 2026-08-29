// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { notificationInboxApi } from '../../api/notificationInbox';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { NotificationInboxItem, NotificationInboxPage } from '../../types/notificationInbox';
import {
  NOTIFICATION_CENTER_PAGE_SIZE,
  buildNotificationCenterListQueryKey,
  useNotificationCenterInbox,
} from '../useNotificationCenterInbox';

vi.mock('../../api/notificationInbox', () => ({
  notificationInboxApi: {
    list: vi.fn(),
    markRead: vi.fn(),
    markAllRead: vi.fn(),
    unreadCount: vi.fn(),
  },
}));

const listMock = vi.mocked(notificationInboxApi.list);
const markReadMock = vi.mocked(notificationInboxApi.markRead);
const markAllReadMock = vi.mocked(notificationInboxApi.markAllRead);

const BELL_PREVIEW_KEY = ['notifications', 'unread-preview', 10] as const;

const ITEM: NotificationInboxItem = {
  id: 'v1:analysis_complete:1:1786233600000000',
  kind: 'analysis_complete',
  titleKey: 'analysisCompleteTitle',
  titleParams: { label: '600519' },
  summary: 'hold',
  severity: 'info',
  createdAt: '2026-08-09T00:00:00Z',
  isRead: false,
  href: '/research/analysis?segment=history&recordId=1',
  sourceId: '1',
};

const ITEM_MORE: NotificationInboxItem = {
  ...ITEM,
  id: 'v1:alert_triggered:2:1786233500000000',
  kind: 'alert_triggered',
  titleKey: 'alertTriggeredTitle',
  titleParams: { target: 'MSFT' },
  summary: 'Threshold crossed',
  severity: 'warning',
  createdAt: '2026-08-09T23:58:20Z',
  href: '/signals?tab=history&trigger=2',
  sourceId: '2',
};

function page(overrides: Partial<NotificationInboxPage> = {}): NotificationInboxPage {
  return {
    items: [ITEM],
    page: 1,
    pageSize: NOTIFICATION_CENTER_PAGE_SIZE,
    total: 1,
    unreadTotal: 1,
    hasMore: false,
    sourceStatuses: [],
    retentionDays: 90,
    maxItems: 500,
    ...overrides,
  };
}

function createWrapper(client?: QueryClient) {
  const queryClient = client ?? createAppQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return { client: queryClient, wrapper: Wrapper };
}

function centerOptions(client: QueryClient, queryKey: readonly unknown[] = buildNotificationCenterListQueryKey('', false)) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertNoNotificationsPrefixOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'notifications' && key.length === 1).toBe(false);
    expect(key.slice(0, 2)).not.toEqual(['notifications', 'unread-preview']);
    if (key[0] === 'notifications' && key[1] === 'center') {
      expect(filters?.exact).toBe(true);
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

describe('useNotificationCenterInbox', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    listMock.mockResolvedValue(page());
    markReadMock.mockResolvedValue({ markedCount: 1, unreadTotal: 0 });
    markAllReadMock.mockResolvedValue({ markedCount: 1, unreadTotal: 0 });
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

  it('does not auto-retry a 5xx list when the QueryClient default would retry', async () => {
    listMock.mockRejectedValue(Object.assign(new Error('server'), { response: { status: 500 } }));
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useNotificationCenterInbox(), { wrapper });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(centerOptions(client)?.retry).toBe(false);
    expect(result.current.items).toEqual([]);
    expect(result.current.pageData).toBeNull();
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useNotificationCenterInbox(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(centerOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(centerOptions(client)?.retry).toBe(false);
    expect(centerOptions(client)?.staleTime).toBe(0);
    expect(listMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(listMock).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call list again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useNotificationCenterInbox(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(centerOptions(client)?.refetchInterval).toBeUndefined();

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

    expect(listMock).toHaveBeenCalledTimes(1);
  });

  it('removes exact center keys on unmount, leaves fetchStatus idle, and ignores a late list failure', async () => {
    const pending = createDeferred<NotificationInboxPage>();
    listMock.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const headKey = buildNotificationCenterListQueryKey('', false);
    const { result, unmount } = renderHook(() => useNotificationCenterInbox(), { wrapper });

    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(Object.assign(new Error('server'), { response: { status: 500 } }));
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.error).toBeNull();
    expect(client.getQueryState(headKey)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['notifications', 'center'] })).toHaveLength(0);
    expect(queryFetchStatus(client, headKey)).toBeUndefined();
  });

  it('recovers fetchStatus to idle after a same-key silent cancel is followed by a successor fetch', async () => {
    const first = createDeferred<NotificationInboxPage>();
    const successor = createDeferred<NotificationInboxPage>();
    listMock
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(successor.promise);
    const { client, wrapper } = createWrapper();
    const headKey = buildNotificationCenterListQueryKey('', false);
    const { result } = renderHook(() => useNotificationCenterInbox(), { wrapper });

    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load('refresh');
    });
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2));

    await act(async () => {
      first.resolve(page({ items: [ITEM], unreadTotal: 9 }));
      successor.resolve(page({ unreadTotal: 1 }));
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.refreshing).toBe(false);
    expect(result.current.pageData?.unreadTotal).toBe(1);
    expect(queryFetchStatus(client, headKey)).toBe('idle');
    expect(result.current.error).toBeNull();
  });

  it('exact-removes an abandoned head key on filter change and does not write the unread-bell preview key', async () => {
    const alertPage = page({
      items: [ITEM_MORE],
      unreadTotal: 1,
    });
    listMock
      .mockResolvedValueOnce(page())
      .mockResolvedValueOnce(alertPage);
    const { client, wrapper } = createWrapper();
    client.setQueryData(BELL_PREVIEW_KEY, { sentinel: true, unreadCount: 4 });
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const { result } = renderHook(() => useNotificationCenterInbox(), { wrapper });

    await waitFor(() => expect(result.current.items).toEqual([ITEM]));
    const abandonedHead = buildNotificationCenterListQueryKey('', false);
    expect(client.getQueryState(abandonedHead)).toBeDefined();

    act(() => {
      result.current.setKind('alert_triggered');
    });

    await waitFor(() => expect(result.current.items[0]?.kind).toBe('alert_triggered'));
    expect(client.getQueryState(abandonedHead)).toBeUndefined();
    expect(client.getQueryData(BELL_PREVIEW_KEY)).toEqual({ sentinel: true, unreadCount: 4 });
    expect(queryFetchStatus(client, BELL_PREVIEW_KEY)).not.toBe('fetching');
    assertNoNotificationsPrefixOps(cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
    assertNoNotificationsPrefixOps(removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
    expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ kind: 'alert_triggered' }));
  });

  it('does not setError when list settles as CancelledError', async () => {
    listMock.mockRejectedValue(new CancelledError({ silent: true, revert: false }));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useNotificationCenterInbox(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.items).toEqual([]);
    expect(result.current.pageData).toBeNull();
  });

  it('issues list while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useNotificationCenterInbox(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(centerOptions(client)?.networkMode).toBe('always');
    expect(result.current.items).toEqual([ITEM]);
  });

  it('uses a distinct load-more cursor key from head and removes the abandoned more key on filter change', async () => {
    listMock
      .mockResolvedValueOnce(page({
        hasMore: true,
        nextCursor: 'cursor-1',
        unreadTotal: 2,
      }))
      .mockResolvedValueOnce(page({
        items: [ITEM_MORE],
        hasMore: false,
        unreadTotal: 3,
      }))
      .mockResolvedValueOnce(page({
        items: [ITEM_MORE],
        unreadTotal: 1,
      }));
    const { client, wrapper } = createWrapper();
    const headKey = buildNotificationCenterListQueryKey('', false);
    const moreKey = buildNotificationCenterListQueryKey('', false, 'cursor-1');
    expect(headKey).toEqual(['notifications', 'center', 'list', 'all', 'all', 50, 'head']);
    expect(moreKey).toEqual(['notifications', 'center', 'list', 'all', 'all', 50, 'cursor-1']);
    expect(moreKey[moreKey.length - 1]).not.toBe('head');

    const { result } = renderHook(() => useNotificationCenterInbox(), { wrapper });
    await waitFor(() => expect(result.current.pageData?.nextCursor).toBe('cursor-1'));

    await act(async () => {
      await result.current.load('more', result.current.pageData?.nextCursor ?? undefined);
    });

    expect(result.current.items.map((item) => item.id)).toEqual([ITEM.id, ITEM_MORE.id]);
    expect(result.current.pageData?.unreadTotal).toBe(3);
    expect(client.getQueryState(headKey)).toBeDefined();
    expect(client.getQueryState(moreKey)).toBeDefined();
    expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({
      cursor: 'cursor-1',
      page: 1,
      pageSize: 50,
    }));

    act(() => {
      result.current.setReadFilter('unread');
    });

    await waitFor(() => {
      expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ unreadOnly: true }));
    });
    expect(client.getQueryState(moreKey)).toBeUndefined();
    expect(client.getQueryState(headKey)).toBeUndefined();
  });
});
