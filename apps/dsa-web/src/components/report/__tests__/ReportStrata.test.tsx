import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReportStrata } from '../ReportStrata';
import { resolveReportStrataFromDetails } from '../reportStrataUtils';
import type { ReportDetails } from '../../../types/analysis';

const strataPayload = {
  schemaVersion: 'report-strata-v1',
  verifiedFacts: [
    {
      statement: 'Close was 1680 on the last daily bar.',
      sourceId: 'ohlcv:daily',
      asOf: '2026-07-25T15:00:00+08:00',
    },
  ],
  missingOrConflicts: [
    {
      kind: 'conflict' as const,
      description: 'Volume sources disagree.',
      sourceIds: ['a', 'b'],
    },
  ],
  modelInference: ['Momentum may improve if volume confirms.'],
  risksCounterEvidence: ['Break below support invalidates the constructive case.'],
  frameworkAlignment: {
    status: 'not_configured' as const,
    summary: 'Personal investment framework not configured or inactive',
  },
  disclaimer: 'AI-generated content for reference only. Not investment advice.',
};

describe('ReportStrata', () => {
  it('renders six strata sections in product order and keeps inference out of facts', () => {
    const details: ReportDetails = { reportStrata: strataPayload };
    render(<ReportStrata details={details} language="en" />);

    const root = screen.getByTestId('report-strata');
    const facts = screen.getByTestId('report-strata-facts');
    const gaps = screen.getByTestId('report-strata-gaps');
    const inference = screen.getByTestId('report-strata-inference');
    const risks = screen.getByTestId('report-strata-risks');
    const framework = screen.getByTestId('report-strata-framework');
    const disclaimer = screen.getByTestId('report-strata-disclaimer');

    expect(within(root).getByText('Evidence Strata')).toBeInTheDocument();
    expect(within(facts).getByText(/Close was 1680/)).toBeInTheDocument();
    expect(within(facts).queryByText(/Momentum may improve/)).not.toBeInTheDocument();
    expect(within(inference).getByText(/Momentum may improve/)).toBeInTheDocument();
    expect(within(gaps).getByText(/Volume sources disagree/)).toBeInTheDocument();
    expect(within(risks).getByText(/Break below support/)).toBeInTheDocument();
    expect(within(framework).getByText(/framework not configured/i)).toBeInTheDocument();
    expect(within(disclaimer).getByText(/Not investment advice/)).toBeInTheDocument();

    const order = [facts, gaps, inference, risks, framework, disclaimer].map(
      (node) => node.compareDocumentPosition.bind(node),
    );
    // facts before gaps before inference ...
    expect(facts.compareDocumentPosition(gaps) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(gaps.compareDocumentPosition(inference) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(inference.compareDocumentPosition(risks) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(risks.compareDocumentPosition(framework) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(framework.compareDocumentPosition(disclaimer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    void order;
  });

  it('shows disclaimer for historical reports without strata', () => {
    render(<ReportStrata details={{}} language="zh" alwaysShowDisclaimer />);
    expect(screen.getByTestId('report-strata-disclaimer')).toHaveTextContent('不构成投资建议');
    expect(screen.queryByTestId('report-strata-facts')).not.toBeInTheDocument();
  });

  it('uses existing report fields when the structured strata lists are empty', () => {
    render(
      <ReportStrata
        language="zh"
        details={{
          reportStrata: {
            schemaVersion: 'report-strata-v1',
            verifiedFacts: [],
            missingOrConflicts: [],
            modelInference: [],
            risksCounterEvidence: [],
          },
          rawResult: {
            technicalAnalysis: '价格位于主要均线上方。',
            fundamentalAnalysis: '关键财务数据缺失。',
            analysisSummary: '等待量价确认。',
            riskWarning: '跌破支撑位时优先控制风险。',
          },
        }}
      />,
    );

    expect(screen.getByTestId('report-strata-facts')).toHaveTextContent('价格位于主要均线上方');
    expect(screen.getByTestId('report-strata-gaps')).toHaveTextContent('关键财务数据缺失');
    expect(screen.getByTestId('report-strata-inference')).toHaveTextContent('等待量价确认');
    expect(screen.getByTestId('report-strata-risks')).toHaveTextContent('跌破支撑位');
  });

  it('resolves strata from rawResult.dashboard when projection is absent', () => {
    const details: ReportDetails = {
      rawResult: {
        dashboard: {
          report_strata: strataPayload,
        },
      },
    };
    const resolved = resolveReportStrataFromDetails(details);
    expect(resolved).toBeTruthy();
    render(<ReportStrata details={details} language="en" />);
    expect(screen.getByTestId('report-strata-facts')).toHaveTextContent('Close was 1680');
  });

  it('renders strata from snake_case rawResult.dashboard.report_strata body fields', () => {
    const details: ReportDetails = {
      rawResult: {
        dashboard: {
          report_strata: {
            schema_version: 'report-strata-v1',
            verified_facts: [
              {
                statement: 'Close was 1680 on the last daily bar.',
                source_id: 'ohlcv:daily',
                as_of: '2026-07-25T15:00:00+08:00',
              },
            ],
            missing_or_conflicts: [
              {
                kind: 'conflict',
                description: 'Volume sources disagree.',
                source_ids: ['a', 'b'],
              },
            ],
            model_inference: ['Momentum may improve if volume confirms.'],
            risks_counter_evidence: ['Break below support invalidates the constructive case.'],
            framework_alignment: {
              status: 'not_configured',
              summary: 'Personal investment framework not configured or inactive',
            },
            disclaimer: 'AI-generated content for reference only. Not investment advice.',
          },
        },
      },
    };
    render(<ReportStrata details={details} language="en" />);
    expect(screen.getByTestId('report-strata-facts')).toHaveTextContent('Close was 1680');
    expect(screen.getByTestId('report-strata-inference')).toHaveTextContent('Momentum may improve');
    expect(screen.getByTestId('report-strata-disclaimer')).toHaveTextContent('Not investment advice');
  });
});
