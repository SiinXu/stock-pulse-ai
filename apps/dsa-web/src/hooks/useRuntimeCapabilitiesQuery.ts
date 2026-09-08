// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings runtime-capabilities inventory
// GET and Agent deployment-models GET. Do not import this hook from Shell,
// App, SettingsPage, first-paint barrels, or hooks/index.ts.

import { CancelledError, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { agentApi, type AgentModelDeployment, type AgentModelsResponse } from '../api/agent';
import { capabilitiesApi, type CapabilityListResponse } from '../api/capabilities';
import { getParsedApiError, type ParsedApiError } from '../api/error';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const RUNTIME_CAPABILITIES_CANCEL = { silent: true, revert: false } as const;

/** Readonly two-element key. Never prefix-cancel or prefix-remove `['capabilities']`. */
export const CAPABILITIES_RUNTIME_QUERY_KEY = ['capabilities', 'runtime'] as const;

/** Readonly two-element key. Never prefix-cancel or prefix-remove `['agent-models']`. */
export const AGENT_MODELS_QUERY_KEY = ['agent-models', 'deployments'] as const;

/** Previous panel effects never retried, never polled, never focus-refetched, and always called axios offline. */
export const RUNTIME_CAPABILITIES_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

export type UseRuntimeCapabilitiesQueryResult = {
  capabilities: CapabilityListResponse | null;
  capabilitiesLoading: boolean;
  capabilitiesError: ParsedApiError | null;
  models: AgentModelDeployment[] | null;
  modelsLoading: boolean;
  modelsError: ParsedApiError | null;
  reloadCapabilities: () => Promise<void>;
  reloadModels: () => Promise<void>;
};

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfRuntimeCapabilitiesCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(RUNTIME_CAPABILITIES_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchCapabilitiesRuntime(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<CapabilityListResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfRuntimeCapabilitiesCancelled(args.signal, stillActive());
    const next = await capabilitiesApi.list();
    throwIfRuntimeCapabilitiesCancelled(args.signal, stillActive());
    return next;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfRuntimeCapabilitiesCancelled(args.signal, stillActive());
    throw error;
  }
}

export async function fetchAgentModels(args: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
} = {}): Promise<AgentModelsResponse> {
  const stillActive = args.stillActive ?? (() => true);
  try {
    throwIfRuntimeCapabilitiesCancelled(args.signal, stillActive());
    const next = await agentApi.getModels();
    throwIfRuntimeCapabilitiesCancelled(args.signal, stillActive());
    return next;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfRuntimeCapabilitiesCancelled(args.signal, stillActive());
    throw error;
  }
}

export function useRuntimeCapabilitiesQuery(): UseRuntimeCapabilitiesQueryResult {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  const [capabilities, setCapabilities] = useState<CapabilityListResponse | null>(null);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(true);
  const [capabilitiesError, setCapabilitiesError] = useState<ParsedApiError | null>(null);
  const [models, setModels] = useState<AgentModelDeployment[] | null>(null);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelsError, setModelsError] = useState<ParsedApiError | null>(null);

  const capabilitiesRequestIdRef = useRef(0);
  const modelsRequestIdRef = useRef(0);

  const discardExactCapabilitiesQuery = useCallback(() => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: CAPABILITIES_RUNTIME_QUERY_KEY, exact: true },
      RUNTIME_CAPABILITIES_CANCEL,
    );
    client.removeQueries({ queryKey: CAPABILITIES_RUNTIME_QUERY_KEY, exact: true });
  }, []);

  const discardExactModelsQuery = useCallback(() => {
    const client = queryClientRef.current;
    void client.cancelQueries(
      { queryKey: AGENT_MODELS_QUERY_KEY, exact: true },
      RUNTIME_CAPABILITIES_CANCEL,
    );
    client.removeQueries({ queryKey: AGENT_MODELS_QUERY_KEY, exact: true });
  }, []);

  const reloadCapabilities = useCallback(async () => {
    const requestId = capabilitiesRequestIdRef.current + 1;
    capabilitiesRequestIdRef.current = requestId;
    const stillActive = () => capabilitiesRequestIdRef.current === requestId;

    setCapabilitiesLoading(true);
    setCapabilitiesError(null);

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactCapabilitiesQuery();

    try {
      const next = await queryClientRef.current.fetchQuery({
        queryKey: CAPABILITIES_RUNTIME_QUERY_KEY,
        queryFn: ({ signal }) => fetchCapabilitiesRuntime({
          signal,
          stillActive,
        }),
        ...RUNTIME_CAPABILITIES_QUERY_SCHEDULE,
      });
      if (!stillActive()) return;
      setCapabilities(next);
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return;
      setCapabilitiesError(getParsedApiError(err));
    } finally {
      if (stillActive()) {
        setCapabilitiesLoading(false);
      }
    }
  }, [discardExactCapabilitiesQuery]);

  const reloadModels = useCallback(async () => {
    const requestId = modelsRequestIdRef.current + 1;
    modelsRequestIdRef.current = requestId;
    const stillActive = () => modelsRequestIdRef.current === requestId;

    setModelsLoading(true);
    setModelsError(null);

    // Same-key refresh must cancel+remove before fetchQuery (Query 5 joins a cancelled retryer).
    discardExactModelsQuery();

    try {
      const next = await queryClientRef.current.fetchQuery({
        queryKey: AGENT_MODELS_QUERY_KEY,
        queryFn: ({ signal }) => fetchAgentModels({
          signal,
          stillActive,
        }),
        ...RUNTIME_CAPABILITIES_QUERY_SCHEDULE,
      });
      if (!stillActive()) return;
      setModels(next.models);
    } catch (err) {
      if (!stillActive() || isCancelledError(err)) return;
      setModelsError(getParsedApiError(err));
    } finally {
      if (stillActive()) {
        setModelsLoading(false);
      }
    }
  }, [discardExactModelsQuery]);

  useEffect(() => {
    void reloadCapabilities();
    void reloadModels();
    return () => {
      capabilitiesRequestIdRef.current += 1;
      modelsRequestIdRef.current += 1;
      discardExactCapabilitiesQuery();
      discardExactModelsQuery();
    };
  }, [
    reloadCapabilities,
    reloadModels,
    discardExactCapabilitiesQuery,
    discardExactModelsQuery,
  ]);

  return {
    capabilities,
    capabilitiesLoading,
    capabilitiesError,
    models,
    modelsLoading,
    modelsError,
    reloadCapabilities,
    reloadModels,
  };
}
