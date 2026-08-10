// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { alertsApi } from '../../api/alerts';
import { decisionSignalsApi } from '../../api/decisionSignals';
import { historyApi } from '../../api/history';
import { onboardingApi } from '../../api/onboarding';
import { scheduledTasksApi } from '../../api/scheduledTasks';
import { systemConfigApi } from '../../api/systemConfig';
import { getTodaysFocus } from '../../api/todaysFocus';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import type { TodaysFocusResponse } from '../../types/todaysFocus';
import {
  RouteFocusRegistrationContext,
  type RouteFocusTarget,
} from '../../contexts/routeFocusContext';
import {
  ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS,
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  APP_ROUTE_PATHS,
  SIGNAL_CENTER_ROUTE_QUERY_KEYS,
  SIGNAL_CENTER_TAB_VALUES,
} from '../../routing/routes';
import {
  ONBOARDING_DISMISSED_STORAGE_KEY,
} from '../../utils/onboardingPreferences';
import HomePage, { HOME_CONFIGURABLE_STORAGE_KEY } from '../HomePage';

vi.mock('../../api/decisionSignals', () => ({
  decisionSignalsApi: {
    list: vi.fn(),
  },
}));

vi.mock('../../api/alerts', () => ({
  alertsApi: {
    listTriggers: vi.fn(),
  },
}));

vi.mock('../../api/history', () => ({
  historyApi: {
    getList: vi.fn(),
  },
}));

vi.mock('../../api/scheduledTasks', () => ({
  scheduledTasksApi: {
    getToday: vi.fn(),
  },
}));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getSetupStatus: vi.fn(),
  },
}));

vi.mock('../../api/onboarding', () => ({
  onboardingApi: {
    getFirstRunReadiness: vi.fn(),
    getDemoAnalysis: vi.fn(),
  },
}));

vi.mock('../../api/todaysFocus', () => ({
  getTodaysFocus: vi.fn(),
}));

