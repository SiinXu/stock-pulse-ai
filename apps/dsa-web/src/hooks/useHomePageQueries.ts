// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { alertsApi } from '../api/alerts';
import { decisionSignalsApi } from '../api/decisionSignals';
import { parseApiError, type ParsedApiError } from '../api/error';
import { historyApi } from '../api/history';
import { scheduledTasksApi } from '../api/scheduledTasks';
import { systemConfigApi } from '../api/systemConfig';
import { getTodaysFocus } from '../api/todaysFocus';
import type { HistoryItem, StockReportType } from '../types/analysis';
import type { DecisionSignalItem } from '../types/decisionSignals';
import type { ScheduledTaskTodayItem } from '../types/scheduledTasks';
import type { SetupStatusResponse } from '../types/systemConfig';
import type { TodaysFocusResponse } from '../types/todaysFocus';
import { getBrowserTimezone } from '../utils/browserTimezone';

/** Stable query key for the Home attention pack (mount + manual refresh). */
export const HOME_ATTENTION_QUERY_KEY = ['home', 'attention'] as const;

/** Query key family for Today's Focus. Language is part of identity. */
export const TODAYS_FOCUS_QUERY_KEY_ROOT = ['home', 'todays-focus'] as const;

/** Stable per-language keys so unmount cleanup does not tear down a live observer. */
const TODAYS_FOCUS_QUERY_KEY_ZH = [...TODAYS_FOCUS_QUERY_KEY_ROOT, 'zh'] as const;
const TODAYS_FOCUS_QUERY_KEY_EN = [...TODAYS_FOCUS_QUERY_KEY_ROOT, 'en'] as const;

/** Stable query key for Home setup-status (mount + manual refresh). */
export const HOME_SETUP_STATUS_QUERY_KEY = ['home', 'setup-status'] as const;

const SIGNAL_PAGE_SIZE = 12;
const RECENT_ANALYSIS_LIMIT = 4;
const REASSESSMENT_WINDOW_MS = 24 * 60 * 60 * 1000;
const STOCK_REPORT_TYPES: readonly StockReportType[] = ['simple', 'detailed', 'full', 'brief'];

/** Shared Query options: previous Home effects had no poll, no focus refetch, no retry. */
const HOME_PAGE_QUERY_SCHEDULE = {
  retry: false,
  refetchOnWindowFocus: false,
  staleTime: 0,
} as const;

export function buildTodaysFocusQueryKey(language: string): readonly unknown[] {
  return resolveFocusLanguage(language) === 'zh'
    ? TODAYS_FOCUS_QUERY_KEY_ZH
    : TODAYS_FOCUS_QUERY_KEY_EN;
}

export function resolveFocusLanguage(language: string): 'zh' | 'en' {
  return language === 'zh' ? 'zh' : 'en';
}

export type HomeAttentionAvailability = {
  activeSignals: boolean;
  reassessments: boolean;
  alerts: boolean;
  marketReview: boolean;
  recentAnalyses: boolean;
  scheduledTasks: boolean;
};

export type HomeAttentionData = {
  activeSignals: DecisionSignalItem[];
  activeSignalTotal: number | null;
  dueReassessmentTotal: number | null;
  triggeredAlertTotal: number | null;
  latestMarketReview: HistoryItem | null;
  recentAnalyses: HistoryItem[];
  scheduledTasks: ScheduledTaskTodayItem[];
};

export type HomeAttentionLoadResult = {
  data: HomeAttentionData;
  availability: HomeAttentionAvailability;
  failedSourceCount: number;
};

export type HomeSignalStaleFields = {
  activeSignals: boolean;
  reassessments: boolean;
  alerts: boolean;
};

export type HomeAttentionQueryResult = {
  data: HomeAttentionData;
  availability: HomeAttentionAvailability;
  failedSourceCount: number;
  signalStale: HomeSignalStaleFields;
};

export type HomeTodaysFocusQueryResult = {
  data: TodaysFocusResponse | null;
  error: ParsedApiError | null;
};

export type HomeSetupStatusQueryResult = {
  status: SetupStatusResponse | null;
  error: ParsedApiError | null;
};

export const EMPTY_SIGNAL_STALE: HomeSignalStaleFields = {
  activeSignals: false,
  reassessments: false,
  alerts: false,
};

export const EMPTY_ATTENTION_DATA: HomeAttentionData = {
  activeSignals: [],
  activeSignalTotal: null,
  dueReassessmentTotal: null,
  triggeredAlertTotal: null,
  latestMarketReview: null,
  recentAnalyses: [],
  scheduledTasks: [],
};

export const EMPTY_ATTENTION_AVAILABILITY: HomeAttentionAvailability = {
  activeSignals: false,
  reassessments: false,
  alerts: false,
  marketReview: false,
  recentAnalyses: false,
  scheduledTasks: false,
};

