// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../../api/history';
import { reportExportApi } from '../../../api/reportExport';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { ReportMarkdownPanel } from '../ReportMarkdownPanel';

vi.mock('../../../api/history', () => ({
  historyApi: {
    getMarkdown: vi.fn(),
    getDetail: vi.fn(),
  },
}));

vi.mock('../../../api/reportExport', () => ({
  reportExportApi: {
    getCapabilities: vi.fn(),
    download: vi.fn(),
  },
}));

describe('ReportMarkdownPanel export controls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# Report');
    vi.mocked(historyApi.getDetail).mockRejectedValue(new Error('detail optional'));
    vi.mocked(reportExportApi.getCapabilities).mockResolvedValue({
      formats: {
        md: { available: true },
        pdf: { available: true },
      },
    });
    vi.mocked(reportExportApi.download).mockResolvedValue({ filename: 'stockpulse-report-7.md' });
  });

  it('exposes markdown and pdf export actions that call the export API', async () => {
    render(
      <UiLanguageProvider initialLanguage="en">
        <ReportMarkdownPanel
          recordId={7}
          stockName="Demo"
          stockCode="600519"
          onRequestClose={() => undefined}
        />
      </UiLanguageProvider>,
    );

    expect(await screen.findByTestId('report-export-md')).toBeInTheDocument();
    expect(screen.getByTestId('report-export-pdf')).toBeInTheDocument();

    await waitFor(() => {
      expect(reportExportApi.getCapabilities).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByTestId('report-export-md'));
    await waitFor(() => {
      expect(reportExportApi.download).toHaveBeenCalledWith(7, 'md');
    });
  });
});
