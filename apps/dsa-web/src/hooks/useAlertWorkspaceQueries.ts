// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useQuery } from '@tanstack/react-query';

export const ALERT_RULES_QUERY_KEY_ROOT = ['alerts', 'rules'] as const;
export const ALERT_TRIGGERS_QUERY_KEY_ROOT = ['alerts', 'triggers'] as const;
export const ALERT_NOTIFICATIONS_QUERY_KEY_ROOT = ['alerts', 'notifications'] as const;

export type AlertRulesQueryKeyInput = {
  scope: string;
  enabledFilter: string;
  alertTypeFilter: string;
  page: number;
};

export function buildAlertRulesQueryKey(input: AlertRulesQueryKeyInput): readonly unknown[] {
  return [
    ...ALERT_RULES_QUERY_KEY_ROOT,
    input.scope,
    input.enabledFilter,
    input.alertTypeFilter,
    input.page,
  ] as const;
}

export function buildAlertTriggersQueryKey(page: number): readonly unknown[] {
  return [...ALERT_TRIGGERS_QUERY_KEY_ROOT, page] as const;
}

export function buildAlertNotificationsQueryKey(input: {
  page: number;
  channelFilter: string;
  successFilter: string;
}): readonly unknown[] {
  return [
    ...ALERT_NOTIFICATIONS_QUERY_KEY_ROOT,
    input.page,
    input.channelFilter,
    input.successFilter,
  ] as const;
}

type ScheduleOptions = {
  queryKey: readonly unknown[];
  load: () => Promise<unknown>;
  onCancelInFlight?: () => void;
  enabled?: boolean;
};

/**
 * Shared schedule helper for Alerts workspace list loads.
 * No poll / no focus refetch — matches prior useEffect-only scheduling.
 */
function useAlertListSchedule({
  queryKey,
  load,
  onCancelInFlight,
  enabled = true,
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

export function useAlertRulesQuery(options: ScheduleOptions) {
  return useAlertListSchedule(options);
}

export function useAlertTriggersQuery(options: ScheduleOptions) {
  return useAlertListSchedule(options);
}

export function useAlertNotificationsQuery(options: ScheduleOptions) {
  return useAlertListSchedule(options);
}
