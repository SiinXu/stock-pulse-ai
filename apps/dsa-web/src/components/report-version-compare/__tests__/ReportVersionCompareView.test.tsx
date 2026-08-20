// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type {
  OptionalSectionPresence,
  ReportVersionCompareResponse,
} from '../../../api/reportVersionCompare';
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
  configComplete: true,
  configMissingKeys: [],
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
      comparisonStatus: 'different',
      baseComplete: true,
      targetComplete: true,
      baseMissingKeys: [],
      targetMissingKeys: [],
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
    optionalSections: [
      {
        section: 'catalysts',
        basePresent: false,
        targetPresent: false,
        comparisonStatus: 'both_missing',
        baseItemCount: 0,
        targetItemCount: 0,
        basePreview: [],
        targetPreview: [],
      },
      {
        section: 'structured_risk',
        basePresent: false,
        targetPresent: false,
        comparisonStatus: 'both_missing',
        baseItemCount: 0,
        targetItemCount: 0,
        basePreview: [],
        targetPreview: [],
      },
      {
        section: 'multi_agent',
        basePresent: false,
        targetPresent: false,
        comparisonStatus: 'both_missing',
        baseItemCount: 0,
        targetItemCount: 0,
        basePreview: [],
        targetPreview: [],
      },
    ],
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
      baselineStatus: 'ok',
      baselineReason: null,
      stockCode: '600519',
      baseRecordId: 1,
      targetRecordId: 2,
      baseQueryId: 'q-base',
      targetQueryId: 'q-target',
      reportType: 'detailed',
      hasMaterialChanges: true,
      conclusionChanges: [{
        field: 'action',
        baseValue: 'buy',
        targetValue: 'sell',
        delta: null,
        direction: 'changed',
        comparable: true,
        unavailability: null,
      }],
      scoreChanges: [],
      evidenceChanges: [],
      riskChanges: [],
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
            baselineStatus: 'missing_history',
            baselineReason: 'No prior comparable history',
            stockCode: '600519',
            baseRecordId: 1,
            targetRecordId: 2,
            baseQueryId: 'q-base',
            targetQueryId: 'q-target',
            reportType: 'detailed',
            hasMaterialChanges: false,
            conclusionChanges: [],
            scoreChanges: [],
            evidenceChanges: [],
            riskChanges: [],
          },
        })}
      />,
    );
    const status = screen.getByTestId('report-version-compare-status-no_baseline');
    expect(status).toBeInTheDocument();
    expect(within(status).getByText(/No baseline available/i)).toBeInTheDocument();
  });

  it('shows incomplete configuration provenance as unknown, not identical', () => {
    render(
      <ReportVersionCompareView
        language="en"
        result={buildResult({
          baseRun: {
            ...baseRun,
            configFingerprint: null,
            configComplete: false,
            configMissingKeys: ['provider_route'],
          },
          targetRun: {
            ...targetRun,
            configFingerprint: null,
            configComplete: false,
            configMissingKeys: ['provider_route'],
          },
          configDiff: {
            baseFingerprint: null,
            targetFingerprint: null,
            identical: false,
            hasDifferences: false,
            comparisonStatus: 'unknown',
            baseComplete: false,
            targetComplete: false,
            baseMissingKeys: ['provider_route'],
            targetMissingKeys: ['provider_route'],
            components: [],
          },
        })}
      />,
    );
    expect(screen.getByText(/provenance is incomplete/i)).toBeInTheDocument();
    expect(screen.queryByText(/fingerprints match/i)).not.toBeInTheDocument();
  });

  function optionalRow(
    section: OptionalSectionPresence['section'],
    status: OptionalSectionPresence['comparisonStatus'],
    extra: Partial<OptionalSectionPresence> = {},
  ): OptionalSectionPresence {
    return {
      section,
      basePresent: status === 'present_identical' || status === 'present_different' || status === 'target_missing',
      targetPresent: status === 'present_identical' || status === 'present_different' || status === 'base_missing',
      comparisonStatus: status,
      baseItemCount: 0,
      targetItemCount: 0,
      basePreview: [],
      targetPreview: [],
      ...extra,
    };
  }

  it('labels both-missing optional sections instead of inventing empty parity', () => {
    render(<ReportVersionCompareView language="en" result={buildResult()} />);
    const panel = screen.getByTestId('report-version-optional-sections');
    expect(within(panel).getByText(/Absence is labeled explicitly/i)).toBeInTheDocument();
    expect(screen.getByTestId('report-version-optional-section-catalysts')).toHaveAttribute(
      'data-comparison-status',
      'both_missing',
    );
    expect(within(screen.getByTestId('report-version-optional-section-catalysts')).getAllByText(
      /Section not produced/i,
    )).toHaveLength(2);
    expect(within(screen.getByTestId('report-version-optional-section-structured_risk')).getByText(
      /Neither run produced this section/i,
    )).toBeInTheDocument();
  });

  it('surfaces left-missing catalysts without treating them as empty content', () => {
    render(
      <ReportVersionCompareView
        language="en"
        result={buildResult({
          optionalSections: [
            optionalRow('catalysts', 'base_missing', {
              targetItemCount: 1,
              targetPreview: ['Export recovery'],
            }),
            optionalRow('structured_risk', 'both_missing'),
            optionalRow('multi_agent', 'both_missing'),
          ],
        })}
      />,
    );
    const row = screen.getByTestId('report-version-optional-section-catalysts');
    expect(row).toHaveAttribute('data-comparison-status', 'base_missing');
    expect(within(row).getByText(/Baseline did not produce this section/i)).toBeInTheDocument();
    expect(within(row).getByText('Export recovery')).toBeInTheDocument();
    expect(within(row).queryByText(/^n\/a$/i)).not.toBeInTheDocument();
  });

  it('surfaces right-missing structured risk', () => {
    render(
      <ReportVersionCompareView
        language="en"
        result={buildResult({
          optionalSections: [
            optionalRow('catalysts', 'both_missing'),
            optionalRow('structured_risk', 'target_missing', {
              baseItemCount: 1,
              basePreview: ['Elevated PE'],
            }),
            optionalRow('multi_agent', 'both_missing'),
          ],
        })}
      />,
    );
    const row = screen.getByTestId('report-version-optional-section-structured_risk');
    expect(row).toHaveAttribute('data-comparison-status', 'target_missing');
    expect(within(row).getByText(/Candidate did not produce this section/i)).toBeInTheDocument();
    expect(within(row).getByText('Elevated PE')).toBeInTheDocument();
  });

  it('shows present-but-different multi-agent contents beside the T17 delta', () => {
    render(
      <ReportVersionCompareView
        language="en"
        result={buildResult({
          optionalSections: [
            optionalRow('catalysts', 'present_different', {
              baseItemCount: 1,
              targetItemCount: 2,
              basePreview: ['Quarterly update clean'],
              targetPreview: ['Quarterly update clean', 'Export recovery'],
            }),
            optionalRow('structured_risk', 'present_identical', {
              baseItemCount: 1,
              targetItemCount: 1,
              basePreview: ['Elevated PE'],
              targetPreview: ['Elevated PE'],
            }),
            optionalRow('multi_agent', 'present_different', {
              baseItemCount: 1,
              targetItemCount: 2,
              basePreview: ['bull_bear_debate'],
              targetPreview: ['bull_bear_debate', 'committee_deliberation'],
            }),
          ],
        })}
      />,
    );
    expect(screen.getByTestId('report-version-optional-section-catalysts')).toHaveAttribute(
      'data-comparison-status',
      'present_different',
    );
    expect(within(screen.getByTestId('report-version-optional-section-structured_risk')).getByText(
      /same content/i,
    )).toBeInTheDocument();
    expect(within(screen.getByTestId('report-version-optional-section-multi_agent')).getByText(
      'committee_deliberation',
    )).toBeInTheDocument();
    expect(screen.getByTestId('report-version-engine-delta')).toBeInTheDocument();
  });
});
