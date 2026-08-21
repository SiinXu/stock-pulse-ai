// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { alertsApi } from '../../api/alerts';
import { decisionSignalsApi } from '../../api/decisionSignals';
import { historyApi } from '../../api/history';
import { scheduledTasksApi } from '../../api/scheduledTasks';
import { systemConfigApi } from '../../api/systemConfig';
import { getTodaysFocus } from '../../api/todaysFocus';
import { createDeferred } from '../../test-utils';
import type { TodaysFocusResponse } from '../../types/todaysFocus';
import {
  HOME_ATTENTION_QUERY_KEY,
  HOME_SETUP_STATUS_QUERY_KEY,
  TODAYS_FOCUS_QUERY_KEY_ROOT,
  buildTodaysFocusQueryKey,
  fetchHomeAttentionData,
  mergeHomeAttentionQueryResult,
  resolveFocusLanguage,
  useHomeAttentionQuery,
  useHomeSetupStatusQuery,
  useTodaysFocusQuery,
  type HomeAttentionLoadResult,
  type HomeAttentionQueryResult,
} from '../useHomePageQueries';

vi.mock('../../api/decisionSignals', () => ({
  decisionSignalsApi: { list: vi.fn() },
}));

vi.mock('../../api/alerts', () => ({
  alertsApi: { listTriggers: vi.fn() },
}));

vi.mock('../../api/history', () => ({
  historyApi: { getList: vi.fn() },
}));

vi.mock('../../api/scheduledTasks', () => ({
  scheduledTasksApi: { getToday: vi.fn() },
}));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: { getSetupStatus: vi.fn() },
}));

vi.mock('../../api/todaysFocus', () => ({
  getTodaysFocus: vi.fn(),
}));

const emptyList = { items: [], total: 0, page: 1, pageSize: 12 };
const emptyHistory = { items: [], total: 0, page: 1, limit: 4 };
const emptyScheduled = {
  date: '2026-08-21',
  timezone: 'UTC',
  generatedAt: '2026-08-21T00:00:00Z',
  items: [],
  total: 0,
};

const emptyTodaysFocus = (language: string): TodaysFocusResponse => ({
  packVersion: 'todays_focus/2.1',
  generatedAt: '2026-08-09T00:00:00Z',
  status: 'empty',
  maxItems: 5,
  itemCount: 0,
  items: [],
  emptyReason: 'no_fresh_deterministic_signals',
  emptyMessage: language === 'zh' ? '今日无需特别关注。' : 'No symbols need special attention today.',
  sourcesUsed: [],
  degradedSources: [],
  temporalPolicy: {
    semantics: 'per_market_local_calendar_day',
    crossMarketRule: 'evidence_uses_target_symbol_market_timezone',
    fallbackTimezone: 'Asia/Shanghai',
    windowEnd: '2026-08-09T00:00:00Z',
    naiveTimestampPolicy: 'assume_utc',
    missingTimestampPolicy: 'exclude',
    nonTradingDayPolicy: 'same_local_day_only',
    markets: [],
  },
  universeContract: {
    symbolCount: 0,
    hardCap: 1000,
    truncated: false,
    sources: ['watchlist_config'],
    excludedNonFinitePositions: 0,
    dataNotes: [],
  },
  costContract: {
    alertRepositoryCalls: 1,
    portfolioRepositoryCalls: 1,
    analysisHistoryRepositoryCalls: 1,
    eventRepositoryCalls: 0,
    databaseWrites: 0,
    providerCalls: 0,
    analysisRunsTriggered: 0,
    zeroExtraFetch: true,
    readOnly: true,
  },
  presentationBoundary: {
    alertsOwnedBy: 'signal_center',
    focusShows: 'prioritized_symbols_with_evidence_links',
    duplicateAlertUi: false,
  },
});

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return { client, wrapper: Wrapper };
}

describe('HomePage query key helpers', () => {
  it('includes language in the Today\'s Focus query key', () => {
    expect(resolveFocusLanguage('zh')).toBe('zh');
    expect(resolveFocusLanguage('en')).toBe('en');
    expect(resolveFocusLanguage('fr')).toBe('en');
    expect(buildTodaysFocusQueryKey('zh')).toEqual([...TODAYS_FOCUS_QUERY_KEY_ROOT, 'zh']);
    expect(buildTodaysFocusQueryKey('en')).toEqual([...TODAYS_FOCUS_QUERY_KEY_ROOT, 'en']);
    expect(buildTodaysFocusQueryKey('zh')).toBe(buildTodaysFocusQueryKey('zh'));
    expect(buildTodaysFocusQueryKey('en')).toBe(buildTodaysFocusQueryKey('fr'));
  });
});

