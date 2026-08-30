// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// TanStack Query schedule adapters for the Research Analysis Workbench mount loads.
// Schedule only: each loader keeps its own state writes and error handling in
// the page, so this migration cannot change either.

import { useQuery } from '@tanstack/react-query';

/** Stable query keys for the two workbench mount loads. */
export const WORKBENCH_SETUP_STATUS_QUERY_KEY = [
  'research-analysis-workbench',
  'setup-status',
] as const;
export const WORKBENCH_ANALYSIS_SKILLS_QUERY_KEY = [
  'research-analysis-workbench',
  'analysis-skills',
] as const;

export type WorkbenchMountLoadResult = {
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
function useWorkbenchMountLoad(
  queryKey: readonly unknown[],
  load: (isActive: () => boolean) => Promise<void>,
) {
  return useQuery({
    queryKey,
    queryFn: async ({ signal }): Promise<WorkbenchMountLoadResult> => {
      await load(() => !signal.aborted);
      return { ok: true };
    },
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 0,
    networkMode: 'always',
  });
}

/** Schedules the setup-status load. */
export function useWorkbenchSetupStatusQuery(
  load: (isActive: () => boolean) => Promise<void>,
) {
  return useWorkbenchMountLoad(WORKBENCH_SETUP_STATUS_QUERY_KEY, load);
}

/** Schedules the analysis-skills load. */
export function useWorkbenchAnalysisSkillsQuery(
  load: (isActive: () => boolean) => Promise<void>,
) {
  return useWorkbenchMountLoad(WORKBENCH_ANALYSIS_SKILLS_QUERY_KEY, load);
}
