// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { SOURCE_PORTFOLIO_INSIGHTS_TEXT } from '../../../locales/portfolioInsights';
import type { PortfolioStressResponse, StressScenario } from '../../../types/portfolioInsights';
import type { UiLanguage } from '../../../i18n/uiText';
import PortfolioStressPanel from '../PortfolioStressPanel';

const listStressScenarios = vi.fn();
const runStressPreset = vi.fn();

vi.mock('../../../api/portfolioInsights', () => ({
  portfolioInsightsApi: {
    listStressScenarios: (...args: unknown[]) => listStressScenarios(...args),
    runStressPreset: (...args: unknown[]) => runStressPreset(...args),
    runStressCustom: vi.fn(),
  },
}));

const scenario: StressScenario = {
  id: 'market_down_10',
  name: 'Market down 10%',
  description: 'Deterministic market shock',
  category: 'market',
  shocks: [{ factor: 'market', valuePct: -10 }],
  requiresTargetSector: false,
  availability: 'ready',
  source: 'built_in',
  version: 1,
  scenarioHash: 'scenario-hash',
};

function makeImpact(overrides: Partial<PortfolioStressResponse['positionImpacts'][number]> = {}) {
  return {
    positionKey: '1-AAPL-us',
    accountId: 1,
    symbol: 'AAPL',
    marketValue: 1000,
    weightPct: 50,
    shockPct: -10,
    pnl: -100,
    stressedMarketValue: 900,
    priceSource: 'history_close',
    priceProvider: 'fixture',
    priceDate: '2026-08-15',
    priceStale: false,
    dataQuality: 'ok' as const,
    limitations: [] as string[],
    ...overrides,
  };
}

function makeResult(overrides: Partial<PortfolioStressResponse> = {}): PortfolioStressResponse {
  const impact = makeImpact();
  return {
    asOf: '2026-08-15',
    calculatedAt: '2026-08-15T12:00:00Z',
    snapshotId: 'a'.repeat(64),
    snapshotVersion: 'portfolio_snapshot_v1',
    accountId: 1,
    costMethod: 'fifo',
    currency: 'USD',
    status: 'ok',
    portfolioValue: 2000,
    authoritativePortfolioValue: 2000,
    reconciliationDelta: 0,
    positionsUsed: 1,
    excludedPositionCount: 0,
    excludedKnownMarketValue: 0,
    excludedUnknownValueCount: 0,
    excludedPositions: [],
    simulationMethod: 'deterministic_factor_shock',
    historicalReplayAvailable: false,
    scenario: { ...scenario, targetSector: null },
    assumptions: { simplifiedAssumptions: [], dataSource: 'portfolio_snapshot' },
    snapshotFxStale: false,
    snapshotDataQuality: 'ok',
    snapshotLimitations: [],
    missingData: [],
    portfolioPnl: -100,
    portfolioPnlPct: -5,
    stressedPortfolioValue: 1900,
    positionImpacts: [impact],
    topLosers: [impact],
    topWinners: [],
    concentration: { status: 'ok' },
    ...overrides,
  };
}

async function renderPanel(language: Extract<UiLanguage, 'en' | 'zh'> = 'en') {
  render(
    <UiLanguageProvider initialLanguage={language}>
      <PortfolioStressPanel
        accountId={1}
        costMethod="fifo"
        text={SOURCE_PORTFOLIO_INSIGHTS_TEXT[language]}
      />
    </UiLanguageProvider>,
  );
}

async function runAnalysis(runLabel: string) {
  const button = await screen.findByRole('button', { name: runLabel });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  expect(await screen.findByText('AAPL')).toBeInTheDocument();
}

