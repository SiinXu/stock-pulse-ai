// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { ReportRiskGateBanner } from '../../components/report/ReportRiskGateBanner';
import { ReportDecisionCard } from '../../components/report/ReportDecisionCard';
import { ReportDetails } from '../../components/report/ReportDetails';
import { ReportDiagnostics } from '../../components/report/ReportDiagnostics';
import { parseRiskGateResult } from '../../components/report/reportRiskGateUtils';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { PLAYGROUND_TEXT } from '../../locales/playground';
import { fixtureDiagnosticSummary, fixtureReport } from '../fixtures';
import { usePlaygroundScenario } from '../scenarioContext';

const ReportDecisionCardStory = () => {
  const { scenario } = usePlaygroundScenario();
  return (
    <ReportDecisionCard
      meta={fixtureReport.meta}
      summary={scenario === 'empty'
        ? {
            analysisSummary: '',
            operationAdvice: '',
            trendPrediction: '',
            sentimentScore: Number.NaN,
          }
        : fixtureReport.summary}
      strategy={scenario === 'empty' ? undefined : fixtureReport.strategy}
      details={scenario === 'empty' ? undefined : fixtureReport.details}
      language="en"
    />
  );
};

const ReportRiskGateBannerStory = () => {
  const { scenario } = usePlaygroundScenario();
  const payload = scenario === 'empty'
    ? undefined
    : { schema_version: 'risk-manager-result/v1', verdict: 'reject' };
  return (
    <ReportRiskGateBanner
      presentation={parseRiskGateResult(payload)}
      language="en"
    />
  );
};

const ReportDetailsStory = () => {
  const { scenario } = usePlaygroundScenario();
  return (
    <ReportDetails
      details={scenario === 'empty' ? undefined : fixtureReport.details}
      recordId={fixtureReport.meta.id}
      language="en"
    />
  );
};

const ReportDiagnosticsStory = () => {
  const { language } = useUiLanguage();
  const { scenario } = usePlaygroundScenario();
  const error = PLAYGROUND_TEXT[language].samples.error;
  const summary = scenario === 'error'
    ? { ...fixtureDiagnosticSummary, status: 'failed' as const, statusLabel: error, reason: error }
    : scenario === 'loading'
      ? undefined
      : fixtureDiagnosticSummary;
  return (
    <ReportDiagnostics
      recordId={fixtureReport.meta.id}
      summary={summary}
      language="en"
      onOpenRunFlow={() => undefined}
    />
  );
};

export default [
  ReportDecisionCardStory,
  ReportRiskGateBannerStory,
  ReportDetailsStory,
  ReportDiagnosticsStory,
] as const;
