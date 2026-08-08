// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useQuery } from '@tanstack/react-query';

export const STOCK_DETAILS_QUOTE_QUERY_KEY_ROOT = ['stocks', 'quote'] as const;
export const STOCK_DETAILS_HISTORY_QUERY_KEY_ROOT = ['stocks', 'daily-history'] as const;

export function buildStockDetailsQuoteQueryKey(code: string): readonly unknown[] {
  return [...STOCK_DETAILS_QUOTE_QUERY_KEY_ROOT, code] as const;
}

export function buildStockDetailsHistoryQueryKey(
  code: string,
  days: number,
): readonly unknown[] {
  return [...STOCK_DETAILS_HISTORY_QUERY_KEY_ROOT, code, days] as const;
}

type ScheduleOptions = {
  queryKey: readonly unknown[];
  enabled: boolean;
  load: () => Promise<void>;
  onCancelInFlight?: () => void;
};

/**
 * Shared schedule for Stock Details quote/history loads.
 * No poll / no focus refetch — matches prior code-change useEffects.
 */
function useStockDetailsSchedule({
  queryKey,
  enabled,
  load,
  onCancelInFlight,
}: ScheduleOptions) {
  return useQuery({
    queryKey,
    enabled,
    queryFn: async ({ signal }) => {
      const onAbort = () => {
        onCancelInFlight?.();
      };
      if (signal.aborted) {
        onAbort();
        return { ok: true as const };
      }
      signal.addEventListener('abort', onAbort);
      try {
        await load();
        return { ok: true as const };
      } finally {
        signal.removeEventListener('abort', onAbort);
      }
    },
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export function useStockDetailsQuoteQuery(options: ScheduleOptions) {
  return useStockDetailsSchedule(options);
}

export function useStockDetailsHistoryQuery(options: ScheduleOptions) {
  return useStockDetailsSchedule(options);
}
