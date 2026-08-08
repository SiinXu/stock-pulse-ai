// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useQuery } from '@tanstack/react-query';

/** Query key family for Approvals workspace snapshot + poll schedule. */
export const APPROVALS_WORKSPACE_QUERY_KEY_ROOT = ['approvals', 'workspace'] as const;

export function buildApprovalsWorkspaceQueryKey(language: string): readonly unknown[] {
  return [...APPROVALS_WORKSPACE_QUERY_KEY_ROOT, language] as const;
}

/** Matches the previous hand-rolled setInterval cadence on ApprovalsPage. */
export const APPROVALS_PROPOSALS_REFETCH_INTERVAL_MS = 5_000;

export type ApprovalsWorkspaceQueryResult = {
  ok: true;
};

type UseApprovalsWorkspaceQueryOptions = {
  language: string;
  /**
   * When true, background proposal polling is suspended (auth precondition
   * blocked) — same as the previous `if (actionsBlocked) return` interval guard.
   */
  actionsBlocked: boolean;
  load: () => Promise<void>;
  pollProposals: () => Promise<void>;
};

/**
 * TanStack Query schedule for Approvals workspace.
 *
 * Parity with the previous page effects:
 * - First successful query run uses the full non-background `load()` (rule + list).
 * - Later interval ticks use `pollProposals()` only (5s cadence).
 * - When `actionsBlocked`, `refetchInterval` is disabled (no 401/403 spam).
 * - No window-focus refetch (page never did focus refresh).
 * - Errors stay on the page error surface (`retry: false`).
 */
export function useApprovalsWorkspaceQuery({
  language,
  actionsBlocked,
  load,
  pollProposals,
}: UseApprovalsWorkspaceQueryOptions) {
  const queryKey = buildApprovalsWorkspaceQueryKey(language);

  return useQuery({
    queryKey,
    queryFn: async ({ client }): Promise<ApprovalsWorkspaceQueryResult> => {
      const previous = client.getQueryData<ApprovalsWorkspaceQueryResult>(queryKey);
      if (previous === undefined) {
        await load();
      } else {
        await pollProposals();
      }
      return { ok: true };
    },
    refetchInterval: actionsBlocked ? false : APPROVALS_PROPOSALS_REFETCH_INTERVAL_MS,
    refetchOnWindowFocus: false,
    retry: false,
  });
}

export default useApprovalsWorkspaceQuery;
