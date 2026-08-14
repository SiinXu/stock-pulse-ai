// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { portfolioHealthApi } from '../../../api/portfolioHealth';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { PortfolioHealthResponse } from '../../../types/portfolioHealth';
import { createDeferred } from '../../../test-utils';
import PortfolioHealthPanel from '../PortfolioHealthPanel';

vi.mock('../../../api/portfolioHealth', () => ({
  portfolioHealthApi: {
    getSummary: vi.fn(),
    refresh: vi.fn(),
  },
}));

const dimension = { status: 'ok' as const, score: 80, input: {} };
const baseResponse: PortfolioHealthResponse = {
  accountId: 7,
  asOf: '2026-08-13',
  band: 'healthy',
  bands: [{ minInclusive: 80, maxExclusive: 101, name: 'healthy' }],
  comparable: true,
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
  coverageRatio: 1,
  currency: 'CNY',
  dataQuality: { fxStale: false, limitations: [], missingPriceSymbols: [], partialReasons: [], status: 'ok' },
  dimensions: { concentration: dimension, riskExposure: dimension, diversification: dimension, pnl: dimension, cashRatio: dimension },
  disclaimer: 'For information only.',
  effectiveWeights: { concentration: 0.25, riskExposure: 0.25, diversification: 0.2, pnl: 0.15, cashRatio: 0.15 },
  formulaVersion: 'portfolio_health_v2',
  inputs: { totalCash: 100, totalEquity: 1000, totalMarketValue: 900 },
  insights: [],
  llmCanModifyScore: false,
  persisted: true,
  provenance: { calculatedAt: '2026-08-13T12:00:00Z', configHash: 'config', riskHash: 'risk', snapshotHash: 'snapshot' },
  score: 82,
  scoreSource: 'rules',
  status: 'ok',
  unavailableDimensions: [],
  weights: { concentration: 0.25, riskExposure: 0.25, diversification: 0.2, pnl: 0.15, cashRatio: 0.15 },
};

function renderPanel() {
  return render(
    <UiLanguageProvider>
      <PortfolioHealthPanel accountId={7} costMethod="fifo" />
    </UiLanguageProvider>,
  );
}

describe('PortfolioHealthPanel', () => {
  beforeEach(() => {
    vi.mocked(portfolioHealthApi.getSummary).mockReset();
    vi.mocked(portfolioHealthApi.refresh).mockReset();
  });

  it('turns a missing snapshot into a real explicit refresh action', async () => {
    vi.mocked(portfolioHealthApi.getSummary).mockResolvedValue(null);
    vi.mocked(portfolioHealthApi.refresh).mockResolvedValue(baseResponse);
    renderPanel();

    expect(await screen.findByText('No health snapshot yet')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: /Refresh health score/ })[0]);

    expect(await screen.findByTestId('portfolio-health-score')).toHaveTextContent('82');
    expect(portfolioHealthApi.refresh).toHaveBeenCalledWith({
      accountId: 7,
      asOf: undefined,
      costMethod: 'fifo',
      persist: true,
    });
  });

  it('prevents repeated refresh submissions while one request is active', async () => {
    const deferred = createDeferred<PortfolioHealthResponse>();
    vi.mocked(portfolioHealthApi.getSummary).mockResolvedValue(baseResponse);
    vi.mocked(portfolioHealthApi.refresh).mockReturnValue(deferred.promise);
    renderPanel();
    const button = await screen.findByRole('button', { name: /Refresh health score/ });

    fireEvent.click(button);
    fireEvent.click(button);
    expect(portfolioHealthApi.refresh).toHaveBeenCalledTimes(1);
    deferred.resolve(baseResponse);
  });

  it('keeps partial and unavailable states explicit', async () => {
    vi.mocked(portfolioHealthApi.getSummary).mockResolvedValue({
      ...baseResponse,
      status: 'partial',
      score: null,
      partialScore: 48,
      comparable: false,
      band: null,
      coverageRatio: 0.6,
    });
    const view = renderPanel();
    expect(await screen.findByTestId('portfolio-health-partial')).toBeInTheDocument();
    expect(screen.getByTestId('portfolio-health-score')).toHaveTextContent('48');

    vi.mocked(portfolioHealthApi.getSummary).mockResolvedValue({
      ...baseResponse,
      status: 'unavailable',
      score: null,
      comparable: false,
      band: null,
      statusMessage: 'Negative equity.',
    });
    view.unmount();
    renderPanel();
    expect(await screen.findByTestId('portfolio-health-unavailable')).toHaveTextContent('Negative equity.');
  });
});
