// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// TanStack Query schedule adapter for the AlphaSift screen-task poll loop.
// Schedule only: the poll body (status machine, error classification, state
// writes, task teardown) stays in the page, so this migration cannot change it.

import { useQuery } from '@tanstack/react-query';

/** Stable query key root for screen-task polling. */
export const SCREEN_TASK_POLL_QUERY_KEY_ROOT = ['screening', 'task-poll'] as const;

export type ScreenTaskPollResult = {
  ok: true;
};

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
  poll: (isActive: () => boolean) => Promise<void>;
  /**
   * Passed in by the page (``SCREEN_TASK_POLL_INTERVAL_MS``) so this hook does
   * not import from ``components/`` against the architecture direction guard.
   */
  intervalMs: number;
};

/**
 * Parity with the previous self-scheduling `setTimeout` chain:
 * - First poll fires immediately on task start (query mounts enabled).
 * - Each subsequent poll fires `intervalMs` after the
 *   previous one settles; TanStack schedules `refetchInterval` after a fetch
 *   completes, so polls never overlap, matching the chained timeout.
 * - The loop ends when the page clears the task id (`enabled` drops), which is
 *   the same teardown path `finishTask()` always drove via `setActiveTaskId`.
 * - Recoverable poll errors are swallowed inside `poll`, so the query stays
 *   "successful" and the interval keeps running — the previous catch branch.
 * - `refetchIntervalInBackground: true` keeps hidden-tab polling, matching
 *   `window.setTimeout`. `retry: false`, `staleTime: 0`, and
 *   `networkMode: 'always'` preserve single-attempt, always-fetch behavior.
 * - The `let active = true` unmount guard becomes the abort signal.
 */
export function useScreenTaskPollQuery({
  taskId,
  restartKey,
  poll,
  intervalMs,
}: UseScreenTaskPollQueryOptions) {
  return useQuery({
    queryKey: [...SCREEN_TASK_POLL_QUERY_KEY_ROOT, taskId, ...restartKey],
    enabled: taskId !== null,
    queryFn: async ({ signal }): Promise<ScreenTaskPollResult> => {
      await poll(() => !signal.aborted);
      return { ok: true };
    },
    refetchInterval: intervalMs,
    refetchIntervalInBackground: true,
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 0,
    networkMode: 'always',
  });
}
