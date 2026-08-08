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
    expect(screen.getByText('Balance path')).toBeInTheDocument();
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
      message: 'With a zero rate and non-positive contribution the target is unreachable.',
    });

    renderPage();
    fireEvent.click(screen.getByRole('radio', { name: 'Time to goal' }));
    fireEvent.click(screen.getByRole('button', { name: 'Calculate' }));

    expect(await screen.findByText('Target unreachable')).toBeInTheDocument();
    expect(
      screen.getByText('With a zero rate and non-positive contribution the target is unreachable.'),
    ).toBeInTheDocument();
    expect(calculatorsApi.targetDuration).toHaveBeenCalled();
  });
});
