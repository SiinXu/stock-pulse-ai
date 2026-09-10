// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings generation-backend saved GET and draft preview POST.
// Do not import this hook from Shell, App, SettingsPage, first-paint barrels,
// LLMChannelEditor, FirstRunWizard, Local Models files, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { systemConfigApi } from '../api/systemConfig';
import type { GenerationBackendStatusResponse, SystemConfigUpdateItem } from '../types/systemConfig';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const GENERATION_BACKEND_STATUS_CANCEL = { silent: true, revert: false } as const;

/** Readonly three-element saved key. Never prefix-cancel or prefix-remove `['generation-backend']`. */
export const GENERATION_BACKEND_SAVED_STATUS_QUERY_KEY = ['generation-backend', 'status', 'saved'] as const;

/** Previous panel effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const GENERATION_BACKEND_STATUS_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

/** Subsequent identity changes wait this long; the first mount load is immediate. */
export const GENERATION_BACKEND_STATUS_PREVIEW_DEBOUNCE_MS = 500;

export type GenerationBackendRequestItem = Pick<SystemConfigUpdateItem, 'key' | 'value'>;

export type GenerationBackendPreviewStatusQueryKey = readonly [
  'generation-backend',
  'status',
  'preview',
  string,
  string,
];

export type GenerationBackendStatusQueryKey =
  | typeof GENERATION_BACKEND_SAVED_STATUS_QUERY_KEY
  | GenerationBackendPreviewStatusQueryKey;

export type UseGenerationBackendStatusQueryResult = {
  status: GenerationBackendStatusResponse | null;
  isLoading: boolean;
  error: ParsedApiError | null;
  load: () => Promise<GenerationBackendStatusResponse | undefined>;
  /** Smoke patches display state without a Query write / re-GET. */
  setStatus: Dispatch<SetStateAction<GenerationBackendStatusResponse | null>>;
  setError: Dispatch<SetStateAction<ParsedApiError | null>>;
  /** Bump generation and drop loading so an in-flight GET/preview cannot overwrite smoke rows. */
  abandonLiveLoad: () => void;
};

export function buildGenerationBackendPreviewStatusQueryKey(
  fingerprint: string,
  maskToken: string,
): GenerationBackendPreviewStatusQueryKey {
  return ['generation-backend', 'status', 'preview', fingerprint, maskToken] as const;
}

export function buildGenerationBackendStatusQueryKey(
  items: readonly GenerationBackendRequestItem[],
  maskToken: string,
): GenerationBackendStatusQueryKey {
  if (items.length === 0) {
    return GENERATION_BACKEND_SAVED_STATUS_QUERY_KEY;
  }
  return buildGenerationBackendPreviewStatusQueryKey(JSON.stringify(items), maskToken);
}

function sameQueryKey(
  left: GenerationBackendStatusQueryKey,
  right: GenerationBackendStatusQueryKey,
): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfGenerationBackendStatusCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(GENERATION_BACKEND_STATUS_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchGenerationBackendStatus(args: {
  items: readonly GenerationBackendRequestItem[];
  maskToken: string;
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = { items: [], maskToken: '' }): Promise<GenerationBackendStatusResponse> {
  const stillActive = args.stillActive ?? (() => true);
  const requestItems = args.items.map((item) => ({ key: item.key, value: item.value }));
  try {
    throwIfGenerationBackendStatusCancelled(args.signal, stillActive());
    const response = requestItems.length > 0
      ? await systemConfigApi.previewGenerationBackendStatus({
        items: requestItems,
        maskToken: args.maskToken,
      })
      : await systemConfigApi.getGenerationBackendStatus();
    throwIfGenerationBackendStatusCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfGenerationBackendStatusCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useGenerationBackendStatusQuery(
  items: readonly GenerationBackendRequestItem[],
  maskToken: string,
): UseGenerationBackendStatusQueryResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [status, setStatus] = useState<GenerationBackendStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);

  const requestIdRef = useRef(0);
  const liveKeyRef = useRef<GenerationBackendStatusQueryKey | null>(null);
  const didInitialRefreshRef = useRef(false);

  const requestItems = useMemo(
    () => items.map((item) => ({ key: item.key, value: item.value })),
    [items],
  );

  const discardExactQuery = useCallback((key: GenerationBackendStatusQueryKey) => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: key, exact: true },
      GENERATION_BACKEND_STATUS_CANCEL,
    );
    client.removeQueries({ queryKey: key, exact: true });
  }, []);

  const load = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const stillActive = () => requestIdRef.current === requestId;
    const key = buildGenerationBackendStatusQueryKey(requestItems, maskToken);

    setError(null);
    setIsLoading(true);

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    // Key-changing loads exact-remove the previous live key, then the successor key.
    const previous = liveKeyRef.current;
    if (previous) discardExactQuery(previous);
    if (!previous || !sameQueryKey(previous, key)) {
      discardExactQuery(key);
    }
    liveKeyRef.current = key;

    try {
      const next = await queryClientRef.current.fetchQuery({
        queryKey: key,
        queryFn: ({ signal }) => fetchGenerationBackendStatus({
          items: requestItems,
          maskToken,
          signal,
          stillActive,
        }),
        ...GENERATION_BACKEND_STATUS_QUERY_SCHEDULE,
      });
      if (!stillActive()) return undefined;
      setStatus(next);
      return next;
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return undefined;
      setStatus(null);
      setError(getParsedApiError(err));
      return undefined;
    } finally {
      if (stillActive()) {
        setIsLoading(false);
      }
    }
  }, [discardExactQuery, maskToken, requestItems]);

  const abandonLiveLoad = useCallback(() => {
    requestIdRef.current += 1;
    setIsLoading(false);
    setError(null);
  }, []);

  useEffect(() => {
    // Refresh the saved status immediately on mount, but debounce subsequent
    // identity-driven loads so typing in the editor doesn't fire a preview
    // request per keystroke. Cleanup only clears the timer; it does not bump
    // generation or cancel in-flight HTTP (an in-flight completion may still
    // apply during the debounce window).
    if (!didInitialRefreshRef.current) {
      didInitialRefreshRef.current = true;
      void load();
      return;
    }
    const timer = window.setTimeout(() => {
      void load();
    }, GENERATION_BACKEND_STATUS_PREVIEW_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => () => {
    requestIdRef.current += 1;
    if (liveKeyRef.current) {
      discardExactQuery(liveKeyRef.current);
      liveKeyRef.current = null;
    }
  }, [discardExactQuery]);

  return {
    status,
    isLoading,
    error,
    load,
    setStatus,
    setError,
    abandonLiveLoad,
  };
}
