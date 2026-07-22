/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { useEffect, useMemo, useState } from 'react';
import { Button } from '../../components/common';
import { DeepResearchPanel } from '../../components/chat/DeepResearchPanel';
import { DecisionSignalCreateDrawer } from '../../components/decision-signals/DecisionSignalCreateDrawer';
import {
  DecisionSignalCard,
  DecisionSignalDetails,
  PortfolioSignalSummary,
} from '../../components/decision-signals/DecisionSignalDisplay';
import { DecisionSignalOutcomeRunPanel } from '../../components/decision-signals/DecisionSignalOutcomeRunPanel';
import {
  EMPTY_MANUAL_SIGNAL_DRAFT,
  type ManualSignalDraft,
} from '../../components/decision-signals/manualSignalDraft';
import {
  DecisionSignalTimeline,
  TimelineTooltip,
} from '../../components/decision-signals/DecisionSignalTimeline';
import { AnalysisContextSummary } from '../../components/report/AnalysisContextSummary';
import { MarketReviewReportView } from '../../components/report/MarketReviewReportView';
import { MarketStructureCard } from '../../components/report/MarketStructureCard';
import { ReportDetails } from '../../components/report/ReportDetails';
import { ReportDiagnostics } from '../../components/report/ReportDiagnostics';
import { ReportMarkdown } from '../../components/report/ReportMarkdown';
import { ReportMarkdownBody } from '../../components/report/ReportMarkdownBody';
import { ReportMarkdownDrawer } from '../../components/report/ReportMarkdownDrawer';
import { ReportMarkdownPanel } from '../../components/report/ReportMarkdownPanel';
import { ReportNews } from '../../components/report/ReportNews';
import { ReportOverview } from '../../components/report/ReportOverview';
import { ReportStrategy } from '../../components/report/ReportStrategy';
import { ReportSummary } from '../../components/report/ReportSummary';
import { RunFlowEventList } from '../../components/run-flow/RunFlowEventList';
import { RunFlowGraph } from '../../components/run-flow/RunFlowGraph';
import { RunFlowNodeDetails } from '../../components/run-flow/RunFlowNodeDetails';
import { RunFlowPanel } from '../../components/run-flow/RunFlowPanel';
import { RunFlowSummaryBar } from '../../components/run-flow/RunFlowSummaryBar';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { PLAYGROUND_TEXT } from '../../locales/playground';
import type { DecisionSignalItem } from '../../types/decisionSignals';
import { buildTimelineData } from '../../utils/decisionSignalTimeline';
import {
  fixtureAnalysisContext,
  fixtureDecisionFeedback,
  fixtureDecisionOutcome,
  fixtureDecisionSignal,
  fixtureDecisionSignals,
  fixtureDiagnosticSummary,
  fixtureMarketReviewPayload,
  fixtureMarketReviewReport,
  fixtureMarketStructure,
  fixtureReport,
  fixtureRunFlowSnapshot,
} from '../fixtures';
import { usePlaygroundScenario } from '../scenarioContext';
import type { PlaygroundScenarioRenderer } from '../types';

const FIXTURE_RECORD_ID = 101;

const useSamples = () => {
  const { language } = useUiLanguage();
  return PLAYGROUND_TEXT[language].samples;
};

const DecisionSignalCardStory = () => {
  const { scenario } = usePlaygroundScenario();
  const [selected, setSelected] = useState(scenario === 'states');
  return (
    <div className="max-w-2xl">
      <DecisionSignalCard
        item={fixtureDecisionSignal}
        selected={selected}
        onSelect={scenario === 'interactive' ? () => setSelected((value) => !value) : undefined}
      />
    </div>
  );
};

const DecisionSignalDetailsStory = () => {
  const text = useSamples();
  const { scenario } = usePlaygroundScenario();
  const [feedback, setFeedback] = useState(scenario === 'empty' ? null : fixtureDecisionFeedback);
  return (
    <DecisionSignalDetails
      item={fixtureDecisionSignal}
      outcomes={scenario === 'empty' ? [] : [fixtureDecisionOutcome]}
      outcomesLoading={scenario === 'loading'}
      outcomesError={scenario === 'error' ? text.error : null}
      feedback={feedback}
      feedbackLoading={scenario === 'loading'}
      feedbackError={scenario === 'error' ? text.error : null}
      onFeedbackSubmit={(value) => setFeedback({ ...fixtureDecisionFeedback, feedbackValue: value })}
      actions={<Button variant="secondary">{text.secondaryAction}</Button>}
    />
  );
};

