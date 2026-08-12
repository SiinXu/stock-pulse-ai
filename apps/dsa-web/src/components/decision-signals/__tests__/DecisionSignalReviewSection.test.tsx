// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ComponentProps } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createParsedApiError } from '../../../api/error';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { DecisionSignalOutcomeStatsResponse } from '../../../types/decisionSignals';
import DecisionSignalReviewSection from '../DecisionSignalReviewSection';

vi.mock('../DecisionSignalOutcomeExplorer', () => ({
  DecisionSignalOutcomeExplorer: ({
    refreshKey,
    onOpenSignal,
  }: {
    refreshKey: number;
    onOpenSignal: (signalId: number) => void;
  }) => (
    <div data-testid="outcome-explorer" data-refresh-key={refreshKey}>
      <button type="button" onClick={() => onOpenSignal(42)}>
        open-signal
      </button>
    </div>
  ),
}));

vi.mock('../DecisionSignalOutcomeRunPanel', () => ({
  DecisionSignalOutcomeRunPanel: ({ onCompleted }: { onCompleted: () => void }) => (
    <button type="button" data-testid="outcome-run-panel" onClick={onCompleted}>
      run-outcomes
    </button>
  ),
}));

const sampleStats: DecisionSignalOutcomeStatsResponse = {
  engineVersion: 'decision-signal-v1',
  horizons: null,
  statuses: ['active', 'expired', 'invalidated', 'closed'],
  total: 4,
  completed: 3,
  unable: 1,
  hit: 2,
  miss: 1,
  neutral: 0,
  sampleSufficient: false,
  minimumCompletedSampleSize: 30,
  hitRatePct: null,
  avgStockReturnPct: null,
  unableReasons: {},
  breakdowns: {
    period: [
      {
        dimension: 'period',
        value: '2024-01',
        total: 4,
        completed: 3,
        unable: 1,
        hit: 2,
        miss: 1,
        neutral: 0,
        sampleSufficient: false,
        hitRatePct: null,
        avgStockReturnPct: null,
        unableReasons: {},
      },
    ],
    market: [
      {
        dimension: 'market',
        value: 'cn',
        total: 4,
        completed: 3,
        unable: 1,
        hit: 2,
        miss: 1,
        neutral: 0,
        sampleSufficient: false,
        hitRatePct: null,
        avgStockReturnPct: null,
        unableReasons: {},
      },
    ],
    action: [
      {
        dimension: 'action',
        value: 'buy',
        total: 4,
        completed: 3,
        unable: 1,
        hit: 2,
        miss: 1,
        neutral: 0,
        sampleSufficient: false,
        hitRatePct: null,
        avgStockReturnPct: null,
        unableReasons: {},
      },
    ],
  },
};

function renderSection(
  props: Partial<ComponentProps<typeof DecisionSignalReviewSection>> = {},
) {
  const onRetryStats = vi.fn();
  const onOpenSignal = vi.fn();
  const onOutcomeRunCompleted = vi.fn();
  render(
    <UiLanguageProvider initialLanguage="en">
      <DecisionSignalReviewSection
        stats={sampleStats}
        loading={false}
        error={null}
        onRetryStats={onRetryStats}
        outcomeExplorerRefreshKey={0}
        onOpenSignal={onOpenSignal}
        onOutcomeRunCompleted={onOutcomeRunCompleted}
        showExplorer={false}
        {...props}
      />
    </UiLanguageProvider>,
  );
  return { onRetryStats, onOpenSignal, onOutcomeRunCompleted };
}

describe('DecisionSignalReviewSection production mount', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('mounts DecisionSignalOutcomeStatsCard on the production Review surface', () => {
    renderSection();

    // Production-discoverable chrome for outcome stats (Signal Center → Review).
    expect(screen.getByText('Process quality stats')).toBeInTheDocument();
    expect(screen.getByText('Global')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByTestId('decision-signal-research-position')).toBeInTheDocument();
    expect(screen.getByText('Research tool positioning')).toBeInTheDocument();
    expect(screen.getByTestId('decision-signal-sample-insufficient')).toBeInTheDocument();
    expect(screen.getByTestId('decision-signal-calibration-breakdown')).toBeInTheDocument();
    expect(screen.getByText('Post-hoc hit calibration')).toBeInTheDocument();
    expect(screen.getByTestId('outcome-run-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('outcome-explorer')).not.toBeInTheDocument();
    // Rates stay unpublished under the sample floor.
    expect(screen.queryByText('66.67%')).not.toBeInTheDocument();
  });

  it('shows honest empty state when there are no reviewed outcomes', () => {
    renderSection({
      stats: {
        ...sampleStats,
        total: 0,
        completed: 0,
        hit: 0,
        miss: 0,
        unable: 0,
        hitRatePct: null,
        sampleSufficient: false,
        breakdowns: {},
      },
      showExplorer: true,
      outcomeExplorerRefreshKey: 1,
    });

    expect(screen.getByText('No reviewed samples yet')).toBeInTheDocument();
    expect(screen.getByTestId('outcome-explorer')).toHaveAttribute('data-refresh-key', '1');
    // Empty-state must not pretend a healthy scoreboard exists.
    expect(screen.queryByText('66.67%')).not.toBeInTheDocument();
    expect(screen.queryByTestId('decision-signal-calibration-breakdown')).not.toBeInTheDocument();
  });

  it('retries stats load from the mounted card error action', () => {
    const { onRetryStats } = renderSection({
      stats: null,
      error: createParsedApiError({
        title: 'Stats unavailable',
        message: 'network failed',
        status: 500,
      }),
    });

    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(onRetryStats).toHaveBeenCalledTimes(1);
  });

  it('forwards outcome-run completion from the mounted stats card', () => {
    const { onOutcomeRunCompleted } = renderSection();
    fireEvent.click(screen.getByTestId('outcome-run-panel'));
    expect(onOutcomeRunCompleted).toHaveBeenCalledTimes(1);
  });
});
