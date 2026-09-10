// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings intelligence sources list GET
// and templates list GET. Do not import this hook from Shell, App,
// SettingsPage, first-paint barrels, Local Models files, generation-backend
// files, Chat, Backtest, Workbench, StockScreening, or hooks/index.ts.
// Display state, mutations, and the items GET stay panel-owned.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef } from 'react';
import {
  intelligenceApi,
  type IntelligenceSourceListResponse,
  type IntelligenceSourceTemplateListResponse,
} from '../api/intelligence';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const INTELLIGENCE_SOURCES_CANCEL = { silent: true, revert: false } as const;

/** Readonly three-element key. Never prefix-cancel or prefix-remove `['intelligence']`. */
export const INTELLIGENCE_SOURCES_LIST_QUERY_KEY = ['intelligence', 'sources', 'list'] as const;

/** Readonly three-element key. Never prefix-cancel or prefix-remove `['intelligence']`. */
export const INTELLIGENCE_TEMPLATES_LIST_QUERY_KEY = ['intelligence', 'templates', 'list'] as const;

/** Previous panel effect never retried, never polled, never focus-refetched, and always called axios offline. */
export const INTELLIGENCE_SOURCES_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type UseIntelligenceSourcesQueryResult = {
  loadSources: () => Promise<IntelligenceSourceListResponse>;
  loadTemplates: () => Promise<IntelligenceSourceTemplateListResponse>;
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfIntelligenceSourcesCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(INTELLIGENCE_SOURCES_CANCEL);
  }
}

export function isIntelligenceSourcesCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchIntelligenceSourcesList(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<IntelligenceSourceListResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfIntelligenceSourcesCancelled(args.signal, stillActive());
    const response = await intelligenceApi.listSources({ pageSize: 100 });
    throwIfIntelligenceSourcesCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isIntelligenceSourcesCancelledError(error)) throw error;
    throwIfIntelligenceSourcesCancelled(args.signal, stillActive());
    throw error;
  }
}

export async function fetchIntelligenceTemplatesList(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<IntelligenceSourceTemplateListResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfIntelligenceSourcesCancelled(args.signal, stillActive());
    const response = await intelligenceApi.listTemplates();
    throwIfIntelligenceSourcesCancelled(args.signal, stillActive());
    return response;
  } catch (error) {
    if (isIntelligenceSourcesCancelledError(error)) throw error;
    throwIfIntelligenceSourcesCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useIntelligenceSourcesQuery(): UseIntelligenceSourcesQueryResult {
  const queryClient = useQueryClient();

  const sourcesRequestIdRef = useRef(0);
  const templatesRequestIdRef = useRef(0);

  const discardExactSourcesQuery = useCallback(() => {
    void queryClient.cancelQueries(
      { queryKey: INTELLIGENCE_SOURCES_LIST_QUERY_KEY, exact: true },
      INTELLIGENCE_SOURCES_CANCEL,
    );
    queryClient.removeQueries({ queryKey: INTELLIGENCE_SOURCES_LIST_QUERY_KEY, exact: true });
  }, [queryClient]);

  const discardExactTemplatesQuery = useCallback(() => {
    void queryClient.cancelQueries(
      { queryKey: INTELLIGENCE_TEMPLATES_LIST_QUERY_KEY, exact: true },
      INTELLIGENCE_SOURCES_CANCEL,
    );
    queryClient.removeQueries({ queryKey: INTELLIGENCE_TEMPLATES_LIST_QUERY_KEY, exact: true });
  }, [queryClient]);

  const loadSources = useCallback(async () => {
    const requestId = sourcesRequestIdRef.current + 1;
    sourcesRequestIdRef.current = requestId;
    const stillActive = () => sourcesRequestIdRef.current === requestId;

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactSourcesQuery();

    return queryClient.fetchQuery({
      queryKey: INTELLIGENCE_SOURCES_LIST_QUERY_KEY,
      queryFn: ({ signal }) => fetchIntelligenceSourcesList({
        signal,
        stillActive,
      }),
      ...INTELLIGENCE_SOURCES_QUERY_SCHEDULE,
    });
  }, [discardExactSourcesQuery, queryClient]);

  const loadTemplates = useCallback(async () => {
    const requestId = templatesRequestIdRef.current + 1;
    templatesRequestIdRef.current = requestId;
    const stillActive = () => templatesRequestIdRef.current === requestId;

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactTemplatesQuery();

    return queryClient.fetchQuery({
      queryKey: INTELLIGENCE_TEMPLATES_LIST_QUERY_KEY,
      queryFn: ({ signal }) => fetchIntelligenceTemplatesList({
        signal,
        stillActive,
      }),
      ...INTELLIGENCE_SOURCES_QUERY_SCHEDULE,
    });
  }, [discardExactTemplatesQuery, queryClient]);

  useEffect(() => () => {
    sourcesRequestIdRef.current += 1;
    templatesRequestIdRef.current += 1;
    discardExactSourcesQuery();
    discardExactTemplatesQuery();
  }, [discardExactSourcesQuery, discardExactTemplatesQuery]);

  return { loadSources, loadTemplates };
}
