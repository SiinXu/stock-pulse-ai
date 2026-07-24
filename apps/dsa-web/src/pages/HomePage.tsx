// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  ArrowRight,
  BellRing,
  CalendarClock,
  ChevronDown,
  ClipboardCheck,
  PlayCircle,
  RefreshCw,
  X,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { alertsApi } from '../api/alerts';
import { decisionSignalsApi } from '../api/decisionSignals';
import { historyApi } from '../api/history';
import { systemConfigApi } from '../api/systemConfig';
import {
  Button,
  EmptyState,
  IconButton,
  InlineAlert,
  PageHeader,
  Section,
  StatePanel,
  WorkspacePage,
} from '../components/common';
import { useRouteFocusTarget } from '../components/routing';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  APP_ROUTE_PATHS,
  REPORT_ROUTE_QUERY_KEYS,
  SIGNAL_CENTER_SCOPE_VALUES,
  SIGNAL_CENTER_TAB_VALUES,
  buildAnalysisWorkbenchHref,
  buildSettingsHref,
  buildSignalCenterHref,
} from '../routing/routes';
import type { HistoryItem } from '../types/analysis';
import type { DecisionSignalItem } from '../types/decisionSignals';
import type { SetupStatusResponse } from '../types/systemConfig';
import { buildDecisionActionLabelMap } from '../utils/decisionAction';
import { getDecisionSignalPresentation } from '../utils/decisionSignalPresentation';
import { parseDecisionSignalDate } from '../utils/decisionSignalTime';
import { formatDateTime } from '../utils/format';
import {
  dismissOnboarding,
  readOnboardingDismissed,
} from '../utils/onboardingPreferences';
import { getUiListSeparator } from '../utils/uiLocale';

export const HOME_CONFIGURABLE_STORAGE_KEY = 'dsa.home.configurable.expanded';

const SIGNAL_PAGE_SIZE = 12;
const HISTORY_PAGE_SIZE = 8;
const FOCUS_ITEM_LIMIT = 3;
const RECENT_ANALYSIS_LIMIT = 4;
const REASSESSMENT_WINDOW_MS = 24 * 60 * 60 * 1000;

type HomeAttentionData = {
  activeSignals: DecisionSignalItem[];
  activeSignalTotal: number;
  triggeredAlertTotal: number;
  historyItems: HistoryItem[];
};

type HomeAttentionLoadResult = {
  data: HomeAttentionData;
  failedSourceCount: number;
  loadedAt: number;
};

const EMPTY_ATTENTION_DATA: HomeAttentionData = {
  activeSignals: [],
  activeSignalTotal: 0,
  triggeredAlertTotal: 0,
  historyItems: [],
};

function isReassessmentDue(item: DecisionSignalItem, now: number): boolean {
  const expiresAt = parseDecisionSignalDate(item.expiresAt);
  return Boolean(expiresAt && expiresAt.getTime() <= now + REASSESSMENT_WINDOW_MS);
}

async function fetchHomeAttentionData(): Promise<HomeAttentionLoadResult> {
  const [signalsResult, alertsResult, historyResult] = await Promise.allSettled([
    decisionSignalsApi.list({ status: 'active', page: 1, pageSize: SIGNAL_PAGE_SIZE }),
    alertsApi.listTriggers({ status: 'triggered', page: 1, pageSize: 1 }),
    historyApi.getList({ page: 1, limit: HISTORY_PAGE_SIZE }),
  ]);
  return {
    data: {
      activeSignals: signalsResult.status === 'fulfilled' ? signalsResult.value.items : [],
      activeSignalTotal: signalsResult.status === 'fulfilled' ? signalsResult.value.total : 0,
      triggeredAlertTotal: alertsResult.status === 'fulfilled' ? alertsResult.value.total : 0,
      historyItems: historyResult.status === 'fulfilled' ? historyResult.value.items : [],
    },
    failedSourceCount: [signalsResult, alertsResult, historyResult]
      .filter((result) => result.status === 'rejected')
      .length,
    loadedAt: Date.now(),
  };
}

