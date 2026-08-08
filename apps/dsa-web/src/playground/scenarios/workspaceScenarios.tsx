/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { useState } from 'react';
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
import { createParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { PLAYGROUND_TEXT } from '../../locales/playground';
import { HOME_WORKSPACE_VALUES } from '../../routing/routes';
import type { TaskInfo } from '../../types/analysis';
import { DEFAULT_ONBOARDING_PROFILE, type OnboardingPlan } from '../../types/onboarding';
import type { SetupStatusResponse } from '../../types/systemConfig';
import { fixtureStockBarItems, fixtureSuggestions, fixtureTasks } from '../fixtures';
import { usePlaygroundScenario } from '../scenarioContext';
import type { PlaygroundScenarioRenderer } from '../types';

const useSamples = () => {
  const { language } = useUiLanguage();
  return PLAYGROUND_TEXT[language].samples;
};

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
  const [open, setOpen] = useState(true);
  return (
    <div className="space-y-3">
      <Button variant="primary" onClick={() => setOpen(true)}>Open agent onboarding wizard</Button>
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

export const WORKSPACE_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'stock-autocomplete': StockAutocompleteStory,
  'suggestions-list': SuggestionsListStory,
  'task-panel': TaskPanelStory,
  'home-stock-workspace': HomeStockWorkspaceStory,
  'home-readiness-card': HomeReadinessCardStory,
  'home-onboarding-section': HomeOnboardingSectionStory,
  'onboarding-today-plan-card': OnboardingTodayPlanCardStory,
  'agent-onboarding-wizard': AgentOnboardingWizardStory,
};
