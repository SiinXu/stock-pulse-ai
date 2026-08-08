// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import type { ReportVersionCompareResponse } from '../../api/reportVersionCompare';
import { ReportVersionCompareView } from '../../components/report-version-compare';
import type { PlaygroundScenarioRenderer } from '../types';
import { usePlaygroundScenario } from '../scenarioContext';

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

const compareResult: ReportVersionCompareResponse = {
  status: 'engine_pending',
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
  ],
  delta: null,
  engineStatus: 'engine_pending',
};

const noBaselineResult: ReportVersionCompareResponse = {
  ...compareResult,
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
  engineStatus: 'ok',
};

function ReportVersionCompareScenario() {
  const scenario = usePlaygroundScenario();
  if (scenario === 'empty') {
    return <ReportVersionCompareView language="en" result={null} idle />;
  }
  if (scenario === 'states') {
    return <ReportVersionCompareView language="en" result={noBaselineResult} />;
  }
  return <ReportVersionCompareView language="en" result={compareResult} />;
}

export const REPORT_VERSION_COMPARE_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'report-version-compare-view': ReportVersionCompareScenario,
};
