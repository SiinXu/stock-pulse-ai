// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { portfolioApi } from '../../api/portfolio';
import {
  RouteFocusRegistrationContext,
  type RouteFocusTarget,
} from '../../contexts/routeFocusContext';
import { UiLanguageProvider, useUiLanguage } from '../../contexts/UiLanguageContext';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import { UI_LANGUAGE_STORAGE_KEY } from '../../utils/uiLanguage';
import type { PaperDecisionQualityResponse } from '../../types/portfolio';
import PersonalPerformancePage from '../PersonalPerformancePage';

vi.mock('../../api/portfolio', () => ({
  portfolioApi: {
    getAccounts: vi.fn(),
    getPaperDecisionQuality: vi.fn(),
  },
}));

const routeFocusRegister = vi.fn((target: RouteFocusTarget) => {
  void target;
  return () => {};
});

function makeQuality(count: number): PaperDecisionQualityResponse {
  return {
    scoreKind: 'process',
    formulaVersion: 'v1',
    disclaimer: 'Process score only.',
    accountId: 7,
    accountType: 'paper',
    asOf: '2026-08-19',
    sampleSize: count,
    totalTradeCount: count,
    truncated: false,
    aggregate: {
      sampleSize: count,
      processScore: 80,
      status: 'ok',
      dimensions: {
        analysis_support: { score: 80, status: 'ok', sampleSize: count },
        risk_gate_compliance: { score: 80, status: 'ok', sampleSize: count },
        position_discipline: { score: 80, status: 'ok', sampleSize: count },
      },
    },
    items: Array.from({ length: count }, (_, index) => ({
      tradeId: index + 1,
      symbol: `SYM${String(index + 1).padStart(3, '0')}`,
      market: 'us',
      side: 'buy',
      tradeDate: '2026-08-01',
      processScore: 80,
      dimensions: {},
      formulaVersion: 'v1',
      reasons: [
        { dimension: 'analysis_support', code: 'linked', message: `Trade ${index + 1} has a linked analysis.` },
        { dimension: 'risk_gate', code: 'stop', message: `Trade ${index + 1} recorded a stop-loss.` },
        { dimension: 'position', code: 'size', message: `Trade ${index + 1} stayed inside the size band.` },
      ],
    })),
    divisionOfLabor: {
      thisIssue: 986,
      owns: 'process',
      doesNotOwn: 'outcome',
      outcomeOwnerIssue: 987,
    },
  };
}

const report: PaperDecisionQualityResponse = {
  scoreKind: 'process',
  formulaVersion: 'paper-decision-quality-v2',
  disclaimer: 'Paper decision quality is a process score. It is not a return evaluation.',
  accountId: 7,
  accountType: 'paper',
  asOf: '2026-08-15',
  sampleSize: 1,
  totalTradeCount: 1,
  truncated: false,
  aggregate: {
    sampleSize: 1,
    processScore: 72,
    status: 'ok',
    dimensions: {
      analysis_support: { score: 70, status: 'ok', sampleSize: 1 },
      risk_gate_compliance: { score: 80, status: 'ok', sampleSize: 1 },
      position_discipline: { score: 60, status: 'ok', sampleSize: 1 },
    },
  },
  items: [
    {
      tradeId: 11,
      symbol: 'AAPL',
      side: 'buy',
      tradeDate: '2026-08-14',
      processScore: 72,
      formulaVersion: 'paper-decision-quality-v2',
      dimensions: {},
      reasons: [
        {
          dimension: 'analysis_support',
          code: 'no_analysis_support',
          message: 'No DecisionSignal or analysis plan was linked to this trade.',
        },
      ],
    },
  ],
  divisionOfLabor: {
    thisIssue: 1134,
    owns: 'process score',
    doesNotOwn: 'outcome metrics',
    outcomeOwnerIssue: 987,
  },
};

function renderPage(language: 'zh' | 'en' = 'en') {
  return render(
    <RouteFocusRegistrationContext.Provider value={{ register: routeFocusRegister }}>
      <UiLanguageProvider initialLanguage={language}>
        <MemoryRouter initialEntries={[APP_ROUTE_PATHS.portfolioPerformance]}>
          <PersonalPerformancePage />
        </MemoryRouter>
      </UiLanguageProvider>
    </RouteFocusRegistrationContext.Provider>,
  );
}