describe('fetchHomeAttentionData', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(decisionSignalsApi.list).mockResolvedValue({
      ...emptyList,
      total: 4,
    });
    vi.mocked(alertsApi.listTriggers).mockResolvedValue({
      items: [],
      total: 2,
      page: 1,
      pageSize: 1,
    });
    vi.mocked(historyApi.getList).mockResolvedValue(emptyHistory);
    vi.mocked(scheduledTasksApi.getToday).mockResolvedValue(emptyScheduled);
  });

  it('keeps fulfilled sources when one attention source rejects', async () => {
    vi.mocked(alertsApi.listTriggers).mockRejectedValue(new Error('alerts unavailable'));

    const result = await fetchHomeAttentionData();

    expect(result.availability.activeSignals).toBe(true);
    expect(result.availability.alerts).toBe(false);
    expect(result.data.activeSignalTotal).toBe(4);
    expect(result.data.triggeredAlertTotal).toBeNull();
    expect(result.failedSourceCount).toBeGreaterThan(0);
  });

  it('keeps history list transport on the existing single-argument call shape', async () => {
    await fetchHomeAttentionData();

    expect(historyApi.getList).toHaveBeenCalledWith(
      expect.objectContaining({ reportType: 'market_review' }),
    );
    expect(scheduledTasksApi.getToday).toHaveBeenCalledWith({
      timezone: expect.any(String),
    });
    expect(vi.mocked(historyApi.getList).mock.calls[0]).toHaveLength(1);
  });
});

describe('mergeHomeAttentionQueryResult', () => {
  it('keeps last-known signal totals and marks them stale after a failed refresh', () => {
    const previous: HomeAttentionQueryResult = {
      data: {
        activeSignals: [],
        activeSignalTotal: 4,
        dueReassessmentTotal: 1,
        triggeredAlertTotal: 2,
        latestMarketReview: null,
        recentAnalyses: [],
        scheduledTasks: [],
      },
      availability: {
        activeSignals: true,
        reassessments: true,
        alerts: true,
        marketReview: true,
        recentAnalyses: true,
        scheduledTasks: true,
      },
      failedSourceCount: 0,
      signalStale: {
        activeSignals: false,
        reassessments: false,
        alerts: false,
      },
    };
    const fetched: HomeAttentionLoadResult = {
      data: {
        activeSignals: [],
        activeSignalTotal: null,
        dueReassessmentTotal: null,
        triggeredAlertTotal: null,
        latestMarketReview: null,
        recentAnalyses: [],
        scheduledTasks: [],
      },
      availability: {
        activeSignals: false,
        reassessments: false,
        alerts: false,
        marketReview: true,
        recentAnalyses: true,
        scheduledTasks: true,
      },
      failedSourceCount: 3,
    };

    const merged = mergeHomeAttentionQueryResult(previous, fetched);

    expect(merged.data.activeSignalTotal).toBe(4);
    expect(merged.data.triggeredAlertTotal).toBe(2);
    expect(merged.signalStale.activeSignals).toBe(true);
    expect(merged.signalStale.alerts).toBe(true);
    expect(merged.failedSourceCount).toBe(3);
  });
});

describe('useHomeAttentionQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(decisionSignalsApi.list).mockResolvedValue({
      ...emptyList,
      total: 4,
    });
    vi.mocked(alertsApi.listTriggers).mockResolvedValue({
      items: [],
      total: 2,
      page: 1,
      pageSize: 1,
    });
    vi.mocked(historyApi.getList).mockResolvedValue(emptyHistory);
    vi.mocked(scheduledTasksApi.getToday).mockResolvedValue(emptyScheduled);
  });

  it('loads the attention pack on mount without polling or window-focus refetch', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useHomeAttentionQuery(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data.activeSignalTotal).toBe(4);
    expect(result.current.availability.alerts).toBe(true);

    const query = client.getQueryCache().find({ queryKey: HOME_ATTENTION_QUERY_KEY });
    const options = query?.options as Record<string, unknown>;
    expect(options.retry).toBe(false);
    expect(options.refetchOnWindowFocus).toBe(false);
    expect(options.refetchInterval).toBeFalsy();
    expect(options.staleTime).toBe(0);
  });

  it('does not wipe fulfilled signal totals when alerts fail on a later refetch', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useHomeAttentionQuery(), { wrapper });

    await waitFor(() => expect(result.current.data.activeSignalTotal).toBe(4));
    vi.mocked(alertsApi.listTriggers).mockRejectedValue(new Error('alerts unavailable'));

    await act(async () => {
      result.current.refetch();
    });

    await waitFor(() => expect(result.current.availability.alerts).toBe(false));
    expect(result.current.data.activeSignalTotal).toBe(4);
    expect(result.current.data.triggeredAlertTotal).toBe(2);
    expect(result.current.signalStale.alerts).toBe(true);
  });
});

