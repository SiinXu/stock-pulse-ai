// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createApiError, createParsedApiError } from '../../../api/error';
import { reportExportApi, type ReportExportCapabilities } from '../../../api/reportExport';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { createDeferred } from '../../../test-utils';
import type { DecisionSignalItem } from '../../../types/decisionSignals';
import { DecisionSignalDetails } from '../DecisionSignalDetails';

vi.mock('../../../api/reportExport', () => ({
  reportExportApi: {
    getCapabilities: vi.fn(),
    download: vi.fn(),
  },
}));

const AVAILABLE_CAPABILITIES: ReportExportCapabilities = {
  formats: {
    md: { available: true },
    html: { available: true },
    pdf: { available: true },
  },
};

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

function signalWithSourceReportId(sourceReportId: unknown): DecisionSignalItem {
  return { ...signal, sourceReportId } as DecisionSignalItem;
}

function renderDetails(item: DecisionSignalItem) {
  return render(
    <UiLanguageProvider initialLanguage="en">
      <DecisionSignalDetails item={item} />
    </UiLanguageProvider>,
  );
}

function expectNoExportControls() {
  expect(screen.queryByTestId('report-export-controls')).not.toBeInTheDocument();
  expect(screen.queryByTestId('report-export-md')).not.toBeInTheDocument();
  expect(screen.queryByTestId('report-export-html')).not.toBeInTheDocument();
  expect(screen.queryByTestId('report-export-pdf')).not.toBeInTheDocument();
  expect(reportExportApi.getCapabilities).not.toHaveBeenCalled();
  expect(reportExportApi.download).not.toHaveBeenCalled();
}

describe('DecisionSignalDetails source-report export', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(reportExportApi.getCapabilities).mockResolvedValue(AVAILABLE_CAPABILITIES);
    vi.mocked(reportExportApi.download).mockResolvedValue({ filename: 'stockpulse-report-3001.md' });
  });

  it('exposes one-click export for a present source report id and downloads that record', async () => {
    renderDetails(signal);

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

  it.each([
    ['null', null],
    ['undefined', undefined],
    ['zero', 0],
    ['negative integer', -1],
    ['non-integer', 3001.5],
    ['numeric string', '3001'],
    ['NaN', Number.NaN],
    ['Infinity', Number.POSITIVE_INFINITY],
    ['boolean true', true],
    ['boolean false', false],
  ])('renders no export controls when the source report id is %s', (_label, sourceReportId) => {
    renderDetails(signalWithSourceReportId(sourceReportId));
    expectNoExportControls();
  });

  it('downloads MAX_SAFE_INTEGER as that record id without substituting another record', async () => {
    const recordId = Number.MAX_SAFE_INTEGER;
    vi.mocked(reportExportApi.download).mockResolvedValue({
      filename: `stockpulse-report-${recordId}.md`,
    });

    renderDetails(signalWithSourceReportId(recordId));

    expect(await screen.findByTestId('report-export-controls')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('report-export-md'));
    await waitFor(() => {
      expect(reportExportApi.download).toHaveBeenCalledTimes(1);
      expect(reportExportApi.download).toHaveBeenCalledWith(recordId, 'md');
    });
    expect(reportExportApi.download).not.toHaveBeenCalledWith(3001, 'md');
    expect(reportExportApi.download).not.toHaveBeenCalledWith(0, 'md');
  });

  it('clears a parsed download error after a successful retry', async () => {
    vi.mocked(reportExportApi.download)
      .mockRejectedValueOnce(createApiError(createParsedApiError({
        title: '需要登录',
        message: '登录状态已失效，请重新登录。',
        code: 'unauthorized',
      })))
      .mockResolvedValueOnce({ filename: 'stockpulse-report-3001.md' });

    renderDetails(signal);
    fireEvent.click(await screen.findByTestId('report-export-md'));

    expect(await screen.findByTestId('report-export-error')).toHaveTextContent(
      'Your session has expired. Sign in again.',
    );

    fireEvent.click(screen.getByTestId('report-export-md'));
    await waitFor(() => {
      expect(screen.queryByTestId('report-export-error')).not.toBeInTheDocument();
      expect(reportExportApi.download).toHaveBeenCalledTimes(2);
    });
    expect(reportExportApi.download).toHaveBeenNthCalledWith(1, 3001, 'md');
    expect(reportExportApi.download).toHaveBeenNthCalledWith(2, 3001, 'md');
  });

  it('disables export actions while a download is in flight and ignores repeated clicks', async () => {
    const pending = createDeferred<{ filename: string }>();
    vi.mocked(reportExportApi.download).mockReturnValueOnce(pending.promise);

    renderDetails(signal);
    await waitFor(() => {
      expect(screen.getByTestId('report-export-html')).not.toBeDisabled();
      expect(screen.getByTestId('report-export-pdf')).not.toBeDisabled();
    });

    fireEvent.click(screen.getByTestId('report-export-md'));
    await waitFor(() => {
      expect(screen.getByTestId('report-export-md')).toBeDisabled();
      expect(screen.getByTestId('report-export-html')).toBeDisabled();
      expect(screen.getByTestId('report-export-pdf')).toBeDisabled();
    });
    expect(reportExportApi.download).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('report-export-md'));
    fireEvent.click(screen.getByTestId('report-export-html'));
    fireEvent.click(screen.getByTestId('report-export-pdf'));
    expect(reportExportApi.download).toHaveBeenCalledTimes(1);

    await act(async () => {
      pending.resolve({ filename: 'stockpulse-report-3001.md' });
      await pending.promise;
    });

    await waitFor(() => {
      expect(screen.getByTestId('report-export-md')).not.toBeDisabled();
      expect(screen.getByTestId('report-export-html')).not.toBeDisabled();
      expect(screen.getByTestId('report-export-pdf')).not.toBeDisabled();
    });
    expect(reportExportApi.download).toHaveBeenCalledTimes(1);
    expect(reportExportApi.download).toHaveBeenCalledWith(3001, 'md');
  });

  it('does not apply late capabilities after unmount', async () => {
    const pending = createDeferred<ReportExportCapabilities>();
    vi.mocked(reportExportApi.getCapabilities).mockReturnValue(pending.promise);

    const { unmount } = renderDetails(signal);
    expect(await screen.findByTestId('report-export-controls')).toBeInTheDocument();
    unmount();
    expect(screen.queryByTestId('report-export-controls')).not.toBeInTheDocument();

    await act(async () => {
      pending.resolve(AVAILABLE_CAPABILITIES);
      await pending.promise;
    });

    expect(screen.queryByTestId('report-export-controls')).not.toBeInTheDocument();
    expect(reportExportApi.download).not.toHaveBeenCalled();
  });
});