const PortfolioSignalSummaryStory = () => {
  const { scenario } = usePlaygroundScenario();
  return (
    <div className="flex min-h-32 items-center justify-end rounded-lg border border-border bg-card p-4">
      <PortfolioSignalSummary item={scenario === 'empty' ? undefined : fixtureDecisionSignal} loading={scenario === 'loading'} />
    </div>
  );
};

const TimelineTooltipStory = () => {
  const datum = buildTimelineData([fixtureDecisionSignal])[0];
  return (
    <div className="flex min-h-48 items-center justify-center">
      <TimelineTooltip active payload={[{ payload: datum }]} />
    </div>
  );
};

const DecisionSignalTimelineStory = () => {
  const text = useSamples();
  const { scenario } = usePlaygroundScenario();
  const [selected, setSelected] = useState<DecisionSignalItem | null>(fixtureDecisionSignals[0]);
  return (
    <DecisionSignalTimeline
      items={scenario === 'empty' ? [] : fixtureDecisionSignals}
      selectedId={selected?.id}
      loading={scenario === 'loading'}
      error={scenario === 'error' ? text.error : null}
      truncated={scenario === 'states'}
      onSelect={setSelected}
    />
  );
};

const DecisionSignalCreateDrawerStory = () => {
  const text = useSamples();
  const { scenario } = usePlaygroundScenario();
  const [open, setOpen] = useState(true);
  const [draft, setDraft] = useState<ManualSignalDraft>(() => ({
    ...EMPTY_MANUAL_SIGNAL_DRAFT,
    stockCode: '600519',
    stockName: 'Kweichow Moutai',
    market: 'cn',
    action: 'watch',
    confidence: scenario === 'states' ? '1.5' : '0.68',
    reason: 'Fixture signal created inside the isolated playground.',
  }));
  return (
    <>
      <Button variant="primary" onClick={() => setOpen(true)}>{text.primaryAction}</Button>
      <DecisionSignalCreateDrawer
        isOpen={open}
        onClose={() => setOpen(false)}
        draft={draft}
        onDraftChange={setDraft}
        onCreated={() => undefined}
      />
    </>
  );
};

const DecisionSignalOutcomeRunPanelStory = () => <DecisionSignalOutcomeRunPanel onCompleted={() => undefined} />;

const DeepResearchPanelStory = () => {
  const { scenario, profile } = usePlaygroundScenario();
  const text = useSamples();
  const [sessionId] = useState(() => {
    const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
    const id = `playground-${profile}-${scenario}-${suffix}`;
    if (scenario === 'error') {
      window.sessionStorage.setItem(`dsa_research_run:${id}`, JSON.stringify({
        question: text.preview,
        stockCode: '600519',
        status: 'error',
        error: text.fieldError,
      }));
    }
    return id;
  });

  useEffect(() => {
    return () => window.sessionStorage.removeItem(`dsa_research_run:${sessionId}`);
  }, [sessionId]);

  return <DeepResearchPanel sessionId={sessionId} />;
};

const AnalysisContextSummaryStory = () => {
  const { scenario } = usePlaygroundScenario();
  return <AnalysisContextSummary overview={scenario === 'empty' ? null : fixtureAnalysisContext} language="en" />;
};

const MarketReviewReportViewStory = () => {
  const { scenario } = usePlaygroundScenario();
  if (scenario === 'loading' || scenario === 'error') {
    return <MarketReviewReportView recordId={fixtureMarketReviewReport.meta.id} reportLanguage="en" />;
  }
  return (
    <MarketReviewReportView
      report={fixtureMarketReviewReport}
      payload={fixtureMarketReviewPayload}
      content={fixtureMarketReviewPayload.markdownReport}
      reportLanguage="en"
      onOpenRunFlow={() => undefined}
    />
  );
};

const MarketStructureCardStory = () => {
  const { scenario } = usePlaygroundScenario();
  return <MarketStructureCard context={scenario === 'empty' ? null : fixtureMarketStructure} language="en" />;
};

const ReportDetailsStory = () => {
  const { scenario } = usePlaygroundScenario();
  return <ReportDetails details={scenario === 'empty' ? undefined : fixtureReport.details} recordId={fixtureReport.meta.id} language="en" />;
};

const ReportDiagnosticsStory = () => {
  const text = useSamples();
  const { scenario } = usePlaygroundScenario();
  const summary = scenario === 'error'
    ? { ...fixtureDiagnosticSummary, status: 'failed' as const, statusLabel: text.error, reason: text.error }
    : scenario === 'loading'
      ? undefined
      : fixtureDiagnosticSummary;
  return <ReportDiagnostics recordId={fixtureReport.meta.id} summary={summary} language="en" onOpenRunFlow={() => undefined} />;
};

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