const EMPTY_ATTENTION_QUERY_RESULT: HomeAttentionQueryResult = {
  data: EMPTY_ATTENTION_DATA,
  availability: EMPTY_ATTENTION_AVAILABILITY,
  failedSourceCount: 0,
  signalStale: EMPTY_SIGNAL_STALE,
};

function useExactQueryCleanup(queryKey: readonly unknown[]): void {
  const queryClient = useQueryClient();
  useEffect(() => {
    return () => {
      queryClient.removeQueries({ queryKey, exact: true });
    };
  }, [queryClient, queryKey]);
}

/**
 * Fetch the Home attention pack with allSettled isolation.
 * One failed source must not reject the whole pack.
 * Query cancellation is not forwarded into these transports: only
 * historyApi.getList accepts AbortSignal, and passing it would change the
 * existing call shape. Query still discards a cancelled queryFn result.
 */
export async function fetchHomeAttentionData(): Promise<HomeAttentionLoadResult> {
  const reassessmentCutoff = new Date(Date.now() + REASSESSMENT_WINDOW_MS).toISOString();
  const [coreResults, recentAnalysisResults] = await Promise.all([
    Promise.allSettled([
      decisionSignalsApi.list({ status: 'active', page: 1, pageSize: SIGNAL_PAGE_SIZE }),
      decisionSignalsApi.list({
        status: 'active',
        expiresTo: reassessmentCutoff,
        page: 1,
        pageSize: 1,
      }),
      alertsApi.listTriggers({ status: 'triggered', page: 1, pageSize: 1 }),
      historyApi.getList({ reportType: 'market_review', page: 1, limit: 1 }),
      scheduledTasksApi.getToday({ timezone: getBrowserTimezone() }),
    ]),
    Promise.allSettled(STOCK_REPORT_TYPES.map((reportType) => (
      historyApi.getList({ reportType, page: 1, limit: RECENT_ANALYSIS_LIMIT })
    ))),
  ]);
  const [
    signalsResult,
    reassessmentsResult,
    alertsResult,
    marketReviewResult,
    scheduledTasksResult,
  ] = coreResults;
  const availability: HomeAttentionAvailability = {
    activeSignals: signalsResult.status === 'fulfilled',
    reassessments: reassessmentsResult.status === 'fulfilled',
    alerts: alertsResult.status === 'fulfilled',
    marketReview: marketReviewResult.status === 'fulfilled',
    recentAnalyses: recentAnalysisResults.every((result) => result.status === 'fulfilled'),
    scheduledTasks: scheduledTasksResult.status === 'fulfilled',
  };
  const recentAnalyses = recentAnalysisResults
    .flatMap((result) => (result.status === 'fulfilled' ? result.value.items : []))
    .filter((item) => item.reportType !== 'market_review' && item.stockCode !== 'MARKET')
    .sort((left, right) => {
      const timeDifference = Date.parse(right.createdAt) - Date.parse(left.createdAt);
      return Number.isFinite(timeDifference) && timeDifference !== 0
        ? timeDifference
        : right.id - left.id;
    })
    .slice(0, RECENT_ANALYSIS_LIMIT);
  return {
    data: {
      activeSignals: signalsResult.status === 'fulfilled' ? signalsResult.value.items : [],
      activeSignalTotal: signalsResult.status === 'fulfilled' ? signalsResult.value.total : null,
      dueReassessmentTotal: reassessmentsResult.status === 'fulfilled'
        ? reassessmentsResult.value.total
        : null,
      triggeredAlertTotal: alertsResult.status === 'fulfilled' ? alertsResult.value.total : null,
      latestMarketReview: marketReviewResult.status === 'fulfilled'
        ? marketReviewResult.value.items[0] ?? null
        : null,
      recentAnalyses,
      scheduledTasks: scheduledTasksResult.status === 'fulfilled'
        ? scheduledTasksResult.value.items
        : [],
    },
    availability,
    failedSourceCount: Object.values(availability).filter((available) => !available).length,
  };
}

/**
 * Keep last-known signal/reassessment/alert totals when a refresh source fails.
 * Matches the previous HomePage applyAttentionData merge.
 */
export function mergeHomeAttentionQueryResult(
  previous: HomeAttentionQueryResult | undefined,
  fetched: HomeAttentionLoadResult,
): HomeAttentionQueryResult {
  const previousData = previous?.data ?? EMPTY_ATTENTION_DATA;
  const nextActiveTotal = fetched.availability.activeSignals
    ? fetched.data.activeSignalTotal
    : previousData.activeSignalTotal;
  const nextDueTotal = fetched.availability.reassessments
    ? fetched.data.dueReassessmentTotal
    : previousData.dueReassessmentTotal;
  const nextAlertTotal = fetched.availability.alerts
    ? fetched.data.triggeredAlertTotal
    : previousData.triggeredAlertTotal;
  return {
    data: {
      ...fetched.data,
      activeSignals: fetched.availability.activeSignals
        ? fetched.data.activeSignals
        : previousData.activeSignals,
      activeSignalTotal: nextActiveTotal,
      dueReassessmentTotal: nextDueTotal,
      triggeredAlertTotal: nextAlertTotal,
    },
    availability: fetched.availability,
    failedSourceCount: fetched.failedSourceCount,
    signalStale: {
      activeSignals: !fetched.availability.activeSignals && previousData.activeSignalTotal !== null,
      reassessments: !fetched.availability.reassessments && previousData.dueReassessmentTotal !== null,
      alerts: !fetched.availability.alerts && previousData.triggeredAlertTotal !== null,
    },
  };
}

