// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// TanStack Query schedule adapters for the Chat page mount loads.
// Schedule only: each loader keeps its own state writes and error handling in
// the page, so this migration cannot change either.

import { useQuery } from '@tanstack/react-query';

/** Stable query keys for the two Chat page mount loads. */
export const CHAT_SKILLS_QUERY_KEY = ['chat', 'skills'] as const;
export const CHAT_CONTEXT_COMPRESSION_QUERY_KEY = [
  'chat',
  'context-compression',
] as const;

export type ChatMountLoadResult = {
  ok: true;
};

/**
 * Parity with the previous `let active = true` mount effects:
 * - One run per mount, no interval poll, no window-focus refetch.
 * - `retry: false`, so a failure surfaces exactly once, as before.
 * - `staleTime: 0` and `networkMode: 'always'` keep the previous behavior of
 *   always calling axios, including offline.
 * - The `active` guard becomes the abort signal: the loader is told to stop
 *   writing state, which is what `active = false` did on unmount.
 */
function useChatMountLoad(
  queryKey: readonly unknown[],
  load: (isActive: () => boolean) => Promise<void>,
) {
  return useQuery({
    queryKey,
    queryFn: async ({ signal }): Promise<ChatMountLoadResult> => {
      await load(() => !signal.aborted);
      return { ok: true };
    },
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 0,
    networkMode: 'always',
  });
}

/** Schedules the chat skills load. */
export function useChatSkillsQuery(load: (isActive: () => boolean) => Promise<void>) {
  return useChatMountLoad(CHAT_SKILLS_QUERY_KEY, load);
}

/** Schedules the context-compression setting load. */
export function useChatContextCompressionQuery(
  load: (isActive: () => boolean) => Promise<void>,
) {
  return useChatMountLoad(CHAT_CONTEXT_COMPRESSION_QUERY_KEY, load);
}
