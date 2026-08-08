/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '../../components/common';
import { ChatComposer } from '../../components/chat/ChatComposer';
import { ChatMessageList } from '../../components/chat/ChatMessageList'
import { WhatIfScenarioPanel } from '../../components/chat/WhatIfScenarioPanel'
import { DEFAULT_WHAT_IF_DRAFT } from '../../components/chat/whatIfScenario';
import { ChatSessionSidebar } from '../../components/chat/ChatSessionSidebar';
import {
  ChatThinkingDetails,
  ChatThinkingToggle,
} from '../../components/chat/ChatThinkingDetails';
import { DeepResearchPanel } from '../../components/chat/DeepResearchPanel';
import type { ChatSessionItem, SkillInfo } from '../../api/agent';
import { createParsedApiError } from '../../api/error';
import type { Message, ProgressStep } from '../../stores/agentChatStore';
import { DecisionSignalCreateDrawer } from '../../components/decision-signals/DecisionSignalCreateDrawer';
import {
  DecisionSignalCard,
  DecisionSignalDetails,
  DecisionSignalOutcomeBadge,
  PortfolioSignalSummary,
} from '../../components/decision-signals/DecisionSignalDisplay';
import { DecisionSignalMemoryControls } from '../../components/decision-signals/DecisionSignalMemoryControls';
import { DecisionSignalOutcomeExplorer } from '../../components/decision-signals/DecisionSignalOutcomeExplorer';
import { DecisionSignalOutcomeRunPanel } from '../../components/decision-signals/DecisionSignalOutcomeRunPanel';
import { DecisionSignalOutcomeStatsCard } from '../../components/decision-signals/DecisionSignalOutcomeStatsCard';
import { DecisionSignalProfileCalibration } from '../../components/decision-signals/DecisionSignalProfileCalibration';
import type {
  DecisionSignalOutcomeStatsResponse,
  DecisionSignalProfileCalibration as DecisionSignalProfileCalibrationData,
} from '../../types/decisionSignals';
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
import { ReportStrata } from '../../components/report/ReportStrata';
import { ReportStrategy } from '../../components/report/ReportStrategy';
import { ReportStructuredInsights } from '../../components/report/ReportStructuredInsights';
import { ReportSummary } from '../../components/report/ReportSummary';
import { ShareImageButton } from '../../components/report/ShareImageButton';
import { MarketReviewRegionSelector } from '../../components/market-review/MarketReviewRegionSelector';
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

const DecisionSignalMemoryControlsStory = () => (
  <DecisionSignalMemoryControls signalId={fixtureDecisionSignal.id} />
);

const DecisionSignalOutcomeBadgeStory = () => {
  const { scenario } = usePlaygroundScenario();
  const variants = scenario === 'variants'
    ? [
        fixtureDecisionOutcome,
        { ...fixtureDecisionOutcome, id: 402, outcome: 'miss' as const },
        { ...fixtureDecisionOutcome, id: 403, outcome: 'neutral' as const },
        {
          ...fixtureDecisionOutcome,
          id: 404,
          evalStatus: 'unable' as const,
          outcome: null,
        },
      ]
    : [fixtureDecisionOutcome];
  return (
    <div className="flex flex-wrap gap-2">
      {variants.map((item) => <DecisionSignalOutcomeBadge key={item.id} item={item} />)}
    </div>
  );
};

const DecisionSignalOutcomeExplorerStory = () => (
  <DecisionSignalOutcomeExplorer onOpenSignal={() => undefined} />
);

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

const fixtureProfileCalibration: DecisionSignalProfileCalibrationData = {
  minimumCompletedSampleSize: 30,
  breakdowns: {
    decisionProfile: [
      {
        dimensions: { decisionProfile: 'balanced' },
        total: 36,
        completed: 36,
        unable: 0,
        hit: 20,
        miss: 12,
        neutral: 4,
        sampleSufficient: true,
        hitRatePct: 62.5,
        avgStockReturnPct: 1.2,
        missRatePct: 37.5,
        unableRatePct: 0,
        maxAdverseExcursionPct: 4.5,
      },
      {
        dimensions: { decisionProfile: 'conservative' },
        total: 12,
        completed: 12,
        unable: 0,
        hit: 6,
        miss: 6,
        neutral: 0,
        sampleSufficient: false,
        hitRatePct: null,
        avgStockReturnPct: null,
        missRatePct: null,
        unableRatePct: null,
        maxAdverseExcursionPct: null,
      },
    ],
    decisionProfileAction: [],
    decisionProfileHorizon: [
      {
        dimensions: { decisionProfile: 'balanced', horizon: '3d' },
        total: 30,
        completed: 30,
        unable: 0,
        hit: 18,
        miss: 12,
        neutral: 0,
        sampleSufficient: true,
        hitRatePct: 60,
        avgStockReturnPct: 0.8,
        missRatePct: 40,
        unableRatePct: 0,
        maxAdverseExcursionPct: 3.1,
      },
    ],
    decisionProfileMarketPhase: [],
    decisionProfileDataQualityLevel: [],
    profileSource: [],
  },
};

