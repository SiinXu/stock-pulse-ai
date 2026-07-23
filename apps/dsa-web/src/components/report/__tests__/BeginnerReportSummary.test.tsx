import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { AnalysisReport } from '../../../types/analysis';
import BeginnerReportSummary from '../BeginnerReportSummary';

const report: AnalysisReport = {
  meta: {
    id: 7,
    queryId: 'q-7',
    stockCode: '600519',
    stockName: '贵州茅台',
    reportType: 'brief',
    reportLanguage: 'zh',
    createdAt: '2026-07-22T08:00:00Z',
  },
  summary: {
    analysisSummary: '趋势走弱，先确认支撑是否有效。',
    operationAdvice: '控制仓位并查看完整风险依据。',
    action: 'reduce',
    trendPrediction: '短期承压',
    sentimentScore: 32,
  },
};

describe('BeginnerReportSummary', () => {
  it('shows a compact conclusion, conservative risk level, and professional-detail action', () => {
    const onShowProfessional = vi.fn();
    render(
      <UiLanguageProvider>
        <BeginnerReportSummary data={report} onShowProfessional={onShowProfessional} />
      </UiLanguageProvider>,
    );

    expect(screen.getByRole('heading', { name: '贵州茅台' })).toBeInTheDocument();
    expect(screen.getByText('趋势走弱，先确认支撑是否有效。')).toBeInTheDocument();
    expect(screen.getByText('控制仓位并查看完整风险依据。')).toBeInTheDocument();
    expect(screen.getByText('Elevated')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'View professional details' }));
    expect(onShowProfessional).toHaveBeenCalledTimes(1);
  });
});
