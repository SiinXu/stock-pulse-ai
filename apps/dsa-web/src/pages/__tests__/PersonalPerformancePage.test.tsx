// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { portfolioApi } from '../../api/portfolio';
import {
  RouteFocusRegistrationContext,
  type RouteFocusTarget,
} from '../../contexts/routeFocusContext';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
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
    expect(screen.getByText('Trade 30 stayed inside the size band.')).toBeInTheDocument();
  });
});
