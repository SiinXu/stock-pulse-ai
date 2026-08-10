/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { useState } from 'react';
import {
  HomeStockWorkspace,
  type HomeWatchlistRow,
  type HomeWorkspaceTab,
} from '../../components/watchlist/HomeStockWorkspace';
import { WatchlistScoreColumn } from '../../components/watchlist/WatchlistScoreColumn';
import type { WatchlistScoreItem } from '../../types/watchlistScore';
import { HOME_WORKSPACE_VALUES } from '../../routing/routes';
import { fixtureStockBarItems, fixtureTasks } from '../fixtures';
import { usePlaygroundScenario } from '../scenarioContext';
import type { PlaygroundScenarioRenderer } from '../types';

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

export const WATCHLIST_WORKSPACE_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'home-stock-workspace': HomeStockWorkspaceStory,
  'watchlist-score-column': WatchlistScoreColumnStory,
};
