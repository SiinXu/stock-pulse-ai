/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { useState } from 'react';
import { StockAutocomplete } from '../../components/StockAutocomplete/StockAutocomplete';
import { SuggestionsList } from '../../components/StockAutocomplete/SuggestionsList';
import { TaskPanel } from '../../components/tasks/TaskPanel';
import {
  HomeStockWorkspace,
  type HomeWatchlistRow,
  type HomeWorkspaceTab,
} from '../../components/watchlist/HomeStockWorkspace';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { PLAYGROUND_TEXT } from '../../locales/playground';
import type { TaskInfo } from '../../types/analysis';
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
  const [activeTab, setActiveTab] = useState<HomeWorkspaceTab>('watchlist');
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

export const WORKSPACE_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'stock-autocomplete': StockAutocompleteStory,
  'suggestions-list': SuggestionsListStory,
  'task-panel': TaskPanelStory,
  'home-stock-workspace': HomeStockWorkspaceStory,
};