/**
 * TanStack Query schedule for the Home attention pack.
 *
 * Parity with the previous page-local useEffect + requestId:
 * - Mount load + manual refetch only (no poll, no window-focus refetch).
 * - allSettled isolation: one failed source does not reject the query.
 * - Failed signal/reassessment/alert sources keep last-known totals and mark stale.
 * - Errors stay on existing Home partial-data surfaces (`retry: false`).
 * - `staleTime: 0` so data is never treated as fresh; unmount removes the cache
 *   row (same remount miss as the previous effect, without `gcTime: 0` loops).
 */
export function useHomeAttentionQuery() {
  useExactQueryCleanup(HOME_ATTENTION_QUERY_KEY);
  const { data, isFetching, refetch } = useQuery({
    queryKey: HOME_ATTENTION_QUERY_KEY,
    queryFn: async ({ client }): Promise<HomeAttentionQueryResult> => {
      const previous = client.getQueryData<HomeAttentionQueryResult>(HOME_ATTENTION_QUERY_KEY);
      const fetched = await fetchHomeAttentionData();
      return mergeHomeAttentionQueryResult(previous, fetched);
    },
    ...HOME_PAGE_QUERY_SCHEDULE,
  });

  const result = data ?? EMPTY_ATTENTION_QUERY_RESULT;
  return {
    data: result.data,
    availability: result.availability,
    failedSourceCount: result.failedSourceCount,
    signalStale: result.signalStale,
    isLoading: isFetching,
    refetch,
  };
}

/**
 * TanStack Query schedule for Today's Focus.
 *
 * Language is in the query key so a locale switch cannot present stale copy.
 * Transport stays in getTodaysFocus (no AbortSignal on that client).
 */
export function useTodaysFocusQuery(language: string) {
  const focusLanguage = resolveFocusLanguage(language);
  const queryKey = buildTodaysFocusQueryKey(focusLanguage);
  useExactQueryCleanup(queryKey);
  const { data, isFetching, refetch } = useQuery({
    queryKey,
    queryFn: async (): Promise<HomeTodaysFocusQueryResult> => {
      try {
        const payload = await getTodaysFocus({ language: focusLanguage });
        return { data: payload, error: null };
      } catch (error) {
        return { data: null, error: parseApiError(error) };
      }
    },
    ...HOME_PAGE_QUERY_SCHEDULE,
  });

  return {
    data: data?.data ?? null,
    error: isFetching ? null : (data?.error ?? null),
    isLoading: isFetching,
    refetch,
  };
}

/**
 * TanStack Query schedule for Home setup-status.
 *
 * `refetch` matches the previous loading refresh (header / readiness card).
 * `refreshSilent` matches onboarding apply: no loading flag, error left as-is,
 * status nulled on failure.
 */
export function useHomeSetupStatusQuery() {
  const queryClient = useQueryClient();
  useExactQueryCleanup(HOME_SETUP_STATUS_QUERY_KEY);
  const { data, isFetching, refetch } = useQuery({
    queryKey: HOME_SETUP_STATUS_QUERY_KEY,
    queryFn: async (): Promise<HomeSetupStatusQueryResult> => {
      try {
        const status = await systemConfigApi.getSetupStatus();
        return { status, error: null };
      } catch (error) {
        return { status: null, error: parseApiError(error) };
      }
    },
    ...HOME_PAGE_QUERY_SCHEDULE,
  });

  const refreshSilent = () => {
    void systemConfigApi.getSetupStatus()
      .then((status) => {
        queryClient.setQueryData<HomeSetupStatusQueryResult>(
          HOME_SETUP_STATUS_QUERY_KEY,
          { status, error: null },
        );
      })
      .catch(() => {
        queryClient.setQueryData<HomeSetupStatusQueryResult>(
          HOME_SETUP_STATUS_QUERY_KEY,
          (previous) => ({
            status: null,
            error: previous?.error ?? null,
          }),
        );
      });
  };

  return {
    status: data?.status ?? null,
    error: isFetching ? null : (data?.error ?? null),
    isLoading: isFetching,
    refetch,
    refreshSilent,
  };
}

export default useHomeAttentionQuery;
