// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ComponentProps } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { WatchlistScoreItem } from '../../../types/watchlistScore';
import { orderWatchlistByScore } from '../../../utils/watchlistScoreOrder';
import { WatchlistScoreColumn } from '../WatchlistScoreColumn';

afterEach(() => {
  cleanup();
});

function renderColumn(item: WatchlistScoreItem, props: Partial<ComponentProps<typeof WatchlistScoreColumn>> = {}) {
  return render(
    <UiLanguageProvider initialLanguage="en">
      <WatchlistScoreColumn item={item} {...props} />
    </UiLanguageProvider>,
  );
}

const scoredItem: WatchlistScoreItem = {
  stockCode: '600519',
  status: 'scored',
  score: 72,
  asOf: '2026-08-08T09:00:00+00:00',
  ageDays: 1,
  analysisId: 5,
  operationAdvice: 'Buy',
  freshness: '1d',
  factors: [
    {
      key: 'analysis_sentiment',
      label: 'Analysis sentiment score',
      value: 72,
      detail: 'advice=Buy; as_of=2026-08-08',
    },
    {
      key: 'decision_signal',
      label: 'Active decision signal',
      value: 'buy',
      detail: 'confidence=0.80',
    },
  ],
};

const unanalyzedItem: WatchlistScoreItem = {
  stockCode: 'AAPL',
  status: 'unanalyzed',
  score: null,
  asOf: null,
  ageDays: null,
  factors: [],
  freshness: 'none',
};

describe('WatchlistScoreColumn', () => {
  it('renders unanalyzed without inventing a zero score', () => {
    renderColumn(unanalyzedItem);
    expect(screen.getByTestId('watchlist-score-unanalyzed')).toHaveTextContent(/not analyzed/i);
    expect(screen.queryByTestId('watchlist-score-value')).toBeNull();
    expect(screen.getByTestId('watchlist-score-column')).toHaveAttribute('data-status', 'unanalyzed');
  });

  it('renders score with freshness and expandable factor drill-down', () => {
    renderColumn(scoredItem);
    expect(screen.getByTestId('watchlist-score-value')).toHaveTextContent('72');
    expect(screen.getByTestId('watchlist-score-freshness')).toBeInTheDocument();
    expect(screen.queryByTestId('watchlist-score-factors')).toBeNull();

    fireEvent.click(screen.getByTestId('watchlist-score-toggle'));
    expect(screen.getByTestId('watchlist-score-factors')).toBeInTheDocument();
    expect(screen.getByText('Analysis sentiment score')).toBeInTheDocument();
    expect(screen.getByText('Active decision signal')).toBeInTheDocument();
    expect(screen.getByText(/not investment advice/i)).toBeInTheDocument();
  });
});

describe('orderWatchlistByScore', () => {
  it('keeps manual order by default and does not override user ordering', () => {
    const rows = [{ code: 'AAPL' }, { code: 'MSFT' }, { code: 'NVDA' }];
    const scores = new Map<string, WatchlistScoreItem>([
      ['AAPL', { ...scoredItem, stockCode: 'AAPL', score: 30 }],
      ['MSFT', { ...scoredItem, stockCode: 'MSFT', score: 90 }],
      ['NVDA', unanalyzedItem],
    ]);
    const ordered = orderWatchlistByScore(rows, scores, 'manual');
    expect(ordered.map((row) => row.code)).toEqual(['AAPL', 'MSFT', 'NVDA']);
  });

  it('supports optional score_desc view without mutating input', () => {
    const rows = [{ code: 'AAPL' }, { code: 'MSFT' }, { code: 'NVDA' }];
    const scores = new Map<string, WatchlistScoreItem>([
      ['AAPL', { ...scoredItem, stockCode: 'AAPL', score: 30 }],
      ['MSFT', { ...scoredItem, stockCode: 'MSFT', score: 90 }],
      ['NVDA', { ...unanalyzedItem, stockCode: 'NVDA' }],
    ]);
    const snapshot = rows.map((row) => row.code);
    const ordered = orderWatchlistByScore(rows, scores, 'score_desc');
    expect(ordered.map((row) => row.code)).toEqual(['MSFT', 'AAPL', 'NVDA']);
    expect(rows.map((row) => row.code)).toEqual(snapshot);
  });
});
