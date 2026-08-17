/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { FieldTrustPanel } from '../../components/stocks/FieldTrustPanel';
import { createParsedApiError } from '../../api/error';
import type { StockFieldTrustResponse } from '../../types/stocks';
import { usePlaygroundScenario } from '../scenarioContext';
import type { PlaygroundScenarioRenderer } from '../types';

const DEGRADED_VIEW: StockFieldTrustResponse = {
  schemaVersion: 'field_trust_view/1.0',
  stockCode: '600519',
  status: 'degraded',
  metadataPresent: true,
  quoteSource: 'efinance',
  staleSeconds: 7200,
  isStale: true,
  missingFields: [],
  fields: [
    {
      field: 'price',
      value: 1688,
      source: 'efinance',
      origin: 'primary',
      staleness: 'stale',
      isStale: true,
      staleSeconds: 7200,
      conflict: true,
    },
  ],
  conflicts: [
    {
      field: 'price',
      severity: 'warn',
      relativeDifference: 0.24,
      threshold: 0.05,
      values: [
        { provider: 'efinance', value: 1688 },
        { provider: 'akshare_em', value: 2100 },
      ],
    },
  ],
  conflictChecks: [
    {
      primaryProvider: 'efinance',
      secondaryProvider: 'akshare_em',
      status: 'evaluated',
    },
  ],
  providerHealth: [
    { provider: 'efinance', status: 'ok', role: 'primary' },
    { provider: 'akshare_em', status: 'failed', role: 'attempted' },
  ],
  analysisInput: {
    schemaVersion: 'field_trust_analysis_input/1.0',
    confidence: 'low',
    gaps: [
      { code: 'stale', field: 'price', detail: 'provider timestamp exceeded the realtime TTL' },
      { code: 'conflict', field: 'price', detail: 'providers disagreed; no source was chosen as truth' },
      { code: 'provider_failed', field: null, detail: 'akshare_em:failed' },
    ],
    conflictCount: 1,
    failedProviderCount: 1,
  },
};

const UNAVAILABLE_VIEW: StockFieldTrustResponse = {
  schemaVersion: 'field_trust_view/1.0',
  stockCode: '600519',
  status: 'unavailable',
  metadataPresent: false,
  missingFields: [],
  fields: [],
  conflicts: [],
  conflictChecks: [],
  providerHealth: [],
  analysisInput: {
    schemaVersion: 'field_trust_analysis_input/1.0',
    confidence: 'low',
    gaps: [{ code: 'quote_unavailable', field: null, detail: 'No realtime quote available from any provider' }],
    conflictCount: 0,
    failedProviderCount: 0,
  },
  message: 'No realtime quote available from any provider',
};

const FieldTrustPanelStory = () => {
  const { scenario } = usePlaygroundScenario();
  if (scenario === 'error') {
    return (
      <FieldTrustPanel
        stockCode="600519"
        fetchView={async () => {
          throw createParsedApiError({
            title: 'Field trust lookup failed',
            message: 'Field trust lookup failed',
          });
        }}
      />
    );
  }
  if (scenario === 'empty') {
    return <FieldTrustPanel stockCode="600519" initialView={UNAVAILABLE_VIEW} />;
  }
  return <FieldTrustPanel stockCode="600519" initialView={DEGRADED_VIEW} />;
};

export const FIELD_TRUST_PANEL_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'field-trust-panel': FieldTrustPanelStory,
};