describe('useTodaysFocusQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('requests the locale-specific pack and does not keep the previous language copy', async () => {
    vi.mocked(getTodaysFocus).mockImplementation(async ({ language } = {}) => (
      emptyTodaysFocus(language === 'zh' ? 'zh' : 'en')
    ));
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ language }: { language: string }) => useTodaysFocusQuery(language),
      { wrapper, initialProps: { language: 'en' } },
    );

    await waitFor(() => expect(result.current.data?.emptyMessage).toContain('No symbols'));
    expect(getTodaysFocus).toHaveBeenCalledWith({ language: 'en' });

    rerender({ language: 'zh' });
    await waitFor(() => expect(result.current.data?.emptyMessage).toContain('今日无需特别关注'));
    expect(getTodaysFocus).toHaveBeenCalledWith({ language: 'zh' });
    expect(result.current.data?.emptyMessage).not.toContain('No symbols');
  });

  it('keeps the observed Today\'s Focus cache across same-language rerenders', async () => {
    vi.mocked(getTodaysFocus).mockResolvedValue(emptyTodaysFocus('en'));
    const { wrapper, client } = createWrapper();
    const { result, rerender } = renderHook(
      ({ language }: { language: string }) => useTodaysFocusQuery(language),
      { wrapper, initialProps: { language: 'en' } },
    );

    await waitFor(() => expect(result.current.data).not.toBeNull());
    expect(getTodaysFocus).toHaveBeenCalledTimes(1);
    const cached = client.getQueryData(buildTodaysFocusQueryKey('en'));
    expect(cached).toEqual({ data: emptyTodaysFocus('en'), error: null });

    rerender({ language: 'en' });
    expect(result.current.data).not.toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(getTodaysFocus).toHaveBeenCalledTimes(1);
    expect(client.getQueryData(buildTodaysFocusQueryKey('en'))).toBe(cached);
  });

  it('clears previous copy while a locale-keyed fetch is in flight', async () => {
    const english = createDeferred<TodaysFocusResponse>();
    const chinese = createDeferred<TodaysFocusResponse>();
    vi.mocked(getTodaysFocus).mockImplementation(async ({ language } = {}) => (
      language === 'zh' ? chinese.promise : english.promise
    ));
    const { wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ language }: { language: string }) => useTodaysFocusQuery(language),
      { wrapper, initialProps: { language: 'en' } },
    );

    await act(async () => {
      english.resolve(emptyTodaysFocus('en'));
      await english.promise;
    });
    await waitFor(() => expect(result.current.data?.emptyMessage).toContain('No symbols'));

    rerender({ language: 'zh' });
    await waitFor(() => expect(result.current.isLoading).toBe(true));
    expect(result.current.data).toBeNull();

    await act(async () => {
      chinese.resolve(emptyTodaysFocus('zh'));
      await chinese.promise;
    });
    await waitFor(() => expect(result.current.data?.emptyMessage).toContain('今日无需特别关注'));
  });

  it('surfaces transport errors on the existing parsed-error field, not a parallel channel', async () => {
    vi.mocked(getTodaysFocus).mockRejectedValue(new Error('focus unavailable'));
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useTodaysFocusQuery('en'), { wrapper });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.data).toBeNull();
    expect(result.current.error?.rawMessage).toContain('focus unavailable');
  });
});

describe('useHomeSetupStatusQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(systemConfigApi.getSetupStatus).mockResolvedValue({
      isComplete: true,
      readyForSmoke: true,
      requiredMissingKeys: [],
      nextStepKey: null,
      checks: [],
    });
  });

  it('loads setup status on mount with the Home schedule defaults', async () => {
    const { wrapper, client } = createWrapper();
    const { result } = renderHook(() => useHomeSetupStatusQuery(), { wrapper });

    await waitFor(() => expect(result.current.status?.isComplete).toBe(true));
    const query = client.getQueryCache().find({ queryKey: HOME_SETUP_STATUS_QUERY_KEY });
    const options = query?.options as Record<string, unknown>;
    expect(options.retry).toBe(false);
    expect(options.refetchOnWindowFocus).toBe(false);
    expect(options.refetchInterval).toBeFalsy();
  });

  it('keeps loading false during silent onboarding refresh and nulls status on silent failure', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useHomeSetupStatusQuery(), { wrapper });
    await waitFor(() => expect(result.current.status?.isComplete).toBe(true));

    const silent = createDeferred<Awaited<ReturnType<typeof systemConfigApi.getSetupStatus>>>();
    vi.mocked(systemConfigApi.getSetupStatus).mockReturnValue(silent.promise);

    act(() => {
      result.current.refreshSilent();
    });
    expect(result.current.isLoading).toBe(false);
    expect(result.current.status?.isComplete).toBe(true);

    await act(async () => {
      silent.reject(new Error('setup unavailable'));
    });
    await waitFor(() => expect(result.current.status).toBeNull());
    expect(result.current.error).toBeNull();
  });
});
