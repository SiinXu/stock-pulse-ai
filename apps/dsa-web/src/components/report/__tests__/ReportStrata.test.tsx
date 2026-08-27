// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReportStrata } from '../ReportStrata';
import {
  resolveReportStrataExpansionIdentity,
  resolveReportStrataFromDetails,
} from '../reportStrataUtils';
import type { ReportDetails } from '../../../types/analysis';
import { getReportText } from '../../../utils/reportLanguage';

const descendantCount = (element: HTMLElement): number => element.querySelectorAll('*').length;

const visibleDescendantCount = (element: HTMLElement): number =>
  [...element.querySelectorAll('*')].filter((node) => !node.closest('[hidden]')).length;

const expandStrata = () => {
  const toggle = screen.getByTestId('report-strata-toggle');
  fireEvent.click(toggle);
};

/**
 * jsdom does not synthesize a click from Enter/Space on a focused native
 * button. Real browsers do; shared Button / Collapsible rely on that activation.
 */
function activateDisclosureWithKey(toggle: HTMLElement, key: 'Enter' | ' ') {
  toggle.focus();
  expect(toggle).toHaveFocus();
  fireEvent.keyDown(toggle, { key });
  if (key === ' ') {
    fireEvent.keyUp(toggle, { key });
  }
  fireEvent.click(toggle);
}

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

const emptyStrataWithRawBlobs = {
  reportStrata: {
    schemaVersion: 'report-strata-v1',
    verifiedFacts: [],
    missingOrConflicts: [],
    modelInference: [],
    risksCounterEvidence: [],
  },
  rawResult: {
    technicalAnalysis: '价格位于主要均线上方。',
    volumeAnalysis: '成交量放大但缺少独立确认。',
    fundamentalAnalysis: '关键财务数据缺失。',
    analysisSummary: '等待量价确认。',
    riskWarning: '跌破支撑位时优先控制风险。',
  },
} satisfies ReportDetails;

