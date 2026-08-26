// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowRight,
  CalendarClock,
  ChevronDown,
  ClipboardCheck,
  PlayCircle,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  useHomeAttentionQuery,
  useHomeSetupStatusQuery,
  useTodaysFocusQuery,
} from '../hooks/useHomePageQueries';
import {
  Badge,
  Button,
  EmptyState,
  IconButton,
  InlineAlert,
  PageHeader,
  Pressable,
  Section,
  StatePanel,
  WorkspacePage,
} from '../components/common';
import {
  HomeReadinessCard,
  HomeSignalSummary,
  TodaysFocusPanel,
  getScheduledTaskStatusPresentation,
  getScheduledTaskTypeLabel,
  resolveSetupCheckLabel,
} from '../components/home';
import {
  HomeAlertsWidget,
  HomeDashboardLayout,
  HomePortfolioHealthWidget,
  HomeRecentReportsWidget,
} from '../components/dashboard';
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

const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const { language, t } = useUiLanguage();
  const pageHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const [scoreRefreshGeneration, setScoreRefreshGeneration] = useState(0);
  const [onboardingDismissed, setOnboardingDismissed] = useState(readOnboardingDismissed);
  const [configurableExpanded, setConfigurableExpanded] = useState(
    readHomeConfigurableExpanded,
  );
  const {
    data,
    availability,
    failedSourceCount,
    signalStale,
    isLoading,
    refetch: refetchAttention,
  } = useHomeAttentionQuery();
  const {
    data: todaysFocusData,
    isLoading: todaysFocusLoading,
    error: todaysFocusError,
    refetch: refetchTodaysFocus,
  } = useTodaysFocusQuery(language);
  const {
    status: setupStatus,
    isLoading: setupStatusLoading,
    error: setupStatusError,
    refetch: refetchSetupStatus,
    refreshSilent: refreshSetupStatus,
  } = useHomeSetupStatusQuery();
  useRouteFocusTarget({
    routeId: APP_ROUTE_PATHS.home,
    headingRef: pageHeadingRef,
    ready: true,
  });

  useEffect(() => {
    document.title = t('home.pageTitle');
  }, [t]);

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
  const handleRefresh = useCallback(() => {
    setScoreRefreshGeneration((generation) => generation + 1);
    refetchAttention();
    refetchSetupStatus();
    refetchTodaysFocus();
  }, [refetchAttention, refetchSetupStatus, refetchTodaysFocus]);

  const watchlistScoreRefreshKey = useMemo(() => JSON.stringify({
    refreshGeneration: scoreRefreshGeneration,
    recentAnalyses: data.recentAnalyses.map((item) => ({
      id: item.id,
      stockCode: item.stockCode,
      createdAt: item.createdAt,
    })),
  }), [data.recentAnalyses, scoreRefreshGeneration]);

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
              variant="ghost"
              size="default"
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
          onRefresh={() => { refetchSetupStatus(); }}
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

      {/* Customizable dashboard board: independent of readiness / Today's Focus. */}
      <HomeDashboardLayout
        widgets={{
          watchlist: (
            <HomeWatchlistGroupsSection scoreRefreshKey={watchlistScoreRefreshKey} />
          ),
          portfolio_health: (
            <HomePortfolioHealthWidget refreshKey={scoreRefreshGeneration} />
          ),
          alerts: (
            <HomeAlertsWidget
              isLoading={isLoading}
              available={availability.alerts}
              triggeredAlertTotal={data.triggeredAlertTotal}
              onRetry={handleRefresh}
            />
          ),
          recent_reports: (
            <HomeRecentReportsWidget
              isLoading={isLoading}
              available={availability.recentAnalyses}
              items={data.recentAnalyses}
              language={language}
              onRetry={handleRefresh}
            />
          ),
        }}
      />

      {/* xl (1280+) only: at 1024 the shell compact rail + a single content column
          avoid the historical three-surface clip (UI01-P1-02 / #879 B1). */}
      <div data-testid="home-core-blocks" className="grid min-w-0 gap-4 xl:grid-cols-3">
        <TodaysFocusPanel
          data={todaysFocusData}
          isLoading={todaysFocusLoading}
          error={todaysFocusError}
          onRefresh={() => { refetchTodaysFocus(); }}
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
              <Pressable
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
              </Pressable>
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

        <HomeSignalSummary
          isLoading={isLoading}
          availability={availability}
          data={data}
          stale={signalStale}
          onRetry={handleRefresh}
          onViewAll={() => navigate(signalCenterHref)}
        />
      </div>

      <section className="rounded-xl border border-border p-4" aria-labelledby="home-configurable-heading">
        <Pressable
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
        </Pressable>

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
              <Pressable
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
              </Pressable>
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
