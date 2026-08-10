// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ComponentProps } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { UiLanguage } from '../../../i18n/uiLanguages';
import type { WatchlistScoreItem } from '../../../types/watchlistScore';
import { orderWatchlistByScore } from '../../../utils/watchlistScoreOrder';
import { WatchlistScoreColumn } from '../WatchlistScoreColumn';

afterEach(() => {
  cleanup();
});

function renderColumn(
  item: WatchlistScoreItem,
  props: Partial<ComponentProps<typeof WatchlistScoreColumn>> = {},
  language: UiLanguage = 'en',
) {
  return render(
    <UiLanguageProvider initialLanguage={language}>
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
  freshness: 'recent',
  degradedReasons: [],
  factors: [
    {
      key: 'analysis_sentiment',
      status: 'applied',
      value: 72,
      params: { operationAdvice: 'Buy', reportType: 'detailed' },
      reason: null,
      source: {
        id: 5,
        sourceReportId: 5,
        profile: null,
        asOf: '2026-08-08T09:00:00+00:00',
        expiresAt: null,
        formulaVersion: 'watchlist_score_v1',
      },
    },
    {
      key: 'decision_signal',
      status: 'applied',
      value: 'buy',
      params: { confidence: 0.8, profile: 'balanced' },
      reason: null,
      source: {
        id: 8,
        sourceReportId: 5,
        profile: 'balanced',
        asOf: '2026-08-08T10:00:00+00:00',
        expiresAt: '2026-08-10T10:00:00+00:00',
        formulaVersion: 'watchlist_score_v1',
      },
    },
  ],
};

const unanalyzedItem: WatchlistScoreItem = {
  stockCode: 'AAPL',
  status: 'unanalyzed',
  score: null,
  asOf: null,
  ageDays: null,
  analysisId: null,
  operationAdvice: null,
  factors: [],
  freshness: 'none',
  degradedReasons: [],
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
    expect(screen.getByText('Analysis sentiment')).toBeInTheDocument();
    expect(screen.getByText('Decision signal')).toBeInTheDocument();
    expect(screen.getByText(/not investment advice/i)).toBeInTheDocument();
  });

  it('uses keyboard expansion with a labelled controlled region', () => {
    renderColumn(scoredItem);
    const toggle = screen.getByTestId('watchlist-score-toggle');
    toggle.focus();
    fireEvent.keyDown(toggle, { key: 'Enter' });
    fireEvent.click(toggle);
    const region = screen.getByRole('region');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveAttribute('aria-controls', region.id);
    expect(region).toHaveAttribute('aria-labelledby', toggle.id);
  });

  it('honors controlled expansion and delegates toggles', () => {
    const onToggleExpand = vi.fn();
    renderColumn(scoredItem, { expanded: true, onToggleExpand });
    expect(screen.getByRole('region')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('watchlist-score-toggle'));
    expect(onToggleExpand).toHaveBeenCalledTimes(1);
  });

  it('uses the shared accessible tooltip instead of a native title', () => {
    renderColumn(scoredItem);
    const freshness = screen.getByTestId('watchlist-score-freshness');
    expect(freshness).not.toHaveAttribute('title');
    fireEvent.focus(freshness.parentElement as HTMLElement);
    expect(screen.getByRole('tooltip')).toHaveTextContent('2026-08-08T09:00:00+00:00');
  });

  it('localizes factor presentation in Chinese and Japanese', () => {
    const { unmount } = renderColumn(scoredItem, { expanded: true }, 'zh');
    expect(screen.getByText('分析情绪分')).toBeInTheDocument();
    expect(screen.getByText(/建议：Buy/)).toBeInTheDocument();
    unmount();
    renderColumn(scoredItem, { expanded: true }, 'ja');
    expect(screen.getByText('分析センチメント')).toBeInTheDocument();
  });

  it('renders long arbitrary factor data inside a wrapping narrow-safe container', () => {
    const longItem = {
      ...scoredItem,
      factors: [{
        ...scoredItem.factors[0],
        params: { operationAdvice: 'x'.repeat(400), reportType: 'detailed' },
      }],
    };
    renderColumn(longItem, { expanded: true, className: 'w-40' });
    expect(screen.getByRole('region').querySelector('.break-words')).toBeInTheDocument();
    expect(screen.getByTestId('watchlist-score-column')).toHaveClass('min-w-0', 'w-40');
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
