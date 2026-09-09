// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings investment-framework current GET.
// Do not import this hook from Shell, App, SettingsPage, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { investmentFrameworkApi } from '../api/investmentFramework';
import type { InvestmentFrameworkResponse } from '../types/investmentFramework';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const INVESTMENT_FRAMEWORK_CURRENT_CANCEL = { silent: true, revert: false } as const;

/** Readonly two-element key. Never prefix-cancel or prefix-remove `['investment-framework']`. */
export const INVESTMENT_FRAMEWORK_CURRENT_QUERY_KEY = ['investment-framework', 'current'] as const;

/** Previous card effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const INVESTMENT_FRAMEWORK_CURRENT_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type InvestmentFrameworkCurrentLoadResult = {
  framework: InvestmentFrameworkResponse | null;
  exists: boolean;
};

export type UseInvestmentFrameworkQueryResult = {
  framework: InvestmentFrameworkResponse | null;
  exists: boolean;
  isLoading: boolean;
  loadError: ParsedApiError | null;
  load: () => Promise<InvestmentFrameworkCurrentLoadResult | undefined>;
  /** Card-owned create/update/deactivate/remove patches display state without a re-GET. */
  setFramework: Dispatch<SetStateAction<InvestmentFrameworkResponse | null>>;
  setExists: Dispatch<SetStateAction<boolean>>;
};

const MISSING_INVESTMENT_FRAMEWORK: InvestmentFrameworkCurrentLoadResult = {
  framework: null,
  exists: false,
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfInvestmentFrameworkCurrentCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(INVESTMENT_FRAMEWORK_CURRENT_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

function isInvestmentFrameworkMissingError(error: unknown): boolean {
  const parsed = getParsedApiError(error);
  return parsed.status === 404 || parsed.code === 'investment_framework_not_found';
}

export async function fetchInvestmentFrameworkCurrent(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<InvestmentFrameworkCurrentLoadResult> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfInvestmentFrameworkCurrentCancelled(args.signal, stillActive());
    const current = await investmentFrameworkApi.get();
    throwIfInvestmentFrameworkCurrentCancelled(args.signal, stillActive());
    return { framework: current, exists: true };
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfInvestmentFrameworkCurrentCancelled(args.signal, stillActive());
    if (isInvestmentFrameworkMissingError(error)) {
      return MISSING_INVESTMENT_FRAMEWORK;
    }
    throw error;
  }
}

export function useInvestmentFrameworkQuery(): UseInvestmentFrameworkQueryResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [framework, setFramework] = useState<InvestmentFrameworkResponse | null>(null);
  const [exists, setExists] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);

  const requestIdRef = useRef(0);

  const discardExactInvestmentFrameworkCurrentQuery = useCallback(() => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: INVESTMENT_FRAMEWORK_CURRENT_QUERY_KEY, exact: true },
      INVESTMENT_FRAMEWORK_CURRENT_CANCEL,
    );
    client.removeQueries({ queryKey: INVESTMENT_FRAMEWORK_CURRENT_QUERY_KEY, exact: true });
  }, []);

  const load = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;

    setLoadError(null);
    setIsLoading(true);

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactInvestmentFrameworkCurrentQuery();

    try {
      const next = await queryClientRef.current.fetchQuery({
        queryKey: INVESTMENT_FRAMEWORK_CURRENT_QUERY_KEY,
        queryFn: ({ signal }) => fetchInvestmentFrameworkCurrent({
          signal,
          stillActive,
        }),
        ...INVESTMENT_FRAMEWORK_CURRENT_QUERY_SCHEDULE,
      });
      if (!stillActive()) return undefined;
      setFramework(next.framework);
      setExists(next.exists);
      return next;
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return undefined;
      setLoadError(getParsedApiError(err));
      return undefined;
    } finally {
      if (stillActive()) {
        setIsLoading(false);
      }
    }
  }, [discardExactInvestmentFrameworkCurrentQuery]);

  useEffect(() => {
    void load();
    return () => {
      requestIdRef.current += 1;
      discardExactInvestmentFrameworkCurrentQuery();
    };
  }, [load, discardExactInvestmentFrameworkCurrentQuery]);

  return {
    framework,
    exists,
    isLoading,
    loadError,
    load,
    setFramework,
    setExists,
  };
}