describe('ReportStrata', () => {
  it('shows risks and disclaimer on first paint while secondary evidence stays collapsed', () => {
    const details: ReportDetails = { reportStrata: strataPayload };
    render(<ReportStrata details={details} language="en" />);

    const root = screen.getByTestId('report-strata');
    expect(root).toHaveAttribute('data-collapsed', 'true');
    expect(screen.getByTestId('report-strata-risks')).toBeVisible();
    expect(screen.getByTestId('report-strata-risks')).toHaveTextContent(
      'Break below support invalidates the constructive case.',
    );
    expect(screen.getByTestId('report-strata-disclaimer')).toBeVisible();
    expect(screen.getByTestId('report-strata-disclaimer')).toHaveTextContent(
      'Not investment advice',
    );
    expect(screen.queryByTestId('report-strata-facts')).not.toBeInTheDocument();
    expect(screen.queryByTestId('report-strata-gaps')).not.toBeInTheDocument();
    expect(screen.queryByTestId('report-strata-inference')).not.toBeInTheDocument();
    expect(screen.queryByTestId('report-strata-framework')).not.toBeInTheDocument();
    expect(screen.getByTestId('report-strata-secondary-before')).not.toBeVisible();
    expect(screen.getByTestId('report-strata-secondary-after')).not.toBeVisible();
    expect(screen.getByTestId('report-strata-secondary-before')).toHaveAttribute('inert');
    expect(screen.getByTestId('report-strata-secondary-after')).toHaveAttribute('inert');
    expect(screen.queryByText('ohlcv:daily')).not.toBeInTheDocument();
    expect(screen.queryByText('2026-07-25T15:00:00+08:00')).not.toBeInTheDocument();
    expect(screen.getByTestId('report-strata-toggle')).toHaveAttribute('aria-expanded', 'false');
  });

  it('keeps expanded product order facts → gaps → inference → risks → framework → disclaimer', () => {
    const details: ReportDetails = { reportStrata: strataPayload };
    render(<ReportStrata details={details} language="en" />);
    expandStrata();

    const root = screen.getByTestId('report-strata');
    expect(root).toHaveAttribute('data-collapsed', 'false');
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

    expect(facts.compareDocumentPosition(gaps) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(gaps.compareDocumentPosition(inference) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(inference.compareDocumentPosition(risks) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(risks.compareDocumentPosition(framework) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(framework.compareDocumentPosition(disclaimer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('hides source and asOf until the existing details annotation is opened', () => {
    const details: ReportDetails = { reportStrata: strataPayload };
    render(<ReportStrata details={details} language="en" />);
    expandStrata();

    const annotations = screen.getByTestId('report-strata-fact-annotations');
    const statement = screen.getByText(/Close was 1680/);
    expect(annotations).not.toHaveAttribute('open');
    expect(statement).not.toHaveTextContent('ohlcv:daily');
    expect(statement).not.toHaveTextContent('2026-07-25T15:00:00+08:00');
    expect(statement.closest('span')).not.toHaveTextContent('Source');

    fireEvent.click(within(annotations).getByText('View details'));
    expect(annotations).toHaveAttribute('open');
    expect(within(annotations).getByText(/Source: ohlcv:daily/)).toBeVisible();
    expect(within(annotations).getByText(/As of: 2026-07-25T15:00:00\+08:00/)).toBeVisible();
  });

  it('does not promote empty-list raw technical/volume/fundamental blobs into default facts or gaps', () => {
    render(<ReportStrata language="zh" details={emptyStrataWithRawBlobs} />);

    expect(screen.getByTestId('report-strata-risks')).toBeVisible();
    expect(screen.getByTestId('report-strata-risks')).toHaveTextContent('跌破支撑位');
    expect(screen.queryByTestId('report-strata-facts')).not.toBeInTheDocument();
    expect(screen.getByTestId('report-strata-secondary-after')).not.toBeVisible();
    expect(screen.queryByText('价格位于主要均线上方。')).not.toBeInTheDocument();
    expect(screen.queryByText('关键财务数据缺失。')).not.toBeInTheDocument();
    expect(screen.queryByText('等待量价确认。')).not.toBeInTheDocument();

    expandStrata();
    expect(screen.getByTestId('report-strata-facts')).toBeVisible();
    expect(screen.getByTestId('report-strata-facts')).not.toHaveTextContent('价格位于主要均线上方');
    expect(screen.getByTestId('report-strata-gaps')).not.toHaveTextContent('关键财务数据缺失');
    expect(screen.getByTestId('report-strata-inference')).not.toHaveTextContent('等待量价确认');

    const rawToggle = within(screen.getByTestId('report-strata-raw-fallback'))
      .getByRole('button', { name: '原始分析结果' });
    const rawPanelId = rawToggle.getAttribute('aria-controls');
    expect(rawPanelId).toBeTruthy();
    const rawPanel = document.getElementById(rawPanelId!);
    expect(rawToggle).toHaveAttribute('aria-expanded', 'false');
    expect(rawPanel).toHaveClass('grid-rows-[0fr]');
    fireEvent.click(rawToggle);
    expect(rawToggle).toHaveAttribute('aria-expanded', 'true');
    expect(rawPanel).toHaveClass('grid-rows-[1fr]');
    expect(screen.getByText('价格位于主要均线上方。')).toBeVisible();
    expect(screen.getByText('关键财务数据缺失。')).toBeVisible();
    expect(screen.getByText('等待量价确认。')).toBeVisible();
    expect(screen.getByTestId('report-strata-facts')).not.toHaveTextContent('价格位于主要均线上方');
    expect(screen.getByTestId('report-strata-gaps')).not.toHaveTextContent('关键财务数据缺失');
  });

  it('uses a shared Button disclosure with aria-expanded/aria-controls and no native button', () => {
    const details: ReportDetails = { reportStrata: strataPayload };
    render(<ReportStrata details={details} language="en" />);

    const toggle = screen.getByTestId('report-strata-toggle');
    expect(toggle.tagName).toBe('BUTTON');
    expect(toggle).toHaveAttribute('type', 'button');
    expect(toggle).toHaveAttribute('data-control', 'button');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    const controlledIds = (toggle.getAttribute('aria-controls') ?? '').split(/\s+/).filter(Boolean);
    expect(controlledIds).toHaveLength(2);
    const before = document.getElementById(controlledIds[0]);
    const after = document.getElementById(controlledIds[1]);
    expect(before).toBe(screen.getByTestId('report-strata-secondary-before'));
    expect(after).toBe(screen.getByTestId('report-strata-secondary-after'));
    expect(before).not.toBeVisible();
    expect(after).not.toBeVisible();

    activateDisclosureWithKey(toggle, 'Enter');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(before).toBeVisible();
    expect(after).toBeVisible();

    activateDisclosureWithKey(toggle, ' ');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(before).not.toBeVisible();

    const source = fs.readFileSync(
      path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../ReportStrata.tsx'),
      'utf8',
    );
    expect(source).not.toMatch(/<button\b/);
  });

  it('localizes first-paint and secondary disclosure copy in zh, en, and ko', () => {
    const details: ReportDetails = { reportStrata: strataPayload };

    const { unmount } = render(<ReportStrata details={details} language="zh" />);
    const zh = getReportText('zh');
    expect(screen.getByTestId('report-strata-toggle')).toHaveTextContent(zh.evidenceDetails);
    expect(screen.getByTestId('report-strata-risks')).toHaveTextContent(zh.risksCounterEvidence);
    expect(screen.getByTestId('report-strata-disclaimer')).toHaveTextContent(zh.disclaimerHeading);
    unmount();

    const { unmount: unmountEn } = render(<ReportStrata details={details} language="en" />);
    const en = getReportText('en');
    expect(screen.getByTestId('report-strata-toggle')).toHaveTextContent(en.evidenceDetails);
    expect(screen.getByTestId('report-strata-risks')).toHaveTextContent(en.risksCounterEvidence);
    expect(screen.getByTestId('report-strata-disclaimer')).toHaveTextContent(en.disclaimerHeading);
    expandStrata();
    expect(screen.getByTestId('report-strata-fact-annotations')).toHaveTextContent(en.details);
    unmountEn();

    render(<ReportStrata details={details} language="ko" />);
    const ko = getReportText('ko');
    expect(screen.getByTestId('report-strata-toggle')).toHaveTextContent(ko.evidenceDetails);
    expect(screen.getByTestId('report-strata-risks')).toHaveTextContent(ko.risksCounterEvidence);
    expect(screen.getByTestId('report-strata-disclaimer')).toHaveTextContent(ko.disclaimerHeading);
    expandStrata();
    expect(screen.getByTestId('report-strata-fact-annotations')).toHaveTextContent(ko.details);
    expect(screen.getByTestId('report-strata-toggle')).toHaveTextContent(ko.evidenceDetailsCollapse);
  });

  it('shows disclaimer for historical reports without strata', () => {
    render(
      <ReportStrata
        details={{
          rawResult: {
            analysis_summary: 'Historical payload without report strata.',
            risk_warning: '波动风险',
            technical_analysis: '价格位于主要均线上方。',
          },
        }}
        language="zh"
        alwaysShowDisclaimer
      />,
    );
    expect(screen.getByTestId('report-strata-disclaimer')).toHaveTextContent('不构成投资建议');
    expect(screen.queryByTestId('report-strata-facts')).not.toBeInTheDocument();
    expect(screen.queryByTestId('report-strata-toggle')).not.toBeInTheDocument();
    expect(screen.queryByTestId('report-strata-raw-fallback')).not.toBeInTheDocument();
    expect(screen.queryByTestId('report-strata-risks')).not.toBeInTheDocument();
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
    expect(screen.getByTestId('report-strata-risks')).toHaveTextContent('Break below support');
    expandStrata();
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
    expect(screen.getByTestId('report-strata-risks')).toBeVisible();
    expandStrata();
    expect(screen.getByTestId('report-strata-facts')).toHaveTextContent('Close was 1680');
    expect(screen.getByTestId('report-strata-inference')).toHaveTextContent('Momentum may improve');
    expect(screen.getByTestId('report-strata-disclaimer')).toHaveTextContent('Not investment advice');
  });

  it('drops default first-paint descendant count versus the expanded evidence wall', () => {
    const details: ReportDetails = {
      reportStrata: {
        ...strataPayload,
        verifiedFacts: Array.from({ length: 12 }, (_, index) => ({
          statement: `Verified fact ${index + 1} with enough text to render as its own list item.`,
          sourceId: `source:${index + 1}`,
          asOf: '2026-07-25T15:00:00+08:00',
        })),
        missingOrConflicts: Array.from({ length: 8 }, (_, index) => ({
          kind: index % 2 === 0 ? 'conflict' as const : 'missing' as const,
          description: `Gap or conflict ${index + 1}.`,
          sourceIds: [`src-a-${index}`, `src-b-${index}`],
        })),
        modelInference: Array.from({ length: 8 }, (_, index) => `Inference ${index + 1}.`),
      },
    };
    render(<ReportStrata details={details} language="en" />);

    const root = screen.getByTestId('report-strata');
    const collapsedTotal = descendantCount(root);
    const collapsedVisible = visibleDescendantCount(root);
    expect(screen.queryByTestId('report-strata-facts')).not.toBeInTheDocument();

    expandStrata();
    const expandedTotal = descendantCount(root);
    const expandedVisible = visibleDescendantCount(root);

    expect(screen.getByTestId('report-strata-facts')).toBeVisible();
    expect(collapsedTotal).toBeLessThan(expandedTotal);
    expect(collapsedVisible).toBeLessThan(expandedVisible);
    expect(collapsedTotal / expandedTotal).toBeLessThanOrEqual(0.5);
    expect(expandedTotal - collapsedTotal).toBeGreaterThanOrEqual(40);
  });

  it('does not leak expansion from one report identity into another', () => {
    const detailsA: ReportDetails = { reportStrata: strataPayload };
    const detailsB: ReportDetails = {
      reportStrata: {
        ...strataPayload,
        verifiedFacts: [{ statement: 'Other report close was 12.' }],
        risksCounterEvidence: ['Other report risk.'],
        disclaimer: 'Other report disclaimer.',
      },
    };
    const { rerender } = render(
      <ReportStrata details={detailsA} language="en" expansionKey="report-a" />,
    );
    expandStrata();
    expect(screen.getByTestId('report-strata')).toHaveAttribute('data-collapsed', 'false');
    expect(screen.getByTestId('report-strata-facts')).toBeVisible();

    rerender(<ReportStrata details={detailsB} language="en" expansionKey="report-b" />);
    expect(screen.getByTestId('report-strata')).toHaveAttribute('data-collapsed', 'true');
    expect(screen.getByTestId('report-strata-risks')).toHaveTextContent('Other report risk.');
    expect(screen.getByTestId('report-strata-disclaimer')).toHaveTextContent('Other report disclaimer.');
    expect(screen.queryByTestId('report-strata-facts')).not.toBeInTheDocument();
    expect(screen.queryByText('Close was 1680')).not.toBeInTheDocument();
  });

  it('keeps expansion when the same report identity re-renders', () => {
    const detailsA: ReportDetails = { reportStrata: strataPayload };
    const detailsARefresh: ReportDetails = {
      reportStrata: { ...strataPayload },
    };
    const { rerender } = render(
      <ReportStrata details={detailsA} language="en" expansionKey={42} />,
    );
    expandStrata();
    expect(screen.getByTestId('report-strata-facts')).toBeVisible();

    rerender(<ReportStrata details={detailsARefresh} language="en" expansionKey={42} />);
    expect(screen.getByTestId('report-strata')).toHaveAttribute('data-collapsed', 'false');
    expect(screen.getByTestId('report-strata-facts')).toBeVisible();
  });

  it('resets expansion from a strata fingerprint when expansionKey is omitted', () => {
    const { rerender } = render(
      <ReportStrata details={{ reportStrata: strataPayload }} language="en" />,
    );
    expandStrata();
    expect(screen.getByTestId('report-strata-facts')).toBeVisible();

    rerender(
      <ReportStrata
        details={{
          reportStrata: {
            ...strataPayload,
            disclaimer: 'Fingerprint-changing disclaimer.',
          },
        }}
        language="en"
      />,
    );
    expect(screen.getByTestId('report-strata')).toHaveAttribute('data-collapsed', 'true');
    expect(screen.queryByTestId('report-strata-facts')).not.toBeInTheDocument();
  });

  it('prefers an explicit expansionKey over the payload fingerprint', () => {
    expect(resolveReportStrataExpansionIdentity({ reportStrata: strataPayload }, 'rec-9')).toBe(
      'rec-9',
    );
    expect(resolveReportStrataExpansionIdentity({ reportStrata: strataPayload }, 12)).toBe('12');
    expect(resolveReportStrataExpansionIdentity({ reportStrata: strataPayload }, '  ')).toMatch(
      /^report-strata:/,
    );
    expect(resolveReportStrataExpansionIdentity({})).toBe('report-strata:none');
  });
});
