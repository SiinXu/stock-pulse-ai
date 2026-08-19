// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
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
  return render(
    <MemoryRouter>
      <UiLanguageProvider>
        <HomePortfolioHealthWidget />
      </UiLanguageProvider>
    </MemoryRouter>,
  );
}

const weights = {
  concentration: 0.25,
  riskExposure: 0.25,
  diversification: 0.2,
  pnl: 0.15,
  cashRatio: 0.15,
};
const unavailableDimension = {
  formula: null,
  input: {},
  reason: 'negative_equity',
  score: null,
  status: 'unavailable' as const,
  statusMessage: 'Portfolio equity is negative; health scoring is undefined.',
};
const storedUnavailable: PortfolioHealthResponse = {
  accountId: 1,
  asOf: '2026-08-13',
  band: null,
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
    weights,
  },
  costMethod: 'fifo',
  coverageRatio: 0,
  currency: 'CNY',
  dataQuality: {
    fxStale: false,
    limitations: ['negative_equity'],
    missingPriceSymbols: [],
    partialReasons: [],
    status: 'unavailable',
  },
  dimensions: {
    concentration: unavailableDimension,
    riskExposure: unavailableDimension,
    diversification: unavailableDimension,
    pnl: unavailableDimension,
    cashRatio: unavailableDimension,
  },
  effectiveWeights: weights,
  formulaVersion: 'portfolio_health_v2',
  inputs: {
    totalCash: 0,
    totalEquity: -1,
    totalMarketValue: 0,
  },
  insights: [],
  llmCanModifyScore: false,
  partialScore: null,
  persisted: true,
  provenance: {
    calculatedAt: '2026-08-13T12:00:00Z',
    configHash: 'config',
    riskHash: 'risk',
    snapshotHash: 'snapshot',
  },
  score: null,
  scoreSource: 'rules',
  status: 'unavailable',
  statusMessage: 'Portfolio equity is negative; health scoring is undefined.',
  unavailableDimensions: [
    'concentration',
    'risk_exposure',
    'diversification',
    'pnl',
    'cash_ratio',
  ],
  weights,
};

describe('HomePortfolioHealthWidget', () => {
  beforeEach(() => {
    vi.mocked(portfolioHealthApi.getSummary).mockReset();
  });

  it('uses empty copy when no snapshot has been stored', async () => {
    vi.mocked(portfolioHealthApi.getSummary).mockResolvedValue(null);
    renderWidget();
    expect(await screen.findByText('No portfolio health snapshot')).toBeInTheDocument();
  });

  it('shows the stored unavailable status message instead of empty copy', async () => {
    vi.mocked(portfolioHealthApi.getSummary).mockResolvedValue(storedUnavailable);
    renderWidget();
    expect(await screen.findByText('Portfolio health unavailable')).toBeInTheDocument();
    expect(
      screen.getByText('Equity is negative, so health scoring is undefined.'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('Portfolio equity is negative; health scoring is undefined.'),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/not investment advice/i)).not.toBeInTheDocument();
    expect(screen.queryByText('No portfolio health snapshot')).not.toBeInTheDocument();
  });
});
