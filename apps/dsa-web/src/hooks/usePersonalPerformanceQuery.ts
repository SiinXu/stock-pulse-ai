// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Personal Performance page loads.
// Do not import this hook from Shell, App, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { portfolioApi } from '../api/portfolio';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import type {
  PaperDecisionQualityResponse,
  PortfolioAccountItem,
  PortfolioAccountListResponse,
} from '../types/portfolio';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const PERSONAL_PERFORMANCE_CANCEL = { silent: true, revert: false } as const;

export const PERSONAL_PERFORMANCE_ACCOUNTS_QUERY_KEY = [
  'portfolio',
  'performance',
  'accounts',
] as const;

export const PERSONAL_PERFORMANCE_QUALITY_QUERY_KEY_ROOT = [
  'portfolio',
  'performance',
  'quality',
] as const;

export const PERSONAL_PERFORMANCE_QUALITY_LIMIT = 50;

/** Readonly query-key tuple. `readonly unknown[][]` is ReadonlyArray<unknown[]>, not this. */
type PersonalPerformanceQueryKey = readonly unknown[];

export type PersonalPerformanceLoadMode = 'initial' | 'refresh';

/** Previous page effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const PERSONAL_PERFORMANCE_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type UsePersonalPerformanceQueryResult = {
  accounts: PortfolioAccountItem[];
  accountId: number | null;
  report: PaperDecisionQualityResponse | null;
  loading: boolean;
  refreshing: boolean;
  error: ParsedApiError | null;
  load: (mode?: PersonalPerformanceLoadMode) => Promise<void>;
  onAccountChange: (nextId: number) => Promise<void>;
};

export function buildPersonalPerformanceQualityQueryKey(
  accountId: number,
): PersonalPerformanceQueryKey {
  return [
    'portfolio',
    'performance',
    'quality',
    accountId,
    PERSONAL_PERFORMANCE_QUALITY_LIMIT,
  ] as const;
}

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfPersonalPerformanceCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(PERSONAL_PERFORMANCE_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

function sameQueryKey(
  left: PersonalPerformanceQueryKey,
  right: PersonalPerformanceQueryKey,
): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function isQualityQueryKey(key: PersonalPerformanceQueryKey): boolean {
  return key[0] === 'portfolio' && key[1] === 'performance' && key[2] === 'quality';
}

function isPaperAccount(item: PortfolioAccountItem): boolean {
  return (item.accountType || 'real') === 'paper';
}

function selectPaperAccountId(
  accounts: readonly PortfolioAccountItem[],
  currentId: number | null,
): number | null {
  const papers = accounts.filter(isPaperAccount);
  if (currentId != null && papers.some((item) => item.id === currentId)) {
    return currentId;
  }
  return papers[0]?.id ?? null;
}

export async function fetchPersonalPerformanceAccounts(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<PortfolioAccountListResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfPersonalPerformanceCancelled(args.signal, stillActive());
    const response = await portfolioApi.getAccounts(false);
    throwIfPersonalPerformanceCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfPersonalPerformanceCancelled(args.signal, stillActive());
    throw error;
  }
}

export async function fetchPersonalPerformanceQuality(args: {
  accountId: number;
  signal?: AbortSignal;
  stillActive?: () => boolean;
}): Promise<PaperDecisionQualityResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfPersonalPerformanceCancelled(args.signal, stillActive());
    const response = await portfolioApi.getPaperDecisionQuality(args.accountId, {
      limit: PERSONAL_PERFORMANCE_QUALITY_LIMIT,
    });
    throwIfPersonalPerformanceCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfPersonalPerformanceCancelled(args.signal, stillActive());
    throw error;
  }
}

export function usePersonalPerformanceQuery(): UsePersonalPerformanceQueryResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [accounts, setAccounts] = useState<PortfolioAccountItem[]>([]);
  const [accountId, setAccountId] = useState<number | null>(null);
  const [report, setReport] = useState<PaperDecisionQualityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);

  const requestIdRef = useRef(0);
  const accountIdRef = useRef<number | null>(null);
  const liveKeysRef = useRef<PersonalPerformanceQueryKey[]>([]);
  accountIdRef.current = accountId;

  const discardExactQuery = useCallback((key: PersonalPerformanceQueryKey) => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: key, exact: true },
      PERSONAL_PERFORMANCE_CANCEL,
    );
    client.removeQueries({ queryKey: key, exact: true });
    liveKeysRef.current = liveKeysRef.current.filter((live) => !sameQueryKey(live, key));
  }, []);

  const discardLiveKeys = useCallback((
    predicate: (key: PersonalPerformanceQueryKey) => boolean,
  ) => {
    for (const live of [...liveKeysRef.current]) {
      if (predicate(live)) discardExactQuery(live);
    }
  }, [discardExactQuery]);

  const trackLiveKey = useCallback((key: PersonalPerformanceQueryKey) => {
    if (liveKeysRef.current.some((live) => sameQueryKey(live, key))) return;
    liveKeysRef.current = [...liveKeysRef.current, key];
  }, []);

  const load = useCallback(async (mode: PersonalPerformanceLoadMode = 'initial') => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const accountsKey = PERSONAL_PERFORMANCE_ACCOUNTS_QUERY_KEY;
    const stillActive = () => requestIdRef.current === requestId;

    if (mode === 'initial') {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardLiveKeys(() => true);
    trackLiveKey(accountsKey);

    try {
      const accountList = await queryClientRef.current.fetchQuery({
        queryKey: accountsKey,
        queryFn: ({ signal }) => fetchPersonalPerformanceAccounts({
          signal,
          stillActive,
        }),
        ...PERSONAL_PERFORMANCE_QUERY_SCHEDULE,
      });
      if (!stillActive()) return;
      const nextAccounts = accountList.accounts ?? [];
      setAccounts(nextAccounts);
      const selected = selectPaperAccountId(nextAccounts, accountIdRef.current);
      accountIdRef.current = selected;
      setAccountId(selected);
      if (selected == null) {
        setReport(null);
        return;
      }
      const qualityKey = buildPersonalPerformanceQualityQueryKey(selected);
      trackLiveKey(qualityKey);
      const quality = await queryClientRef.current.fetchQuery({
        queryKey: qualityKey,
        queryFn: ({ signal }) => fetchPersonalPerformanceQuality({
          accountId: selected,
          signal,
          stillActive,
        }),
        ...PERSONAL_PERFORMANCE_QUERY_SCHEDULE,
      });
      if (!stillActive()) return;
      setReport(quality);
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return;
      setReport(null);
      setError(getParsedApiError(err));
    } finally {
      if (stillActive()) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [discardLiveKeys, trackLiveKey]);

  const onAccountChange = useCallback(async (nextId: number) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;
    const qualityKey = buildPersonalPerformanceQualityQueryKey(nextId);

    accountIdRef.current = nextId;
    setAccountId(nextId);
    setRefreshing(true);
    setError(null);

    discardLiveKeys((key) => isQualityQueryKey(key));
    trackLiveKey(qualityKey);

    try {
      const quality = await queryClientRef.current.fetchQuery({
        queryKey: qualityKey,
        queryFn: ({ signal }) => fetchPersonalPerformanceQuality({
          accountId: nextId,
          signal,
          stillActive,
        }),
        ...PERSONAL_PERFORMANCE_QUERY_SCHEDULE,
      });
      if (!stillActive()) return;
      setReport(quality);
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return;
      setReport(null);
      setError(getParsedApiError(err));
    } finally {
      if (stillActive()) {
        setRefreshing(false);
      }
    }
  }, [discardLiveKeys, trackLiveKey]);

  useEffect(() => {
    void load('initial');
    return () => {
      requestIdRef.current += 1;
      discardLiveKeys(() => true);
    };
  }, [load, discardLiveKeys]);

  return {
    accounts,
    accountId,
    report,
    loading,
    refreshing,
    error,
    load,
    onAccountChange,
  };
}