describe('PortfolioStressPanel data-quality column', () => {
  beforeEach(() => {
    listStressScenarios.mockReset();
    runStressPreset.mockReset();
    listStressScenarios.mockResolvedValue({
      scenarios: [scenario],
      simulationMethod: 'deterministic_factor_shock',
      historicalReplayAvailable: false,
    });
  });

  it('renders localized known quality and limitation labels after Run analysis', async () => {
    runStressPreset.mockResolvedValue(makeResult({
      snapshotDataQuality: 'partial',
      snapshotLimitations: ['realtime_quote_best_effort'],
      positionImpacts: [makeImpact({
        dataQuality: 'partial',
        priceStale: true,
        limitations: ['realtime_quote_best_effort'],
      })],
    }));

    await renderPanel('en');
    await runAnalysis('Run analysis');

    expect(screen.getByText('Partial · Stale · Realtime quotes are best-effort')).toBeInTheDocument();
    expect(screen.queryByText('realtime_quote_best_effort')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Assumptions and limitations' }));
    expect(screen.getByText('Partial')).toBeInTheDocument();
    expect(screen.getByText('Realtime quotes are best-effort')).toBeInTheDocument();
    expect(screen.queryByText('realtime_quote_best_effort')).not.toBeInTheDocument();
  });

  it('renders zh known quality and limitation labels instead of raw codes', async () => {
    runStressPreset.mockResolvedValue(makeResult({
      snapshotDataQuality: 'partial',
      snapshotLimitations: ['realtime_quote_best_effort'],
      positionImpacts: [makeImpact({
        dataQuality: 'partial',
        priceStale: true,
        limitations: ['realtime_quote_best_effort'],
      })],
    }));

    await renderPanel('zh');
    await runAnalysis('运行分析');

    expect(screen.getByText('部分可用 · 过期 · 实时行情为尽力获取')).toBeInTheDocument();
    expect(screen.queryByText('partial')).not.toBeInTheDocument();
    expect(screen.queryByText('realtime_quote_best_effort')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '假设与限制' }));
    expect(screen.getByText('实时行情为尽力获取')).toBeInTheDocument();
    expect(screen.queryByText('realtime_quote_best_effort')).not.toBeInTheDocument();
  });

  it('joins partial quality without stale separately from stale-only rows', async () => {
    runStressPreset.mockResolvedValue(makeResult({
      snapshotDataQuality: 'partial',
      snapshotLimitations: ['fx_and_cost_basis_partial'],
      positionImpacts: [makeImpact({
        dataQuality: 'partial',
        priceStale: false,
        limitations: ['fx_and_cost_basis_partial'],
      })],
    }));

    await renderPanel('en');
    await runAnalysis('Run analysis');

    expect(screen.getByText('Partial · FX and cost basis are partial')).toBeInTheDocument();
    expect(screen.queryByText('Partial · Stale · FX and cost basis are partial')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Assumptions and limitations' }));
    expect(screen.getByText('FX and cost basis are partial')).toBeInTheDocument();
  });

  it('localizes excluded-position reasons in the assumptions list', async () => {
    runStressPreset.mockResolvedValue(makeResult({
      excludedPositions: [
        { symbol: 'MSFT', reason: 'price_unavailable' },
        { symbol: 'TSLA', reason: 'non_positive_market_value' },
      ],
    }));

    await renderPanel('en');
    await runAnalysis('Run analysis');
    fireEvent.click(screen.getByRole('button', { name: 'Assumptions and limitations' }));

    expect(screen.getByText('No usable stored daily close.')).toBeInTheDocument();
    expect(screen.getByText('Market value is not positive, so the position is excluded from the stress run.')).toBeInTheDocument();
    expect(screen.queryByText('price_unavailable')).not.toBeInTheDocument();
    expect(screen.queryByText('non_positive_market_value')).not.toBeInTheDocument();
  });

  it('keeps unknown quality and limitation codes visible', async () => {
    runStressPreset.mockResolvedValue(makeResult({
      snapshotDataQuality: 'weird_quality' as PortfolioStressResponse['snapshotDataQuality'],
      snapshotLimitations: ['brand_new_limitation'],
      positionImpacts: [makeImpact({
        dataQuality: 'weird_quality' as never,
        limitations: ['brand_new_limitation'],
      })],
    }));

    await renderPanel('zh');
    expect(await screen.findByText('大盘下跌 10%')).toBeInTheDocument();
    await runAnalysis('运行分析');

    expect(screen.getAllByText(/未知状态 \(weird_quality\)/)).not.toHaveLength(0);
    expect(screen.getAllByText(/未知编码（brand_new_limitation）/)).not.toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: '假设与限制' }));
    expect(screen.getAllByText(/未知状态 \(weird_quality\)/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/未知编码（brand_new_limitation）/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/^brand_new_limitation$/)).not.toBeInTheDocument();
  });
});