const fixtureOutcomeStats: DecisionSignalOutcomeStatsResponse = {
  engineVersion: 'decision-signal-v1',
  statuses: ['active'],
  total: 48,
  completed: 48,
  unable: 0,
  hit: 26,
  miss: 18,
  neutral: 4,
  hitRatePct: 59.09,
  avgStockReturnPct: 0.9,
  unableReasons: {},
  breakdowns: {},
  profileCalibration: fixtureProfileCalibration,
};

const DecisionSignalOutcomeStatsCardStory = () => {
  const { scenario } = usePlaygroundScenario();
  if (scenario === 'loading') {
    return (
      <DecisionSignalOutcomeStatsCard
        outcomeStats={null}
        statsLoading
        statsError={null}
        onRetryStats={() => undefined}
        onRunCompleted={() => undefined}
      />
    );
  }
  if (scenario === 'empty') {
    return (
      <DecisionSignalOutcomeStatsCard
        outcomeStats={{ ...fixtureOutcomeStats, total: 0, completed: 0, hit: 0, miss: 0, neutral: 0, profileCalibration: undefined }}
        statsLoading={false}
        statsError={null}
        onRetryStats={() => undefined}
        onRunCompleted={() => undefined}
      />
    );
  }
  return (
    <DecisionSignalOutcomeStatsCard
      outcomeStats={fixtureOutcomeStats}
      statsLoading={false}
      statsError={null}
      onRetryStats={() => undefined}
      onRunCompleted={() => undefined}
    />
  );
};

const DecisionSignalProfileCalibrationStory = () => {
  const { scenario } = usePlaygroundScenario();
  if (scenario === 'states') {
    return (
      <DecisionSignalProfileCalibration
        calibration={{
          ...fixtureProfileCalibration,
          breakdowns: {
            ...fixtureProfileCalibration.breakdowns,
            decisionProfile: fixtureProfileCalibration.breakdowns.decisionProfile.map((bucket) => ({
              ...bucket,
              sampleSufficient: false,
              hitRatePct: null,
              avgStockReturnPct: null,
              missRatePct: null,
              unableRatePct: null,
              maxAdverseExcursionPct: null,
            })),
          },
        }}
      />
    );
  }
  return <DecisionSignalProfileCalibration calibration={fixtureProfileCalibration} />;
};

const FIXTURE_SKILLS: SkillInfo[] = [
  { id: 'skill-a', name: 'Fixture Skill A', description: 'Playground skill A' },
  { id: 'skill-b', name: 'Fixture Skill B', description: 'Playground skill B' },
];

const FIXTURE_SESSIONS: ChatSessionItem[] = [
  {
    session_id: 'session-1',
    title: 'Fixture session one',
    message_count: 4,
    created_at: '2026-07-20T10:00:00Z',
    last_active: '2026-07-20T11:00:00Z',
  },
  {
    session_id: 'session-2',
    title: 'Fixture session two',
    message_count: 1,
    created_at: '2026-07-19T09:00:00Z',
    last_active: '2026-07-19T09:30:00Z',
  },
];

const FIXTURE_CHAT_MESSAGES: Message[] = [
  { id: 'msg-user-1', role: 'user', content: 'Summarize 600519 risk factors.' },
  {
    id: 'msg-assistant-1',
    role: 'assistant',
    content: 'Fixture assistant reply with a short risk summary.',
    thinkingSteps: [
      { type: 'thinking', step: 1, message: 'Gathering report context' },
      { type: 'tool_done', tool: 'lookup', display_name: 'Lookup', duration: 0.4, success: true },
    ],
  },
];

const FIXTURE_PROGRESS_STEPS: ProgressStep[] = [
  { type: 'thinking', step: 1, message: 'Planning next action' },
  { type: 'tool_start', tool: 'search', display_name: 'Search' },
  { type: 'tool_done', tool: 'search', display_name: 'Search', duration: 1.2, success: true },
];

const useChatTranslate = () => {
  const { t } = useUiLanguage();
  return t;
};

