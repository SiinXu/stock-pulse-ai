// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ReportVersionCompareResponse } from '../../../api/reportVersionCompare';
import { ReportVersionCompareView } from '../ReportVersionCompareView';

const baseRun = {
  runId: '1',
  queryId: 'q-base',
  stockCode: '600519',
  stockName: 'Kweichow Moutai',
  reportType: 'detailed',
  createdAt: '2026-08-01T10:00:00',
  modelUsed: 'model-a',
  reportLanguage: 'en',
  action: 'buy',
  actionLabel: 'Buy',
  operationAdvice: 'Buy',
  sentimentScore: 80,
  trendPrediction: 'up',
  analysisSummary: 'Bullish',
  configFingerprint: 'aaa111',
  configComponents: {
    model_used: 'model-a',
    report_type: 'detailed',
    report_language: 'en',
    analysis_phase: 'postmarket',
    strategy_mode: '',
    config_profile: '',
  },
};

const targetRun = {
  ...baseRun,
  runId: '2',
  queryId: 'q-target',
  createdAt: '2026-08-08T10:00:00',
  modelUsed: 'model-b',
  action: 'sell',
  actionLabel: 'Sell',
  operationAdvice: 'Sell',
  sentimentScore: 25,
  analysisSummary: 'Bearish',
  configFingerprint: 'bbb222',
  configComponents: {
    ...baseRun.configComponents,
    model_used: 'model-b',
  },
};

function buildResult(
  overrides: Partial<ReportVersionCompareResponse> = {},
): ReportVersionCompareResponse {
  return {
    status: 'ok',
    stockCode: '600519',
    baseRun,
    targetRun,
    configDiff: {
      baseFingerprint: 'aaa111',
      targetFingerprint: 'bbb222',
      identical: false,
      hasDifferences: true,
      components: [
        {
          key: 'model_used',
          baseValue: 'model-a',
          targetValue: 'model-b',
          changed: true,
        },
        {
          key: 'report_type',
          baseValue: 'detailed',
          targetValue: 'detailed',
          changed: false,
        },
      ],
    },
    fieldDiffs: [
      {
        field: 'action',
        baseValue: 'buy',
        targetValue: 'sell',
        changed: true,
        severity: 'major',
      },
      {
        field: 'sentiment_score',
        baseValue: '80',
        targetValue: '82',
        changed: true,
        severity: 'minor',
      },
      {
        field: 'trend_prediction',
        baseValue: 'up',
        targetValue: 'up',
        changed: false,
        severity: 'none',
      },
    ],
    delta: {
      hasBaseline: true,
      conclusionChanges: [{ field: 'action', base: 'buy', target: 'sell' }],
      scoreChanges: [],
      evidenceChanges: [],
      riskChanges: [],
      baseRunId: '1',
      targetRunId: '2',
    },
    engineStatus: 'ok',
    ...overrides,
  };
}

describe('ReportVersionCompareView', () => {
  it('renders idle empty state', () => {
    render(<ReportVersionCompareView language="en" result={null} idle />);
    expect(screen.getByTestId('report-version-compare-idle')).toBeInTheDocument();
  });

  it('highlights major conclusion reversals more strongly than minor score tweaks', () => {
    render(<ReportVersionCompareView language="en" result={buildResult()} />);
    const actionRow = screen.getByTestId('report-version-field-action');
    const scoreRow = screen.getByTestId('report-version-field-sentiment_score');
    expect(actionRow).toHaveAttribute('data-severity', 'major');
    expect(scoreRow).toHaveAttribute('data-severity', 'minor');
    expect(actionRow.className).toContain('bg-danger/10');
    expect(scoreRow.className).toContain('bg-primary/5');
    expect(screen.getByTestId('report-version-config-diff')).toBeInTheDocument();
    expect(screen.getByText(/Configuration differs/i)).toBeInTheDocument();
  });

  it('renders engine_pending distinctly from unchanged fields', () => {
    render(
      <ReportVersionCompareView
        language="en"
        result={buildResult({
          status: 'engine_pending',
          engineStatus: 'engine_pending',
          delta: null,
        })}
      />,
    );
    expect(screen.getByTestId('report-version-compare-status-engine_pending')).toBeInTheDocument();
    expect(screen.getByText(/Comparison engine not wired yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Unchanged$/i)).not.toBeNull();
  });

  it('renders no_baseline as missing baseline, not as no change', () => {
    render(
      <ReportVersionCompareView
        language="en"
        result={buildResult({
          status: 'no_baseline',
          delta: {
            hasBaseline: false,
            conclusionChanges: [],
            scoreChanges: [],
            evidenceChanges: [],
            riskChanges: [],
            baseRunId: '1',
            targetRunId: '2',
          },
        })}
      />,
    );
    expect(screen.getByTestId('report-version-compare-status-no_baseline')).toBeInTheDocument();
    expect(screen.getByText(/No baseline available/i)).toBeInTheDocument();
  });
});
