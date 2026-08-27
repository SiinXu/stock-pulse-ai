// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { agentFeedbackApi } from '../../../api/agentFeedback';
import { createApiError, createParsedApiError } from '../../../api/error';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { AnalysisReport } from '../../../types/analysis';
import { ReportSummary } from '../ReportSummary';

vi.mock('../../../api/history', () => ({
  historyApi: {
    getDiagnostics: vi.fn().mockResolvedValue(null),
    getNews: vi.fn().mockResolvedValue({ total: 0, items: [] }),
    getRecordFlow: vi.fn().mockResolvedValue(null),
    getMarkdown: vi.fn().mockResolvedValue('# Market Review'),
  },
}));

vi.mock('../../../api/agentFeedback', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/agentFeedback')>();
  return {
    ...actual,
    agentFeedbackApi: {
      getRunFeedback: vi.fn(),
      putRunFeedback: vi.fn(),
    },
  };
});

const stockReport: AnalysisReport = {
  meta: {
    id: 1,
    queryId: 'q1',
    stockCode: '600519',
    stockName: 'Kweichow Moutai',
    reportType: 'detailed',
    reportLanguage: 'en',
    createdAt: '2026-04-10T12:00:00Z',
  },
  summary: {
    analysisSummary: 'summary',
    operationAdvice: 'hold',
    trendPrediction: 'range',
    sentimentScore: 70,
  },
};

const marketReviewReport: AnalysisReport = {
  ...stockReport,
  meta: {
    ...stockReport.meta,
    queryId: 'market-review-q-1',
    reportType: 'market_review',
    stockCode: 'MARKET',
    stockName: 'Market Review',
  },
};

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  const wrap = (node: ReactElement) => (
    <QueryClientProvider client={client}>
      <UiLanguageProvider>{node}</UiLanguageProvider>
    </QueryClientProvider>
  );
  const view = render(wrap(ui));
  return {
    ...view,
    rerender: (next: ReactElement) => view.rerender(wrap(next)),
  };
}

describe('ReportSummary run feedback mount', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(agentFeedbackApi.getRunFeedback).mockResolvedValue({
      runId: 'q1',
      feedbackValue: null,
      note: null,
      source: null,
      provenanceSource: null,
      actorId: null,
      createdAt: null,
      updatedAt: null,
    });
  });

  it('mounts the panel for a stock report with queryId after analysis context', async () => {
    renderWithClient(<ReportSummary data={stockReport} />);
    const panel = await screen.findByTestId('report-run-feedback');
    expect(agentFeedbackApi.getRunFeedback).toHaveBeenCalledWith('q1');
    expect(within(panel).getByRole('button', { name: 'Useful' })).toHaveAttribute(
      'data-control',
      'selection-chip',
    );
    const context = document.querySelector('[data-testid="analysis-context-summary"]');
    if (context) {
      expect(context.compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it('hides the panel when queryId is missing', async () => {
    const report: AnalysisReport = {
      ...stockReport,
      meta: { ...stockReport.meta, queryId: '   ' },
    };
    renderWithClient(<ReportSummary data={report} />);
    await waitFor(() => expect(agentFeedbackApi.getRunFeedback).not.toHaveBeenCalled());
    expect(screen.queryByTestId('report-run-feedback')).not.toBeInTheDocument();
  });

  it('does not double-mount on a market_review report', async () => {
    vi.mocked(agentFeedbackApi.getRunFeedback).mockResolvedValue({
      runId: 'market-review-q-1',
      feedbackValue: null,
      note: null,
      source: null,
      provenanceSource: null,
      actorId: null,
      createdAt: null,
      updatedAt: null,
    });
    renderWithClient(<ReportSummary data={marketReviewReport} />);
    expect(await screen.findAllByTestId('report-run-feedback')).toHaveLength(1);
    expect(agentFeedbackApi.getRunFeedback).toHaveBeenCalledTimes(1);
    expect(agentFeedbackApi.getRunFeedback).toHaveBeenCalledWith('market-review-q-1');
  });

  it('hides the panel for a 404 parent without a broken error page', async () => {
    vi.mocked(agentFeedbackApi.getRunFeedback).mockRejectedValue(
      createApiError(createParsedApiError({
        title: 'Not found',
        message: 'Analysis run not found.',
        status: 404,
        code: 'not_found',
        category: 'http_error',
      })),
    );
    renderWithClient(<ReportSummary data={stockReport} />);
    await waitFor(() => expect(agentFeedbackApi.getRunFeedback).toHaveBeenCalled());
    await waitFor(() => {
      expect(screen.queryByTestId('report-run-feedback')).not.toBeInTheDocument();
    });
    expect(screen.queryByText('Analysis run not found.')).not.toBeInTheDocument();
  });
});

describe('ReportSummary report-strata expansion identity', () => {
  const strataA = {
    schemaVersion: 'report-strata-v1',
    verifiedFacts: [{ statement: 'Report A close was 1680.' }],
    missingOrConflicts: [],
    modelInference: ['Report A inference.'],
    risksCounterEvidence: ['Report A risk.'],
    disclaimer: 'Report A disclaimer.',
  };
  const strataB = {
    schemaVersion: 'report-strata-v1',
    verifiedFacts: [{ statement: 'Report B close was 12.' }],
    missingOrConflicts: [],
    modelInference: ['Report B inference.'],
    risksCounterEvidence: ['Report B risk.'],
    disclaimer: 'Report B disclaimer.',
  };

  it('collapses evidence again when the selected report id changes', async () => {
    const reportA: AnalysisReport = {
      ...stockReport,
      details: { reportStrata: strataA },
    };
    const reportB: AnalysisReport = {
      ...stockReport,
      meta: { ...stockReport.meta, id: 2, queryId: 'q2' },
      details: { reportStrata: strataB },
    };
    const { rerender } = renderWithClient(<ReportSummary data={reportA} />);
    expect(await screen.findByTestId('report-strata-risks')).toHaveTextContent('Report A risk.');
    fireEvent.click(screen.getByTestId('report-strata-toggle'));
    expect(await screen.findByTestId('report-strata-facts')).toHaveTextContent('Report A close was 1680.');
    expect(screen.getByTestId('report-strata')).toHaveAttribute('data-collapsed', 'false');

    rerender(<ReportSummary data={reportB} />);

    expect(await screen.findByTestId('report-strata-risks')).toHaveTextContent('Report B risk.');
    expect(screen.getByTestId('report-strata')).toHaveAttribute('data-collapsed', 'true');
    expect(screen.queryByTestId('report-strata-facts')).not.toBeInTheDocument();
  });
});