const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const { language, t } = useUiLanguage();
  const pageHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const requestIdRef = useRef(0);
  const [data, setData] = useState<HomeAttentionData>(EMPTY_ATTENTION_DATA);
  const [isLoading, setIsLoading] = useState(true);
  const [loadedAt, setLoadedAt] = useState(0);
  const [failedSourceCount, setFailedSourceCount] = useState(0);
  const [setupStatus, setSetupStatus] = useState<SetupStatusResponse | null>(null);
  const [onboardingDismissed, setOnboardingDismissed] = useState(readOnboardingDismissed);
  const [configurableExpanded, setConfigurableExpanded] = useState(
    () => window.localStorage.getItem(HOME_CONFIGURABLE_STORAGE_KEY) === '1',
  );

  useRouteFocusTarget({
    routeId: APP_ROUTE_PATHS.home,
    headingRef: pageHeadingRef,
    ready: true,
  });

  const applyAttentionData = useCallback((result: HomeAttentionLoadResult) => {
    setData(result.data);
    setFailedSourceCount(result.failedSourceCount);
    setLoadedAt(result.loadedAt);
    setIsLoading(false);
  }, []);

  const loadAttentionData = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const result = await fetchHomeAttentionData();
    if (requestIdRef.current !== requestId) return;
    applyAttentionData(result);
  }, [applyAttentionData]);

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
    let active = true;
    systemConfigApi.getSetupStatus()
      .then((status) => {
        if (active) setSetupStatus(status);
      })
      .catch(() => {
        if (active) setSetupStatus(null);
      });
    return () => {
      active = false;
    };
  }, []);

  const actionLabels = useMemo(() => buildDecisionActionLabelMap(t), [t]);
  const focusSignals = useMemo(
    () => data.activeSignals.slice(0, FOCUS_ITEM_LIMIT),
    [data.activeSignals],
  );
  const dueSignals = useMemo(() => {
    return data.activeSignals.filter((item) => isReassessmentDue(item, loadedAt));
  }, [data.activeSignals, loadedAt]);
  const latestMarketReview = useMemo(
    () => data.historyItems.find((item) => item.reportType === 'market_review' || item.stockCode === 'MARKET'),
    [data.historyItems],
  );
  const recentAnalyses = useMemo(
    () => data.historyItems
      .filter((item) => item.reportType !== 'market_review' && item.stockCode !== 'MARKET')
      .slice(0, RECENT_ANALYSIS_LIMIT),
    [data.historyItems],
  );
  const setupMissingLabels = useMemo(() => setupStatus?.checks
    .filter((check) => check.required && check.status === 'needs_action')
    .map((check) => check.title)
    .slice(0, 3)
    .join(getUiListSeparator(language)) ?? '', [language, setupStatus]);

  const toggleConfigurable = useCallback(() => {
    setConfigurableExpanded((expanded) => {
      const next = !expanded;
      window.localStorage.setItem(HOME_CONFIGURABLE_STORAGE_KEY, next ? '1' : '0');
      return next;
    });
  }, []);

  const handleDismissOnboarding = useCallback(() => {
    dismissOnboarding();
    setOnboardingDismissed(true);
  }, []);
  const handleRefresh = useCallback(() => {
    setIsLoading(true);
    void loadAttentionData();
  }, [loadAttentionData]);

  const analysisHref = buildAnalysisWorkbenchHref({
    segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch,
  });
  const signalCenterHref = buildSignalCenterHref({ scope: SIGNAL_CENTER_SCOPE_VALUES.all });
  const reviewHref = buildSignalCenterHref({
    scope: SIGNAL_CENTER_SCOPE_VALUES.all,
    tab: SIGNAL_CENTER_TAB_VALUES.review,
  });

  return (
    <WorkspacePage data-testid="home-attention-hub" contentClassName="space-y-6">
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
            <Button variant="primary" size="comfortable" onClick={() => navigate(analysisHref)}>
              <PlayCircle aria-hidden="true" />
              {t('home.startAnalysisTitle')}
            </Button>
          </>
        )}
      />

      {setupStatus && !setupStatus.isComplete && !onboardingDismissed ? (
        <InlineAlert
          variant="warning"
          size="compact"
          title={t('home.setupIncomplete')}
          message={setupMissingLabels
            ? t('home.setupMissingWithLabels', { labels: setupMissingLabels })
            : t('home.setupMissingGeneric')}
          action={(
            <div className="flex items-center gap-1">
              <Button
                variant="secondary"
                size="default"
                onClick={() => navigate(buildSettingsHref({
                  section: 'overview',
                  view: 'readiness',
                  source: 'onboarding',
                }))}
              >
                {t('home.startGuidedSetup')}
              </Button>
              <IconButton
                variant="ghost"
                size="default"
                aria-label={t('common.close')}
                onClick={handleDismissOnboarding}
              >
                <X aria-hidden="true" />
              </IconButton>
            </div>
          )}
        />
      ) : null}

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

      <div data-testid="home-core-blocks" className="grid gap-4 xl:grid-cols-3">
        <Section
          title={t('home.todayFocus')}
          description={t('home.todayFocusDescription')}
          level="section"
          padding="md"
          actions={<Activity className="h-5 w-5 text-primary" aria-hidden="true" />}
        >
          {isLoading ? (
            <StatePanel state="loading" title={t('common.loading')} size="compact" />
          ) : focusSignals.length > 0 ? (
            <div className="divide-y divide-border/70">
              {focusSignals.map((item) => {
                const presentation = getDecisionSignalPresentation(item, actionLabels);
                return (
                  <button
                    key={item.id}
                    type="button"
                    className="flex min-h-14 w-full items-center justify-between gap-3 py-3 text-left transition-colors hover:text-primary"
                    onClick={() => navigate(buildSignalCenterHref({
                      scope: SIGNAL_CENTER_SCOPE_VALUES.all,
                      stock: item.stockCode,
                    }))}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold text-foreground">
                        {item.stockName || item.stockCode}
                      </span>
                      <span className="mt-1 block truncate text-xs text-secondary-text">
                        {presentation.label} · {item.stockCode}
                      </span>
                    </span>
                    <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
                  </button>
                );
              })}
            </div>
          ) : (
            <EmptyState
              compact
              title={t('home.noFocusTitle')}
              description={t('home.noFocusDescription')}
              action={(
                <Button variant="primary" size="default" onClick={() => navigate(analysisHref)}>
                  {t('home.startAnalysisTitle')}
                </Button>
              )}
            />
          )}
        </Section>

        <Section
          title={t('home.todos')}
          description={t('home.todosDescription')}
          level="section"
          padding="md"
          actions={<ClipboardCheck className="h-5 w-5 text-warning" aria-hidden="true" />}
        >
          {isLoading ? (
            <StatePanel state="loading" title={t('common.loading')} size="compact" />
          ) : dueSignals.length > 0 ? (
            <div className="space-y-3">
              <button
                type="button"
                className="flex min-h-14 w-full items-center justify-between gap-3 rounded-lg border border-warning/25 bg-warning/10 px-3 py-2 text-left"
                onClick={() => navigate(reviewHref)}
              >
                <span>
                  <span className="block text-sm font-semibold text-foreground">
                    {t('home.reassessmentDue', { count: dueSignals.length })}
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
        </Section>

        <Section
          title={t('home.signalSummary')}
          description={t('home.signalSummaryDescription')}
          level="section"
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
                    {data.activeSignalTotal}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-secondary-text">{t('home.triggeredAlerts')}</dt>
                  <dd className="mt-1 text-xl font-semibold tabular-nums text-foreground">
                    {data.triggeredAlertTotal}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-secondary-text">{t('home.dueReassessments')}</dt>
                  <dd className="mt-1 text-xl font-semibold tabular-nums text-foreground">
                    {dueSignals.length}
                  </dd>
                </div>
              </dl>
              <Button variant="secondary" size="default" onClick={() => navigate(signalCenterHref)}>
                {t('decisionSignals.viewAll')}
                <ArrowRight aria-hidden="true" />
              </Button>
            </div>
          )}
        </Section>
      </div>

      <section className="border-t border-border pt-4" aria-labelledby="home-configurable-heading">
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

        <div id="home-configurable-content" className="mt-4 grid gap-4 lg:grid-cols-2" hidden={!configurableExpanded}>
          <Section
            title={t('home.morningReport')}
            level="section"
            padding="md"
            actions={<CalendarClock className="h-5 w-5 text-primary" aria-hidden="true" />}
          >
            {latestMarketReview ? (
              <button
                type="button"
                className="flex min-h-14 w-full items-center justify-between gap-3 text-left"
                onClick={() => navigate({
                  pathname: APP_ROUTE_PATHS.researchMarket,
                  search: `?${REPORT_ROUTE_QUERY_KEYS.recordId}=${latestMarketReview.id}`,
                })}
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

          <Section title={t('home.recentAnalyses')} level="section" padding="md">
            {recentAnalyses.length > 0 ? (
              <div className="divide-y divide-border/70">
                {recentAnalyses.map((item) => (
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
        </div>
      </section>
    </WorkspacePage>
  );
};

export default HomePage;
