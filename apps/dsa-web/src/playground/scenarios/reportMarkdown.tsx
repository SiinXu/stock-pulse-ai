// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { ReportMarkdown } from '../../components/report/ReportMarkdown';
import { ReportMarkdownBody } from '../../components/report/ReportMarkdownBody';
import { ReportMarkdownDrawer } from '../../components/report/ReportMarkdownDrawer';
import { ReportMarkdownPanel } from '../../components/report/ReportMarkdownPanel';
import { fixtureMarketReviewPayload, fixtureReport } from '../fixtures';

const FIXTURE_RECORD_ID = 101;

const ReportMarkdownStory = () => (
  <ReportMarkdown
    recordId={FIXTURE_RECORD_ID}
    stockName={fixtureReport.meta.stockName || fixtureReport.meta.stockCode}
    stockCode={fixtureReport.meta.stockCode}
    reportLanguage="en"
    onClose={() => undefined}
  />
);

const ReportMarkdownBodyStory = () => (
  <div className="rounded-lg border border-border bg-card p-5">
    <ReportMarkdownBody content={fixtureMarketReviewPayload.markdownReport || ''} />
  </div>
);

const ReportMarkdownDrawerStory = () => (
  <ReportMarkdownDrawer
    recordId={FIXTURE_RECORD_ID}
    stockName={fixtureReport.meta.stockName || fixtureReport.meta.stockCode}
    stockCode={fixtureReport.meta.stockCode}
    reportLanguage="en"
    onClose={() => undefined}
  />
);

const ReportMarkdownPanelStory = () => (
  <ReportMarkdownPanel
    recordId={FIXTURE_RECORD_ID}
    stockName={fixtureReport.meta.stockName || fixtureReport.meta.stockCode}
    stockCode={fixtureReport.meta.stockCode}
    reportLanguage="en"
    onRequestClose={() => undefined}
  />
);

export default [
  ReportMarkdownStory,
  ReportMarkdownBodyStory,
  ReportMarkdownDrawerStory,
  ReportMarkdownPanelStory,
] as const;