const emptyTodaysFocus: TodaysFocusResponse = {
  packVersion: 'todays_focus/2.0',
  generatedAt: '2026-08-09T00:00:00Z',
  status: 'empty',
  maxItems: 5,
  itemCount: 0,
  items: [],
  emptyReason: 'no_fresh_deterministic_signals',
  emptyMessage: 'No symbols need special attention today.',
  sourcesUsed: [],
  degradedSources: [],
  temporalPolicy: {
    semantics: 'local_calendar_day',
    timezone: 'UTC',
    localDate: '2026-08-09',
    windowStart: '2026-08-08T16:00:00Z',
    windowEnd: '2026-08-09T00:00:00Z',
    naiveTimestampPolicy: 'assume_utc',
    missingTimestampPolicy: 'exclude',
    nonTradingDayPolicy: 'same_local_day_only',
  },
  universeContract: {
    symbolCount: 0,
    hardCap: 1000,
    truncated: false,
    sources: ['watchlist_config'],
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
};

const routeFocusRegister = vi.fn((target: RouteFocusTarget) => {
  void target;
  return () => {};
});

const activeSignal = {
  id: 17,
  stockCode: 'AAPL',
  stockName: 'Apple',
  market: 'us' as const,
  sourceType: 'analysis' as const,
  triggerSource: 'analysis',
  action: 'hold' as const,
  actionLabel: 'Hold',
  confidence: 0.82,
  planQuality: 'complete' as const,
  status: 'active' as const,
  expiresAt: new Date(Date.now() - 60_000).toISOString(),
  createdAt: '2026-07-23T10:00:00Z',
};

const analysisHistory = {
  id: 41,
  queryId: 'analysis-41',
  stockCode: 'AAPL',
  stockName: 'Apple',
  reportType: 'detailed' as const,
  createdAt: '2026-07-23T11:00:00Z',
};

const marketHistory = {
  id: 42,
  queryId: 'market-42',
  stockCode: 'MARKET',
  stockName: 'Market review',
  reportType: 'market_review' as const,
  createdAt: '2026-07-23T12:00:00Z',
};

const demoReadiness = {
  schemaVersion: 1 as const,
  isFreshEnvironment: true,
  hasPrimaryModel: false,
  beginnerModeRecommended: true,
  primaryPath: 'demo' as const,
  primaryCta: 'view_demo' as const,
  reasonCode: 'local_runtime_unavailable' as const,
  reasonParams: {},
  localRuntime: {
    reachable: false,
    modelsAvailable: false,
    runnable: false,
    models: [],
    suggestedProfile: {},
    reasonCode: 'ollama_unreachable' as const,
    detectEnabled: true,
  },
  suggestedProfile: {},
  demoAvailable: true as const,
  configMutated: false as const,
  existingConfigUntouched: true as const,
  snapshotId: '0123456789abcdef01234567',
  generatedAt: '2026-08-09T00:00:00Z',
};

const demoAnalysis = {
  schemaVersion: 1 as const,
  isSample: true as const,
  sampleBanner: 'Sample data - not a live analysis',
  sampleDisclaimer: 'Offline fixture only.',
  queryId: 'demo-sample-analysis-v1' as const,
  stockCode: '600519' as const,
  stockName: 'Kweichow Moutai (sample)',
  createdAt: '2026-08-09T00:00:00Z',
  report: {
    meta: {
      queryId: 'demo-sample-analysis-v1' as const,
      stockCode: '600519' as const,
      stockName: 'Kweichow Moutai (sample)',
      reportType: 'brief' as const,
      reportLanguage: 'en' as const,
      createdAt: '2026-08-09T00:00:00Z',
      currentPrice: null,
      changePct: null,
      modelUsed: 'demo-fixture/offline' as const,
    },
    summary: {
      analysisSummary: 'Offline first-success report.',
      operationAdvice: 'Configure a live model when ready.',
      action: 'watch' as const,
      actionLabel: 'Watch (sample)',
      trendPrediction: 'Sample trend',
      sentimentScore: 50,
      sentimentLabel: 'Neutral' as const,
    },
    strategy: { idealBuy: null, secondaryBuy: null, stopLoss: null, takeProfit: null },
    details: { news: [], technical: [] },
  },
};

const scheduledRiskCheck = {
  task: {
    compatibility: 'supported' as const,
    id: 'scheduled-risk-1',
    schemaVersion: 2,
    name: 'AAPL downside review',
    taskType: 'risk_check',
    enabled: true,
    nextRunAt: '2026-07-25T10:00:00Z',
    createdAt: '2026-07-24T20:00:00Z',
    updatedAt: '2026-07-24T20:00:00Z',
  },
  scheduledFor: '2026-07-25T10:00:00Z',
  status: 'retry_wait' as const,
  run: null,
};

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}${location.hash}`}</output>;
}

function renderHome() {
  return render(
    <RouteFocusRegistrationContext.Provider value={{ register: routeFocusRegister }}>
      <UiLanguageProvider initialLanguage="en">
        <MemoryRouter initialEntries={[APP_ROUTE_PATHS.home]}>
          <LocationProbe />
          <HomePage />
        </MemoryRouter>
      </UiLanguageProvider>
    </RouteFocusRegistrationContext.Provider>,
  );
}

describe('HomePage attention hub', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    vi.mocked(decisionSignalsApi.list).mockImplementation(async (params) => (
      params?.expiresTo
        ? {
            items: [activeSignal],
            total: 1,
            page: 1,
            pageSize: 1,
          }
        : {
            items: [activeSignal],
            total: 4,
            page: 1,
            pageSize: 12,
          }
    ));
    vi.mocked(alertsApi.listTriggers).mockResolvedValue({
      items: [],
      total: 2,
      page: 1,
      pageSize: 1,
    });
    vi.mocked(historyApi.getList).mockImplementation(async (params = {}) => {
      const items = params.reportType === 'market_review'
        ? [marketHistory]
        : params.reportType === 'detailed'
          ? [analysisHistory]
          : [];
      return {
        items,
        total: items.length,
        page: 1,
        limit: params.limit ?? 20,
      };
    });
    vi.mocked(systemConfigApi.getSetupStatus).mockResolvedValue({
      isComplete: true,
      readyForSmoke: true,
      requiredMissingKeys: [],
      nextStepKey: null,
      checks: [],
    });
    vi.mocked(onboardingApi.getFirstRunReadiness).mockResolvedValue(demoReadiness);
    vi.mocked(onboardingApi.getDemoAnalysis).mockResolvedValue(demoAnalysis);
    vi.mocked(scheduledTasksApi.getToday).mockResolvedValue({
      date: '2026-07-25',
      timezone: 'UTC',
      generatedAt: '2026-07-25T12:00:00Z',
      items: [scheduledRiskCheck],
      total: 1,
    });
    vi.mocked(getTodaysFocus).mockResolvedValue(emptyTodaysFocus);
  });

  it('renders exactly the three default attention blocks and keeps configuration collapsed', async () => {
    renderHome();

    expect(await screen.findByRole('heading', { name: 'Home', level: 1 })).toBeInTheDocument();
    const core = screen.getByTestId('home-core-blocks');
    expect(within(core).getAllByRole('region')).toHaveLength(3);
    expect(within(core).getByRole('heading', { name: "Today's Focus" })).toBeInTheDocument();
    expect(within(core).getByRole('heading', { name: 'To-dos' })).toBeInTheDocument();
    expect(within(core).getByRole('heading', { name: 'Signal summary' })).toBeInTheDocument();
    // Production reachability: deterministic focus panel is mounted on Home (not Playground-only).
    expect(within(core).getByTestId('todays-focus-panel')).toBeInTheDocument();
    await waitFor(() => {
      expect(getTodaysFocus).toHaveBeenCalled();
    });
    expect(await within(core).findByTestId('todays-focus-empty')).toBeInTheDocument();
    const todos = within(core).getByRole('region', { name: 'To-dos' });
    const signalSummary = within(core).getByRole('region', { name: 'Signal summary' });
    const approvals = within(core).getByRole('button', { name: 'Review human approvals' });
    expect(approvals.parentElement).toHaveClass(
      'order-last',
      'justify-center',
    );
    expect(approvals).toHaveAttribute('data-variant', 'secondary');
    expect(approvals.parentElement).not.toHaveClass('w-full', '[&>button]:w-full');
    expect(approvals.parentElement).not.toHaveClass('border-t', 'border-border/70');
    expect(todos).toHaveClass('rounded-xl', 'border', 'border-border');
    expect(todos.querySelector(':scope > div.mt-4')).toHaveClass('flex', 'flex-col', 'gap-3');
    expect(signalSummary).toHaveClass('rounded-xl', 'border', 'border-border');
    expect(within(core).getByRole('region', { name: "Today's Focus" }))
      .toHaveAttribute('data-surface-level', 'interactive');
    expect(within(core).getByTestId('todays-focus-panel'))
      .toHaveAttribute('data-surface-level', 'interactive');
    expect(todos).toHaveAttribute('data-surface-level', 'interactive');
    expect(signalSummary).toHaveAttribute('data-surface-level', 'interactive');
    const startAnalysis = screen.getByRole('button', { name: 'Start analysis' });
    expect(startAnalysis).toHaveAttribute('data-size', 'primary');
    expect(startAnalysis.querySelector('.lucide-circle-play')).toHaveClass('h-4', 'w-4');

    expect(screen.getByTestId('home-attention-hub').querySelector('[data-slot="workspace-content"]'))
      .toHaveClass('rounded-xl', 'border', 'border-border', 'p-5');
    const configurable = screen.getByRole('button', { name: /Configurable area/ });
    expect(configurable.closest('section')).toHaveClass('rounded-xl', 'border', 'border-border', 'p-4');
    expect(configurable).toHaveAttribute('aria-expanded', 'false');
    expect(document.getElementById('home-configurable-content')).not.toBeVisible();
    expect(window.localStorage.getItem(HOME_CONFIGURABLE_STORAGE_KEY)).toBeNull();
    // Watchlist groups may expose a name field on Home; configurable area must stay collapsed.
    expect(document.getElementById('home-configurable-content')?.querySelector('input')).toBeNull();
  });

  it('keeps the configurable area usable when browser preference storage fails', async () => {
    const storagePrototype = Object.getPrototypeOf(window.localStorage) as Storage;
    const getItem = vi.spyOn(storagePrototype, 'getItem').mockImplementation(() => {
      throw new DOMException('Storage denied', 'SecurityError');
    });
    renderHome();

    const configurable = await screen.findByRole('button', { name: /Configurable area/ });
    expect(configurable).toHaveAttribute('aria-expanded', 'false');
    getItem.mockRestore();

    const setItem = vi.spyOn(storagePrototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Storage full', 'QuotaExceededError');
    });
    fireEvent.click(configurable);

    expect(configurable).toHaveAttribute('aria-expanded', 'true');
    expect(document.getElementById('home-configurable-content')).toBeVisible();
    setItem.mockRestore();
  });

  it('uses the filtered reassessment total instead of the active-signal page window', async () => {
    vi.mocked(decisionSignalsApi.list).mockImplementation(async (params) => (
      params?.expiresTo
        ? { items: [], total: 13, page: 1, pageSize: 1 }
        : { items: [activeSignal], total: 30, page: 1, pageSize: 12 }
    ));

    renderHome();

    expect(await screen.findByText('Due for reassessment: 13')).toBeInTheDocument();
    expect(decisionSignalsApi.list).toHaveBeenCalledWith(expect.objectContaining({
      status: 'active',
      expiresTo: expect.any(String),
      page: 1,
      pageSize: 1,
    }));
  });

  it('loads market review and every stock-report category through independent filters', async () => {
    renderHome();

    fireEvent.click(await screen.findByRole('button', { name: /Configurable area/ }));
    const morningReport = screen.getByRole('region', { name: 'Morning report / Market review' });
    const recentAnalyses = screen.getByRole('region', { name: 'Recent analyses' });
    expect(morningReport).toHaveClass('border', 'border-border');
    expect(recentAnalyses).toHaveClass('border', 'border-border');
    expect(within(morningReport).getByText('Market review')).toBeInTheDocument();
    expect(within(recentAnalyses).getByText('Apple')).toBeInTheDocument();
    expect(recentAnalyses.querySelector(':scope > header .lucide-history')).toBeInTheDocument();
    const scheduled = screen.getByRole('region', { name: 'Versioned scheduled tasks today' });
    expect(scheduled).toHaveAttribute('data-surface-level', 'interactive');
    expect(scheduled).toHaveClass('border', 'border-border');
    expect(scheduled.querySelector(':scope > header')).not.toHaveClass('border', 'border-border', 'p-3');
    expect(within(scheduled).getByText('AAPL downside review')).toBeInTheDocument();
    expect(within(scheduled).getByText('Risk check', { exact: false })).toBeInTheDocument();
    expect(within(scheduled).getByText('Waiting to retry')).toBeInTheDocument();
    const taskList = within(scheduled).getByRole('region', {
      name: "Today's versioned scheduled task list",
    });
    expect(taskList).toHaveAttribute('tabindex', '0');
    expect(within(taskList).getByRole('list')).toBeInTheDocument();
    expect(within(taskList).getAllByRole('listitem')).toHaveLength(1);
    const manageSchedules = within(scheduled).getByRole('button', { name: 'Manage schedules' });
    expect(scheduled.querySelector(':scope > header')).toContainElement(manageSchedules);

    const viewAllSignals = within(screen.getByRole('region', { name: 'Signal summary' }))
      .getByRole('button', { name: 'View all' });
    expect(viewAllSignals).toHaveClass('mx-auto');
    expect(viewAllSignals.querySelector('svg')).toHaveClass('h-3.5', 'w-3.5');

    const reviewApprovals = screen.getByRole('button', { name: 'Review human approvals' });
    expect(reviewApprovals).toHaveAttribute('data-variant', 'secondary');
    expect(reviewApprovals.parentElement).toHaveClass('justify-center');
    expect(reviewApprovals.parentElement).not.toHaveClass('w-full', '[&>button]:w-full');

    for (const reportType of ['market_review', 'simple', 'detailed', 'full', 'brief']) {
      expect(historyApi.getList).toHaveBeenCalledWith(expect.objectContaining({ reportType }));
    }
    expect(scheduledTasksApi.getToday).toHaveBeenCalledWith({
      timezone: expect.any(String),
    });
  });

  it('frames the empty scheduled-task state without changing the shared empty-state component', async () => {
    window.localStorage.setItem(HOME_CONFIGURABLE_STORAGE_KEY, '1');
    vi.mocked(scheduledTasksApi.getToday).mockResolvedValue({
      date: '2026-07-25',
      timezone: 'UTC',
      generatedAt: '2026-07-25T12:00:00Z',
      items: [],
      total: 0,
    });

    renderHome();

    const scheduled = await screen.findByRole('region', { name: 'Versioned scheduled tasks today' });
    const emptyState = within(scheduled)
      .getByText('No versioned scheduled tasks today')
      .closest('[data-state-panel="empty"]');
    expect(emptyState?.parentElement).toHaveClass('rounded-lg', 'border', 'border-border');
    expect(emptyState).toContainElement(
      within(scheduled).getByRole('button', { name: 'Manage schedules' }),
    );
  });

  it('isolates an unavailable scheduled-task projection from other Home data', async () => {
    window.localStorage.setItem(HOME_CONFIGURABLE_STORAGE_KEY, '1');
    vi.mocked(scheduledTasksApi.getToday).mockRejectedValue(
      new Error('scheduled tasks unavailable'),
    );

    renderHome();

    const scheduled = await screen.findByRole('region', { name: 'Versioned scheduled tasks today' });
    expect(within(scheduled).getByText('Home data is incomplete')).toBeInTheDocument();
    expect(screen.getAllByText('Apple')).not.toHaveLength(0);
    expect(screen.queryByText('No versioned scheduled tasks today')).not.toBeInTheDocument();
  });

  it('shows loading rather than false empty history states when configuration starts expanded', async () => {
    window.localStorage.setItem(HOME_CONFIGURABLE_STORAGE_KEY, '1');
    let resolveHistory!: (value: Awaited<ReturnType<typeof historyApi.getList>>) => void;
    const historyResult = new Promise<Awaited<ReturnType<typeof historyApi.getList>>>((resolve) => {
      resolveHistory = resolve;
    });
    vi.mocked(historyApi.getList).mockReturnValue(historyResult);

    renderHome();

    const morningReport = screen.getByRole('region', { name: 'Morning report / Market review' });
    const recentAnalyses = screen.getByRole('region', { name: 'Recent analyses' });
    expect(within(morningReport).getByText('Loading')).toBeInTheDocument();
    expect(within(recentAnalyses).getByText('Loading')).toBeInTheDocument();
    expect(screen.queryByText('No morning report')).not.toBeInTheDocument();
    expect(screen.queryByText('No recent analyses')).not.toBeInTheDocument();

    await act(async () => {
      resolveHistory({ items: [], total: 0, page: 1, limit: 4 });
      await historyResult;
    });
    expect(await screen.findByText('No morning report')).toBeInTheDocument();
    expect(screen.getByText('No recent analyses')).toBeInTheDocument();
  });

  it('shows unavailable history sources as partial data instead of empty collections', async () => {
    window.localStorage.setItem(HOME_CONFIGURABLE_STORAGE_KEY, '1');
    vi.mocked(historyApi.getList).mockRejectedValue(new Error('history unavailable'));

    renderHome();

    expect(await screen.findAllByText('Home data is incomplete')).toHaveLength(3);
    expect(within(screen.getByRole('region', { name: 'Morning report / Market review' }))
      .getByText('Home data is incomplete')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Recent analyses' }))
      .getByText('Home data is incomplete')).toBeInTheDocument();
    expect(screen.queryByText('No morning report')).not.toBeInTheDocument();
    expect(screen.queryByText('No recent analyses')).not.toBeInTheDocument();
  });

  it('links focus, reassessment, signal summary, morning report, and recent analysis to canonical pages', async () => {
    renderHome();

    const core = screen.getByTestId('home-core-blocks');
    expect(await within(core).findByTestId('todays-focus-panel')).toBeInTheDocument();
    await waitFor(() => expect(getTodaysFocus).toHaveBeenCalled());
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('Due for reassessment: 1')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Due for reassessment: 1/ }));
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(
      `${APP_ROUTE_PATHS.signals}?${SIGNAL_CENTER_ROUTE_QUERY_KEYS.scope}=all&${SIGNAL_CENTER_ROUTE_QUERY_KEYS.tab}=${SIGNAL_CENTER_TAB_VALUES.review}`,
    ));

    fireEvent.click(screen.getByRole('button', { name: /Configurable area/ }));
    expect(window.localStorage.getItem(HOME_CONFIGURABLE_STORAGE_KEY)).toBe('1');
    expect(document.getElementById('home-configurable-content')).toBeVisible();

    const morningReport = screen.getByRole('region', { name: 'Morning report / Market review' });
    fireEvent.click(within(morningReport).getByRole('button', { name: /Market review/ }));
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(
      `${APP_ROUTE_PATHS.researchMarket}?recordId=42`,
    ));

    const recentAnalyses = screen.getByRole('region', { name: 'Recent analyses' });
    fireEvent.click(within(recentAnalyses).getByRole('button', { name: /Apple/ }));
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(
      `${APP_ROUTE_PATHS.researchAnalysis}?${ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment}=${ANALYSIS_WORKBENCH_SEGMENT_VALUES.history}&${ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.recordId}=41`,
    ));
  });

  it('gives empty focus and to-do states primary actions', async () => {
    vi.mocked(decisionSignalsApi.list).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 12,
    });
    vi.mocked(historyApi.getList).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      limit: 8,
    });

    renderHome();

    expect(await screen.findByTestId('todays-focus-empty')).toBeInTheDocument();
    expect(screen.getByText('Nothing special today')).toBeInTheDocument();
    // Header Start analysis remains; to-do empty state still offers Review signals.
    expect(screen.getByRole('button', { name: 'Start analysis' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Review signals' })).toBeInTheDocument();
  });

  it('surfaces partial data without hiding successful sources and retries all sources', async () => {
    vi.mocked(alertsApi.listTriggers).mockRejectedValueOnce(new Error('alerts unavailable'));

    renderHome();

    expect(await screen.findByText('Home data is incomplete')).toBeInTheDocument();
    expect(screen.getAllByText('Apple')).not.toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(alertsApi.listTriggers).toHaveBeenCalledTimes(2));
  });

  it('preserves the setup handoff and configurable-area preference', async () => {
    window.localStorage.setItem(HOME_CONFIGURABLE_STORAGE_KEY, '1');
    vi.mocked(systemConfigApi.getSetupStatus).mockResolvedValue({
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['OPENAI_API_KEY'],
      nextStepKey: 'OPENAI_API_KEY',
      checks: [{
        key: 'OPENAI_API_KEY',
        title: 'Model key',
        category: 'ai_model',
        required: true,
        status: 'needs_action',
        message: 'Configure a model key',
      }],
    });

    renderHome();

    expect(await screen.findByTestId('home-readiness-card')).toBeInTheDocument();
    expect(await screen.findByTestId('home-first-run-entry')).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: 'View sample analysis' }));
    expect(await screen.findByTestId('beginner-report-summary')).toBeInTheDocument();
    expect(screen.getByText('Offline first-success report.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'System readiness' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Configurable area/ })).toHaveAttribute('aria-expanded', 'true');
    // Single dismiss owner: onboarding incomplete alert (not readiness card).
    const closeButtons = screen.getAllByRole('button', { name: 'Close' });
    expect(closeButtons).toHaveLength(1);
    fireEvent.click(closeButtons[0]);
    expect(window.localStorage.getItem(ONBOARDING_DISMISSED_STORAGE_KEY)).toBe('true');
  });

  it('routes a detected local runtime to the canonical Local Models settings view', async () => {
    vi.mocked(systemConfigApi.getSetupStatus).mockResolvedValue({
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['llm_primary'],
      nextStepKey: 'llm_primary',
      checks: [{
        key: 'llm_primary',
        title: 'Primary model',
        category: 'ai_model',
        required: true,
        status: 'needs_action',
        message: 'Select a local model',
      }],
    });
    vi.mocked(onboardingApi.getFirstRunReadiness).mockResolvedValue({
      ...demoReadiness,
      primaryPath: 'local_ollama',
      primaryCta: 'open_local_setup',
      reasonCode: 'local_model_ready',
      recommendedPresetId: 'local-first',
      localRuntime: {
        ...demoReadiness.localRuntime,
        reachable: true,
        modelsAvailable: true,
        runnable: true,
        backend: 'ollama',
        models: ['qwen3:4b'],
        reasonCode: 'ollama_ready',
      },
    });

    renderHome();

    fireEvent.click(await screen.findByRole('button', { name: 'Open local model setup' }));
    expect(screen.getByTestId('location')).toHaveTextContent(
      `${APP_ROUTE_PATHS.settings}?section=ai_models&view=local_models&from=onboarding`,
    );
  });

  it('keeps home core blocks single-column below the xl breakpoint class', async () => {
    renderHome();
    const core = await screen.findByTestId('home-core-blocks');
    expect(core).toHaveClass('xl:grid-cols-3');
    expect(core).not.toHaveClass('lg:grid-cols-3');
    expect(core).toHaveClass('min-w-0');
  });

  it('links the today scheduled-tasks card to Settings management', async () => {
    renderHome();
    const configurable = await screen.findByRole('button', { name: /Configurable area/ });
    fireEvent.click(configurable);
    expect(await screen.findByRole('button', { name: 'Manage schedules' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Manage schedules' }));
    expect(screen.getByTestId('location')).toHaveTextContent(
      `${APP_ROUTE_PATHS.settings}?section=system_security&view=runtime`,
    );
  });


  it('maps known setup-status check keys to localized banner labels', async () => {
    vi.mocked(systemConfigApi.getSetupStatus).mockResolvedValue({
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['llm_primary', 'stock_list'],
      nextStepKey: 'llm_primary',
      checks: [
        {
          key: 'llm_primary',
          title: '主要模型',
          category: 'ai_model',
          required: true,
          status: 'needs_action',
          message: 'missing model',
        },
        {
          key: 'stock_list',
          title: '自选股',
          category: 'base',
          required: true,
          status: 'needs_action',
          message: 'empty list',
        },
      ],
    });

    renderHome();

    expect(await screen.findByTestId('home-readiness-card')).toBeInTheDocument();
    // Goal-language labels, not backend Chinese titles.
    expect(screen.getByText('Model is not connected yet')).toBeInTheDocument();
    expect(screen.getByText('Watchlist is empty')).toBeInTheDocument();
    expect(screen.queryByText(/主要模型/)).not.toBeInTheDocument();
  });

  it('falls back to backend setup-check titles for unknown keys', async () => {
    vi.mocked(systemConfigApi.getSetupStatus).mockResolvedValue({
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['future_check'],
      nextStepKey: 'future_check',
      checks: [{
        key: 'future_check',
        title: 'Future readiness item',
        category: 'system',
        required: true,
        status: 'needs_action',
        message: 'unknown to this client',
      }],
    });

    renderHome();

    expect(await screen.findByTestId('home-readiness-card')).toBeInTheDocument();
    expect(screen.getByText('Future readiness item')).toBeInTheDocument();
  });


});
