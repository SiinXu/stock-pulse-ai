// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// TanStack Query schedule adapter for the AlphaSift screen-task poll loop.
// Schedule only: the poll body (status machine, error classification, state
// writes, task teardown) stays in the page, so this migration cannot change it.

import { useQuery } from '@tanstack/react-query';

/** Stable query key root for screen-task polling. */
export const SCREEN_TASK_POLL_QUERY_KEY_ROOT = ['screen', 'poll'] as const;

export type ScreenTaskPollResult = true;

type UseScreenTaskPollQueryOptions = {
  /** Null disables polling entirely — the previous `if (!activeTaskId) return`. */
  taskId: string | null;
  /**
   * Key extension mirroring the previous effect deps (`language` etc.): when
   * one changes, the old loop is torn down and a fresh one starts immediately,
   * exactly as the effect cleanup + re-run did.
   */
  restartKey: readonly unknown[];
  /** One poll step. Must swallow recoverable errors, as the effect body did. */
  poll: (isActive: () => boolean) => Promise<true>;
  /**
   * Passed in by the page (``SCREEN_TASK_POLL_INTERVAL_MS``) so this hook does
   * not import from ``components/`` against the architecture direction guard.
   */
  intervalMs: number;
};

/**
 * Parity with the previous self-scheduling `setTimeout` chain:
 * - First poll fires immediately on task start (query mounts enabled).
 * - Each subsequent poll fires `intervalMs` after the previous one settles.
 * - Terminal `finishTask()` nulls the task id and drops `enabled`.
 * - Recoverable errors are swallowed inside `poll` so the interval continues.
 * - Hidden-tab, no retry, no focus refetch, always-fetch, abort = unmount guard.
 * - `staleTime` is left at the TanStack default of 0 (no TTL widening).
 */
export function useScreenTaskPollQuery({
  taskId,
  restartKey,
  poll,
  intervalMs,
}: UseScreenTaskPollQueryOptions) {
  'use no memo';
  return useQuery({
    queryKey: [...SCREEN_TASK_POLL_QUERY_KEY_ROOT, taskId, ...restartKey],
    enabled: taskId !== null,
    queryFn: ({ signal }) => poll(() => !signal.aborted),
    refetchInterval: intervalMs,
    refetchIntervalInBackground: true,
    retry: false,
    refetchOnWindowFocus: false,
    networkMode: 'always',
  });
}
