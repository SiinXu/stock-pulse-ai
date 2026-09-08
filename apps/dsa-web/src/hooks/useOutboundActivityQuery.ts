// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings outbound-activity GET.
// Do not import this hook from Shell, App, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { outboundActivityApi } from '../api/outboundActivity';
import type { LocalOnlyModeStatus, OutboundActivityItem } from '../types/outboundActivity';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const OUTBOUND_ACTIVITY_CANCEL = { silent: true, revert: false } as const;

/** Readonly two-element key. Never prefix-cancel or prefix-remove `['outbound-activity']`. */
export const OUTBOUND_ACTIVITY_QUERY_KEY = ['outbound-activity', 'load'] as const;

/** Previous panel effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const OUTBOUND_ACTIVITY_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

/** Previous panel always requested the first 50 retained decisions. */
export const OUTBOUND_ACTIVITY_LIMIT = 50;

export type OutboundActivityLoadMode = 'initial' | 'refresh';

export type OutboundActivitySnapshot = {
  status: LocalOnlyModeStatus;
  items: OutboundActivityItem[];
};

export type UseOutboundActivityQueryResult = {
  status: LocalOnlyModeStatus | null;
  items: OutboundActivityItem[];
  isLoading: boolean;
  isRefreshing: boolean;
  loadError: ParsedApiError | null;
  load: (mode?: OutboundActivityLoadMode) => Promise<void>;
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfOutboundActivityCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(OUTBOUND_ACTIVITY_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchOutboundActivity(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<OutboundActivitySnapshot> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfOutboundActivityCancelled(args.signal, stillActive());
    const [status, page] = await Promise.all([
      outboundActivityApi.getLocalOnlyStatus(),
      outboundActivityApi.listActivity({ limit: OUTBOUND_ACTIVITY_LIMIT }),
    ]);
    throwIfOutboundActivityCancelled(args.signal, stillActive());
    return { status, items: page.items };
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfOutboundActivityCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useOutboundActivityQuery(): UseOutboundActivityQueryResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [status, setStatus] = useState<LocalOnlyModeStatus | null>(null);
  const [items, setItems] = useState<OutboundActivityItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);

  const requestIdRef = useRef(0);

  const discardExactOutboundQuery = useCallback(() => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: OUTBOUND_ACTIVITY_QUERY_KEY, exact: true },
      OUTBOUND_ACTIVITY_CANCEL,
    );
    client.removeQueries({ queryKey: OUTBOUND_ACTIVITY_QUERY_KEY, exact: true });
  }, []);

  const load = useCallback(async (mode: OutboundActivityLoadMode = 'initial') => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;

    setLoadError(null);
    if (mode === 'initial') {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactOutboundQuery();

    try {
      const next = await queryClientRef.current.fetchQuery({
        queryKey: OUTBOUND_ACTIVITY_QUERY_KEY,
        queryFn: ({ signal }) => fetchOutboundActivity({
          signal,
          stillActive,
        }),
        ...OUTBOUND_ACTIVITY_QUERY_SCHEDULE,
      });
      if (!stillActive()) return;
      setStatus(next.status);
      setItems(next.items);
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return;
      setStatus(null);
      setItems([]);
      setLoadError(getParsedApiError(err));
    } finally {
      if (stillActive()) {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    }
  }, [discardExactOutboundQuery]);

  useEffect(() => {
    void load('initial');
    return () => {
      requestIdRef.current += 1;
      discardExactOutboundQuery();
    };
  }, [load, discardExactOutboundQuery]);

  return {
    status,
    items,
    isLoading,
    isRefreshing,
    loadError,
    load,
  };
}
