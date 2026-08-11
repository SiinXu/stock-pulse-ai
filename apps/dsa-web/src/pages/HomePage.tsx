// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowRight,
  BellRing,
  CalendarClock,
  ChevronDown,
  ClipboardCheck,
  History,
  PlayCircle,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { alertsApi } from '../api/alerts';
import { decisionSignalsApi } from '../api/decisionSignals';
import { historyApi } from '../api/history';
import { scheduledTasksApi } from '../api/scheduledTasks';
import { systemConfigApi } from '../api/systemConfig';
import { getTodaysFocus } from '../api/todaysFocus';
import type { ParsedApiError } from '../api/error';
import { parseApiError } from '../api/error';
import {
  Badge,
  Button,
  EmptyState,
  IconButton,
  InlineAlert,
  PageHeader,
  Section,
  StatePanel,
  WorkspacePage,
} from '../components/common';
import {
  HomeReadinessCard,
  TodaysFocusPanel,
  getBrowserTimezone,
  getScheduledTaskStatusPresentation,
  getScheduledTaskTypeLabel,
  resolveSetupCheckLabel,
} from '../components/home';
import { HomeOnboardingSection } from '../components/onboarding/HomeOnboardingSection';
import { HomeWatchlistGroupsSection } from '../components/watchlist/HomeWatchlistGroupsSection';
import { useRouteFocusTarget } from '../components/routing';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  APP_ROUTE_PATHS,
  SIGNAL_CENTER_SCOPE_VALUES,
  SIGNAL_CENTER_TAB_VALUES,
  buildAnalysisWorkbenchHref,
  buildSettingsHref,
  buildSignalCenterHref,
} from '../routing/routes';
import type { HistoryItem, StockReportType } from '../types/analysis';
import type { DecisionSignalItem } from '../types/decisionSignals';
import type {
  ScheduledTaskTodayItem,
} from '../types/scheduledTasks';
import type { SetupStatusResponse } from '../types/systemConfig';
import type { TodaysFocusResponse } from '../types/todaysFocus';
import { buildDeepLink } from '../utils/deepLink';
import { formatDateTime } from '../utils/format';
import {
  dismissOnboarding,
  readOnboardingDismissed,
} from '../utils/onboardingPreferences';
import { getUiListSeparator } from '../utils/uiLocale';

export const HOME_CONFIGURABLE_STORAGE_KEY = 'dsa.home.configurable.expanded';

