/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { useState } from 'react';
import { MiniSparkline } from '../../components/screening/MiniSparkline';
import { ScreenAlertMessage } from '../../components/screening/ScreenAlertMessage';
import { ScreeningConfigurationModal } from '../../components/screening/ScreeningConfigurationModal';
import { ScreeningHotspotsSection } from '../../components/screening/ScreeningHotspotsSection';
import { ScreeningResultsSection } from '../../components/screening/ScreeningResultsSection';
import { ScreeningRunStatusCard } from '../../components/screening/ScreeningRunStatusCard';
import { ScreeningStrategyBar } from '../../components/screening/ScreeningStrategyBar';
import { SCREENING_TEXT } from '../../locales/screening';
import type { PlaygroundScenarioRenderer } from '../types';
import { usePlaygroundScenario } from '../scenarioContext';

const text = SCREENING_TEXT.en;

const MiniSparklineStory = () => <MiniSparkline score={72} selected={false} />;

const ScreenAlertMessageStory = () => (
  <ScreenAlertMessage messages={['Snapshot source fallback was applied.', 'LLM ranking used local scores.']} />
);

const ScreeningConfigurationModalStory = () => {
  const { scenario } = usePlaygroundScenario();
  const [open, setOpen] = useState(scenario === 'interactive');
  return (
    <ScreeningConfigurationModal
      text={text}
      cancelLabel="Cancel"
      isOpen={open}
      onClose={() => setOpen(false)}
      formId="playground-screening-config"
      description={text.strategyDescription}
      loading={false}
      isScreeningEnabled
      configurationError=""
      market="cn"
      markets={[{ id: 'cn', label: text.marketCn }]}
      strategy="dual_low"
      maxResultsDraft="20"
      maxResultsError=""
      onSubmit={(event) => event.preventDefault()}
      onMarketChange={() => undefined}
      onStrategyChange={() => undefined}
      onMaxResultsChange={() => undefined}
    />
  );
};

const ScreeningHotspotsSectionStory = () => {
  const { scenario } = usePlaygroundScenario();
  const empty = scenario === 'empty';
  return (
    <ScreeningHotspotsSection
      text={text}
      language="en"
      isScreeningEnabled
      hotspots={empty ? [] : [{
        topic: 'ai-compute',
        name: 'AI Compute',
        rank: 1,
        heatScore: 92,
        changePct: 6.2,
        trendScore: 80,
        persistenceScore: 70,
        sampleStockCount: 8,
        leaders: ['Leader A', 'Leader B'],
      }]}
      hotspotsUpdatedAt={empty ? null : '2026-08-05T12:00:00Z'}
      hotspotsExpanded={!empty}
      selectedHotspotTopic={empty ? null : 'ai-compute'}
      hotspotDetail={empty ? null : {
        enabled: true,
        provider: 'akshare',
        topic: 'ai-compute',
        name: 'AI Compute',
        summary: 'Theme summary for playground preview.',
        route: [{ title: 'Catalyst', description: 'Preview route item', publishedAt: '2026-08-05' }],
        stocks: [{ code: '000001', name: 'Demo Stock', changePct: 2.1, hotStockScore: 88 }],
        stockCount: 1,
      }}
      loadingHotspots={false}
      loadingHotspotDetail={false}
      hotspotError=""
      hotspotDetailError=""
      onToggleExpanded={() => undefined}
      onRefresh={() => undefined}
      onSelectHotspot={() => undefined}
      onAnalyzeStock={() => undefined}
    />
  );
};

const ScreeningResultsSectionStory = () => {
  const { scenario } = usePlaygroundScenario();
  const empty = scenario === 'empty';
  return (
    <ScreeningResultsSection
      text={text}
      language="en"
      candidates={empty ? [] : [{
        rank: 1,
        code: '600519',
        name: 'Demo Stock',
        industry: 'Consumer',
        price: 1600,
        changePct: 1.2,
        score: 88.5,
        llmScore: 0.82,
        riskLevel: 'low',
        reason: 'Playground candidate summary.',
        raw: {},
      }]}
      expandedCode={empty ? null : '600519'}
      llmDegraded={false}
      onExpandedCodeChange={() => undefined}
    />
  );
};

const ScreeningRunStatusCardStory = () => {
  const { scenario } = usePlaygroundScenario();
  const loading = scenario === 'loading';
  return (
    <ScreeningRunStatusCard
      text={text}
      loading={loading}
      isScreeningEnabled
      statusTitle={loading ? text.running : text.completed}
      candidatesCount={loading ? 0 : 3}
      taskMessage={loading ? text.runningTask : ''}
      taskProgress={loading ? 42 : 100}
      displayedStrategy="Dual Low"
      marketLabel={text.marketCn}
      activeTaskId={loading ? 'task-demo-123' : null}
      screenMeta={loading ? null : {
        enabled: true,
        runId: 'run-demo',
        candidates: [],
        snapshotCount: 100,
        afterFilterCount: 20,
        candidateCount: 3,
        llmRanked: true,
        llmCoverage: 0.9,
        dsaEnrichment: { enrichedCount: 3, requestedCount: 3 },
      }}
      showingLastGood={false}
    />
  );
};

const ScreeningStrategyBarStory = () => (
  <ScreeningStrategyBar
    text={text}
    strategy="dual_low"
    strategyOptions={[{ value: 'dual_low', label: 'Dual Low' }]}
    selectedStrategyTag="quality"
    strategyDescription={text.strategyDescription}
    strategyLoadError=""
    loading={false}
    loadingStrategies={false}
    onStrategyChange={() => undefined}
    onOpenConfiguration={() => undefined}
  />
);

export const SCREENING_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'mini-sparkline': MiniSparklineStory,
  'screen-alert-message': ScreenAlertMessageStory,
  'screening-configuration-modal': ScreeningConfigurationModalStory,
  'screening-hotspots-section': ScreeningHotspotsSectionStory,
  'screening-results-section': ScreeningResultsSectionStory,
  'screening-run-status-card': ScreeningRunStatusCardStory,
  'screening-strategy-bar': ScreeningStrategyBarStory,
};
