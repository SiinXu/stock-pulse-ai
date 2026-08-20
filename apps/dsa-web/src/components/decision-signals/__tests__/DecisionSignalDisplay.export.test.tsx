// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { reportExportApi } from '../../../api/reportExport';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { DecisionSignalItem } from '../../../types/decisionSignals';
import { DecisionSignalDetails } from '../DecisionSignalDisplay';

vi.mock('../../../api/reportExport', () => ({
  reportExportApi: {
    getCapabilities: vi.fn(),
    download: vi.fn(),
  },
}));

const signal: DecisionSignalItem = {
  id: 7,
  stockCode: '600519',
  stockName: '贵州茅台',
  market: 'cn',
  sourceType: 'analysis',
  sourceReportId: 3001,
  decisionProfile: 'aggressive',
  marketPhase: 'intraday',
  triggerSource: 'web',
  action: 'hold',
  actionLabel: null,
  confidence: 0.72,
  score: 82,
  horizon: '3d',
  entryLow: 1600,
  entryHigh: 1620,
  stopLoss: 1550,
  targetPrice: 1700,
  invalidation: '跌破 1550',
  watchConditions: '观察成交量',
  reason: '趋势保持',
  riskSummary: '放量下跌风险',
  catalystSummary: '业绩窗口',
  evidence: { technical: 'ma' },
  dataQualitySummary: { freshness: 'ok' },
  planQuality: 'complete',
  status: 'active',
  expiresAt: '2026-06-18T09:30:00',
  createdAt: '2026-06-17T09:30:00',
  updatedAt: '2026-06-17T09:30:00',
  metadata: { source: 'test', decision_profile: 'balanced' },
};

describe('DecisionSignalDetails source-report export', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(reportExportApi.getCapabilities).mockResolvedValue({
      formats: {
        md: { available: true },
        html: { available: true },
        pdf: { available: true },
      },
    });
    vi.mocked(reportExportApi.download).mockResolvedValue({ filename: 'stockpulse-report-3001.md' });
  });

  it('exposes one-click export for a present source report id and downloads that record', async () => {
    render(
      <UiLanguageProvider initialLanguage="en">
        <DecisionSignalDetails item={signal} />
      </UiLanguageProvider>,
    );

    expect(await screen.findByTestId('report-export-controls')).toBeInTheDocument();
    expect(screen.getByTestId('report-export-md')).toHaveAttribute('aria-label', 'Download Markdown');
    expect(screen.getByTestId('report-export-html')).toBeInTheDocument();
    expect(screen.getByTestId('report-export-pdf')).toBeInTheDocument();

    await waitFor(() => {
      expect(reportExportApi.getCapabilities).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByTestId('report-export-md'));
    await waitFor(() => {
      expect(reportExportApi.download).toHaveBeenCalledWith(3001, 'md');
    });
  });

  it('renders no export controls when the source report id is absent', () => {
    render(
      <UiLanguageProvider initialLanguage="en">
        <DecisionSignalDetails item={{ ...signal, sourceReportId: null }} />
      </UiLanguageProvider>,
    );

    expect(screen.queryByTestId('report-export-controls')).not.toBeInTheDocument();
    expect(screen.queryByTestId('report-export-md')).not.toBeInTheDocument();
    expect(screen.queryByTestId('report-export-html')).not.toBeInTheDocument();
    expect(screen.queryByTestId('report-export-pdf')).not.toBeInTheDocument();
    expect(reportExportApi.getCapabilities).not.toHaveBeenCalled();
    expect(reportExportApi.download).not.toHaveBeenCalled();
  });
});
