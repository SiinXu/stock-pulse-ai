import type React from 'react';
import type {
  ReportLanguage,
  ReportStructuredInsights as ReportStructuredInsightsType,
} from '../../types/analysis';
import { ReportStructuredInsights } from '../report/ReportStructuredInsights';
import { normalizeCommitteeDeliberation } from '../report/reportStructuredInsightsUtils';

interface DecisionSignalCommitteeInsightsProps {
  evidence: unknown;
  language: ReportLanguage;
}

const DecisionSignalCommitteeInsights: React.FC<DecisionSignalCommitteeInsightsProps> = ({
  evidence,
  language,
}) => {
  if (!evidence || typeof evidence !== 'object' || Array.isArray(evidence)) {
    return null;
  }
  const record = evidence as Record<string, unknown>;
  const deliberation = normalizeCommitteeDeliberation(
    record.committeeDeliberation ?? record.committee_deliberation,
  );
  if (!deliberation) {
    return null;
  }
  const insights: ReportStructuredInsightsType = {
    schemaVersion: 'report-structured-insights-v1',
    committeeDeliberation: deliberation,
  };
  return (
    <div data-testid="decision-signal-committee-deliberation">
      <ReportStructuredInsights insights={insights} language={language} />
    </div>
  );
};

export default DecisionSignalCommitteeInsights;
