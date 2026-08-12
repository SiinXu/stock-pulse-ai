// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { notificationInboxApi } from '../../api/notificationInbox';
import type {
  NotificationInboxItem,
  NotificationInboxPage,
  NotificationInboxUnreadCount,
} from '../../types/notificationInbox';
import { useUnreadNotifications } from '../useUnreadNotifications';

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

describe('useUnreadNotifications', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    listMock.mockResolvedValue(page());
    countMock.mockResolvedValue(count());
    markAllMock.mockResolvedValue({ markedCount: 1, unreadTotal: 0 });
  });

  it('uses the inbox list and unread-count endpoints as one server authority', async () => {
    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }));

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(listMock).toHaveBeenCalledWith({ pageSize: 10 });
    expect(countMock).toHaveBeenCalledWith();
    expect(result.current.items).toEqual([ITEM]);
    expect(result.current.unreadCount).toBe(1);
    expect(window.localStorage.length).toBe(0);
  });

  it('marks the same server-side occurrences read when the Bell opens', async () => {
    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }));
    await waitFor(() => expect(result.current.unreadCount).toBe(1));

    await act(async () => result.current.markAllSeen());

    expect(markAllMock).toHaveBeenCalledWith();
    expect(result.current.unreadCount).toBe(0);
    expect(result.current.items[0]?.isRead).toBe(true);
  });

  it('keeps the count available when the preview list fails', async () => {
    listMock.mockRejectedValue(new Error('list down'));

    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }));
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

    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.hasPartialError).toBe(true);
    expect(result.current.hasError).toBe(false);
  });

  it('reports a hard error only when both inbox reads fail', async () => {
    listMock.mockRejectedValue(new Error('list down'));
    countMock.mockRejectedValue(new Error('count down'));

    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.hasError).toBe(true);
    expect(result.current.hasPartialError).toBe(false);
  });
});
