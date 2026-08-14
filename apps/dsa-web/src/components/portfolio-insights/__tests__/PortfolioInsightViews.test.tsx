// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { fireEvent, render, screen } from '@testing-library/react';
import type React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { portfolioInsightsApi } from '../../../api/portfolioInsights';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { createDeferred } from '../../../test-utils';
import type {
  PortfolioBasketResponse,
  PortfolioRebalancingResponse,
  PortfolioStressResponse,
  StressScenario,
} from '../../../types/portfolioInsights';
import BasketAnalysisView from '../BasketAnalysisView';
import RebalanceView from '../RebalanceView';
import StressTestView from '../StressTestView';

vi.mock('../../../api/portfolioInsights', () => ({
  portfolioInsightsApi: {
    analyzeBasket: vi.fn(),
    listStressScenarios: vi.fn(),
    runStressPreset: vi.fn(),
    runStressCustom: vi.fn(),
    getRebalancing: vi.fn(),
  },
}));

const basket: PortfolioBasketResponse = {
  formulaVersion: 'portfolio_level_analysis_v1', analysisMode: 'portfolio_level_basket', snapshotKind: 'synthetic_basket_v1',
  asOf: '2026-08-13', currency: 'CNY', status: 'partial', statusMessage: 'One symbol was excluded.', disclaimer: 'Research aid only.',
  requestedSymbols: ['AAPL', 'MISSING'], symbolsUsed: ['AAPL'], symbolsRequestedCount: 2, symbolsUsedCount: 1, maxSymbols: 20,
  weightingMode: 'custom', weights: [{ symbol: 'AAPL', weightPct: 100 }],
  degradedSymbols: [{ stockCode: 'MISSING', reason: 'price_unavailable' }], annotations: [], correlationHighlights: [], sharedRiskExposures: [],
  stanceDistribution: { status: 'partial', scoredCount: 1, unanalyzedCount: 1, averageScore: 70, byOperationAdvice: {} },
  health: { status: 'partial', partialScore: 55, coverageRatio: 0.6 }, stress: null, calculatedAt: '2026-08-13T12:00:00Z',
};

const scenario: StressScenario = {
  id: 'market_down_10', name: 'Market down 10%', description: 'Broad market shock', category: 'market',
  shocks: [{ factor: 'market', valuePct: -10 }], requiresTargetSector: false, availability: 'ready', source: 'built_in', version: 1, scenarioHash: 'a'.repeat(64),
};

const stress: PortfolioStressResponse = {
  asOf: '2026-08-13', calculatedAt: '2026-08-13T12:00:00Z', accountId: 7, costMethod: 'fifo', currency: 'CNY',
  status: 'partial', statusMessage: 'Unit beta used.', portfolioValue: 1000, positionsUsed: 1, excludedPositionCount: 0,
  portfolioPnl: -100, portfolioPnlPct: -10, stressedPortfolioValue: 900, scenario,
  positionImpacts: [], topLosers: [], topWinners: [], snapshotLimitations: [], missingData: [],
};

const rebalance: PortfolioRebalancingResponse = {
  asOf: '2026-08-13', accountId: 7, costMethod: 'fifo', currency: 'CNY', status: 'insufficient_data', statusMessage: 'Need more history.',
  disclaimer: 'Research aid only.', riskTolerance: 'moderate', isSuggestionOnly: true, autoExecute: false,
  targetModel: { name: 'risk_band_v1', description: 'Moderate', maxSingleWeightPct: 15, minEffectiveN: 4, maxHhi: 0.35, targetVarPctCeiling: 3.5 },
  current: { portfolioValue: 1000, varPct: null, hhi: 1, effectiveN: 1 }, drift: { maxAbsWeightDriftPct: 0, breaches: [] },
  suggestions: [], positionBands: [],
};

function withLanguage(node: React.ReactNode) {
  return render(<UiLanguageProvider>{node}</UiLanguageProvider>);
}

describe('Portfolio insight views', () => {
  beforeEach(() => {
    vi.mocked(portfolioInsightsApi.analyzeBasket).mockReset();
    vi.mocked(portfolioInsightsApi.listStressScenarios).mockReset();
    vi.mocked(portfolioInsightsApi.runStressPreset).mockReset();
    vi.mocked(portfolioInsightsApi.runStressCustom).mockReset();
    vi.mocked(portfolioInsightsApi.getRebalancing).mockReset();
  });

  it('parses weighted basket input, shows partial degradation, and prevents duplicate runs', async () => {
    const deferred = createDeferred<PortfolioBasketResponse>();
    vi.mocked(portfolioInsightsApi.analyzeBasket).mockReturnValue(deferred.promise);
    withLanguage(<BasketAnalysisView />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Symbols and optional weights' }), { target: { value: 'AAPL:2\nMISSING:1' } });
    const button = screen.getByRole('button', { name: 'Analyze basket' });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(portfolioInsightsApi.analyzeBasket).toHaveBeenCalledTimes(1);
    expect(portfolioInsightsApi.analyzeBasket).toHaveBeenCalledWith({ stockCodes: ['AAPL', 'MISSING'], weights: { AAPL: 2, MISSING: 1 }, includeStress: true });
    deferred.resolve(basket);
    expect(await screen.findByTestId('portfolio-basket-result')).toHaveTextContent('MISSING');
    expect(screen.getByTestId('portfolio-basket-result')).toHaveTextContent('partial');
  });

  it('loads stress scenarios before running a preset for the selected account', async () => {
    vi.mocked(portfolioInsightsApi.listStressScenarios).mockResolvedValue({ scenarios: [scenario], simulationMethod: 'deterministic_factor_shock', historicalReplayAvailable: false });
    vi.mocked(portfolioInsightsApi.runStressPreset).mockResolvedValue(stress);
    withLanguage(<StressTestView accountId={7} costMethod="fifo" />);
    const button = await screen.findByRole('button', { name: 'Run stress test' });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(await screen.findByTestId('portfolio-stress-result')).toHaveTextContent('Unit beta used.');
    expect(portfolioInsightsApi.runStressPreset).toHaveBeenCalledWith({ scenarioId: 'market_down_10', accountId: 7, costMethod: 'fifo' });
  });

  it('renders insufficient data as an explicit rebalancing refusal', async () => {
    vi.mocked(portfolioInsightsApi.getRebalancing).mockResolvedValue(rebalance);
    withLanguage(<RebalanceView accountId={7} costMethod="avg" />);
    fireEvent.click(screen.getByRole('button', { name: 'Generate recommendations' }));
    expect(await screen.findByTestId('portfolio-rebalance-refused')).toHaveTextContent('Need more history.');
    expect(portfolioInsightsApi.getRebalancing).toHaveBeenCalledWith(expect.objectContaining({ accountId: 7, costMethod: 'avg', riskTolerance: 'moderate' }));
  });
});
