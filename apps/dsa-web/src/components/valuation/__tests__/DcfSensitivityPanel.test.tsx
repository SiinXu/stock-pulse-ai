// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ReactElement } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ValuationEstimate } from '../../../api/valuation';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { DcfSensitivityPanel } from '../DcfSensitivityPanel';

const sampleEstimate: ValuationEstimate = {
  schemaVersion: 'valuation-estimate-v1',
  status: 'ok',
  stockCode: 'AAPL',
  dcf: {
    status: 'ok',
    equityValue: 1446.21,
    intrinsicValuePerShare: 14.46,
    assumptions: {
      growthRate: 0.05,
      discountRate: 0.1,
      terminalGrowthRate: 0.02,
      projectionYears: 5,
      cashFlowSource: 'operating_cash_flow',
    },
    sensitivity: {
      rows: [
        { growthRate: 0.03, discountRate: 0.09, equityValue: 1600 },
        { growthRate: 0.05, discountRate: 0.09, equityValue: 1700 },
        { growthRate: 0.07, discountRate: 0.09, equityValue: 1800 },
        { growthRate: 0.03, discountRate: 0.1, equityValue: 1400 },
        { growthRate: 0.05, discountRate: 0.1, equityValue: 1446.21 },
        { growthRate: 0.07, discountRate: 0.1, equityValue: 1500 },
        { growthRate: 0.03, discountRate: 0.11, equityValue: 1200 },
        { growthRate: 0.05, discountRate: 0.11, equityValue: 1300 },
        { growthRate: 0.07, discountRate: 0.11, equityValue: 1350 },
      ],
      equityValueLow: 1200,
      equityValueMid: 1446.21,
      equityValueHigh: 1800,
    },
  },
  relative: { status: 'ok' },
  disclaimer: 'Model estimate for research support only. Not investment advice.',
};

const insufficientEstimate: ValuationEstimate = {
  status: 'insufficient_fundamentals',
  stockCode: 'EMPTY',
  dcf: {
    status: 'insufficient_fundamentals',
    message: 'Insufficient fundamentals for DCF',
    sensitivity: { rows: [], equityValueLow: null, equityValueMid: null, equityValueHigh: null },
    assumptions: { growthRate: 0.05, discountRate: 0.1, terminalGrowthRate: 0.03, projectionYears: 5 },
  },
  disclaimer: 'Model estimate for research support only. Not investment advice.',
};

const renderPanel = (ui: ReactElement) =>
  render(<UiLanguageProvider initialLanguage="en">{ui}</UiLanguageProvider>);

describe('DcfSensitivityPanel', () => {
  it('renders visible assumptions, sensitivity matrix, and disclaimer', () => {
    renderPanel(<DcfSensitivityPanel estimate={sampleEstimate} stockCode="AAPL" />);
    expect(screen.getByTestId('dcf-sensitivity-panel')).toBeInTheDocument();
    const assumptions = screen.getByTestId('dcf-visible-assumptions');
    expect(within(assumptions).getByText(/Growth rate/i)).toBeInTheDocument();
    expect(within(assumptions).getByText(/5\.0%/)).toBeInTheDocument();
    const table = screen.getByTestId('dcf-sensitivity-table');
    expect(within(table).getByText('1,446.21')).toBeInTheDocument();
    expect(screen.getByTestId('dcf-disclaimer')).toHaveTextContent(/Not investment advice/i);
  });

  it('shows empty sensitivity state when rows are missing', () => {
    renderPanel(<DcfSensitivityPanel estimate={insufficientEstimate} />);
    expect(screen.getByTestId('dcf-empty-sensitivity')).toBeInTheDocument();
    expect(screen.getByTestId('dcf-insufficient')).toBeInTheDocument();
    expect(screen.queryByTestId('dcf-sensitivity-table')).not.toBeInTheDocument();
  });

  it('shows empty estimate state when no payload is provided', () => {
    renderPanel(<DcfSensitivityPanel />);
    expect(screen.getByTestId('dcf-empty-estimate')).toBeInTheDocument();
  });

  it('re-estimates with adjustable assumptions via fetchEstimate', async () => {
    const fetchEstimate = vi.fn().mockResolvedValue({
      ...sampleEstimate,
      dcf: {
        ...sampleEstimate.dcf,
        equityValue: 2000,
        assumptions: { growthRate: 0.08, discountRate: 0.09, terminalGrowthRate: 0.02, projectionYears: 5 },
      },
    });
    renderPanel(<DcfSensitivityPanel estimate={sampleEstimate} stockCode="AAPL" fetchEstimate={fetchEstimate} />);
    const growthInput = screen.getByTestId('dcf-growth-rate') as HTMLInputElement;
    fireEvent.change(growthInput, { target: { value: '0.08' } });
    fireEvent.click(screen.getByTestId('dcf-recompute'));
    expect(fetchEstimate).toHaveBeenCalledWith(expect.objectContaining({ stockCode: 'AAPL', growthRate: 0.08 }));
    expect(await screen.findByText('2,000')).toBeInTheDocument();
  });
});