const ChatComposerStory = () => {
  const { scenario } = usePlaygroundScenario();
  const t = useChatTranslate();
  const { language } = useUiLanguage();
  const samples = useSamples();
  const skillPickerRef = useRef<HTMLDivElement | null>(null);
  const [input, setInput] = useState(scenario === 'error' ? '' : samples.preview);
  const selectedSkillIds = scenario === 'empty' ? [] : [FIXTURE_SKILLS[0].id];
  return (
    <div className="max-w-3xl rounded-xl border border-border bg-card">
      <ChatComposer
        language={language}
        t={t}
        sessionError={scenario === 'error' ? createParsedApiError({ title: samples.fieldError, message: samples.fieldError, status: 500, code: 'fixture' }) : null}
        sessionLoading={scenario === 'loading'}
        chatError={null}
        lastFailedRequest={null}
        onRetryLastStream={() => undefined}
        isFollowUpContextLoading={false}
        contextCompressionEnabled={false}
        contextCompressionLoaded
        contextCompressionSaving={false}
        contextCompressionError={null}
        onContextCompressionChange={() => undefined}
        skills={FIXTURE_SKILLS}
        selectedSkillIds={selectedSkillIds}
        selectedSkillIdSet={new Set(selectedSkillIds)}
        skillLimitReached={false}
        selectedSkillSummary={selectedSkillIds.length ? FIXTURE_SKILLS[0].name : samples.preview}
        mobileSkillPickerOpen={false}
        onMobileSkillPickerOpenChange={() => undefined}
        skillPickerRef={skillPickerRef}
        showSkillDesc={null}
        onShowSkillDesc={() => undefined}
        onToggleSkill={() => undefined}
        onClearSkills={() => undefined}
        activeStockCode="600519"
        stockInWatchlist={false}
        isWatchlistActioning={false}
        watchlistMessage={null}
        onToggleWatchlist={() => undefined}
        input={input}
        onInputChange={setInput}
        onKeyDown={() => undefined}
        loading={scenario === 'loading'}
        isSkillsLoading={false}
        onStop={() => undefined}
        onSend={() => undefined}
      />
    </div>
  );
};

const ChatMessageListStory = () => {
  const { scenario } = usePlaygroundScenario();
  const t = useChatTranslate();
  const { language } = useUiLanguage();
  const samples = useSamples();
  const messagesViewportRef = useRef<HTMLDivElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const messages = scenario === 'empty' ? [] : FIXTURE_CHAT_MESSAGES;
  const [expandedThinking, setExpandedThinking] = useState(() => new Set(['msg-assistant-1']));
  return (
    <div className="flex h-[28rem] max-w-3xl flex-col rounded-xl border border-border bg-card">
      <ChatMessageList
        language={language}
        t={t}
        text={{ copied: samples.preview, copy: samples.secondaryAction }}
        messages={messages}
        loading={scenario === 'loading'}
        progressSteps={scenario === 'loading' ? FIXTURE_PROGRESS_STEPS : []}
        agentUnavailable={false}
        quickQuestions={[{ label: samples.primaryAction, skill: 'skill-a' }]}
        onQuickQuestion={() => undefined}
        quickQuestionsDisabled={false}
        expandedThinking={expandedThinking}
        onToggleThinking={(messageId) => {
          setExpandedThinking((current) => {
            const next = new Set(current);
            if (next.has(messageId)) next.delete(messageId);
            else next.add(messageId);
            return next;
          });
        }}
        copiedMessages={new Set()}
        onCopyMessage={() => undefined}
        onDownloadMessage={() => undefined}
        messagesViewportRef={messagesViewportRef}
        messagesEndRef={messagesEndRef}
        onScroll={() => undefined}
      />
    </div>
  );
};

const ChatSessionSidebarStory = () => {
  const { scenario } = usePlaygroundScenario();
  const t = useChatTranslate();
  const { language } = useUiLanguage();
  const samples = useSamples();
  const [search, setSearch] = useState('');
  const sessions = scenario === 'empty' ? [] : FIXTURE_SESSIONS;
  return (
    <div className="flex h-[28rem] w-80 flex-col overflow-hidden rounded-xl border border-border bg-card">
      <ChatSessionSidebar
        language={language}
        t={t}
        sessionSearch={search}
        onSessionSearchChange={setSearch}
        sessions={sessions}
        filteredSessions={sessions}
        sessionsLoading={scenario === 'loading'}
        sessionsError={scenario === 'error' ? createParsedApiError({ title: samples.fieldError, message: samples.fieldError, status: 500, code: 'fixture' }) : null}
        sessionLoading={false}
        sessionId={sessions[0]?.session_id ?? ''}
        onNewChat={() => undefined}
        onRetryLoadSessions={() => undefined}
        onSwitchSession={() => undefined}
        onRequestDelete={() => undefined}
      />
    </div>
  );
};

const ChatThinkingDetailsStory = () => {
  const t = useChatTranslate();
  return (
    <div className="max-w-xl rounded-xl border border-border bg-card p-4">
      <ChatThinkingDetails steps={FIXTURE_PROGRESS_STEPS} t={t} />
    </div>
  );
};

