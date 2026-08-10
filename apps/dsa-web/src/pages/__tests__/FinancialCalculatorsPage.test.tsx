// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { calculatorsApi } from '../../api/calculators';
import { RouteFocusRegistrationContext } from '../../contexts/routeFocusContext';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import FinancialCalculatorsPage from '../FinancialCalculatorsPage';

vi.mock('../../api/calculators', () => ({
  calculatorsApi: {
    compoundGrowth: vi.fn(),
    targetContribution: vi.fn(),
    targetDuration: vi.fn(),
  },
}));

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  LineChart: ({ children }: { children: React.ReactNode }) => <div data-testid="line-chart">{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
}));

const routeFocusRegister = vi.fn(() => () => undefined);

function renderPage() {
  return render(
    <MemoryRouter>
      <RouteFocusRegistrationContext.Provider value={{ register: routeFocusRegister }}>
        <UiLanguageProvider initialLanguage="en">
          <FinancialCalculatorsPage />
        </UiLanguageProvider>
      </RouteFocusRegistrationContext.Provider>
    </MemoryRouter>,
  );
}

describe('FinancialCalculatorsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    routeFocusRegister.mockImplementation(() => () => undefined);
  });

  it('renders calculator modes and default form fields', () => {
    renderPage();
    expect(screen.getByRole('heading', { name: 'Financial calculators' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Compound growth' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Contribution needed' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Time to goal' })).toBeInTheDocument();
    expect(screen.getByLabelText('Principal')).toBeInTheDocument();
    expect(screen.getByLabelText('Annual rate (%)')).toBeInTheDocument();
  });

  it('rejects non-finite client input before calling the API', async () => {
    renderPage();
    fireEvent.change(screen.getByLabelText('Principal'), { target: { value: 'Infinity' } });
    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));
    expect(await screen.findByText('Enter a finite number (not NaN or Infinity)')).toBeInTheDocument();
    expect(calculatorsApi.compoundGrowth).not.toHaveBeenCalled();
  });

  it('shows compound growth results and chart after calculate', async () => {
    vi.mocked(calculatorsApi.compoundGrowth).mockResolvedValue({
      status: 'ok',
      principal: 1000,
      annualRate: 0.12,
      years: 1,
      contributionPerPeriod: 0,
      periodsPerYear: 12,
      periodCount: 12,
      periodRate: 0.01,
      finalValue: 1126.83,
      totalContributed: 1000,
      totalGain: 126.83,
      seriesTotalPoints: 13,
      seriesReturnedPoints: 2,
      seriesSampled: true,
      seriesStride: 12,
      series: [
        { period: 0, balance: 1000, totalContributed: 1000, gain: 0 },
        { period: 12, balance: 1126.83, totalContributed: 1000, gain: 126.83 },
      ],
    });

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));

    expect(await screen.findByText('Results')).toBeInTheDocument();
    await waitFor(() => {
      expect(calculatorsApi.compoundGrowth).toHaveBeenCalled();
    });
    expect(screen.getByTestId('growth-chart')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Balance path' })).toBeInTheDocument();
  });

  it('shows unreachable status for duration mode', async () => {
    vi.mocked(calculatorsApi.targetDuration).mockResolvedValue({
      status: 'unreachable',
      target: 5000,
      principal: 1000,
      annualRate: 0,
      contributionPerPeriod: 0,
      periodsPerYear: 12,
      periodRate: 0,
      periodCount: null,
      years: null,
      reasonCode: 'non_positive_trajectory',
    });

    renderPage();
    fireEvent.click(screen.getByRole('radio', { name: 'Time to goal' }));
    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));

    expect(await screen.findByText('Target unreachable')).toBeInTheDocument();
    expect(screen.getByText(
      'The current growth and contribution trajectory does not increase toward the target.',
    )).toBeInTheDocument();
    expect(calculatorsApi.targetDuration).toHaveBeenCalled();
  });

  it('discards an old-mode response after the user switches calculators', async () => {
    let resolveGrowth: ((value: Awaited<ReturnType<typeof calculatorsApi.compoundGrowth>>) => void) | undefined;
    vi.mocked(calculatorsApi.compoundGrowth).mockImplementation((_body, options) => new Promise((resolve) => {
      expect(options?.signal).toBeInstanceOf(AbortSignal);
      resolveGrowth = resolve;
    }));

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));
    fireEvent.click(screen.getByRole('radio', { name: 'Contribution needed' }));

    resolveGrowth?.({
      status: 'ok',
      principal: 1000,
      annualRate: 0.12,
      years: 1,
      contributionPerPeriod: 0,
      periodsPerYear: 12,
      periodCount: 12,
      periodRate: 0.01,
      finalValue: 999999,
      totalContributed: 1000,
      totalGain: 998999,
      seriesTotalPoints: 13,
      seriesReturnedPoints: 2,
      seriesSampled: true,
      seriesStride: 12,
      series: [
        { period: 0, balance: 1000, totalContributed: 1000, gain: 0 },
        { period: 12, balance: 999999, totalContributed: 1000, gain: 998999 },
      ],
    });

    await waitFor(() => expect(screen.queryByText('999,999')).not.toBeInTheDocument());
    expect(screen.getByLabelText('Target amount')).toBeInTheDocument();
  });
});
