// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReportDecisionCard } from '../ReportDecisionCard';
import { ReportRiskGateBanner } from '../ReportRiskGateBanner';
import {
  buildRiskGatePresentation,
  parseRiskGateResult,
} from '../reportRiskGateUtils';
import type { ReportDetails, ReportMeta, ReportSummary } from '../../../types/analysis';

const baseMeta: ReportMeta = {
  queryId: 'q-1',
  stockCode: '600519',
  stockName: '贵州茅台',
  reportType: 'detailed',
  reportLanguage: 'zh',
  createdAt: '2026-03-21T08:00:00Z',
};

const baseSummary: ReportSummary = {
  analysisSummary: '趋势维持强势',
  operationAdvice: '继续观察买点',
  action: 'buy',
  trendPrediction: '短线震荡偏强',
  sentimentScore: 78,
};

const rejectPayload = {
  schema_version: 'risk-manager-result/v1',
  verdict: 'reject',
  original_action: 'buy',
  final_action: 'hold',
  reason_codes: ['portfolio_exposure_limit', 'volatility_limit'],
  evidence_codes: ['portfolio_exposure', 'volatility'],
  profile: 'balanced',
  fail_closed: false,
};

describe('reportRiskGateUtils', () => {
  it('treats missing risk gate payload as not_evaluated, never pass', () => {
    const missing = parseRiskGateResult(undefined);
    expect(missing.status).toBe('not_evaluated');
    expect(missing.verdict).toBeUndefined();

    const nullish = parseRiskGateResult(null);
    expect(nullish.status).toBe('not_evaluated');

    const fromReport = buildRiskGatePresentation({
      summary: baseSummary,
      details: { rawResult: {} },
    });
    expect(fromReport.status).toBe('not_evaluated');
    expect(fromReport.status).not.toBe('pass');
  });

  it('parses reject payload with reason and evidence codes', () => {
    const presentation = parseRiskGateResult(rejectPayload);
    expect(presentation.status).toBe('reject');
    expect(presentation.verdict).toBe('reject');
    expect(presentation.originalAction).toBe('buy');
    expect(presentation.finalAction).toBe('hold');
    expect(presentation.reasonCodes).toEqual([
      'portfolio_exposure_limit',
      'volatility_limit',
    ]);
    expect(presentation.evidenceCodes).toEqual(['portfolio_exposure', 'volatility']);
  });

  it('reads summary.riskManager and camelCase rawResult.riskGateResult', () => {
    const fromSummary = buildRiskGatePresentation({
      summary: {
        ...baseSummary,
        riskManager: {
          schemaVersion: 'risk-manager-result/v1',
          verdict: 'downgrade',
          originalAction: 'buy',
          finalAction: 'hold',
          reasonCodes: ['directional_conflict'],
          evidenceCodes: [],
          profile: 'conservative',
        },
      },
    });
    expect(fromSummary.status).toBe('downgrade');

    const fromRaw: ReportDetails = {
      rawResult: {
        riskGateResult: {
          schemaVersion: 'risk-manager-result/v1',
          verdict: 'pass',
          originalAction: 'hold',
          finalAction: 'hold',
          reasonCodes: [],
          evidenceCodes: [],
          profile: 'balanced',
        },
      },
    };
    expect(buildRiskGatePresentation({ details: fromRaw }).status).toBe('pass');
  });

  it('does not treat invalid schema as pass', () => {
    const invalid = parseRiskGateResult({ schema_version: 'other/v1', verdict: 'pass' });
    expect(invalid.status).toBe('not_evaluated');
    expect(invalid.errorCode).toBe('unsupported_schema');

    const missingVerdict = parseRiskGateResult({
      schema_version: 'risk-manager-result/v1',
      original_action: 'buy',
      final_action: 'buy',
    });
    expect(missingVerdict.status).toBe('not_evaluated');
    expect(missingVerdict.errorCode).toBe('missing_verdict');
  });
});

