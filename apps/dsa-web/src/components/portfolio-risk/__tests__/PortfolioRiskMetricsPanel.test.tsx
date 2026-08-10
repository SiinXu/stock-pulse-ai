// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PortfolioRiskMetricsResponse } from '../../../types/portfolioRiskMetrics';
import { PortfolioRiskMetricsPanel } from '../PortfolioRiskMetricsPanel';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';

const getRiskMetrics = vi.fn();

vi.mock('../../../api/portfolioRiskMetrics', () => ({
  getPortfolioRiskMetrics: (...args: unknown[]) => getRiskMetrics(...args),
}));

const assumptions: PortfolioRiskMetricsResponse['assumptions'] = {
  varMethod: 'historical',
  confidence: 0.95,
  horizonDays: 1,
  lookbackTradingDays: 252,
  minReturnObservations: 60,
  minCorrelationObservations: 30,
  returnDefinition: 'simple_close_to_close',
  portfolioAggregation: 'static_current_market_value_weights',
  cashExcluded: true,
  weightBasis: 'market_value_base',
  horizonScaling: 'none',
  distributionAssumption: 'empirical',
  correlationMethod: 'pearson',
  concentrationMetrics: 'hhi_effective_n_normalized_diversification_score',
  dataSource: 'stored_stock_daily_closes_and_portfolio_holdings',
  providerCallsOnHotPath: false,
};

function okPayload(): PortfolioRiskMetricsResponse {
  return {
    asOf: '2026-06-01',
    accountId: 1,
    costMethod: 'fifo',
    currency: 'CNY',
    status: 'ok',
    statusMessage: 'Risk metrics computed from stored daily history.',
    portfolioValue: 10000,
    positionsUsed: 2,
    assumptions,
    var: {
      status: 'ok',
      confidence: 0.95,
      horizonDays: 1,
      varPct: 2.5,
      varValue: 250,
      observationCount: 100,
      percentileUsed: 0.05,
      oneDayVarPct: 2.5,
    },
    correlation: {
      status: 'ok',
      symbols: ['AAA', 'BBB'],
      matrix: [
        [1, 0.5],
        [0.5, 1],
      ],
      observationCount: 100,
    },
    concentration: {
      status: 'ok',
      hhi: 0.5,
      effectiveN: 2,
      diversificationScore: 1,
      topWeightPct: 50,
      positionCount: 2,
      weights: [
        { symbol: 'AAA', weightPct: 50 },
        { symbol: 'BBB', weightPct: 50 },
      ],
    },
    history: {
      alignedTradingDays: 100,
      lookbackTradingDaysRequested: 252,
      priceSeriesSymbols: ['AAA', 'BBB'],
      alignedStart: '2025-01-01',
      alignedEnd: '2026-06-01',
    },
  };
}

function renderPanel(props: { accountId?: number } = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <UiLanguageProvider initialLanguage="en">
        <PortfolioRiskMetricsPanel accountId={props.accountId} costMethod="fifo" />
      </UiLanguageProvider>
    </QueryClientProvider>,
  );
}

describe('PortfolioRiskMetricsPanel', () => {
  beforeEach(() => {
    getRiskMetrics.mockReset();
  });

  it('renders VaR, correlation, concentration, and always-visible assumptions on ok', async () => {
    getRiskMetrics.mockResolvedValue(okPayload());
    renderPanel({ accountId: 1 });

    await waitFor(() => {
      expect(screen.getByTestId('portfolio-risk-var-pct')).toHaveTextContent('2.50%');
    });
    expect(screen.getByTestId('portfolio-risk-var-value')).toHaveTextContent('250');
    expect(screen.getByTestId('portfolio-risk-correlation-matrix')).toBeInTheDocument();
    expect(screen.getByTestId('portfolio-risk-diversification-score')).toHaveTextContent('1');
    expect(screen.getByTestId('portfolio-risk-assumptions-card')).toHaveTextContent('historical');
    expect(screen.getByTestId('portfolio-risk-assumptions-card')).toHaveTextContent(
      'Provider calls on hot path',
    );
    expect(screen.getByTestId('portfolio-risk-assumptions-card')).toHaveTextContent('No');
    expect(getRiskMetrics).toHaveBeenCalledWith(
      expect.objectContaining({ accountId: 1, costMethod: 'fifo' }),
    );
  });

  it('keeps VaR null display and shows insufficient-history honesty', async () => {
    const payload = okPayload();
    payload.status = 'insufficient_history';
    payload.statusMessage = 'Insufficient aligned trading-day history (10 < 60 required).';
    payload.var = {
      status: 'insufficient_history',
      statusMessage: 'Need at least 60 observations',
      varPct: null,
      varValue: null,
      observationCount: 10,
    };
    payload.correlation = {
      status: 'insufficient_history',
      symbols: ['AAA', 'BBB'],
      matrix: [],
      observationCount: 10,
    };
    getRiskMetrics.mockResolvedValue(payload);
    renderPanel();

    await waitFor(() => {
      expect(screen.getByTestId('portfolio-risk-insufficient-banner')).toBeInTheDocument();
    });
    expect(screen.getByTestId('portfolio-risk-var-pct')).toHaveTextContent('—');
    expect(screen.getByTestId('portfolio-risk-var-value')).toHaveTextContent('—');
    expect(screen.getByTestId('portfolio-risk-var-unavailable')).toBeInTheDocument();
    // Assumptions remain visible even when VaR is unavailable.
    expect(screen.getByTestId('portfolio-risk-assumptions-card')).toBeInTheDocument();
  });

  it('renders empty-portfolio state without inventing risk numbers', async () => {
    const payload = okPayload();
    payload.status = 'empty_portfolio';
    payload.portfolioValue = 0;
    payload.positionsUsed = 0;
    payload.var = {
      status: 'unavailable',
      varPct: null,
      varValue: null,
      observationCount: 0,
    };
    payload.correlation = {
      status: 'unavailable',
      symbols: [],
      matrix: [],
      observationCount: 0,
    };
    payload.concentration = {
      status: 'empty_portfolio',
      hhi: null,
      effectiveN: null,
      diversificationScore: null,
      topWeightPct: null,
      positionCount: 0,
      weights: [],
    };
    getRiskMetrics.mockResolvedValue(payload);
    renderPanel();

    await waitFor(() => {
      expect(screen.getByTestId('portfolio-risk-empty-state')).toBeInTheDocument();
    });
    expect(screen.getByTestId('portfolio-risk-var-pct')).toHaveTextContent('—');
    expect(screen.getByTestId('portfolio-risk-assumptions-card')).toBeInTheDocument();
  });

  it('surfaces load failures with retry and never fills zeros', async () => {
    getRiskMetrics.mockRejectedValue(new Error('network down'));
    renderPanel();

    await waitFor(() => {
      expect(screen.getByTestId('portfolio-risk-error')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('portfolio-risk-var-pct')).not.toBeInTheDocument();

    getRiskMetrics.mockResolvedValue(okPayload());
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    await waitFor(() => {
      expect(screen.getByTestId('portfolio-risk-var-pct')).toHaveTextContent('2.50%');
    });
  });
});
