// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// TanStack Query schedule adapter for Chat page mount loads.
// Schedule only: load bodies and error surfaces stay in ChatPage.

import { useQuery } from '@tanstack/react-query';

/**
 * Parity with the previous `let active = true` mount effects:
 * one run per mount, no poll, no focus refetch, retry false,
 * staleTime 0, networkMode always. isActive() is !signal.aborted.
 */
export function useChatMountLoad(
  queryKey: readonly unknown[],
  load: (isActive: () => boolean) => Promise<void>,
) {
  return useQuery({
    queryKey,
    queryFn: ({ signal }) => load(() => !signal.aborted).then(() => true),
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 0,
    networkMode: 'always',
  });
}