describe('ReportRiskGateBanner', () => {
  it('renders reject presentation prominently with reason codes', () => {
    render(
      <ReportRiskGateBanner
        presentation={parseRiskGateResult(rejectPayload)}
        language="zh"
      />,
    );

    const banner = screen.getByTestId('report-risk-gate-banner');
    expect(banner).toBeVisible();
    expect(banner).toHaveAttribute('data-risk-gate-status', 'reject');
    expect(banner).toHaveAttribute('data-risk-gate-reject', 'true');
    expect(screen.getByTestId('report-risk-gate-verdict')).toHaveTextContent('拒绝');
    expect(screen.getByText('最终风控裁决')).toBeVisible();
    expect(screen.getByTestId('report-risk-gate-reasons')).toHaveTextContent(
      'portfolio_exposure_limit',
    );
    // danger + urgent → role=alert
    expect(banner.querySelector('[role="alert"]')).not.toBeNull();
  });

  it('renders not evaluated when gate conclusion is missing', () => {
    render(
      <ReportRiskGateBanner
        presentation={parseRiskGateResult(undefined)}
        language="zh"
      />,
    );

    const banner = screen.getByTestId('report-risk-gate-banner');
    expect(banner).toHaveAttribute('data-risk-gate-status', 'not_evaluated');
    expect(banner).toHaveAttribute('data-risk-gate-not-evaluated', 'true');
    expect(screen.getByTestId('report-risk-gate-verdict')).toHaveTextContent('未评估');
    expect(screen.getByTestId('report-risk-gate-message')).toHaveTextContent('不能视为已通过');
    expect(screen.queryByText('通过')).not.toBeInTheDocument();
  });

  it('renders loading and error states', () => {
    const { rerender } = render(
      <ReportRiskGateBanner
        presentation={buildRiskGatePresentation({ loading: true })}
        language="en"
      />,
    );
    expect(screen.getByTestId('report-risk-gate-verdict')).toHaveTextContent('Loading');

    rerender(
      <ReportRiskGateBanner
        presentation={buildRiskGatePresentation({ error: true })}
        language="en"
      />,
    );
    expect(screen.getByTestId('report-risk-gate-verdict')).toHaveTextContent('Load failed');
  });
});

describe('ReportDecisionCard risk gate integration', () => {
  it('shows reject banner on the decision card when gate rejects', () => {
    render(
      <ReportDecisionCard
        meta={baseMeta}
        summary={{
          ...baseSummary,
          riskManager: {
            schemaVersion: 'risk-manager-result/v1',
            verdict: 'reject',
            originalAction: 'buy',
            finalAction: 'hold',
            reasonCodes: ['portfolio_exposure_limit'],
            evidenceCodes: ['portfolio_exposure'],
            profile: 'balanced',
          },
        }}
        details={{ rawResult: {} }}
      />,
    );

    expect(screen.getByTestId('report-decision-card')).toBeVisible();
    expect(screen.getByTestId('report-risk-gate-banner')).toHaveAttribute(
      'data-risk-gate-reject',
      'true',
    );
    expect(screen.getByTestId('report-risk-gate-verdict')).toHaveTextContent('拒绝');
  });

  it('shows 未评估 on the decision card when risk gate is missing (not 通过)', () => {
    render(
      <ReportDecisionCard
        meta={baseMeta}
        summary={baseSummary}
        details={{ rawResult: {} }}
      />,
    );

    const banner = screen.getByTestId('report-risk-gate-banner');
    expect(banner).toHaveAttribute('data-risk-gate-not-evaluated', 'true');
    expect(screen.getByTestId('report-risk-gate-verdict')).toHaveTextContent('未评估');
    // Verdict badge must not claim pass when unevaluated.
    expect(screen.getByTestId('report-risk-gate-verdict')).not.toHaveTextContent('通过');
  });
});