const ReportNewsStory = () => <ReportNews recordId={fixtureReport.meta.id} limit={8} language="en" />;

const ReportOverviewStory = () => {
  const { scenario } = usePlaygroundScenario();
  const [watchlisted, setWatchlisted] = useState(scenario === 'states');
  return (
    <ReportOverview
      meta={fixtureReport.meta}
      summary={fixtureReport.summary}
      details={fixtureReport.details}
      watchlist={{
        isInWatchlist: () => watchlisted,
        onToggle: () => setWatchlisted((value) => !value),
        isActioning: false,
        actionMessage: null,
      }}
    />
  );
};

const ReportStrategyStory = () => {
  const { scenario } = usePlaygroundScenario();
  return <ReportStrategy strategy={scenario === 'empty' ? undefined : fixtureReport.strategy} language="en" />;
};

const ReportSummaryStory = () => <ReportSummary data={fixtureReport} isHistory onOpenRunFlow={() => undefined} />;

const RunFlowEventListStory = () => {
  const { scenario } = usePlaygroundScenario();
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  return (
    <RunFlowEventList
      events={scenario === 'empty' ? [] : fixtureRunFlowSnapshot.events}
      selectedNodeId={selectedNodeId}
      onSelectNode={setSelectedNodeId}
    />
  );
};

const RunFlowGraphStory = () => {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(fixtureRunFlowSnapshot.nodes[0]?.id ?? null);
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(new Set());
  return (
    <RunFlowGraph
      lanes={fixtureRunFlowSnapshot.lanes}
      nodes={fixtureRunFlowSnapshot.nodes}
      edges={fixtureRunFlowSnapshot.edges}
      selectedNodeId={selectedNodeId}
      expandedNodeIds={expandedNodeIds}
      onSelectNode={(node) => setSelectedNodeId(node.id)}
      onToggleExpanded={(nodeId) => setExpandedNodeIds((current) => {
        const next = new Set(current);
        if (next.has(nodeId)) next.delete(nodeId); else next.add(nodeId);
        return next;
      })}
    />
  );
};

const RunFlowNodeDetailsStory = () => {
  const { scenario } = usePlaygroundScenario();
  const node = scenario === 'empty' ? null : fixtureRunFlowSnapshot.nodes[2];
  const [expanded, setExpanded] = useState(false);
  return (
    <RunFlowNodeDetails
      node={node}
      isExpanded={expanded}
      onToggleExpanded={() => setExpanded((value) => !value)}
      onClose={() => undefined}
    />
  );
};

const RunFlowPanelStory = () => {
  const { scenario } = usePlaygroundScenario();
  const source = useMemo(() => (
    scenario === 'empty' ? null : { type: 'history' as const, recordId: FIXTURE_RECORD_ID }
  ), [scenario]);
  return <RunFlowPanel source={source} />;
};

const RunFlowSummaryBarStory = () => <RunFlowSummaryBar snapshot={fixtureRunFlowSnapshot} />;

export const DECISION_REPORT_RUN_FLOW_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'decision-signal-card': DecisionSignalCardStory,
  'decision-signal-details': DecisionSignalDetailsStory,
  'portfolio-signal-summary': PortfolioSignalSummaryStory,
  'timeline-tooltip': TimelineTooltipStory,
  'decision-signal-timeline': DecisionSignalTimelineStory,
  'decision-signal-create-drawer': DecisionSignalCreateDrawerStory,
  'decision-signal-outcome-run-panel': DecisionSignalOutcomeRunPanelStory,
  'analysis-context-summary': AnalysisContextSummaryStory,
  'market-review-report-view': MarketReviewReportViewStory,
  'market-structure-card': MarketStructureCardStory,
  'report-details': ReportDetailsStory,
  'report-diagnostics': ReportDiagnosticsStory,
  'report-markdown': ReportMarkdownStory,
  'report-markdown-body': ReportMarkdownBodyStory,
  'report-markdown-drawer': ReportMarkdownDrawerStory,
  'report-markdown-panel': ReportMarkdownPanelStory,
  'report-news': ReportNewsStory,
  'report-overview': ReportOverviewStory,
  'report-strategy': ReportStrategyStory,
  'report-summary': ReportSummaryStory,
  'deep-research-panel': DeepResearchPanelStory,
  'run-flow-event-list': RunFlowEventListStory,
  'run-flow-graph': RunFlowGraphStory,
  'run-flow-node-details': RunFlowNodeDetailsStory,
  'run-flow-panel': RunFlowPanelStory,
  'run-flow-summary-bar': RunFlowSummaryBarStory,
};