describe('PersonalPerformancePage virtualization fallback', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'en');
    vi.mocked(portfolioApi.getAccounts).mockReset();
    vi.mocked(portfolioApi.getPaperDecisionQuality).mockReset();
    vi.mocked(portfolioApi.getAccounts).mockResolvedValue({
      accounts: [{
        id: 7,
        name: 'Paper book',
        market: 'us',
        baseCurrency: 'USD',
        isActive: true,
        accountType: 'paper',
      }],
    });
    vi.mocked(portfolioApi.getPaperDecisionQuality).mockResolvedValue(makeQuality(30));
  });

  it('keeps stacked reason lists on the full DataTable path', async () => {
    render(
      <RouteFocusRegistrationContext.Provider value={{ register: routeFocusRegister }}>
        <MemoryRouter>
          <UiLanguageProvider initialLanguage="en">
            <PersonalPerformancePage />
          </UiLanguageProvider>
        </MemoryRouter>
      </RouteFocusRegistrationContext.Provider>,
    );

    expect(await screen.findByText('SYM030')).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Trade process breakdown' });
    const region = table.parentElement;
    expect(region).toHaveAttribute('data-data-table-virtualized', 'false');
    expect(region).toHaveAttribute('data-data-table-virtual-reason', 'disabled');
    expect(region).toHaveAttribute('data-mounted-count', '30');
    expect(region).toHaveAttribute('data-total-count', '30');
    expect(screen.getByText('SYM001')).toBeInTheDocument();
    expect(screen.getByText(/Unknown code \(size\).*Trade 30 stayed inside the size band/)).toBeInTheDocument();
    expect(screen.queryByText(/^Trade 30 stayed inside the size band\.$/)).not.toBeInTheDocument();
  });
});

describe('PersonalPerformancePage presentation', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'en');
    vi.mocked(portfolioApi.getAccounts).mockReset();
    vi.mocked(portfolioApi.getPaperDecisionQuality).mockReset();
    vi.mocked(portfolioApi.getAccounts).mockResolvedValue({
      accounts: [{ id: 7, name: 'Paper', market: 'us', baseCurrency: 'USD', isActive: true, accountType: 'paper' }],
    });
    vi.mocked(portfolioApi.getPaperDecisionQuality).mockResolvedValue(report);
  });

  it('renders localized reason and side instead of server English prose', async () => {
    renderPage('en');
    await waitFor(() => expect(screen.getByText('AAPL')).toBeInTheDocument());
    expect(screen.getByText('Buy')).toBeInTheDocument();
    expect(screen.getByText('No DecisionSignal or analysis plan was linked to this trade.')).toBeInTheDocument();
    expect(screen.queryByText('buy')).not.toBeInTheDocument();
    expect(screen.getAllByText(/Process scores reflect decision discipline only/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/It is not a return evaluation/)).not.toBeInTheDocument();
  });

  it('updates reason copy immediately after a language switch', async () => {
    render(
      <RouteFocusRegistrationContext.Provider value={{ register: routeFocusRegister }}>
        <UiLanguageProvider initialLanguage="en">
          <MemoryRouter initialEntries={[APP_ROUTE_PATHS.portfolioPerformance]}>
            <LanguageSwitchHarness />
          </MemoryRouter>
        </UiLanguageProvider>
      </RouteFocusRegistrationContext.Provider>,
    );
    await waitFor(() => expect(screen.getByText('No DecisionSignal or analysis plan was linked to this trade.')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'switch-language' }));
    await waitFor(() => expect(screen.getByText('这笔成交没有关联的 DecisionSignal 或分析计划。')).toBeInTheDocument());
    expect(screen.queryByText('No DecisionSignal or analysis plan was linked to this trade.')).not.toBeInTheDocument();
  });
});

function LanguageSwitchHarness() {
  const { language, setLanguage } = useUiLanguage();
  return (
    <>
      <button type="button" onClick={() => setLanguage(language === 'en' ? 'zh' : 'en')}>
        switch-language
      </button>
      <PersonalPerformancePage />
    </>
  );
}
