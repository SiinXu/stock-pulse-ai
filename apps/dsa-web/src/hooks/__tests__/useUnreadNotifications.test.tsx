// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useUnreadNotifications } from '../useUnreadNotifications';
import { decisionSignalsApi } from '../../api/decisionSignals';
import { alertsApi } from '../../api/alerts';
import type { DecisionSignalListResponse } from '../../types/decisionSignals';
import type { AlertTriggerListResponse } from '../../types/alerts';

vi.mock('../../api/decisionSignals', () => ({
  decisionSignalsApi: { list: vi.fn() },
}));
vi.mock('../../api/alerts', () => ({
  alertsApi: { listTriggers: vi.fn() },
}));

const listMock = vi.mocked(decisionSignalsApi.list);
const triggersMock = vi.mocked(alertsApi.listTriggers);

function signalResponse(createdAts: string[]): DecisionSignalListResponse {
  return {
    items: createdAts.map((createdAt, index) => ({
      id: index + 1,
      stockCode: '600519',
      action: 'buy',
      status: 'active',
      createdAt,
    })) as DecisionSignalListResponse['items'],
    total: createdAts.length,
    page: 1,
    pageSize: 20,
  };
}

function triggerResponse(triggeredAts: string[]): AlertTriggerListResponse {
  return {
    items: triggeredAts.map((triggeredAt, index) => ({
      id: index + 1,
      ruleId: 1,
      target: '600519',
      status: 'sent',
      triggeredAt,
    })),
    total: triggeredAts.length,
    page: 1,
    pageSize: 20,
  };
}

const OLD = '2026-07-20T00:00:00Z';
const NEW_A = '2026-07-23T10:00:00Z';
const NEW_B = '2026-07-23T11:00:00Z';

describe('useUnreadNotifications', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-07-22T00:00:00Z'));
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('counts items newer than the persisted lastSeenAt across both channels', async () => {
    // lastSeen is 2026-07-21; OLD (07-20) is read, NEW_A/NEW_B (07-23) are unread.
    window.localStorage.setItem(
      'stockpulse.notifications.lastSeenAt',
      String(Date.parse('2026-07-21T00:00:00Z')),
    );
    listMock.mockResolvedValue(signalResponse([OLD, NEW_A]));
    triggersMock.mockResolvedValue(triggerResponse([NEW_B]));

    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.unreadSignalCount).toBe(1);
    expect(result.current.unreadAlertCount).toBe(1);
    expect(result.current.unreadCount).toBe(2);
    expect(result.current.signalItems).toHaveLength(2);
  });

  it('zeroes the unread count after markAllSeen', async () => {
    listMock.mockResolvedValue(signalResponse([NEW_A]));
    triggersMock.mockResolvedValue(triggerResponse([NEW_B]));

    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }));
    await waitFor(() => expect(result.current.unreadCount).toBe(2));

    // markAllSeen stamps Date.now(); advance it past the newest item.
    vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-07-24T00:00:00Z'));
    act(() => result.current.markAllSeen());

    expect(result.current.unreadCount).toBe(0);
    expect(window.localStorage.getItem('stockpulse.notifications.lastSeenAt')).toBe(
      String(Date.parse('2026-07-24T00:00:00Z')),
    );
  });

  it('fails soft: a rejected signals channel still counts alert triggers', async () => {
    listMock.mockRejectedValue(new Error('signals down'));
    triggersMock.mockResolvedValue(triggerResponse([NEW_A]));

    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.signalItems).toEqual([]);
    expect(result.current.alertItems).toHaveLength(1);
    expect(result.current.unreadAlertCount).toBe(1);
    // Only one channel failed, so the Bell is not in a hard-error state.
    expect(result.current.hasError).toBe(false);
  });

  it('reports a hard error only when both channels fail', async () => {
    listMock.mockRejectedValue(new Error('signals down'));
    triggersMock.mockRejectedValue(new Error('alerts down'));

    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.hasError).toBe(true);
    expect(result.current.unreadCount).toBe(0);
  });

  it('requests active signals with a bounded page size', async () => {
    listMock.mockResolvedValue(signalResponse([]));
    triggersMock.mockResolvedValue(triggerResponse([]));

    renderHook(() => useUnreadNotifications({ pollMs: 0, pageSize: 5 }));

    await waitFor(() => expect(listMock).toHaveBeenCalled());
    expect(listMock).toHaveBeenCalledWith({ status: 'active', page: 1, pageSize: 5 });
    expect(triggersMock).toHaveBeenCalledWith({ page: 1, pageSize: 5 });
  });
});
