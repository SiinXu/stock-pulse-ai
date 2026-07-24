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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
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

  it('uses the legacy shared boundary when per-channel boundaries are absent', async () => {
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

    // The server timestamps are ahead of the client clock; opening the Bell
    // must still mark every currently loaded item as seen.
    act(() => result.current.markAllSeen());

    expect(result.current.unreadCount).toBe(0);
    expect(window.localStorage.getItem('stockpulse.notifications.signalsLastSeenAt')).toBe(
      String(Date.parse(NEW_A)),
    );
    expect(window.localStorage.getItem('stockpulse.notifications.alertsLastSeenAt')).toBe(
      String(Date.parse(NEW_B)),
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
    expect(result.current.signalsFailed).toBe(true);
    expect(result.current.alertsFailed).toBe(false);
    expect(result.current.hasPartialError).toBe(true);
    expect(result.current.hasError).toBe(false);
  });

  it('keeps recovered signal items unread after the Bell opens during a signal failure', async () => {
    const legacyBoundary = Date.parse('2026-07-21T00:00:00Z');
    window.localStorage.setItem(
      'stockpulse.notifications.lastSeenAt',
      String(legacyBoundary),
    );
    vi.mocked(Date.now).mockReturnValue(Date.parse('2026-07-24T00:00:00Z'));
    listMock
      .mockRejectedValueOnce(new Error('signals down'))
      .mockResolvedValueOnce(signalResponse([NEW_A]));
    triggersMock.mockResolvedValue(triggerResponse([OLD]));

    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }));
    await waitFor(() => expect(result.current.hasPartialError).toBe(true));

    act(() => result.current.markAllSeen());

    expect(result.current.signalLastSeenAt).toBe(legacyBoundary);
    expect(window.localStorage.getItem('stockpulse.notifications.signalsLastSeenAt'))
      .toBe(String(legacyBoundary));
    expect(result.current.alertLastSeenAt).toBe(Date.parse('2026-07-24T00:00:00Z'));

    act(() => result.current.refresh());

    await waitFor(() => expect(result.current.signalsFailed).toBe(false));
    expect(result.current.unreadSignalCount).toBe(1);
    expect(result.current.signalItems[0]?.createdAt).toBe(NEW_A);
  });

  it('advances a failed channel only through its visible cached items', async () => {
    vi.mocked(Date.now).mockReturnValue(Date.parse('2026-07-24T00:00:00Z'));
    listMock
      .mockResolvedValueOnce(signalResponse([NEW_A]))
      .mockRejectedValueOnce(new Error('signals down'));
    triggersMock.mockResolvedValue(triggerResponse([]));

    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }));
    await waitFor(() => expect(result.current.signalItems).toHaveLength(1));

    act(() => result.current.refresh());
    await waitFor(() => expect(result.current.signalsFailed).toBe(true));
    act(() => result.current.markAllSeen());

    expect(result.current.signalLastSeenAt).toBe(Date.parse(NEW_A));
    expect(result.current.alertLastSeenAt).toBe(Date.parse('2026-07-24T00:00:00Z'));
  });

  it('reports a hard error only when both channels fail', async () => {
    listMock.mockRejectedValue(new Error('signals down'));
    triggersMock.mockRejectedValue(new Error('alerts down'));

    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.hasError).toBe(true);
    expect(result.current.hasPartialError).toBe(false);
    expect(result.current.unreadCount).toBe(0);
  });

  it('retains cached rows but exposes total failure after a successful refresh', async () => {
    listMock
      .mockResolvedValueOnce(signalResponse([NEW_A]))
      .mockRejectedValueOnce(new Error('signals down'));
    triggersMock
      .mockResolvedValueOnce(triggerResponse([NEW_B]))
      .mockRejectedValueOnce(new Error('alerts down'));

    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }));
    await waitFor(() => expect(result.current.unreadCount).toBe(2));

    act(() => result.current.refresh());

    await waitFor(() => expect(result.current.hasError).toBe(true));
    expect(result.current.signalItems).toHaveLength(1);
    expect(result.current.alertItems).toHaveLength(1);
  });

  it('requests active signals with a bounded page size', async () => {
    listMock.mockResolvedValue(signalResponse([]));
    triggersMock.mockResolvedValue(triggerResponse([]));

    renderHook(() => useUnreadNotifications({ pollMs: 0, pageSize: 5 }));

    await waitFor(() => expect(listMock).toHaveBeenCalled());
    expect(listMock).toHaveBeenCalledWith({ status: 'active', page: 1, pageSize: 5 });
    expect(triggersMock).toHaveBeenCalledWith({ page: 1, pageSize: 5 });
  });

  it('does not let an older refresh overwrite a newer generation', async () => {
    const oldSignals = deferred<DecisionSignalListResponse>();
    const oldAlerts = deferred<AlertTriggerListResponse>();
    listMock
      .mockReturnValueOnce(oldSignals.promise)
      .mockResolvedValueOnce(signalResponse([NEW_B]));
    triggersMock
      .mockReturnValueOnce(oldAlerts.promise)
      .mockResolvedValueOnce(triggerResponse([NEW_B]));

    const { result } = renderHook(() => useUnreadNotifications({ pollMs: 0 }));
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(1));

    act(() => result.current.refresh());
    await waitFor(() => expect(result.current.signalItems[0]?.createdAt).toBe(NEW_B));

    await act(async () => {
      oldSignals.resolve(signalResponse([OLD]));
      oldAlerts.resolve(triggerResponse([OLD]));
      await Promise.all([oldSignals.promise, oldAlerts.promise]);
    });

    expect(result.current.signalItems[0]?.createdAt).toBe(NEW_B);
    expect(result.current.alertItems[0]?.triggeredAt).toBe(NEW_B);
  });
});
