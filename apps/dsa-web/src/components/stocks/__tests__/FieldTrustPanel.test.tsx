// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ReactElement } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { StockFieldTrustResponse } from '../../../types/stocks';
import { FieldTrustPanel } from '../FieldTrustPanel';

const staleConflictView: StockFieldTrustResponse = {
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
    { provider: 'akshare_em', status: 'ok', role: 'supplement' },
  ],
  analysisInput: {
    schemaVersion: 'field_trust_analysis_input/1.0',
    confidence: 'low',
    gaps: [
      { code: 'stale', field: 'price', detail: 'provider timestamp exceeded the realtime TTL' },
      { code: 'conflict', field: 'price', detail: 'providers disagreed; no source was chosen as truth' },
    ],
    conflictCount: 1,
    failedProviderCount: 0,
  },
};

const unavailableView: StockFieldTrustResponse = {
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

const renderPanel = (ui: ReactElement) =>
  render(<UiLanguageProvider initialLanguage="en">{ui}</UiLanguageProvider>);

describe('FieldTrustPanel', () => {
  it('renders stale and conflict degradation without picking a silent winner', () => {
    renderPanel(<FieldTrustPanel stockCode="600519" initialView={staleConflictView} />);
    expect(screen.getByTestId('field-trust-panel')).toBeInTheDocument();
    expect(screen.getByTestId('field-trust-degraded')).toBeInTheDocument();
    expect(screen.getByTestId('field-trust-status')).toHaveTextContent('Degraded');
    expect(screen.getByTestId('field-trust-quote-source')).toHaveTextContent('efinance');
    expect(screen.getByTestId('field-trust-lag')).toHaveTextContent('7,200');
    expect(screen.getByTestId('field-trust-stale')).toHaveTextContent('Yes');
    expect(screen.getByTestId('field-trust-confidence')).toHaveTextContent('Low');
    expect(screen.getByTestId('field-trust-fields')).toHaveTextContent(/1,?688/);
    expect(screen.getByTestId('field-trust-fields')).toHaveTextContent('Stale');
    expect(screen.getByTestId('field-trust-fields')).toHaveTextContent('Yes');
    expect(screen.getByTestId('field-trust-gaps')).toHaveTextContent(/providers disagreed/i);
    expect(screen.getByTestId('field-trust-conflicts')).toHaveTextContent(/efinance=1,?688/);
    expect(screen.getByTestId('field-trust-conflicts')).toHaveTextContent(/akshare_em=2,?100/);
    expect(screen.getByTestId('field-trust-provider-health')).toHaveTextContent('efinance');
    expect(screen.getByTestId('field-trust-fields')).not.toHaveTextContent(/2,?100/);
  });

  it('renders unavailable degradation when no quote exists', () => {
    renderPanel(<FieldTrustPanel stockCode="600519" initialView={unavailableView} />);
    expect(screen.getByTestId('field-trust-unavailable')).toBeInTheDocument();
    expect(screen.getByTestId('field-trust-status')).toHaveTextContent('Unavailable');
    expect(screen.getByTestId('field-trust-confidence')).toHaveTextContent('Low');
    expect(screen.queryByTestId('field-trust-fields')).not.toBeInTheDocument();
  });

  it('loads through the injected fetcher', async () => {
    const fetchView = vi.fn().mockResolvedValue(staleConflictView);
    renderPanel(<FieldTrustPanel stockCode="600519" fetchView={fetchView} />);
    expect(await screen.findByTestId('field-trust-degraded')).toBeInTheDocument();
    expect(fetchView).toHaveBeenCalledWith('600519');
  });
});
