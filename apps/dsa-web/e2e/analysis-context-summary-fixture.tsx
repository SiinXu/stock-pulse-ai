// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/geist/index.css';
import '../src/index.css';
import '../src/App.css';
import { AnalysisContextSummary } from '../src/components/report';
import { ThemeProvider } from '../src/components/theme/ThemeProvider';
import type { AnalysisContextPackOverview } from '../src/types/analysis';

const overview: AnalysisContextPackOverview = {
  packVersion: '1.0',
  createdAt: '2026-07-20T08:30:00+00:00',
  subject: {
    code: 'AAPL',
    stockName: 'Apple',
    market: 'us',
  },
  blocks: [
    {
      key: 'quote',
      label: 'quote',
      status: 'fallback',
      source: 'cached_quote_provider_with_a_long_source_name',
      warnings: ['quote_fallback'],
      missingReasons: [],
    },
    {
      key: 'news',
      label: 'news',
      status: 'missing',
      source: null,
      warnings: ['news_provider_timeout'],
      missingReasons: ['news_context_missing'],
    },
    {
      key: 'fundamentals',
      label: 'fundamentals',
      status: 'available',
      source: null,
      warnings: [],
      missingReasons: ['fundamental_source_chain_missing'],
    },
    {
      key: 'technical',
      label: 'technical',
      status: 'partial',
      source: 'technical_pipeline',
      warnings: ['intraday_realtime_overlay'],
      missingReasons: [],
    },
    {
      key: 'chip',
      label: 'chip',
      status: 'estimated',
      source: 'estimated_chip',
      warnings: [],
      missingReasons: [],
    },
    {
      key: 'daily_bars',
      label: 'daily bars',
      status: 'not_supported',
      source: null,
      warnings: [],
      missingReasons: [],
    },
  ],
  counts: {
    available: 1,
    missing: 1,
    notSupported: 1,
    fallback: 1,
    stale: 0,
    estimated: 1,
    partial: 1,
    fetchFailed: 0,
  },
  dataQuality: {
    overallScore: 58,
    level: 'limited',
    blockScores: {},
    limitations: ['news: missing', 'technical: partial'],
  },
  warnings: ['analysis_input_degraded'],
  metadata: {
    triggerSource: 'api',
    newsResultCount: 0,
  },
};

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <main className="min-h-dvh bg-background px-4 py-6 text-foreground sm:px-6">
        <div className="mx-auto max-w-5xl">
          <AnalysisContextSummary overview={overview} language="en" />
        </div>
      </main>
    </ThemeProvider>
  </StrictMode>,
);
