// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { CancelledError, QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { eventCalendarApi } from '../../api/eventCalendar';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import type { EventCalendarResponse } from '../../types/eventCalendar';
import {
  EVENT_CALENDAR_CANCEL,
  EVENT_CALENDAR_QUERY_SCHEDULE,
  buildEventCalendarListQueryKey,
  fetchEventCalendarList,
  useEventCalendarQuery,
} from '../useEventCalendarQuery';

vi.mock('../../api/eventCalendar', () => ({
  eventCalendarApi: {
    getCalendar: vi.fn(),
  },
}));

const getCalendar = vi.mocked(eventCalendarApi.getCalendar);

const FROM = '2026-07-01';
const TO = '2026-07-31';
const NEXT_FROM = '2026-08-01';
const NEXT_TO = '2026-08-31';

function payload(summary: string): EventCalendarResponse {
  return {
    events: [{
      eventId: 7,
      eventDate: '2026-07-10',
      symbol: '600519',
      status: 'triggered',
      eventCategory: 'earnings',
      whatHappened: 'Earnings disclosure',
      whyItMatters: summary,
      degraded: false,
      inWatchlist: true,
      inPortfolio: false,
      source: 'corporate_event_service',
    }],
    loadedCount: 1,
    total: 1,
    partialErrors: [],
  };
}

function createWrapper(client?: QueryClient) {
  const queryClient = client ?? createAppQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return { client: queryClient, wrapper: Wrapper };
}

function listOptions(
  client: QueryClient,
  queryKey: readonly unknown[] = buildEventCalendarListQueryKey(FROM, TO),
) {
  const query = client.getQueryCache().find({ queryKey, exact: true });
  return query?.options as Record<string, unknown> | undefined;
}

function queryFetchStatus(client: QueryClient, queryKey: readonly unknown[]) {
  return client.getQueryState(queryKey)?.fetchStatus;
}

