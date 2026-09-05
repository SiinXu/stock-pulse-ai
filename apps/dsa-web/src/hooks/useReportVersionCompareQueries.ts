// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Report Version Compare list and compare GETs.
// Do not import this hook from Shell, App, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import {
  reportVersionCompareApi,
  type ReportVersionCompareResponse,
  type ReportVersionRunItem,
  type ReportVersionRunListResponse,
} from '../api/reportVersionCompare';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const REPORT_VERSION_COMPARE_CANCEL = { silent: true, revert: false } as const;

export const REPORT_VERSION_COMPARE_RUNS_QUERY_KEY_ROOT = [
  'report-version-compare',
  'runs',
] as const;

export const REPORT_VERSION_COMPARE_COMPARE_QUERY_KEY_ROOT = [
  'report-version-compare',
  'compare',
] as const;

export const REPORT_VERSION_COMPARE_RUN_PAGE_SIZE = 50;

/** Readonly query-key tuple. `readonly unknown[][]` is ReadonlyArray<unknown[]>, not this. */
type ReportVersionCompareQueryKey = readonly unknown[];

/** Previous page effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const REPORT_VERSION_COMPARE_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type FailedOperation =
  | {
    kind: 'list';
    stockCode: string;
    page: number;
    append: boolean;
  }
  | {
    kind: 'compare';
    stockCode: string;
    baseRunId: string;
    targetRunId: string;
  };

export type UseReportVersionCompareQueriesResult = {
  runs: ReportVersionRunItem[];
  totalRuns: number;
  runPage: number;
  loadedStockCode: string | null;
  hasLoadedRuns: boolean;
  result: ReportVersionCompareResponse | null;
  loadingRuns: boolean;
  loadingMore: boolean;
  comparing: boolean;
  error: ParsedApiError | null;
  failedOperation: FailedOperation | null;
  loadRuns: (args: {
    stockCode: string;
    page: number;
    append: boolean;
  }) => Promise<void>;
  compare: (args: {
    stockCode: string;
    baseRunId: string;
    targetRunId: string;
  }) => Promise<void>;
  cancelInFlight: () => void;
};

export function buildReportVersionRunsQueryKey(
  stockCode: string,
  page: number,
  limit: number = REPORT_VERSION_COMPARE_RUN_PAGE_SIZE,
): ReportVersionCompareQueryKey {
  return ['report-version-compare', 'runs', stockCode, page, limit] as const;
}

export function buildReportVersionCompareQueryKey(
  stockCode: string,
  baseRunId: string,
  targetRunId: string,
): ReportVersionCompareQueryKey {
  return ['report-version-compare', 'compare', stockCode, baseRunId, targetRunId] as const;
}

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfReportVersionCompareCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(REPORT_VERSION_COMPARE_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

function sameQueryKey(
  left: ReportVersionCompareQueryKey,
  right: ReportVersionCompareQueryKey,
): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function normalizeStockIdentity(value: string): string {
  return value.trim().toUpperCase();
}

export async function fetchReportVersionRuns(args: {
  stockCode: string;
  page: number;
  limit?: number;
  signal?: AbortSignal;
  stillActive?: () => boolean;
}): Promise<ReportVersionRunListResponse> {
  const stillActive = args.stillActive ?? (() => true);
  const limit = args.limit ?? REPORT_VERSION_COMPARE_RUN_PAGE_SIZE;
  try {
    throwIfReportVersionCompareCancelled(args.signal, stillActive());
    const response = await reportVersionCompareApi.listRuns({
      stockCode: args.stockCode,
      page: args.page,
      limit,
      signal: args.signal,
    });
    throwIfReportVersionCompareCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfReportVersionCompareCancelled(args.signal, stillActive());
    throw error;
  }
}

export async function fetchReportVersionCompare(args: {
  stockCode: string;
  baseRunId: string;
  targetRunId: string;
  signal?: AbortSignal;
  stillActive?: () => boolean;
}): Promise<ReportVersionCompareResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfReportVersionCompareCancelled(args.signal, stillActive());
    const response = await reportVersionCompareApi.compare({
      stockCode: args.stockCode,
      baseRunId: args.baseRunId,
      targetRunId: args.targetRunId,
      signal: args.signal,
    });
    throwIfReportVersionCompareCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfReportVersionCompareCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useReportVersionCompareQueries(): UseReportVersionCompareQueriesResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [runs, setRuns] = useState<ReportVersionRunItem[]>([]);
  const [totalRuns, setTotalRuns] = useState(0);
  const [runPage, setRunPage] = useState(1);
  const [loadedStockCode, setLoadedStockCode] = useState<string | null>(null);
  const [hasLoadedRuns, setHasLoadedRuns] = useState(false);
  const [result, setResult] = useState<ReportVersionCompareResponse | null>(null);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [failedOperation, setFailedOperation] = useState<FailedOperation | null>(null);

  const requestIdRef = useRef(0);
  const liveKeysRef = useRef<ReportVersionCompareQueryKey[]>([]);

  const discardExactQuery = useCallback((key: ReportVersionCompareQueryKey) => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: key, exact: true },
      REPORT_VERSION_COMPARE_CANCEL,
    );
    client.removeQueries({ queryKey: key, exact: true });
    liveKeysRef.current = liveKeysRef.current.filter((live) => !sameQueryKey(live, key));
  }, []);

  const discardLiveKeys = useCallback((
    predicate: (key: ReportVersionCompareQueryKey) => boolean,
  ) => {
    for (const live of [...liveKeysRef.current]) {
      if (predicate(live)) discardExactQuery(live);
    }
  }, [discardExactQuery]);

  const loadRuns = useCallback(async ({
    stockCode,
    page,
    append,
  }: {
    stockCode: string;
    page: number;
    append: boolean;
  }) => {
    const code = stockCode.trim();
    if (!code) return;

    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const key = buildReportVersionRunsQueryKey(
      code,
      page,
      REPORT_VERSION_COMPARE_RUN_PAGE_SIZE,
    );

    setComparing(false);
    if (append) {
      setLoadingMore(true);
      setLoadingRuns(false);
    } else {
      setLoadingRuns(true);
      setLoadingMore(false);
    }
    setError(null);
    setFailedOperation(null);
    if (!append) setResult(null);

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    // A valid list also exact-removes the sibling compare family.
    discardLiveKeys(() => true);
    liveKeysRef.current = [...liveKeysRef.current, key];

    try {
      const response = await queryClientRef.current.fetchQuery({
        queryKey: key,
        queryFn: ({ signal }) => fetchReportVersionRuns({
          stockCode: code,
          page,
          limit: REPORT_VERSION_COMPARE_RUN_PAGE_SIZE,
          signal,
          stillActive: () => requestIdRef.current === requestId,
        }),
        ...REPORT_VERSION_COMPARE_QUERY_SCHEDULE,
      });
      if (requestIdRef.current !== requestId) return;
      if (append) {
        setRuns((current) => {
          const byId = new Map(current.map((run) => [run.runId, run]));
          for (const run of response.items ?? []) byId.set(run.runId, run);
          return [...byId.values()];
        });
      } else {
        setRuns(response.items ?? []);
      }
      setLoadedStockCode(normalizeStockIdentity(response.stockCode || code));
      setTotalRuns(response.total);
      setRunPage(response.page);
      setHasLoadedRuns(true);
    } catch (err) {
      if (requestIdRef.current !== requestId || isCancelledError(err)) return;
      if (!append) {
        setRuns([]);
        setTotalRuns(0);
        setLoadedStockCode(null);
        setHasLoadedRuns(true);
      }
      setError(getParsedApiError(err));
      setFailedOperation({
        kind: 'list',
        stockCode: code,
        page,
        append,
      });
    } finally {
      if (requestIdRef.current === requestId) {
        if (append) setLoadingMore(false);
        else setLoadingRuns(false);
      }
    }
  }, [discardLiveKeys]);

  const compare = useCallback(async ({
    stockCode,
    baseRunId,
    targetRunId,
  }: {
    stockCode: string;
    baseRunId: string;
    targetRunId: string;
  }) => {
    if (!stockCode || !baseRunId || !targetRunId) return;
    if (baseRunId === targetRunId) {
      setError(null);
      setResult(null);
      return;
    }

    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const key = buildReportVersionCompareQueryKey(stockCode, baseRunId, targetRunId);

    setLoadingRuns(false);
    setLoadingMore(false);
    setComparing(true);
    setError(null);
    setFailedOperation(null);

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    // A valid compare also exact-removes the sibling list family.
    discardLiveKeys(() => true);
    liveKeysRef.current = [...liveKeysRef.current, key];

    try {
      const response = await queryClientRef.current.fetchQuery({
        queryKey: key,
        queryFn: ({ signal }) => fetchReportVersionCompare({
          stockCode,
          baseRunId,
          targetRunId,
          signal,
          stillActive: () => requestIdRef.current === requestId,
        }),
        ...REPORT_VERSION_COMPARE_QUERY_SCHEDULE,
      });
      if (requestIdRef.current !== requestId) return;
      setResult(response);
    } catch (err) {
      if (requestIdRef.current !== requestId || isCancelledError(err)) return;
      setResult(null);
      setError(getParsedApiError(err));
      setFailedOperation({
        kind: 'compare',
        stockCode,
        baseRunId,
        targetRunId,
      });
    } finally {
      if (requestIdRef.current === requestId) {
        setComparing(false);
      }
    }
  }, [discardLiveKeys]);

  const cancelInFlight = useCallback(() => {
    requestIdRef.current += 1;
    discardLiveKeys(() => true);
    setRuns([]);
    setTotalRuns(0);
    setRunPage(1);
    setLoadedStockCode(null);
    setHasLoadedRuns(false);
    setResult(null);
    setError(null);
    setFailedOperation(null);
    setLoadingRuns(false);
    setLoadingMore(false);
    setComparing(false);
  }, [discardLiveKeys]);

  useEffect(() => {
    return () => {
      requestIdRef.current += 1;
      discardLiveKeys(() => true);
    };
  }, [discardLiveKeys]);

  return {
    runs,
    totalRuns,
    runPage,
    loadedStockCode,
    hasLoadedRuns,
    result,
    loadingRuns,
    loadingMore,
    comparing,
    error,
    failedOperation,
    loadRuns,
    compare,
    cancelInFlight,
  };
}
