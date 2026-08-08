// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useQuery } from '@tanstack/react-query';

/** Stable query key root for skill-outcome performance loads. */
export const SKILL_OUTCOMES_QUERY_KEY_ROOT = ['skill-outcomes', 'performance'] as const;

export function buildSkillOutcomesQueryKey(reloadToken: number): readonly unknown[] {
  return [...SKILL_OUTCOMES_QUERY_KEY_ROOT, reloadToken] as const;
}

export type SkillOutcomesQueryResult = {
  ok: true;
};

type UseSkillOutcomesQueryOptions = {
  reloadToken: number;
  /** Always invoked as initial-mode load (matches previous useEffect([load, reloadToken])). */
  loadInitial: () => Promise<void>;
  onCancelInFlight?: () => void;
};

/**
 * TanStack Query schedule adapter for Skill Outcomes page data.
 *
 * Parity with the previous mount/reloadToken useEffect:
 * - No interval poll, no window-focus refetch.
 * - Manual icon refresh stays page-owned (`load('refresh')`) and is not this key.
 * - Errors remain on the page error surface (`retry: false`).
 */
export function useSkillOutcomesQuery({
  reloadToken,
  loadInitial,
  onCancelInFlight,
}: UseSkillOutcomesQueryOptions) {
  return useQuery({
    queryKey: buildSkillOutcomesQueryKey(reloadToken),
    queryFn: async ({ signal }): Promise<SkillOutcomesQueryResult> => {
      const onAbort = () => {
        onCancelInFlight?.();
      };
      if (signal.aborted) {
        onAbort();
        return { ok: true };
      }
      signal.addEventListener('abort', onAbort);
      try {
        await loadInitial();
        return { ok: true };
      } finally {
        signal.removeEventListener('abort', onAbort);
      }
    },
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export default useSkillOutcomesQuery;
