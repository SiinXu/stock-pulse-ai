// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { DemoAnalysisPayload, FirstRunReadiness } from '../../../types/onboarding';
import { ZeroConfigFirstRunPanel } from '../ZeroConfigFirstRunPanel';

const getFirstRunReadiness = vi.fn();
const getDemoAnalysis = vi.fn();

vi.mock('../../../api/onboarding', () => ({
  onboardingApi: {
    getFirstRunReadiness: (...args: unknown[]) => getFirstRunReadiness(...args),
    getDemoAnalysis: (...args: unknown[]) => getDemoAnalysis(...args),
  },
}));

const demoPayload: DemoAnalysisPayload = {
  schemaVersion: 1,
  isSample: true,
  sampleBanner: 'Sample data — not a live analysis',
  sampleDisclaimer: 'Offline fixture only.',
  queryId: 'demo-sample-analysis-v1',
  stockCode: '600519',
  stockName: 'Kweichow Moutai (sample)',
  createdAt: '2026-08-09T00:00:00Z',
  report: {
    meta: {
      queryId: 'demo-sample-analysis-v1',
      stockCode: '600519',
      stockName: 'Kweichow Moutai (sample)',
      reportType: 'brief',
      reportLanguage: 'en',
      createdAt: '2026-08-09T00:00:00Z',
      currentPrice: null,
      changePct: null,
      modelUsed: 'demo-fixture/offline',
    },
    summary: {
      analysisSummary: 'SAMPLE DATA — offline demonstration only.',
      operationAdvice: 'SAMPLE DATA — configure a real model next.',
      action: 'watch',
      actionLabel: 'Watch (sample)',
      trendPrediction: 'Sample trend',
      sentimentScore: 50,
      sentimentLabel: 'Neutral',
    },
    strategy: {
      idealBuy: null,
      secondaryBuy: null,
      stopLoss: null,
      takeProfit: null,
    },
    details: { news: [], technical: [] },
  },
};

const demoReadiness: FirstRunReadiness = {
  schemaVersion: 1,
  isFreshEnvironment: true,
  hasPrimaryModel: false,
  beginnerModeRecommended: true,
  primaryPath: 'demo',
  primaryCta: 'view_demo',
  reasonCode: 'local_runtime_unavailable',
  reasonParams: {},
  localRuntime: {
    reachable: false,
    modelsAvailable: false,
    runnable: false,
    models: [],
    suggestedProfile: {},
    reasonCode: 'ollama_unreachable',
    detectEnabled: true,
  },
  suggestedProfile: {},
  demoAvailable: true,
  configMutated: false,
  existingConfigUntouched: true,
  snapshotId: '0123456789abcdef01234567',
  generatedAt: '2026-08-09T00:00:00Z',
};

const configuredReadiness: FirstRunReadiness = {
  ...demoReadiness,
  isFreshEnvironment: false,
  hasPrimaryModel: true,
  beginnerModeRecommended: false,
  primaryPath: 'configured',
  primaryCta: 'continue',
  reasonCode: 'primary_model_configured',
};

function renderPanel(readiness: FirstRunReadiness, onContinue?: () => void | Promise<void>) {
  const t = (key: string) => key;
  return render(
    <UiLanguageProvider>
      <ZeroConfigFirstRunPanel
        readiness={readiness}
        autoLoad={false}
        reportLanguage="en"
        onContinue={onContinue}
        t={t as never}
      />
    </UiLanguageProvider>,
  );
}

describe('ZeroConfigFirstRunPanel', () => {
  beforeEach(() => {
    getFirstRunReadiness.mockReset();
    getDemoAnalysis.mockReset();
    getDemoAnalysis.mockResolvedValue(demoPayload);
  });

  it('shows demo path CTA and sample banner after loading demo analysis', async () => {
    renderPanel(demoReadiness);
    expect(screen.getByTestId('zero-config-first-run-panel')).toBeInTheDocument();
    expect(screen.getByText('firstRun.pathDemo')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'firstRun.ctaDemo' }));
    await waitFor(() => {
      expect(getDemoAnalysis).toHaveBeenCalledWith('en');
    });
    await waitFor(() => {
      expect(screen.getByTestId('zero-config-demo-analysis')).toBeInTheDocument();
    });
    expect(screen.getByText('Sample data — not a live analysis')).toBeInTheDocument();
    expect(screen.getByText('SAMPLE DATA — offline demonstration only.')).toBeInTheDocument();
  });

  it('does not force beginner path when model is already configured', () => {
    renderPanel(configuredReadiness);
    expect(screen.getByText('firstRun.pathConfigured')).toBeInTheDocument();
    expect(screen.queryByText('firstRun.beginnerRecommended')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'firstRun.ctaContinue' })).toBeDisabled();
    expect(screen.getByText('firstRun.integrationUnavailable')).toBeInTheDocument();
  });

  it('runs the host navigation callback instead of substituting the demo', async () => {
    const onContinue = vi.fn();
    renderPanel(configuredReadiness, onContinue);
    fireEvent.click(screen.getByRole('button', { name: 'firstRun.ctaContinue' }));
    await waitFor(() => expect(onContinue).toHaveBeenCalledTimes(1));
    expect(getDemoAnalysis).not.toHaveBeenCalled();
  });

  it('reports a rejected host action without an unhandled promise', async () => {
    renderPanel(configuredReadiness, vi.fn().mockRejectedValue(new Error('navigation failed')));
    fireEvent.click(screen.getByRole('button', { name: 'firstRun.ctaContinue' }));
    await waitFor(() => {
      expect(screen.getByText('firstRun.actionError')).toBeInTheDocument();
    });
  });
});
