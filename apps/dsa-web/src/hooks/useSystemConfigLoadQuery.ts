// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Imperative fetchQuery schedule for Settings system-config GET loads.
// Do not import this module from Shell, App, first-paint barrels, or hooks/index.ts.

import { CancelledError, type QueryClient } from '@tanstack/react-query';
import { systemConfigApi } from '../api/systemConfig';
import type { SystemConfigResponse } from '../types/systemConfig';

/** Query 5 cancelQueries defaults `revert: true`; silent+non-revert matches cancelRefetch. */
export const SYSTEM_CONFIG_LOAD_CANCEL = { silent: true, revert: false } as const;

export const SYSTEM_CONFIG_LOAD_QUERY_KEY = ['settings', 'system-config', 'load'] as const;

/** Previous load() never retried, never polled, never focus-refetched, and always called axios offline. */
export const SYSTEM_CONFIG_LOAD_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
  networkMode: 'always',
} as const;

/**
 * Silent CancelledError skips Query error dispatch and leaves fetchStatus
 * fetching until a same-key successor fetch or exact-key removeQueries.
 */
export function throwIfSystemConfigLoadCancelled(
  signal: AbortSignal | undefined,
  stillActive: boolean,
): void {
  if (signal?.aborted || !stillActive) {
    throw new CancelledError(SYSTEM_CONFIG_LOAD_CANCEL);
  }
}

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

export async function fetchSystemConfigLoad(args?: {
  signal?: AbortSignal;
  stillActive?: () => boolean;
}): Promise<SystemConfigResponse> {
  const stillActive = args?.stillActive ?? (() => true);
  try {
    throwIfSystemConfigLoadCancelled(args?.signal, stillActive());
    const response = await systemConfigApi.getConfig(true);
    throwIfSystemConfigLoadCancelled(args?.signal, stillActive());
    return response;
  } catch (error) {
    if (isCancelledError(error)) throw error;
    throwIfSystemConfigLoadCancelled(args?.signal, stillActive());
    throw error;
  }
}

export function discardSystemConfigLoadQuery(client: QueryClient): void {
  void client.cancelQueries(
    { queryKey: SYSTEM_CONFIG_LOAD_QUERY_KEY, exact: true },
    SYSTEM_CONFIG_LOAD_CANCEL,
  );
  client.removeQueries({ queryKey: SYSTEM_CONFIG_LOAD_QUERY_KEY, exact: true });
}
