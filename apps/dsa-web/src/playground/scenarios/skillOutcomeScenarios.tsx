// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { PlaygroundScenarioRenderer } from '../types';
import {
  SkillOutcomePerformanceTable,
  SkillOutcomeRecentLists,
  SkillOutcomeRunPanel,
} from '../../components/skill-outcomes';
import type {
  SkillOutcomeItem,
  SkillOutcomePerformanceBucket,
  SkillOutcomeSampleItem,
} from '../../api/skillOutcomes';
import { usePlaygroundScenario } from '../scenarioContext';

const insufficientBucket: SkillOutcomePerformanceBucket = {
  skillId: 'momentum',
  horizon: '5d',
  engineVersion: 'skill-opinion-outcome-v1',
  total: 12,
  pending: 2,
  evaluated: 8,
  observational: 1,
  unable: 1,
  hit: 5,
  miss: 3,
  sampleSufficient: false,
  sampleStatus: 'insufficient',
  hitRatePct: null,
  missRatePct: null,
  avgDirectionalReturnPct: null,
  unableRatePct: null,
};

const sufficientBucket: SkillOutcomePerformanceBucket = {
  skillId: 'value',
  horizon: '10d',
  engineVersion: 'skill-opinion-outcome-v1',
  total: 40,
  pending: 2,
  evaluated: 32,
  observational: 3,
  unable: 3,
  hit: 20,
  miss: 12,
  sampleSufficient: true,
  sampleStatus: 'sufficient',
  hitRatePct: 62.5,
  missRatePct: 37.5,
  avgDirectionalReturnPct: 1.25,
  unableRatePct: 7.9,
};

const sampleOutcome: SkillOutcomeItem = {
  id: 1,
  skillOpinionSampleId: 9,
  analysisHistoryId: 100,
  stockCode: 'AAPL',
  skillId: 'momentum',
  signal: 'buy',
  horizon: '5d',
  engineVersion: 'skill-opinion-outcome-v1',
  evalStatus: 'pending',
  outcome: null,
  directionCorrect: null,
  unableReason: null,
  analysisDate: '2026-08-01',
  startTradeDate: null,
  endTradeDate: null,
  startPrice: null,
  endClose: null,
  stockReturnPct: null,
  directionalReturnPct: null,
  createdAt: null,
  updatedAt: null,
};

const sampleRow: SkillOutcomeSampleItem = {
  id: 9,
  analysisHistoryId: 100,
  stockCode: 'AAPL',
  skillId: 'momentum',
  skillVersion: '1',
  signal: 'buy',
  confidence: 0.82,
  horizon: '5d',
  dataQualityLevel: null,
  opinionCreatedAt: null,
  sampleSchemaVersion: 'v1',
  createdAt: null,
};

const SkillOutcomePerformanceTableStory = () => {
  const { scenario } = usePlaygroundScenario();
  return (
    <SkillOutcomePerformanceTable
      buckets={scenario === 'empty' ? [] : [insufficientBucket, sufficientBucket]}
    />
  );
};

const SkillOutcomeRecentListsStory = () => {
  const { scenario } = usePlaygroundScenario();
  return (
    <SkillOutcomeRecentLists
      outcomes={scenario === 'empty' ? [] : [sampleOutcome]}
      samples={scenario === 'empty' ? [] : [sampleRow]}
    />
  );
};

const SkillOutcomeRunPanelStory = () => (
  <SkillOutcomeRunPanel onCompleted={() => undefined} />
);

export const SKILL_OUTCOME_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'skill-outcome-performance-table': SkillOutcomePerformanceTableStory,
  'skill-outcome-recent-lists': SkillOutcomeRecentListsStory,
  'skill-outcome-run-panel': SkillOutcomeRunPanelStory,
};
