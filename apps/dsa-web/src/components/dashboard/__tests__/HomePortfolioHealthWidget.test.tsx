// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { portfolioHealthApi } from '../../../api/portfolioHealth';
import type { PortfolioHealthResponse } from '../../../types/portfolioHealth';
import { HomePortfolioHealthWidget } from '../HomePortfolioHealthWidget';

vi.mock('../../../api/portfolioHealth', () => ({
  portfolioHealthApi: {
    getSummary: vi.fn(),
  },
}));

function renderWidget() {
  const LocationProbe = () => <span data-testid="location">{useLocation().pathname}{useLocation().search}</span>;
  return render(
    <MemoryRouter>
      <UiLanguageProvider>
        <HomePortfolioHealthWidget />
        <LocationProbe />
      </UiLanguageProvider>
    </MemoryRouter>,
  );
}

const unavailableDimension = { status: 'unavailable' as const, score: null };
const storedUnavailable: PortfolioHealthResponse = {
  asOf: '2026-08-13',
  bands: [],
  comparable: false,
  config: {
    cashHighAlertPct: 50,
    cashLowAlertPct: 2,
    concentrationAlertPct: 35,
    diversificationAlert: 0.35,
    pnlLossAlertPct: -15,
    source: 'shared_config',
    varAlertPct: 5,
    weights: { concentration: 0.25, riskExposure: 0.25, diversification: 0.2, pnl: 0.15, cashRatio: 0.15 },
  },
  costMethod: 'fifo',
  coverageRatio: 0,
  currency: 'CNY',
  dataQuality: { fxStale: false, limitations: [], missingPriceSymbols: [], partialReasons: [], status: 'unavailable' },
  dimensions: { concentration: unavailableDimension, riskExposure: unavailableDimension, diversification: unavailableDimension, pnl: unavailableDimension, cashRatio: unavailableDimension },
  disclaimer: 'For information only.',
  effectiveWeights: { concentration: null, riskExposure: null, diversification: null, pnl: null, cashRatio: null },
  formulaVersion: 'portfolio_health_v2',
  inputs: { totalCash: 0, totalEquity: -1, totalMarketValue: 0 },
  insights: [],
  llmCanModifyScore: false,
  persisted: true,
  provenance: { calculatedAt: '2026-08-13T00:00:00Z', configHash: 'config', riskHash: 'risk', snapshotHash: 'snapshot' },
  scoreSource: 'rules',
  status: 'unavailable',
  statusMessage: 'Portfolio equity is negative; health scoring is undefined.',
  unavailableDimensions: ['concentration', 'risk_exposure', 'diversification', 'pnl', 'cash_ratio'],
  weights: { concentration: 0.25, riskExposure: 0.25, diversification: 0.2, pnl: 0.15, cashRatio: 0.15 },
};

describe('HomePortfolioHealthWidget', () => {
  beforeEach(() => {
    vi.mocked(portfolioHealthApi.getSummary).mockReset();
  });

  it('uses empty copy when no snapshot has been stored', async () => {
    vi.mocked(portfolioHealthApi.getSummary).mockResolvedValue(null);
    renderWidget();
    expect(await screen.findByText('No portfolio health snapshot')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open portfolio' }));
    expect(screen.getByTestId('location')).toHaveTextContent('/portfolio?tab=insights&view=health');
  });

  it('shows the stored unavailable status message instead of empty copy', async () => {
    vi.mocked(portfolioHealthApi.getSummary).mockResolvedValue(storedUnavailable);
    renderWidget();
    expect(await screen.findByText('Portfolio health unavailable')).toBeInTheDocument();
    expect(
      screen.getByText('Portfolio equity is negative; health scoring is undefined.'),
    ).toBeInTheDocument();
    expect(screen.queryByText('No portfolio health snapshot')).not.toBeInTheDocument();
  });
});