function readHomeConfigurableExpanded(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(HOME_CONFIGURABLE_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function writeHomeConfigurableExpanded(expanded: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(HOME_CONFIGURABLE_STORAGE_KEY, expanded ? '1' : '0');
  } catch {
    // Persistence is best-effort; the in-memory disclosure state remains usable.
  }
}




const SIGNAL_PAGE_SIZE = 12;
const RECENT_ANALYSIS_LIMIT = 4;
const REASSESSMENT_WINDOW_MS = 24 * 60 * 60 * 1000;
const STOCK_REPORT_TYPES: readonly StockReportType[] = ['simple', 'detailed', 'full', 'brief'];

type HomeAttentionAvailability = {
  activeSignals: boolean;
  reassessments: boolean;
  alerts: boolean;
  marketReview: boolean;
  recentAnalyses: boolean;
  scheduledTasks: boolean;
};

type HomeAttentionData = {
  activeSignals: DecisionSignalItem[];
  activeSignalTotal: number | null;
  dueReassessmentTotal: number | null;
  triggeredAlertTotal: number | null;
  latestMarketReview: HistoryItem | null;
  recentAnalyses: HistoryItem[];
  scheduledTasks: ScheduledTaskTodayItem[];
};

type HomeAttentionLoadResult = {
  data: HomeAttentionData;
  availability: HomeAttentionAvailability;
  failedSourceCount: number;
};

const EMPTY_ATTENTION_DATA: HomeAttentionData = {
  activeSignals: [],
  activeSignalTotal: null,
  dueReassessmentTotal: null,
  triggeredAlertTotal: null,
  latestMarketReview: null,
  recentAnalyses: [],
  scheduledTasks: [],
};

const EMPTY_ATTENTION_AVAILABILITY: HomeAttentionAvailability = {
  activeSignals: false,
  reassessments: false,
  alerts: false,
  marketReview: false,
  recentAnalyses: false,
  scheduledTasks: false,
};


async function fetchHomeAttentionData(): Promise<HomeAttentionLoadResult> {
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

const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const { language, t } = useUiLanguage();
  const pageHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const requestIdRef = useRef(0);
  const [data, setData] = useState<HomeAttentionData>(EMPTY_ATTENTION_DATA);
  const [availability, setAvailability] = useState<HomeAttentionAvailability>(
    EMPTY_ATTENTION_AVAILABILITY,
  );
  const [isLoading, setIsLoading] = useState(true);
  const [failedSourceCount, setFailedSourceCount] = useState(0);
  const [setupStatus, setSetupStatus] = useState<SetupStatusResponse | null>(null);
  const [setupStatusLoading, setSetupStatusLoading] = useState(true);
  const [setupStatusError, setSetupStatusError] = useState<ParsedApiError | null>(null);
  const [onboardingDismissed, setOnboardingDismissed] = useState(readOnboardingDismissed);
  const [configurableExpanded, setConfigurableExpanded] = useState(
    readHomeConfigurableExpanded,
  );
  const todaysFocusRequestIdRef = useRef(0);
  const [todaysFocusData, setTodaysFocusData] = useState<TodaysFocusResponse | null>(null);
  const [todaysFocusLoading, setTodaysFocusLoading] = useState(true);
  const [todaysFocusError, setTodaysFocusError] = useState<ParsedApiError | null>(null);
  useRouteFocusTarget({
    routeId: APP_ROUTE_PATHS.home,
    headingRef: pageHeadingRef,
    ready: true,
  });

  const applyAttentionData = useCallback((result: HomeAttentionLoadResult) => {
    setData(result.data);
    setAvailability(result.availability);
    setFailedSourceCount(result.failedSourceCount);
    setIsLoading(false);
  }, []);

  const loadAttentionData = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const result = await fetchHomeAttentionData();
    if (requestIdRef.current !== requestId) return;
    applyAttentionData(result);
  }, [applyAttentionData]);

  const loadTodaysFocus = useCallback(async () => {
    const requestId = todaysFocusRequestIdRef.current + 1;
    todaysFocusRequestIdRef.current = requestId;
    setTodaysFocusLoading(true);
    setTodaysFocusError(null);
    try {
      const response = await getTodaysFocus({
        language: language === 'zh' ? 'zh' : 'en',
      });
      if (todaysFocusRequestIdRef.current !== requestId) return;
      setTodaysFocusData(response);
    } catch (error) {
      if (todaysFocusRequestIdRef.current !== requestId) return;
      setTodaysFocusData(null);
      setTodaysFocusError(parseApiError(error));
    } finally {
      if (todaysFocusRequestIdRef.current === requestId) {
        setTodaysFocusLoading(false);
      }
    }
  }, [language]);

  useEffect(() => {
    document.title = t('home.pageTitle');
  }, [t]);

  useEffect(() => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    void fetchHomeAttentionData().then((result) => {
      if (requestIdRef.current === requestId) applyAttentionData(result);
    });
    return () => {
      requestIdRef.current += 1;
    };
  }, [applyAttentionData]);

  useEffect(() => {
    void loadTodaysFocus();
    return () => {
      todaysFocusRequestIdRef.current += 1;
    };
  }, [loadTodaysFocus]);

  const loadSetupStatus = useCallback(async () => {
    setSetupStatusLoading(true);
    setSetupStatusError(null);
    try {
      const status = await systemConfigApi.getSetupStatus();
      setSetupStatus(status);
    } catch (error) {
      setSetupStatus(null);
      setSetupStatusError(parseApiError(error));
    } finally {
      setSetupStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    setSetupStatusLoading(true);
    systemConfigApi.getSetupStatus()
      .then((status) => {
        if (!active) return;
        setSetupStatus(status);
        setSetupStatusError(null);
      })
      .catch((error) => {
        if (!active) return;
        setSetupStatus(null);
        setSetupStatusError(parseApiError(error));
      })
      .finally(() => {
        if (active) setSetupStatusLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const latestMarketReview = data.latestMarketReview;
  const lastSuccessSignal = useMemo(() => {
    if (isLoading || !availability.recentAnalyses) return null;
    const latest = data.recentAnalyses[0];
    return {
      ok: Boolean(latest),
      href: buildAnalysisWorkbenchHref({
        segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch,
      }),
      detail: latest
        ? t('home.readiness.lastSuccess.detail', {
          stock: latest.stockName || latest.stockCode,
          time: formatDateTime(latest.createdAt, language),
        })
        : undefined,
    };
  }, [availability.recentAnalyses, data.recentAnalyses, isLoading, language, t]);
  const setupMissingLabels = useMemo(() => setupStatus?.checks
    .filter((check) => check.required && check.status === 'needs_action')
    .map((check) => resolveSetupCheckLabel(check, t))
    .slice(0, 3)
    .join(getUiListSeparator(language)) ?? '', [language, setupStatus, t]);


  const toggleConfigurable = useCallback(() => {
    setConfigurableExpanded((expanded) => {
      const next = !expanded;
      writeHomeConfigurableExpanded(next);
      return next;
    });
  }, []);

  const handleDismissOnboarding = useCallback(() => {
    dismissOnboarding();
    setOnboardingDismissed(true);
  }, []);
  const refreshSetupStatus = useCallback(() => {
    void systemConfigApi.getSetupStatus()
      .then((status) => setSetupStatus(status))
      .catch(() => setSetupStatus(null));
  }, []);
  const handleRefresh = useCallback(() => {
    setIsLoading(true);
    void loadAttentionData();
    void loadSetupStatus();
    void loadTodaysFocus();
  }, [loadAttentionData, loadSetupStatus, loadTodaysFocus]);

  const analysisHref = buildAnalysisWorkbenchHref({
    segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch,
  });
  const signalCenterHref = buildSignalCenterHref({ scope: SIGNAL_CENTER_SCOPE_VALUES.all });
  const reviewHref = buildSignalCenterHref({
    scope: SIGNAL_CENTER_SCOPE_VALUES.all,
    tab: SIGNAL_CENTER_TAB_VALUES.review,
  });
  const approvalsHref = APP_ROUTE_PATHS.approvals;

  return (
    <WorkspacePage
      data-testid="home-attention-hub"
      contentClassName="space-y-6 rounded-xl border border-border p-5"
    >
      <PageHeader
        ref={pageHeadingRef}
        title={t('layout.route.home.title')}
        description={t('home.attentionDescription')}
        actions={(
          <>
            <IconButton
              aria-label={t('home.refreshAttention')}
              variant="outline"
              size="comfortable"
              isLoading={isLoading}
              onClick={handleRefresh}
            >
              <RefreshCw aria-hidden="true" />
            </IconButton>
            <Button variant="primary" size="primary" onClick={() => navigate(analysisHref)}>
              <PlayCircle className="h-4 w-4" aria-hidden="true" />
              {t('home.startAnalysisTitle')}
            </Button>
          </>
        )}
      />

      {!onboardingDismissed || setupStatusLoading || setupStatusError || setupStatus ? (
        <HomeReadinessCard
          status={setupStatus}
          isLoading={setupStatusLoading}
          error={setupStatusError}
          lastSuccess={lastSuccessSignal}
          onRefresh={() => { void loadSetupStatus(); }}
          // Incomplete-setup dismiss lives only on HomeOnboardingSection so Home
          // does not render two identical "Close" controls at once (#879 B6 spirit).
          dismissible={false}
          t={t}
        />
      ) : null}
      <HomeOnboardingSection
        setupStatus={setupStatus}
        setupMissingLabels={setupMissingLabels}
        onboardingDismissed={onboardingDismissed}
        onDismissOnboarding={handleDismissOnboarding}
        onSetupRefresh={refreshSetupStatus}
        reportLanguage={language === 'zh' ? 'zh' : 'en'}
        t={t}
      />

      {failedSourceCount > 0 ? (
        <InlineAlert
          variant="warning"
          size="compact"
          title={t('home.partialDataTitle')}
          message={t('home.partialDataMessage')}
          action={(
            <Button variant="ghost" size="default" onClick={handleRefresh}>
              {t('common.retry')}
            </Button>
          )}
        />
      ) : null}

      {/* xl (1280+) only: at 1024 the shell compact rail + a single content column
          avoid the historical three-surface clip (UI01-P1-02 / #879 B1). */}
      <HomeWatchlistGroupsSection />

      {/* xl (1280+) only: at 1024 the shell compact rail + a single content column
          avoid the historical three-surface clip (UI01-P1-02 / #879 B1). */}
      <div data-testid="home-core-blocks" className="grid min-w-0 gap-4 xl:grid-cols-3">
        <TodaysFocusPanel
          data={todaysFocusData}
          isLoading={todaysFocusLoading}
          error={todaysFocusError}
          onRefresh={() => { void loadTodaysFocus(); }}
          onSelectSymbol={(code) => navigate(`/stocks/${encodeURIComponent(code)}`)}
          t={t}
        />

        <Section
          title={t('home.todos')}
          description={t('home.todosDescription')}
          level="interactive"
          padding="md"
          contentClassName="flex flex-col gap-3"
          actions={<ClipboardCheck className="h-5 w-5 text-warning" aria-hidden="true" />}
        >
          {isLoading ? (
            <StatePanel state="loading" title={t('common.loading')} size="compact" />
          ) : !availability.reassessments ? (
            <StatePanel
              state="error"
              title={t('home.partialDataTitle')}
              description={t('home.partialDataMessage')}
              action={<Button variant="secondary" size="default" onClick={handleRefresh}>{t('common.retry')}</Button>}
              size="compact"
              titleAs="p"
            />
          ) : (data.dueReassessmentTotal ?? 0) > 0 ? (
            <div className="space-y-3">
              <button
                type="button"
                className="flex min-h-14 w-full items-center justify-between gap-3 rounded-lg border border-warning/25 bg-warning/10 px-3 py-2 text-left"
                onClick={() => navigate(reviewHref)}
              >
                <span>
                  <span className="block text-sm font-semibold text-foreground">
                    {t('home.reassessmentDue', { count: data.dueReassessmentTotal ?? 0 })}
                  </span>
                  <span className="mt-1 block text-xs text-secondary-text">
                    {t('home.reassessmentDueDescription')}
                  </span>
                </span>
                <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
              </button>
            </div>
          ) : (
            <EmptyState
              compact
              title={t('home.noTodosTitle')}
              description={t('home.noTodosDescription')}
              action={(
                <Button variant="secondary" size="default" onClick={() => navigate(reviewHref)}>
                  {t('home.reviewSignals')}
                </Button>
              )}
            />
          )}
          <div className="order-last flex justify-center">
            <Button
              variant="secondary"
              size="default"
              onClick={() => navigate(approvalsHref)}
            >
              <ShieldAlert className="h-4 w-4" aria-hidden="true" />
              {t('home.reviewApprovals')}
            </Button>
          </div>
        </Section>

        <Section
          title={t('home.signalSummary')}
          description={t('home.signalSummaryDescription')}
          level="interactive"
          padding="md"
          actions={<BellRing className="h-5 w-5 text-danger" aria-hidden="true" />}
        >
          {isLoading ? (
            <StatePanel state="loading" title={t('common.loading')} size="compact" />
          ) : (
            <div className="space-y-4">
              <dl className="grid grid-cols-3 gap-3">
                <div>
                  <dt className="text-xs text-secondary-text">{t('home.activeSignals')}</dt>
                  <dd className="mt-1 text-xl font-semibold tabular-nums text-foreground">
                    {data.activeSignalTotal ?? '—'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-secondary-text">{t('home.triggeredAlerts')}</dt>
                  <dd className="mt-1 text-xl font-semibold tabular-nums text-foreground">
                    {data.triggeredAlertTotal ?? '—'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-secondary-text">{t('home.dueReassessments')}</dt>
                  <dd className="mt-1 text-xl font-semibold tabular-nums text-foreground">
                    {data.dueReassessmentTotal ?? '—'}
                  </dd>
                </div>
              </dl>
              <Button className="mx-auto" variant="secondary" size="default" onClick={() => navigate(signalCenterHref)}>
                {t('decisionSignals.viewAll')}
                <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
            </div>
          )}
        </Section>
      </div>

      <section className="rounded-xl border border-border p-4" aria-labelledby="home-configurable-heading">
        <button
          type="button"
          className="flex min-h-11 w-full items-center justify-between gap-4 text-left"
          aria-expanded={configurableExpanded}
          aria-controls="home-configurable-content"
          onClick={toggleConfigurable}
        >
          <span className="min-w-0">
            <span id="home-configurable-heading" className="block text-base font-semibold text-foreground">
              {t('home.configurableArea')}
            </span>
            <span className="mt-1 block text-sm text-secondary-text">
              {t('home.configurableAreaDescription')}
            </span>
          </span>
          <ChevronDown
            className={`h-5 w-5 shrink-0 transition-transform ${configurableExpanded ? 'rotate-180' : ''}`}
            aria-hidden="true"
          />
        </button>

        <div id="home-configurable-content" className="mt-4 grid gap-4 lg:grid-cols-2 xl:grid-cols-3" hidden={!configurableExpanded}>
          <Section
            title={t('home.morningReport')}
            level="interactive"
            padding="md"
            actions={<CalendarClock className="h-5 w-5 text-primary" aria-hidden="true" />}
          >
            {isLoading ? (
              <StatePanel state="loading" title={t('common.loading')} size="compact" titleAs="p" />
            ) : !availability.marketReview ? (
              <StatePanel
                state="error"
                title={t('home.partialDataTitle')}
                description={t('home.partialDataMessage')}
                action={<Button variant="secondary" size="default" onClick={handleRefresh}>{t('common.retry')}</Button>}
                size="compact"
                titleAs="p"
              />
            ) : latestMarketReview ? (
              <button
                type="button"
                className="flex min-h-14 w-full items-center justify-between gap-3 text-left"
                onClick={() => navigate(buildDeepLink({
                  page: 'market-review',
                  recordId: latestMarketReview.id,
                }))}
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-foreground">
                    {latestMarketReview.stockName || t('home.marketReview')}
                  </span>
                  <span className="mt-1 block text-xs text-secondary-text">
                    {formatDateTime(latestMarketReview.createdAt, language)}
                  </span>
                </span>
                <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
              </button>
            ) : (
              <EmptyState
                compact
                title={t('home.noMorningReportTitle')}
                description={t('home.noMorningReportDescription')}
                action={(
                  <Button
                    variant="secondary"
                    size="default"
                    onClick={() => navigate(APP_ROUTE_PATHS.researchMarket)}
                  >
                    {t('home.marketReview')}
                  </Button>
                )}
              />
            )}
          </Section>

          <Section
            title={t('home.recentAnalyses')}
            level="interactive"
            padding="md"
            actions={<History className="h-5 w-5 text-primary" aria-hidden="true" />}
          >
            {isLoading ? (
              <StatePanel state="loading" title={t('common.loading')} size="compact" titleAs="p" />
            ) : data.recentAnalyses.length > 0 ? (
              <div className="divide-y divide-border/70">
                {data.recentAnalyses.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="flex min-h-12 w-full items-center justify-between gap-3 py-2 text-left"
                    onClick={() => navigate(buildAnalysisWorkbenchHref({ recordId: item.id }))}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-foreground">
                        {item.stockName || item.stockCode}
                      </span>
                      <span className="mt-0.5 block truncate text-xs text-secondary-text">
                        {item.stockCode} · {formatDateTime(item.createdAt, language)}
                      </span>
                    </span>
                    <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
                  </button>
                ))}
              </div>
            ) : !availability.recentAnalyses ? (
              <StatePanel
                state="partial"
                title={t('home.partialDataTitle')}
                description={t('home.partialDataMessage')}
                action={<Button variant="secondary" size="default" onClick={handleRefresh}>{t('common.retry')}</Button>}
                size="compact"
                titleAs="p"
              />
            ) : (
              <EmptyState
                compact
                title={t('home.noRecentAnalysesTitle')}
                description={t('home.noRecentAnalysesDescription')}
                action={(
                  <Button variant="secondary" size="default" onClick={() => navigate(analysisHref)}>
                    {t('home.startAnalysisTitle')}
                  </Button>
                )}
              />
            )}
          </Section>

          <div>
            <Section
              title={t('home.scheduledTasksToday')}
              description={t('home.scheduledTasksTodayDescription')}
              level="interactive"
              padding="md"
              actions={(
                <>
                  {isLoading || !availability.scheduledTasks || data.scheduledTasks.length > 0 ? (
                    <Button
                      variant="secondary"
                      size="compact"
                      onClick={() => navigate(buildSettingsHref({ section: 'system_security', view: 'runtime' }))}
                    >
                      {t('home.manageScheduledTasks')}
                    </Button>
                  ) : null}
                  <CalendarClock className="h-5 w-5 text-primary" aria-hidden="true" />
                </>
              )}
            >
              {isLoading ? (
                <StatePanel state="loading" title={t('common.loading')} size="compact" titleAs="p" />
              ) : !availability.scheduledTasks ? (
                <StatePanel
                  state="partial"
                  title={t('home.partialDataTitle')}
                  description={t('home.partialDataMessage')}
                  action={<Button variant="secondary" size="default" onClick={handleRefresh}>{t('common.retry')}</Button>}
                  size="compact"
                  titleAs="p"
                />
              ) : data.scheduledTasks.length > 0 ? (
                <div
                  role="region"
                  aria-label={t('home.scheduledTasksListLabel')}
                  tabIndex={0}
                  className="max-h-72 overflow-y-auto rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/55 focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                  data-testid="today-scheduled-tasks"
                >
                  <ul className="divide-y divide-border/70">
                    {data.scheduledTasks.map((item) => {
                      const status = getScheduledTaskStatusPresentation(item.status, t);
                      return (
                        <li
                          key={`${item.task.id}-${item.scheduledFor}`}
                          className="flex min-h-12 items-center justify-between gap-3 py-2"
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-medium text-foreground">
                              {item.task.name}
                            </span>
                            <span className="mt-0.5 block truncate text-xs text-secondary-text">
                              {getScheduledTaskTypeLabel(item.task.taskType, t)}
                              {' · '}
                              {formatDateTime(item.scheduledFor, language)}
                            </span>
                          </span>
                          <Badge variant={status.variant} className="shrink-0">
                            {status.label}
                          </Badge>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ) : (
                <div className="rounded-lg border border-border">
                  <EmptyState
                    compact
                    title={t('home.noScheduledTasksTodayTitle')}
                    description={t('home.noScheduledTasksTodayDescription')}
                    action={(
                      <Button
                        variant="secondary"
                        size="default"
                        onClick={() => navigate(buildSettingsHref({ section: 'system_security', view: 'runtime' }))}
                      >
                        {t('home.manageScheduledTasks')}
                      </Button>
                    )}
                  />
                </div>
              )}
            </Section>
          </div>
        </div>
      </section>
    </WorkspacePage>
  );
};

export default HomePage;
