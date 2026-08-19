/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { lazy, Suspense, useState } from 'react';
import { Button, ToastProvider } from '../../components/common';
import { StockAutocomplete } from '../../components/StockAutocomplete/StockAutocomplete';
import { SuggestionsList } from '../../components/StockAutocomplete/SuggestionsList';
import { HomeAlertsWidget } from '../../components/dashboard/HomeAlertsWidget';
import { HomeDashboardLayout } from '../../components/dashboard/HomeDashboardLayout';
import { HomePortfolioHealthWidget } from '../../components/dashboard/HomePortfolioHealthWidget';
import { HomeRecentReportsWidget } from '../../components/dashboard/HomeRecentReportsWidget';
import { HomeReadinessCard } from '../../components/home/HomeReadinessCard';
import { HomeSignalSummary } from '../../components/home/HomeSignalSummary';
import { AgentOnboardingWizard } from '../../components/onboarding/AgentOnboardingWizard';
import { HomeOnboardingSection } from '../../components/onboarding/HomeOnboardingSection';
import { OnboardingTodayPlanCard } from '../../components/onboarding/OnboardingTodayPlanCard';
import { TaskPanel } from '../../components/tasks/TaskPanel';
import { HomeWatchlistGroupsSection } from '../../components/watchlist/HomeWatchlistGroupsSection';
import { WatchlistGroupsPanel } from '../../components/watchlist/WatchlistGroupsPanel';
import { MoneyFlowPanel } from '../../components/money-flow/MoneyFlowPanel';
import type { MoneyFlowView } from '../../api/moneyFlow';
import { createParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { PLAYGROUND_TEXT } from '../../locales/playground';
import type { HistoryItem, TaskInfo } from '../../types/analysis';
import {
  DEFAULT_ONBOARDING_PROFILE,
  type OnboardingPlan,
} from '../../types/onboarding';
import type { WatchlistGroup } from '../../types/watchlist';
import type { SetupStatusResponse } from '../../types/systemConfig';
import { fixtureStockBarItems, fixtureSuggestions, fixtureTasks } from '../fixtures';
import { usePlaygroundScenario } from '../scenarioContext';
import type { PlaygroundScenarioRenderer } from '../types';

const useSamples = () => {
  const { language } = useUiLanguage();
  return PLAYGROUND_TEXT[language].samples;
};

const LazyTodaysFocusStory = lazy(() => import('./todaysFocusScenario'));

const LazyZeroConfigFirstRunPanelStory = lazy(async () => {
  const module = await import('./zeroConfigFirstRunScenario');
  return { default: module.ZeroConfigFirstRunPanelStory };
});

const ZeroConfigFirstRunPanelStory = () => <LazyZeroConfigFirstRunPanelStory />;

const StockAutocompleteStory = () => {
  const text = useSamples();
  const { scenario } = usePlaygroundScenario();
  const [value, setValue] = useState('');
  return (
    <div className="max-w-xl rounded-lg border border-border bg-card p-4">
      <StockAutocomplete
        value={value}
        onChange={setValue}
        onSubmit={(code) => setValue(code)}
        disabled={scenario === 'states'}
        ariaLabel={text.searchPlaceholder}
      />
    </div>
  );
};

const SuggestionsListStory = () => {
  const { scenario } = usePlaygroundScenario();
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const [items, setItems] = useState(scenario === 'empty' ? [] : fixtureSuggestions);
  return (
    <div className="relative min-h-64 max-w-xl">
      <SuggestionsList
        suggestions={items}
        highlightedIndex={highlightedIndex}
        onMouseEnter={setHighlightedIndex}
        onSelect={(suggestion) => setItems([suggestion])}
        style={{ position: 'relative', inset: 'auto', width: '100%' }}
      />
    </div>
  );
};

const TaskPanelStory = () => {
  const { scenario } = usePlaygroundScenario();
  const initialTasks: TaskInfo[] = scenario === 'states'
    ? fixtureTasks.map((task, index) => ({ ...task, status: index === 0 ? 'failed' : 'cancel_requested' }))
    : fixtureTasks;
  const [tasks, setTasks] = useState(scenario === 'loading'
    ? fixtureTasks.map((task) => ({ ...task, status: 'processing' as const, progress: 28 }))
    : initialTasks);
  return (
    <TaskPanel
      tasks={tasks}
      onOpenRunFlow={() => undefined}
      onDismiss={(taskId) => setTasks((current) => current.filter((task) => task.taskId !== taskId))}
    />
  );
};

const WATCHLIST_GROUP_FIXTURES: WatchlistGroup[] = [
  {
    id: 'default',
    name: '__default__',
    nameKey: 'watchlist.defaultGroupName',
    sortOrder: 0,
    isDefault: true,
    createdAt: '2026-08-09T00:00:00+00:00',
    updatedAt: '2026-08-09T00:00:00+00:00',
    members: [
      { stockCode: '600519', sortOrder: 0, attrs: { schemaVersion: 1, aiScore: 91, focus: true } },
      { stockCode: 'AAPL', sortOrder: 1, attrs: { schemaVersion: 1 } },
    ],
  },
  {
    id: 'growth',
    name: 'Growth',
    nameKey: null,
    sortOrder: 1,
    isDefault: false,
    createdAt: '2026-08-09T00:00:00+00:00',
    updatedAt: '2026-08-09T00:00:00+00:00',
    members: [],
  },
];

const WatchlistGroupsPanelStory = () => {
  const [groups, setGroups] = useState(WATCHLIST_GROUP_FIXTURES);
  return (
    <ToastProvider>
    <div className="max-w-3xl rounded-xl border border-border bg-card p-4">
      <WatchlistGroupsPanel
        groups={groups}
        watchlistRows={[
          { code: '600519', analyzedToday: true, latestItem: fixtureStockBarItems[0] },
          { code: 'AAPL', analyzedToday: false, latestItem: fixtureStockBarItems[1] },
        ]}
        onCreateGroup={async (name) => {
          setGroups((current) => [...current, {
            id: `group-${current.length}`,
            name,
            sortOrder: current.length,
            isDefault: false,
            createdAt: '2026-08-09T00:00:00+00:00',
            updatedAt: '2026-08-09T00:00:00+00:00',
            members: [],
          }]);
          return true;
        }}
        onDeleteGroup={async (groupId) => {
          setGroups((current) => current.filter((group) => group.id !== groupId));
          return true;
        }}
        onRestoreGroup={async (snapshot) => {
          setGroups((current) => {
            if (current.some((group) => group.id === snapshot.groupId)) return current;
            const restored = {
              id: snapshot.groupId,
              name: snapshot.name,
              sortOrder: current.length,
              isDefault: false,
              createdAt: '2026-08-09T00:00:00+00:00',
              updatedAt: '2026-08-09T00:00:00+00:00',
              members: snapshot.memberCodes.map((stockCode, sortOrder) => ({
                stockCode,
                sortOrder,
                attrs: { schemaVersion: 1 as const },
              })),
            };
            const byId = new Map(current.map((group) => [group.id, group]));
            byId.set(restored.id, restored);
            return snapshot.orderedGroupIds
              .map((id) => byId.get(id))
              .filter((group): group is NonNullable<typeof group> => Boolean(group));
          });
          return true;
        }}
        onReorderGroups={async (orderedIds) => {
          setGroups((current) => orderedIds.map((id) => current.find((group) => group.id === id)!).filter(Boolean));
          return true;
        }}
        onReorderMembers={async () => true}
        onMoveMember={async () => true}
        onRemoveFromWatchlist={async () => true}
      />
    </div>
    </ToastProvider>
  );
};

const HomeWatchlistGroupsSectionStory = () => <HomeWatchlistGroupsSection />;

const FIXTURE_RECENT_REPORTS: HistoryItem[] = [
  {
    id: 101,
    queryId: 'query-fixture-101',
    stockCode: 'AAPL',
    stockName: 'Apple',
    reportType: 'detailed',
    createdAt: '2026-08-09T12:00:00Z',
  },
];

const HomeDashboardLayoutStory = () => (
  <HomeDashboardLayout
    widgets={{
      watchlist: <div className="rounded-lg border border-border p-3 text-sm" data-testid="playground-watchlist-fixture" />,
      portfolio_health: <HomePortfolioHealthWidget />,
      alerts: (
        <HomeAlertsWidget
          isLoading={false}
          available
          triggeredAlertTotal={2}
          onRetry={() => undefined}
        />
      ),
      recent_reports: (
        <HomeRecentReportsWidget
          isLoading={false}
          available
          items={FIXTURE_RECENT_REPORTS}
          language="en"
          onRetry={() => undefined}
        />
      ),
    }}
  />
);

const HomeAlertsWidgetStory = () => (
  <HomeAlertsWidget
    isLoading={false}
    available
    triggeredAlertTotal={3}
    onRetry={() => undefined}
  />
);

const HomePortfolioHealthWidgetStory = () => <HomePortfolioHealthWidget />;

const HomeRecentReportsWidgetStory = () => (
  <HomeRecentReportsWidget
    isLoading={false}
    available
    items={FIXTURE_RECENT_REPORTS}
    language="en"
    onRetry={() => undefined}
  />
);

const FIXTURE_SETUP_STATUS: SetupStatusResponse = {
  isComplete: false,
  readyForSmoke: false,
  requiredMissingKeys: ['LITELLM_MODEL'],
  nextStepKey: 'llm_primary',
  checks: [
    {
      key: 'llm_primary',
      title: 'Primary model',
      category: 'ai_model',
      required: true,
      status: 'needs_action',
      message: 'Primary model is not configured.',
      nextStep: 'Configure a primary model in Settings.',
    },
    {
      key: 'data_source',
      title: 'Data source',
      category: 'base',
      required: true,
      status: 'configured',
      message: 'Data providers are ready.',
    },
  ],
};

const FIXTURE_ONBOARDING_PLAN: OnboardingPlan = {
  schemaVersion: 1,
  engine: 'rules',
  llmNote: 'Fixture plan generated without LLM.',
  modelAvailable: false,
  preferLlm: false,
  profile: DEFAULT_ONBOARDING_PROFILE,
  featureStage: 'beginner',
  featurePath: {
    stage: 'beginner',
    label: 'Beginner path',
    primaryPath: ['Configure model', 'Run first analysis'],
    emphasize: ['Home readiness'],
    defer: ['Advanced routing'],
  },
  recommendedPresetId: 'fixture-preset',
  recommendedPresetName: 'Fixture preset',
  beginnerModeRecommended: true,
  configChanges: [],
  configItems: [],
  todos: [
    {
      id: 'todo-1',
      priority: 1,
      title: 'Configure primary model',
      description: 'Add a usable model before the first analysis.',
      href: '/settings',
      kind: 'setup',
    },
  ],
  todayPlan: [
    {
      id: 'today-1',
      title: 'Open Settings',
      detail: 'Configure a primary model route.',
    },
    {
      id: 'today-2',
      title: 'Run first analysis',
      detail: 'Analyze one watchlist symbol.',
    },
  ],
  weekPlan: [],
  disclaimer: 'Fixture onboarding plan for playground preview only.',
  generatedAt: '2026-07-20T12:00:00Z',
};

const HomeReadinessCardStory = () => {
  const { scenario } = usePlaygroundScenario();
  const { t } = useUiLanguage();
  const isLoading = scenario === 'loading';
  const isError = scenario === 'error';
  const isEmpty = scenario === 'empty';
  return (
    <div className="max-w-xl">
      <HomeReadinessCard
        status={isEmpty || isLoading || isError ? null : FIXTURE_SETUP_STATUS}
        isLoading={isLoading}
        error={isError ? createParsedApiError({ title: 'Fixture error', message: 'Unable to load readiness.' }) : null}
        lastSuccess={isEmpty ? null : { ok: true, href: '/history', detail: 'Last analysis succeeded' }}
        onRefresh={() => undefined}
        dismissible
        onDismiss={() => undefined}
        t={t}
      />
    </div>
  );
};

const HomeSignalSummaryStory = () => {
  const { scenario } = usePlaygroundScenario();
  const isLoading = scenario === 'loading';
  const isError = scenario === 'error';
  const hasSnapshot = !isLoading && !isError;
  return (
    <div className="max-w-xl">
      <HomeSignalSummary
        isLoading={isLoading}
        availability={{
          activeSignals: hasSnapshot,
          reassessments: hasSnapshot,
          alerts: hasSnapshot,
        }}
        data={{
          activeSignalTotal: hasSnapshot ? 4 : null,
          triggeredAlertTotal: hasSnapshot ? 2 : null,
          dueReassessmentTotal: hasSnapshot ? 1 : null,
        }}
        stale={{
          activeSignals: false,
          reassessments: false,
          alerts: false,
        }}
        onRetry={() => undefined}
        onViewAll={() => undefined}
      />
    </div>
  );
};

const TodaysFocusPanelStory = () => {
  return (
    <Suspense fallback={null}>
      <LazyTodaysFocusStory />
    </Suspense>
  );
};

const HomeOnboardingSectionStory = () => {
  const { scenario } = usePlaygroundScenario();
  const { t } = useUiLanguage();
  const [dismissed, setDismissed] = useState(scenario === 'empty');
  return (
    <div className="max-w-2xl space-y-3">
      <HomeOnboardingSection
        setupStatus={scenario === 'empty' ? { ...FIXTURE_SETUP_STATUS, isComplete: true, requiredMissingKeys: [], checks: FIXTURE_SETUP_STATUS.checks.map((check) => ({ ...check, status: 'configured' })) } : FIXTURE_SETUP_STATUS}
        setupMissingLabels={scenario === 'empty' ? '' : 'Primary model'}
        onboardingDismissed={dismissed}
        onDismissOnboarding={() => setDismissed(true)}
        onSetupRefresh={() => undefined}
        reportLanguage="en"
        t={t}
      />
    </div>
  );
};

const OnboardingTodayPlanCardStory = () => {
  const { t } = useUiLanguage();
  return (
    <div className="max-w-xl">
      <OnboardingTodayPlanCard plan={FIXTURE_ONBOARDING_PLAN} t={t} onDismiss={() => undefined} />
    </div>
  );
};

const AgentOnboardingWizardStory = () => {
  const { t } = useUiLanguage();
  const text = useSamples();
  const [open, setOpen] = useState(true);
  return (
    <div className="space-y-3">
      <Button variant="primary" onClick={() => setOpen(true)}>{text.openAgentOnboardingWizard}</Button>
      <AgentOnboardingWizard
        open={open}
        onClose={() => setOpen(false)}
        onApplied={() => setOpen(false)}
        modelAvailable={false}
        reportLanguage="en"
        t={t}
      />
    </div>
  );
};


const FIXTURE_MONEY_FLOW_VIEW: MoneyFlowView = {
  schemaVersion: 'money_flow_view/1.0',
  stockCode: '600519',
  enabled: true,
  status: 'partial',
  requestedDays: 5,
  asOf: '2026-08-08T08:00:00+00:00',
  providerDate: '2026-08-08',
  ageDays: 0,
  source: 'akshare:stock_individual_fund_flow',
  message: 'Money-flow data is degraded (status=partial).',
  warnings: ['money_flow_amount_scale_is_not_authoritatively_calibrated'],
  sourceChain: [{ provider: 'akshare', status: 'success' }],
  disclaimer: 'Research evidence only.',
  snapshot: {
    code: '600519',
    date: '2026-08-08',
    source: 'akshare:stock_individual_fund_flow',
    market: 'cn',
    mainNetInflowRatio: 1.5,
    superLargeNetInflowRatio: 0.8,
    largeNetInflowRatio: 0.7,
    mediumNetInflowRatio: -0.3,
    smallNetInflowRatio: -1.2,
    unit: 'unknown',
    amountScale: 'unknown',
    bucketDefinition: 'eastmoney_em_order_size_buckets_v1',
    asOf: '2026-08-08T08:00:00+00:00',
    completeness: 'complete',
    observedDays: 5,
    requestedDays: 5,
    attitude: 'inflow',
    calibrationNote: 'Order-size buckets follow bucket_definition.',
  },
};

const MoneyFlowPanelStory = () => {
  const { scenario } = usePlaygroundScenario();
  return (
    <MoneyFlowPanel
      stockCode="600519"
      initialView={scenario === 'states' ? { ...FIXTURE_MONEY_FLOW_VIEW, status: 'disabled', enabled: false, snapshot: undefined, message: 'SmartMoney money-flow is disabled.' } : FIXTURE_MONEY_FLOW_VIEW}
    />
  );
};

export const WORKSPACE_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'money-flow-panel': MoneyFlowPanelStory,
  'stock-autocomplete': StockAutocompleteStory,
  'suggestions-list': SuggestionsListStory,
  'task-panel': TaskPanelStory,
  'home-watchlist-groups-section': HomeWatchlistGroupsSectionStory,
  'watchlist-groups-panel': WatchlistGroupsPanelStory,
  'home-dashboard-layout': HomeDashboardLayoutStory,
  'home-alerts-widget': HomeAlertsWidgetStory,
  'home-portfolio-health-widget': HomePortfolioHealthWidgetStory,
  'home-recent-reports-widget': HomeRecentReportsWidgetStory,
  'home-readiness-card': HomeReadinessCardStory,
  'home-signal-summary': HomeSignalSummaryStory,
  'todays-focus-panel': TodaysFocusPanelStory,
  'home-onboarding-section': HomeOnboardingSectionStory,
  'onboarding-today-plan-card': OnboardingTodayPlanCardStory,
  'agent-onboarding-wizard': AgentOnboardingWizardStory,
  'zero-config-first-run-panel': ZeroConfigFirstRunPanelStory,
};
