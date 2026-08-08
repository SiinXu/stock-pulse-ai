// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { skillOutcomesApi } from '../../api/skillOutcomes';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import {
  RouteFocusRegistrationContext,
  type RouteFocusTarget,
} from '../../contexts/routeFocusContext';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import SkillOutcomesPage from '../SkillOutcomesPage';

vi.mock('../../api/skillOutcomes', () => ({
  skillOutcomesApi: {
    getStats: vi.fn(),
    listOutcomes: vi.fn(),
    listSamples: vi.fn(),
    runOutcomes: vi.fn(),
  },
}));

const routeFocusRegister = vi.fn((target: RouteFocusTarget) => {
  void target;
  return () => {};
});

function wrapWithQueryClient(ui: ReactElement): ReactElement {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

function renderPage() {
  return render(
    wrapWithQueryClient(
      <RouteFocusRegistrationContext.Provider value={{ register: routeFocusRegister }}>
        <UiLanguageProvider initialLanguage="en">
          <MemoryRouter initialEntries={[APP_ROUTE_PATHS.researchSkillOutcomes]}>
            <SkillOutcomesPage />
          </MemoryRouter>
        </UiLanguageProvider>
      </RouteFocusRegistrationContext.Provider>,
    ),
  );
}

const insufficientBucket = {
  skillId: 'momentum',
  horizon: '5d',
  engineVersion: 'skill-opinion-outcome-v1',
  total: 12,
  pending: 2,
  evaluated: 8,
  observational: 1,
  unable: 1,
  hit: 5,
  miss: 3,
  sampleSufficient: false,
  sampleStatus: 'insufficient',
  hitRatePct: null,
  missRatePct: null,
  avgDirectionalReturnPct: null,
  unableRatePct: null,
};

const sufficientBucket = {
  skillId: 'value',
  horizon: '10d',
  engineVersion: 'skill-opinion-outcome-v1',
  total: 40,
  pending: 2,
  evaluated: 32,
  observational: 3,
  unable: 3,
  hit: 20,
  miss: 12,
  sampleSufficient: true,
  sampleStatus: 'sufficient',
  hitRatePct: 62.5,
  missRatePct: 37.5,
  avgDirectionalReturnPct: 1.25,
  unableRatePct: 7.9,
};

describe('SkillOutcomesPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    routeFocusRegister.mockClear();
    document.title = '';
  });

  it('renders loading then empty state with settings link when recording has no data', async () => {
    vi.mocked(skillOutcomesApi.getStats).mockResolvedValue({
      engineVersion: 'skill-opinion-outcome-v1',
      minimumEvaluatedSampleSize: 30,
      buckets: [],
    });
    vi.mocked(skillOutcomesApi.listOutcomes).mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
      engineVersion: 'skill-opinion-outcome-v1',
    });
    vi.mocked(skillOutcomesApi.listSamples).mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    });

    renderPage();

    expect(screen.getByTestId('skill-outcomes-loading')).toBeInTheDocument();

    expect(await screen.findByTestId('skill-outcomes-empty')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Skill outcome performance' })).toBeInTheDocument();
    expect(screen.getByText(/SKILL_OPINION_RECORDING_ENABLED/)).toBeInTheDocument();
    expect(screen.getByTestId('skill-outcomes-settings-link')).toHaveAttribute(
      'href',
      `${APP_ROUTE_PATHS.settings}?section=agent_behavior&view=execution`,
    );
    expect(screen.getByTestId('skill-outcomes-threshold-strip')).toHaveTextContent('30');
    expect(screen.getByTestId('skill-outcome-run-panel')).toBeInTheDocument();
    expect(document.title).toBe('Skill outcome performance - StockPulse');
  });

  it('renders error state with retry', async () => {
    vi.mocked(skillOutcomesApi.getStats).mockRejectedValue({
      response: { status: 500, data: { error: 'internal_error', message: 'boom' } },
    });
    vi.mocked(skillOutcomesApi.listOutcomes).mockRejectedValue(new Error('fail'));
    vi.mocked(skillOutcomesApi.listSamples).mockRejectedValue(new Error('fail'));

    renderPage();

    expect(await screen.findByTestId('skill-outcomes-error')).toBeInTheDocument();
    expect(screen.getByText('Failed to load skill outcomes')).toBeInTheDocument();

    vi.mocked(skillOutcomesApi.getStats).mockResolvedValue({
      engineVersion: 'skill-opinion-outcome-v1',
      minimumEvaluatedSampleSize: 30,
      buckets: [],
    });
    vi.mocked(skillOutcomesApi.listOutcomes).mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
      engineVersion: 'skill-opinion-outcome-v1',
    });
    vi.mocked(skillOutcomesApi.listSamples).mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    });

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByTestId('skill-outcomes-empty')).toBeInTheDocument();
  });

  it('renders insufficient and sufficient buckets with pending/unable counts and threshold gating', async () => {
    vi.mocked(skillOutcomesApi.getStats).mockResolvedValue({
      engineVersion: 'skill-opinion-outcome-v1',
      minimumEvaluatedSampleSize: 30,
      buckets: [insufficientBucket, sufficientBucket],
    });
    vi.mocked(skillOutcomesApi.listOutcomes).mockResolvedValue({
      items: [{
        id: 1,
        skillOpinionSampleId: 9,
        analysisHistoryId: 100,
        stockCode: 'AAPL',
        skillId: 'momentum',
        signal: 'buy',
        horizon: '5d',
        engineVersion: 'skill-opinion-outcome-v1',
        evalStatus: 'pending',
        outcome: null,
        directionCorrect: null,
        unableReason: null,
        analysisDate: '2026-08-01',
        startTradeDate: null,
        endTradeDate: null,
        startPrice: null,
        endClose: null,
        stockReturnPct: null,
        directionalReturnPct: null,
        createdAt: null,
        updatedAt: null,
      }],
      total: 1,
      limit: 20,
      offset: 0,
      engineVersion: 'skill-opinion-outcome-v1',
    });
    vi.mocked(skillOutcomesApi.listSamples).mockResolvedValue({
      items: [{
        id: 9,
        analysisHistoryId: 100,
        stockCode: 'AAPL',
        skillId: 'momentum',
        skillVersion: '1',
        signal: 'buy',
        confidence: 0.82,
        horizon: '5d',
        dataQualityLevel: null,
        opinionCreatedAt: null,
        sampleSchemaVersion: 'v1',
        createdAt: null,
      }],
      total: 1,
      limit: 20,
      offset: 0,
    });

    renderPage();

    expect(await screen.findByTestId('skill-outcome-performance-table')).toBeInTheDocument();
    expect(screen.getAllByText('momentum').length).toBeGreaterThan(0);
    expect(screen.getAllByText('value').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Insufficient').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Sufficient').length).toBeGreaterThan(0);

    const hitRates = screen.getAllByTestId('skill-outcome-hit-rate');
    expect(hitRates.some((node) => node.textContent === 'Below threshold')).toBe(true);
    expect(hitRates.some((node) => node.textContent?.includes('62.5'))).toBe(true);

    // Count columns remain visible for pending / unable even when rates are gated.
    expect(screen.getByText('Pending')).toBeInTheDocument();
    expect(screen.getByText('Unable')).toBeInTheDocument();

    const outcomes = screen.getByTestId('skill-outcome-recent-outcomes');
    expect(within(outcomes).getByText('pending')).toBeInTheDocument();
    expect(within(outcomes).getAllByText('AAPL').length).toBeGreaterThan(0);

    const samples = screen.getByTestId('skill-outcome-recent-samples');
    expect(within(samples).getAllByText('momentum').length).toBeGreaterThan(0);
  });

  it('runs explicit offline evaluation after confirm and reloads data', async () => {
    vi.mocked(skillOutcomesApi.getStats).mockResolvedValue({
      engineVersion: 'skill-opinion-outcome-v1',
      minimumEvaluatedSampleSize: 30,
      buckets: [],
    });
    vi.mocked(skillOutcomesApi.listOutcomes).mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
      engineVersion: 'skill-opinion-outcome-v1',
    });
    vi.mocked(skillOutcomesApi.listSamples).mockResolvedValue({
      items: [],
      total: 0,
      limit: 20,
      offset: 0,
    });
    vi.mocked(skillOutcomesApi.runOutcomes).mockResolvedValue({
      items: [],
      processedKeys: 3,
      created: 1,
      updated: 1,
      skipped: 1,
      failed: 0,
      errors: [],
      historiesScanned: 2,
      samplesCreated: 1,
      limitUnit: 'outcome_keys',
      engineVersion: 'skill-opinion-outcome-v1',
    });

    renderPage();
    expect(await screen.findByTestId('skill-outcome-run-panel')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Run evaluation' }));
    expect(await screen.findByRole('heading', { name: 'Run skill outcome evaluation?' })).toBeInTheDocument();
    const confirmButtons = screen.getAllByRole('button', { name: 'Run evaluation' });
    fireEvent.click(confirmButtons[confirmButtons.length - 1]!);

    await waitFor(() => {
      expect(skillOutcomesApi.runOutcomes).toHaveBeenCalledWith({ limit: 100 });
    });
    expect(await screen.findByTestId('skill-outcome-run-result')).toBeInTheDocument();
    // Initial load + post-run reload.
    await waitFor(() => {
      expect(skillOutcomesApi.getStats).toHaveBeenCalledTimes(2);
    });
  });
});