function assertNoEventCalendarPrefixOps(
  calls: Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>,
) {
  for (const [filters] of calls) {
    const key = filters?.queryKey ?? [];
    expect(key[0] === 'event-calendar' && key.length === 1).toBe(false);
    if (key[0] === 'event-calendar') {
      expect(filters?.exact).toBe(true);
      expect([...key]).toEqual(['event-calendar', 'list', key[2], key[3]]);
      expect(key).toHaveLength(4);
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

describe('useEventCalendarQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onlineManager.setOnline(true);
    getCalendar.mockResolvedValue(payload('ok'));
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

  it('pins the exact list key, schedule, and getCalendar({dateFrom,dateTo},{signal})', async () => {
    expect(buildEventCalendarListQueryKey(FROM, TO)).toEqual(['event-calendar', 'list', FROM, TO]);
    expect(EVENT_CALENDAR_QUERY_SCHEDULE).toEqual({
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 0,
      networkMode: 'always',
    });
    const signal = new AbortController().signal;
    await fetchEventCalendarList({ dateFrom: FROM, dateTo: TO, signal });
    expect(getCalendar).toHaveBeenCalledTimes(1);
    expect(getCalendar).toHaveBeenCalledWith(
      { dateFrom: FROM, dateTo: TO },
      { signal },
    );
  });

  it('does not auto-retry a 5xx load when the QueryClient default would retry', async () => {
    getCalendar.mockRejectedValue(Object.assign(new Error('server'), { response: { status: 500 } }));
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: 3, refetchOnWindowFocus: false },
      },
    });
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useEventCalendarQuery(FROM, TO), { wrapper });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(getCalendar).toHaveBeenCalledTimes(1);
    expect(listOptions(client)?.retry).toBe(false);
    expect(result.current.data).toBeNull();
  });

  it('does not refetch when the window regains focus', async () => {
    const client = createAppQueryClient();
    expect(client.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(true);
    const { wrapper } = createWrapper(client);
    const { result } = renderHook(() => useEventCalendarQuery(FROM, TO), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(listOptions(client)?.refetchOnWindowFocus).toBe(false);
    expect(listOptions(client)?.retry).toBe(false);
    expect(listOptions(client)?.staleTime).toBe(0);
    expect(getCalendar).toHaveBeenCalledTimes(1);

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(getCalendar).toHaveBeenCalledTimes(1);
  });

  it('does not poll: hidden-tab ticks and a 60s timer do not call getCalendar again', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useEventCalendarQuery(FROM, TO), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getCalendar).toHaveBeenCalledTimes(1);
    expect(listOptions(client)?.refetchInterval).toBeUndefined();

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

    expect(getCalendar).toHaveBeenCalledTimes(1);
  });

  it('issues getCalendar while offline because networkMode is always', async () => {
    onlineManager.setOnline(false);
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useEventCalendarQuery(FROM, TO), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getCalendar).toHaveBeenCalledTimes(1);
    expect(listOptions(client)?.networkMode).toBe('always');
    expect(result.current.data?.events[0]?.whyItMatters).toBe('ok');
  });

  it('schedules through fetchQuery with no live observer and without includeImpact in the key', async () => {
    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result } = renderHook(() => useEventCalendarQuery(FROM, TO), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetchSpy).toHaveBeenCalled();
    for (const [options] of fetchSpy.mock.calls) {
      expect(options.queryKey).toEqual(['event-calendar', 'list', FROM, TO]);
      expect(options.queryKey).not.toContain(true);
      expect(options.queryKey).not.toContain(false);
      expect(options.queryKey).not.toContain('includeImpact');
    }
    const key = buildEventCalendarListQueryKey(FROM, TO);
    expect(client.getQueryCache().find({ queryKey: key, exact: true })?.getObserversCount()).toBe(0);
  });

  it('cancels the previous date key and ignores its late response', async () => {
    const first = createDeferred<EventCalendarResponse>();
    getCalendar
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(payload('Newest response'));
    const { client, wrapper } = createWrapper();
    const cancelSpy = vi.spyOn(client, 'cancelQueries');
    const removeSpy = vi.spyOn(client, 'removeQueries');
    const abandoned = buildEventCalendarListQueryKey(FROM, TO);
    const nextKey = buildEventCalendarListQueryKey(NEXT_FROM, NEXT_TO);
    const { result, rerender } = renderHook(
      ({ dateFrom, dateTo }) => useEventCalendarQuery(dateFrom, dateTo),
      { wrapper, initialProps: { dateFrom: FROM, dateTo: TO } },
    );

    await waitFor(() => expect(getCalendar).toHaveBeenCalledTimes(1));
    const firstSignal = getCalendar.mock.calls[0][1]?.signal;
    rerender({ dateFrom: NEXT_FROM, dateTo: NEXT_TO });

    await waitFor(() => expect(result.current.data?.events[0]?.whyItMatters).toBe('Newest response'));
    expect(firstSignal?.aborted).toBe(true);
    expect(client.getQueryState(abandoned)).toBeUndefined();
    expect(client.getQueryState(nextKey)).toBeDefined();
    expect(getCalendar).toHaveBeenLastCalledWith(
      { dateFrom: NEXT_FROM, dateTo: NEXT_TO },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );

    await act(async () => {
      first.resolve(payload('Stale response'));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.data?.events[0]?.whyItMatters).toBe('Newest response');
    expect(result.current.error).toBeNull();
    assertNoEventCalendarPrefixOps(cancelSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
    assertNoEventCalendarPrefixOps(removeSpy.mock.calls as Array<[filters?: { queryKey?: readonly unknown[]; exact?: boolean }]>);
  });

  it('does not setError when getCalendar settles as CancelledError', async () => {
    getCalendar.mockRejectedValue(new CancelledError(EVENT_CALENDAR_CANCEL));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useEventCalendarQuery(FROM, TO), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.data).toBeNull();
  });

  it('does not setError or clear newer data when an aborted predecessor fails', async () => {
    const first = createDeferred<EventCalendarResponse>();
    getCalendar
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(payload('Newest response'));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useEventCalendarQuery(FROM, TO), { wrapper });

    await waitFor(() => expect(getCalendar).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load();
    });
    await waitFor(() => expect(result.current.data?.events[0]?.whyItMatters).toBe('Newest response'));

    await act(async () => {
      first.reject(Object.assign(new Error('server'), { response: { status: 500 } }));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.error).toBeNull();
    expect(result.current.data?.events[0]?.whyItMatters).toBe('Newest response');
  });

  it('clears data only for a live-generation hard error', async () => {
    getCalendar.mockResolvedValueOnce(payload('kept'));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useEventCalendarQuery(FROM, TO), { wrapper });

    await waitFor(() => expect(result.current.data?.events[0]?.whyItMatters).toBe('kept'));

    getCalendar.mockRejectedValueOnce(Object.assign(new Error('server'), { response: { status: 500 } }));
    await act(async () => {
      await result.current.load();
    });

    expect(result.current.error).not.toBeNull();
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it('fences a stale predecessor completion so it cannot overwrite a newer generation', async () => {
    const first = createDeferred<EventCalendarResponse>();
    const successor = createDeferred<EventCalendarResponse>();
    getCalendar
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(successor.promise);
    const { client, wrapper } = createWrapper();
    const key = buildEventCalendarListQueryKey(FROM, TO);
    const { result } = renderHook(() => useEventCalendarQuery(FROM, TO), { wrapper });

    await waitFor(() => expect(getCalendar).toHaveBeenCalledTimes(1));
    await act(async () => {
      void result.current.load();
    });
    await waitFor(() => expect(getCalendar).toHaveBeenCalledTimes(2));

    await act(async () => {
      successor.resolve(payload('Newest response'));
    });
    await waitFor(() => expect(result.current.data?.events[0]?.whyItMatters).toBe('Newest response'));

    await act(async () => {
      first.resolve(payload('Stale response'));
      await first.promise.catch(() => undefined);
    });

    expect(result.current.data?.events[0]?.whyItMatters).toBe('Newest response');
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(queryFetchStatus(client, key)).toBe('idle');
  });

  it('uses the same load path for Refresh and date-key changes', async () => {
    const { client, wrapper } = createWrapper();
    const fetchSpy = vi.spyOn(client, 'fetchQuery');
    const { result, rerender } = renderHook(
      ({ dateFrom, dateTo }) => useEventCalendarQuery(dateFrom, dateTo),
      { wrapper, initialProps: { dateFrom: FROM, dateTo: TO } },
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getCalendar).toHaveBeenCalledTimes(1);
    const firstLoad = result.current.load;

    await act(async () => {
      await result.current.load();
    });
    expect(result.current.load).toBe(firstLoad);
    expect(getCalendar).toHaveBeenCalledTimes(2);
    expect(getCalendar.mock.calls[1][0]).toEqual({ dateFrom: FROM, dateTo: TO });

    rerender({ dateFrom: NEXT_FROM, dateTo: NEXT_TO });
    await waitFor(() => expect(getCalendar).toHaveBeenCalledTimes(3));
    expect(result.current.load).toBe(firstLoad);
    expect(getCalendar.mock.calls[2][0]).toEqual({ dateFrom: NEXT_FROM, dateTo: NEXT_TO });

    for (const [options] of fetchSpy.mock.calls) {
      const scheduled = options as unknown as Record<string, unknown>;
      expect(scheduled.queryFn).toEqual(expect.any(Function));
      expect(scheduled.retry).toBe(false);
      expect(scheduled.refetchOnWindowFocus).toBe(false);
      expect(scheduled.staleTime).toBe(0);
      expect(scheduled.networkMode).toBe('always');
    }
  });

  it('removes exact list keys on unmount and ignores a late getCalendar failure', async () => {
    const pending = createDeferred<EventCalendarResponse>();
    getCalendar.mockReturnValueOnce(pending.promise);
    const { client, wrapper } = createWrapper();
    const key = buildEventCalendarListQueryKey(FROM, TO);
    const { result, unmount } = renderHook(() => useEventCalendarQuery(FROM, TO), { wrapper });

    await waitFor(() => expect(getCalendar).toHaveBeenCalledTimes(1));
    unmount();

    await act(async () => {
      pending.reject(Object.assign(new Error('server'), { response: { status: 500 } }));
      await pending.promise.catch(() => undefined);
      await Promise.resolve();
    });

    expect(result.current.error).toBeNull();
    expect(client.getQueryState(key)).toBeUndefined();
    expect(client.getQueryCache().findAll({ queryKey: ['event-calendar', 'list'] })).toHaveLength(0);
    expect(queryFetchStatus(client, key)).toBeUndefined();
  });
});