const ChatThinkingToggleStory = () => {
  const samples = useSamples();
  const [expanded, setExpanded] = useState(true);
  return (
    <div className="max-w-xl rounded-xl border border-border bg-card p-4">
      <ChatThinkingToggle
        isExpanded={expanded}
        summary={samples.preview}
        onToggle={() => setExpanded((value) => !value)}
        thinkingProcessLabel={samples.details}
      />
      {expanded ? <p className="mt-2 text-sm text-secondary-text">{samples.preview}</p> : null}
    </div>
  );
};

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

const ReportStrataStory = () => {
  const { scenario } = usePlaygroundScenario();
  if (scenario === 'empty') {
    return <ReportStrata details={{}} language="en" alwaysShowDisclaimer />;
  }
  return (
    <ReportStrata
      details={{
        reportStrata: {
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
              kind: 'conflict',
              description: 'Volume sources disagree.',
              sourceIds: ['a', 'b'],
            },
          ],
          modelInference: ['Momentum may improve if volume confirms.'],
          risksCounterEvidence: ['Break below support invalidates the constructive case.'],
          frameworkAlignment: {
            status: 'not_configured',
            summary: 'Personal investment framework not configured or inactive',
          },
          disclaimer: 'AI-generated content for reference only. Not investment advice.',
        },
      }}
      language="en"
    />
  );
};

const ReportStructuredInsightsStory = () => {
  const { scenario } = usePlaygroundScenario();
  return (
    <ReportStructuredInsights
      insights={scenario === 'empty' ? undefined : fixtureReport.details?.structuredInsights}
      language="en"
    />
  );
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


const ShareImageButtonStory = () => (
  <div className="flex justify-end p-4">
    <ShareImageButton recordId={FIXTURE_RECORD_ID} reportTitle="Playground report" reportLanguage="en" />
  </div>
);

const MarketReviewRegionSelectorStory = () => {
  const [regions, setRegions] = useState<Array<'cn' | 'hk' | 'us' | 'jp' | 'kr'> | undefined>(undefined);
  return (
    <div className="flex justify-end p-4">
      <MarketReviewRegionSelector value={regions} onChange={setRegions} />
    </div>
  );
};

export const DECISION_REPORT_RUN_FLOW_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'decision-signal-card': DecisionSignalCardStory,
  'decision-signal-details': DecisionSignalDetailsStory,
  'decision-signal-memory-controls': DecisionSignalMemoryControlsStory,
  'decision-signal-outcome-badge': DecisionSignalOutcomeBadgeStory,
  'decision-signal-outcome-explorer': DecisionSignalOutcomeExplorerStory,
  'portfolio-signal-summary': PortfolioSignalSummaryStory,
  'timeline-tooltip': TimelineTooltipStory,
  'decision-signal-timeline': DecisionSignalTimelineStory,
  'decision-signal-create-drawer': DecisionSignalCreateDrawerStory,
  'decision-signal-outcome-run-panel': DecisionSignalOutcomeRunPanelStory,
  'decision-signal-outcome-stats-card': DecisionSignalOutcomeStatsCardStory,
  'decision-signal-profile-calibration': DecisionSignalProfileCalibrationStory,
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
  'share-image-button': ShareImageButtonStory,
  'market-review-region-selector': MarketReviewRegionSelectorStory,
  'report-strata': ReportStrataStory,
  'report-strategy': ReportStrategyStory,
  'report-structured-insights': ReportStructuredInsightsStory,
  'report-summary': ReportSummaryStory,
  'deep-research-panel': DeepResearchPanelStory,
  'chat-composer': ChatComposerStory,

function WhatIfScenarioPanelStory({ scenarioId }: { scenarioId: string }) {
  const t = (key: string) => key;
  const enabled = scenarioId !== 'default';
  const draft = {
    ...DEFAULT_WHAT_IF_DRAFT,
    enabled,
    turnCount: scenarioId === 'limit' ? 5 : 1,
  };
  return (
    <div className="max-w-3xl rounded-lg border border-subtle bg-card p-2">
      <WhatIfScenarioPanel t={t as never} draft={draft} onChange={() => undefined} />
    </div>
  );
}

  'chat-message-list': ChatMessageListStory,
  'what-if-scenario-panel': WhatIfScenarioPanelStory,
  'chat-session-sidebar': ChatSessionSidebarStory,
  'chat-thinking-details': ChatThinkingDetailsStory,
  'chat-thinking-toggle': ChatThinkingToggleStory,
  'run-flow-event-list': RunFlowEventListStory,
  'run-flow-graph': RunFlowGraphStory,
  'run-flow-node-details': RunFlowNodeDetailsStory,
  'run-flow-panel': RunFlowPanelStory,
  'run-flow-summary-bar': RunFlowSummaryBarStory,
};
