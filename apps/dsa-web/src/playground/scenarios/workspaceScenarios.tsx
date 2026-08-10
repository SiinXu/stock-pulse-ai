/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { lazy, useState } from 'react';
import { Button } from '../../components/common';
import { StockAutocomplete } from '../../components/StockAutocomplete/StockAutocomplete';
import { SuggestionsList } from '../../components/StockAutocomplete/SuggestionsList';
import { HomeReadinessCard } from '../../components/home/HomeReadinessCard';
import { AgentOnboardingWizard } from '../../components/onboarding/AgentOnboardingWizard';
import { HomeOnboardingSection } from '../../components/onboarding/HomeOnboardingSection';
import { OnboardingTodayPlanCard } from '../../components/onboarding/OnboardingTodayPlanCard';
import { TaskPanel } from '../../components/tasks/TaskPanel';
import {
  HomeStockWorkspace,
  type HomeWatchlistRow,
  type HomeWorkspaceTab,
} from '../../components/watchlist/HomeStockWorkspace';
import { WatchlistScoreColumn } from '../../components/watchlist/WatchlistScoreColumn';
import type { WatchlistScoreItem } from '../../types/watchlistScore';
import { HomeWatchlistGroupsSection } from '../../components/watchlist/HomeWatchlistGroupsSection';
import { WatchlistGroupsPanel } from '../../components/watchlist/WatchlistGroupsPanel';
import { createParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { PLAYGROUND_TEXT } from '../../locales/playground';
import { HOME_WORKSPACE_VALUES } from '../../routing/routes';
import type { TaskInfo } from '../../types/analysis';
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

const HomeStockWorkspaceStory = () => {
  const { scenario, profile } = usePlaygroundScenario();
  const [activeTab, setActiveTab] = useState<HomeWorkspaceTab>(HOME_WORKSPACE_VALUES.watchlist);
  const [codes, setCodes] = useState(['600519', 'AAPL']);
  const isEmpty = scenario === 'empty' || profile === 'empty';
  const isError = scenario === 'error' || profile === 'error';
  const isLoading = scenario === 'loading' || profile === 'slow';
  const rows: HomeWatchlistRow[] = isEmpty ? [] : codes.map((code, index) => ({
    code,
    latestItem: fixtureStockBarItems[index],
    analyzedToday: index === 0,
    isTodayStatusLoading: isLoading,
    isTodayStatusUnknown: isError,
    activeTask: index === 1 ? fixtureTasks[0] : undefined,
  }));
  return (
    <HomeStockWorkspace
      activeTab={activeTab}
      onTabChange={setActiveTab}
      watchlistRows={rows}
      watchlistLoading={isLoading}
      watchlistActioning={false}
      watchlistLoadError={isError}
      watchlistMessage={null}
      onAddToWatchlist={async (code) => {
        setCodes((current) => current.includes(code) ? current : [...current, code]);
        return true;
      }}
      onRemoveFromWatchlist={async (code) => {
        setCodes((current) => current.filter((item) => item !== code));
        return true;
      }}
      onRefreshWatchlist={async () => true}
      onAnalyzeWatchlist={async () => undefined}
      isBatchAnalyzing={isLoading}
      batchStatus={null}
      todayItems={isEmpty ? [] : fixtureStockBarItems}
      isLoadingTodayItems={isLoading}
      todayLoadError={isError}
      watchlistAnalyzedTodayCount={isEmpty ? 0 : 1}
      historyItems={isEmpty ? [] : fixtureStockBarItems}
      isLoadingHistory={isLoading}
      selectedRecordId={fixtureStockBarItems[0]?.id}
      onHistoryItemClick={() => undefined}
      onDeleteStock={(code) => setCodes((current) => current.filter((item) => item !== code))}
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
        onReorderGroups={async (orderedIds) => {
          setGroups((current) => orderedIds.map((id) => current.find((group) => group.id === id)!).filter(Boolean));
          return true;
        }}
        onReorderMembers={async () => true}
        onMoveMember={async () => true}
        onRemoveFromWatchlist={async () => true}
      />
    </div>
  );
};

const HomeWatchlistGroupsSectionStory = () => <HomeWatchlistGroupsSection />;

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

const scoredFixture: WatchlistScoreItem = {
  stockCode: '600519',
  status: 'scored',
  score: 72,
  asOf: '2026-08-08T09:00:00+00:00',
  ageDays: 1,
  analysisId: 5,
  operationAdvice: 'Buy',
  freshness: 'recent',
  degradedReasons: [],
  factors: [
    {
      key: 'analysis_sentiment',
      status: 'applied',
      value: 72,
      params: { operationAdvice: 'Buy', reportType: 'detailed' },
      reason: null,
      source: {
        id: 5,
        sourceReportId: 5,
        profile: null,
        asOf: '2026-08-08T09:00:00+00:00',
        expiresAt: null,
        formulaVersion: 'watchlist_score_v1',
      },
    },
    {
      key: 'decision_signal',
      status: 'applied',
      value: 'buy',
      params: { confidence: 0.8, profile: 'balanced' },
      reason: null,
      source: {
        id: 8,
        sourceReportId: 5,
        profile: 'balanced',
        asOf: '2026-08-08T10:00:00+00:00',
        expiresAt: '2026-08-10T10:00:00+00:00',
        formulaVersion: 'watchlist_score_v1',
      },
    },
  ],
};

const unanalyzedFixture: WatchlistScoreItem = {
  stockCode: 'AAPL',
  status: 'unanalyzed',
  score: null,
  asOf: null,
  ageDays: null,
  analysisId: null,
  operationAdvice: null,
  factors: [],
  freshness: 'none',
  degradedReasons: [],
};

const WatchlistScoreColumnStory = () => {
  const { scenario } = usePlaygroundScenario();
  if (scenario === 'empty') {
    return (
      <div className="max-w-sm rounded-lg border border-border bg-card p-4">
        <WatchlistScoreColumn item={unanalyzedFixture} />
      </div>
    );
  }
  if (scenario === 'interactive') {
    return (
      <div className="max-w-sm space-y-3 rounded-lg border border-border bg-card p-4">
        <WatchlistScoreColumn item={scoredFixture} expanded />
        <WatchlistScoreColumn item={unanalyzedFixture} />
      </div>
    );
  }
  return (
    <div className="max-w-sm rounded-lg border border-border bg-card p-4">
      <WatchlistScoreColumn item={scoredFixture} />
    </div>
  );
};

export const WORKSPACE_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'stock-autocomplete': StockAutocompleteStory,
  'suggestions-list': SuggestionsListStory,
  'task-panel': TaskPanelStory,
  'home-stock-workspace': HomeStockWorkspaceStory,
  'home-watchlist-groups-section': HomeWatchlistGroupsSectionStory,
  'watchlist-groups-panel': WatchlistGroupsPanelStory,
  'home-readiness-card': HomeReadinessCardStory,
  'home-onboarding-section': HomeOnboardingSectionStory,
  'onboarding-today-plan-card': OnboardingTodayPlanCardStory,
  'agent-onboarding-wizard': AgentOnboardingWizardStory,
  'zero-config-first-run-panel': ZeroConfigFirstRunPanelStory,
  'watchlist-score-column': WatchlistScoreColumnStory,
};
