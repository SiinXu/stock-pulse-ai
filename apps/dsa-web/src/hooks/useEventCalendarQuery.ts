// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Event Calendar page loads.
// Do not import this hook from Shell, App, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { eventCalendarApi } from '../api/eventCalendar';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import type { EventCalendarResponse } from '../types/eventCalendar';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const EVENT_CALENDAR_CANCEL = { silent: true, revert: false } as const;

export const EVENT_CALENDAR_LIST_QUERY_KEY_ROOT = [
  'event-calendar',
  'list',
] as const;

/** Readonly query-key tuple. `readonly unknown[][]` is ReadonlyArray<unknown[]>, not this. */
type EventCalendarListQueryKey = readonly unknown[];

/** Previous page effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const EVENT_CALENDAR_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type UseEventCalendarQueryResult = {
  data: EventCalendarResponse | null;
  loading: boolean;
  error: ParsedApiError | null;
  load: () => Promise<void>;
};

export function buildEventCalendarListQueryKey(
  dateFrom: string,
  dateTo: string,
): EventCalendarListQueryKey {
  return ['event-calendar', 'list', dateFrom, dateTo] as const;
}

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfEventCalendarCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(EVENT_CALENDAR_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

function sameQueryKey(
  left: EventCalendarListQueryKey,
  right: EventCalendarListQueryKey,
): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

export async function fetchEventCalendarList(args: {
  dateFrom: string;
  dateTo: string;
  signal?: AbortSignal;
  stillActive?: () => boolean;
}): Promise<EventCalendarResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfEventCalendarCancelled(args.signal, stillActive());
    const response = await eventCalendarApi.getCalendar(
      { dateFrom: args.dateFrom, dateTo: args.dateTo },
      { signal: args.signal },
    );
    throwIfEventCalendarCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfEventCalendarCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useEventCalendarQuery(
  dateFrom: string,
  dateTo: string,
): UseEventCalendarQueryResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [data, setData] = useState<EventCalendarResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ParsedApiError | null>(null);

  const requestIdRef = useRef(0);
  const dateFromRef = useRef(dateFrom);
  const dateToRef = useRef(dateTo);
  const liveKeysRef = useRef<EventCalendarListQueryKey[]>([]);
  dateFromRef.current = dateFrom;
  dateToRef.current = dateTo;

  const discardExactQuery = useCallback((key: EventCalendarListQueryKey) => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: key, exact: true },
      EVENT_CALENDAR_CANCEL,
    );
    client.removeQueries({ queryKey: key, exact: true });
    liveKeysRef.current = liveKeysRef.current.filter((live) => !sameQueryKey(live, key));
  }, []);

  const discardLiveKeys = useCallback((
    predicate: (key: EventCalendarListQueryKey) => boolean,
  ) => {
    for (const live of [...liveKeysRef.current]) {
      if (predicate(live)) discardExactQuery(live);
    }
  }, [discardExactQuery]);

  const load = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const dateFromAtStart = dateFromRef.current;
    const dateToAtStart = dateToRef.current;
    const key = buildEventCalendarListQueryKey(dateFromAtStart, dateToAtStart);

    setLoading(true);
    setError(null);

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    // Date-key change also exact-removes the abandoned range key.
    discardLiveKeys(() => true);
    liveKeysRef.current = [...liveKeysRef.current, key];

    try {
      const response = await queryClientRef.current.fetchQuery({
        queryKey: key,
        queryFn: ({ signal }) => fetchEventCalendarList({
          dateFrom: dateFromAtStart,
          dateTo: dateToAtStart,
          signal,
          stillActive: () => requestIdRef.current === requestId,
        }),
        ...EVENT_CALENDAR_QUERY_SCHEDULE,
      });
      if (requestIdRef.current !== requestId) return;
      setData(response);
    } catch (err) {
      if (requestIdRef.current !== requestId || isCancelledError(err)) return;
      setError(getParsedApiError(err));
      setData(null);
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  }, [discardLiveKeys]);

  useEffect(() => {
    void load();
    return () => {
      requestIdRef.current += 1;
      discardLiveKeys(() => true);
    };
  }, [load, dateFrom, dateTo, discardLiveKeys]);

  return {
    data,
    loading,
    error,
    load,
  };
}
