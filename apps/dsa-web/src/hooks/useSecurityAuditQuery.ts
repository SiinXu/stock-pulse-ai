// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings security-audit list GET.
// Do not import this hook from Shell, App, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { securityAuditApi } from '../api/securityAudit';
import type { UiLanguage } from '../i18n/uiText';
import type {
  SecurityAuditEvent,
  SecurityAuditEventPage,
  SecurityAuditListQuery,
  SecurityAuditOutcome,
} from '../types/securityAudit';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const SECURITY_AUDIT_CANCEL = { silent: true, revert: false } as const;

/** Readonly two-element root. Never prefix-cancel or prefix-remove `['security-audit']`. */
export const SECURITY_AUDIT_QUERY_KEY_ROOT = ['security-audit', 'events'] as const;

/** Previous panel always requested the first page of 50 events. */
export const SECURITY_AUDIT_DEFAULT_PAGE_SIZE = 50;

/** Previous panel effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const SECURITY_AUDIT_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

/** Readonly query-key tuple. `readonly unknown[][]` is ReadonlyArray<unknown[]>, not this. */
export type SecurityAuditQueryKey = readonly unknown[];

export type SecurityAuditLoadMode = 'initial' | 'refresh';

export type SecurityAuditLoadOverrides = {
  page?: number;
  pageSize?: number;
  eventType?: string;
  outcome?: SecurityAuditOutcome | '';
  correlationId?: string;
};

export type UseSecurityAuditQueryResult = {
  items: SecurityAuditEvent[];
  page: number;
  pageSize: number;
  total: number;
  isLoading: boolean;
  isRefreshing: boolean;
  loadError: ParsedApiError | null;
  load: (mode?: SecurityAuditLoadMode, overrides?: SecurityAuditLoadOverrides) => Promise<void>;
};

type AppliedSecurityAuditQuery = {
  page: number;
  pageSize: number;
  eventType: string;
  outcome: SecurityAuditOutcome | '';
  correlationId: string;
};

function sameQueryKey(left: SecurityAuditQueryKey, right: SecurityAuditQueryKey): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

export function buildSecurityAuditQueryKey(
  page: number,
  pageSize: number,
  eventType: string,
  outcome: SecurityAuditOutcome | '',
  correlationId: string,
): SecurityAuditQueryKey {
  const eventTypeTrimmed = eventType.trim();
  const correlationTrimmed = correlationId.trim();
  return [
    ...SECURITY_AUDIT_QUERY_KEY_ROOT,
    page,
    pageSize,
    eventTypeTrimmed || 'all',
    outcome || 'all',
    correlationTrimmed || 'none',
  ] as const;
}

export function buildSecurityAuditListQuery(
  page: number,
  pageSize: number,
  eventType: string,
  outcome: SecurityAuditOutcome | '',
  correlationId: string,
): SecurityAuditListQuery {
  const trimmedEventType = eventType.trim();
  const trimmedCorrelation = correlationId.trim();
  return {
    page,
    pageSize,
    ...(trimmedEventType ? { eventType: trimmedEventType } : {}),
    ...(outcome ? { outcome } : {}),
    ...(trimmedCorrelation ? { correlationId: trimmedCorrelation } : {}),
  };
}

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfSecurityAuditCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(SECURITY_AUDIT_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchSecurityAuditEvents(args: {
  page: number;
  pageSize: number;
  eventType: string;
  outcome: SecurityAuditOutcome | '';
  correlationId: string;
  signal?: AbortSignal;
  stillActive?: () => boolean;
}): Promise<SecurityAuditEventPage> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfSecurityAuditCancelled(args.signal, stillActive());
    const page = await securityAuditApi.list(
      buildSecurityAuditListQuery(
        args.page,
        args.pageSize,
        args.eventType,
        args.outcome,
        args.correlationId,
      ),
    );
    throwIfSecurityAuditCancelled(args.signal, stillActive());
    return page;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfSecurityAuditCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useSecurityAuditQuery(language: UiLanguage): UseSecurityAuditQueryResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [items, setItems] = useState<SecurityAuditEvent[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(SECURITY_AUDIT_DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);

  const requestIdRef = useRef(0);
  const languageRef = useRef(language);
  languageRef.current = language;
  const appliedRef = useRef<AppliedSecurityAuditQuery>({
    page: 1,
    pageSize: SECURITY_AUDIT_DEFAULT_PAGE_SIZE,
    eventType: '',
    outcome: '',
    correlationId: '',
  });
  const liveKeyRef = useRef<SecurityAuditQueryKey | null>(null);

  const discardExactQuery = useCallback((key: SecurityAuditQueryKey) => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: key, exact: true },
      SECURITY_AUDIT_CANCEL,
    );
    client.removeQueries({ queryKey: key, exact: true });
  }, []);

  const load = useCallback(async (
    mode: SecurityAuditLoadMode = 'initial',
    overrides?: SecurityAuditLoadOverrides,
  ) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;

    const nextPage = overrides?.page ?? appliedRef.current.page;
    const nextPageSize = overrides?.pageSize ?? appliedRef.current.pageSize;
    const nextEventType = (overrides?.eventType ?? appliedRef.current.eventType).trim();
    const nextOutcome = overrides?.outcome ?? appliedRef.current.outcome;
    const nextCorrelation = (overrides?.correlationId ?? appliedRef.current.correlationId).trim();

    appliedRef.current = {
      page: nextPage,
      pageSize: nextPageSize,
      eventType: nextEventType,
      outcome: nextOutcome,
      correlationId: nextCorrelation,
    };
    if (overrides?.pageSize !== undefined) {
      setPageSize(nextPageSize);
    }

    const key = buildSecurityAuditQueryKey(
      nextPage,
      nextPageSize,
      nextEventType,
      nextOutcome,
      nextCorrelation,
    );

    setLoadError(null);
    if (mode === 'initial') {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    // Key-changing loads exact-remove the previous live key, then the successor key.
    const previous = liveKeyRef.current;
    if (previous) discardExactQuery(previous);
    if (!previous || !sameQueryKey(previous, key)) {
      discardExactQuery(key);
    }
    liveKeyRef.current = key;

    try {
      const response = await queryClientRef.current.fetchQuery({
        queryKey: key,
        queryFn: ({ signal }) => fetchSecurityAuditEvents({
          page: nextPage,
          pageSize: nextPageSize,
          eventType: nextEventType,
          outcome: nextOutcome,
          correlationId: nextCorrelation,
          signal,
          stillActive,
        }),
        ...SECURITY_AUDIT_QUERY_SCHEDULE,
      });
      if (!stillActive()) return;
      appliedRef.current.page = response.page;
      appliedRef.current.pageSize = response.pageSize;
      setItems(response.items);
      setPage(response.page);
      setPageSize(response.pageSize);
      setTotal(response.total);
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return;
      setItems([]);
      setTotal(0);
      setLoadError(getParsedApiError(err, languageRef.current));
    } finally {
      if (stillActive()) {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    }
  }, [discardExactQuery]);

  useEffect(() => {
    void load('initial');
    return () => {
      requestIdRef.current += 1;
      if (liveKeyRef.current) {
        discardExactQuery(liveKeyRef.current);
        liveKeyRef.current = null;
      }
    };
  }, [load, discardExactQuery]);

  return {
    items,
    page,
    pageSize,
    total,
    isLoading,
    isRefreshing,
    loadError,
    load,
  };
}
