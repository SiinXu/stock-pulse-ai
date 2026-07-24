// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { alertsApi } from '../../api/alerts';
import { decisionSignalsApi } from '../../api/decisionSignals';
import { historyApi } from '../../api/history';
import { systemConfigApi } from '../../api/systemConfig';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
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

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getSetupStatus: vi.fn(),
  },
}));

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
  });

  it('renders exactly the three default attention blocks and keeps configuration collapsed', async () => {
    renderHome();

    expect(await screen.findByRole('heading', { name: 'Home', level: 1 })).toBeInTheDocument();
    const core = screen.getByTestId('home-core-blocks');
    expect(within(core).getAllByRole('region')).toHaveLength(3);
    expect(within(core).getByRole('heading', { name: "Today's Focus" })).toBeInTheDocument();
    expect(within(core).getByRole('heading', { name: 'To-dos' })).toBeInTheDocument();
    expect(within(core).getByRole('heading', { name: 'Signal summary' })).toBeInTheDocument();
    for (const block of within(core).getAllByRole('region')) {
      expect(block).toHaveAttribute('data-surface-level', 'canvas');
    }

    const configurable = screen.getByRole('button', { name: /Configurable area/ });
    expect(configurable).toHaveAttribute('aria-expanded', 'false');
    expect(document.getElementById('home-configurable-content')).not.toBeVisible();
    expect(window.localStorage.getItem(HOME_CONFIGURABLE_STORAGE_KEY)).toBeNull();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
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
    expect(within(screen.getByRole('region', { name: 'Morning report / Market review' }))
      .getByText('Market review')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Recent analyses' }))
      .getByText('Apple')).toBeInTheDocument();

    for (const reportType of ['market_review', 'simple', 'detailed', 'full', 'brief']) {
      expect(historyApi.getList).toHaveBeenCalledWith(expect.objectContaining({ reportType }));
    }
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
    await within(core).findByText('Apple');
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

    expect(await screen.findByText('No signals need attention')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Start analysis' })).toHaveLength(2);
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

    expect(await screen.findByText('Base configuration incomplete')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Configurable area/ })).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(window.localStorage.getItem(ONBOARDING_DISMISSED_STORAGE_KEY)).toBe('true');
  });
});
