// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ComponentProps } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider, useUiLanguage } from '../../../contexts/UiLanguageContext';
import type { TodaysFocusResponse } from '../../../types/todaysFocus';
import { TodaysFocusPanel } from '../TodaysFocusPanel';

function Harness(props: Omit<ComponentProps<typeof TodaysFocusPanel>, 't'>) {
  const { t } = useUiLanguage();
  return <TodaysFocusPanel {...props} t={t} />;
}

function renderPanel(props: Omit<ComponentProps<typeof TodaysFocusPanel>, 't'>) {
  return render(
    <UiLanguageProvider initialLanguage="en">
      <Harness {...props} />
    </UiLanguageProvider>,
  );
}

const withItems: TodaysFocusResponse = {
  packVersion: 'todays_focus/2.1',
  generatedAt: '2026-08-09T00:00:00Z',
  status: 'ok',
  maxItems: 5,
  itemCount: 2,
  items: [
    {
      code: '600519',
      name: 'Kweichow Moutai',
      reasonCode: 'alert_triggered',
      reasonDisplay: 'Alert triggered: price above MA',
      priority: 100,
      weightPct: null,
      secondaryReasonCodes: [],
      evidence: {
        type: 'alert',
        triggerId: 7,
        ruleId: 9,
        observedAt: '2026-08-09T00:00:00Z',
        status: 'triggered',
      },
    },
    {
      code: 'AAPL',
      name: 'Apple',
      reasonCode: 'analysis_reversal',
      reasonDisplay: 'Analysis conclusion changed: buy to sell',
      priority: 70,
      weightPct: null,
      secondaryReasonCodes: [],
      evidence: {
        type: 'analysis',
        recordId: 42,
        queryId: 'q-42',
        observedAt: '2026-08-09T00:00:00Z',
        previousObservedAt: '2026-08-08T00:00:00Z',
        previousAction: 'buy',
        latestAction: 'sell',
      },
    },
  ],
  emptyReason: null,
  emptyMessage: null,
  sourcesUsed: ['alerts', 'analysis_history'],
  degradedSources: [],
  temporalPolicy: {
    semantics: 'per_market_local_calendar_day',
    crossMarketRule: 'evidence_uses_target_symbol_market_timezone',
    fallbackTimezone: 'Asia/Shanghai',
    windowEnd: '2026-08-09T00:00:00Z',
    naiveTimestampPolicy: 'assume_utc',
    missingTimestampPolicy: 'exclude',
    nonTradingDayPolicy: 'same_local_day_only',
    markets: [
      {
        market: 'cn',
        timezone: 'Asia/Shanghai',
        localDate: '2026-08-09',
        windowStart: '2026-08-08T16:00:00Z',
        windowEnd: '2026-08-09T00:00:00Z',
        isTradingDay: true,
      },
      {
        market: 'hk',
        timezone: 'Asia/Hong_Kong',
        localDate: '2026-08-09',
        windowStart: '2026-08-08T16:00:00Z',
        windowEnd: '2026-08-09T00:00:00Z',
        isTradingDay: true,
      },
      {
        market: 'us',
        timezone: 'America/New_York',
        localDate: '2026-08-09',
        windowStart: '2026-08-09T04:00:00Z',
        windowEnd: '2026-08-09T00:00:00Z',
        isTradingDay: false,
      },
      {
        market: 'unknown',
        timezone: 'Asia/Shanghai',
        localDate: '2026-08-09',
        windowStart: '2026-08-08T16:00:00Z',
        windowEnd: '2026-08-09T00:00:00Z',
        isTradingDay: null,
      },
    ],
  },
  universeContract: {
    symbolCount: 2,
    hardCap: 1000,
    truncated: false,
    sources: ['watchlist_config'],
    excludedNonFinitePositions: 0,
    dataNotes: [],
  },
  costContract: {
    alertRepositoryCalls: 1,
    portfolioRepositoryCalls: 1,
    analysisHistoryRepositoryCalls: 1,
    eventRepositoryCalls: 0,
    databaseWrites: 0,
    providerCalls: 0,
    analysisRunsTriggered: 0,
    zeroExtraFetch: true,
    readOnly: true,
  },
  presentationBoundary: {
    alertsOwnedBy: 'signal_center',
    focusShows: 'prioritized_symbols_with_evidence_links',
    duplicateAlertUi: false,
  },
};

const emptyFocus: TodaysFocusResponse = {
  ...withItems,
  status: 'empty',
  itemCount: 0,
  items: [],
  emptyReason: 'no_fresh_deterministic_signals',
  emptyMessage: 'No symbols need special attention today.',
  sourcesUsed: [],
};

describe('TodaysFocusPanel', () => {
  it('renders focus items with deterministic reasons', () => {
    renderPanel({ data: withItems, isLoading: false, error: null, onRefresh: () => undefined });
    expect(screen.getByTestId('todays-focus-panel')).toBeInTheDocument();
    expect(screen.getByTestId('todays-focus-item-600519')).toBeInTheDocument();
    expect(screen.getByTestId('todays-focus-item-AAPL')).toBeInTheDocument();
    expect(screen.getByText(/Alert triggered/i)).toBeInTheDocument();
    expect(screen.queryByTestId('todays-focus-empty')).not.toBeInTheDocument();
  });

  it('shows honest empty state without padding fake rows', () => {
    renderPanel({ data: emptyFocus, isLoading: false, error: null, onRefresh: () => undefined });
    expect(screen.getByTestId('todays-focus-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('todays-focus-list')).not.toBeInTheDocument();
  });

  it('surfaces source degradation instead of presenting a normal empty state', () => {
    renderPanel({
      data: {
        ...emptyFocus,
        status: 'degraded',
        emptyReason: 'source_unavailable',
        degradedSources: ['analysis_history'],
      },
      isLoading: false,
      error: null,
      onRefresh: () => undefined,
    });
    expect(screen.getByTestId('todays-focus-degraded')).toHaveTextContent(
      'Some local sources are unavailable',
    );
  });

  it('invokes refresh and symbol select callbacks', () => {
    const onRefresh = vi.fn();
    const onSelectSymbol = vi.fn();
    renderPanel({ data: withItems, isLoading: false, error: null, onRefresh, onSelectSymbol });
    fireEvent.click(screen.getByTestId('todays-focus-refresh'));
    expect(onRefresh).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId('todays-focus-item-AAPL'));
    expect(onSelectSymbol).toHaveBeenCalledWith('AAPL');
  });

  it('links alert and analysis evidence to exact records with accessible names', () => {
    renderPanel({ data: withItems, isLoading: false, error: null, onRefresh: () => undefined });
    const alertLink = screen.getByTestId('todays-focus-evidence-600519');
    const analysisLink = screen.getByTestId('todays-focus-evidence-AAPL');
    expect(alertLink).toHaveAttribute(
      'href',
      '/signals?tab=history&trigger=7&stock=600519',
    );
    expect(alertLink).toHaveAccessibleName('View evidence: 600519');
    expect(analysisLink).toHaveAttribute(
      'href',
      '/research/analysis?segment=history&recordId=42&stock=AAPL',
    );
    expect(analysisLink).toHaveAccessibleName('View evidence: AAPL');
  });

  it('does not render an unsafe link for unknown runtime evidence', () => {
    const malformed = {
      ...withItems,
      items: [{ ...withItems.items[0], evidence: { type: 'unknown' } }],
      itemCount: 1,
    } as unknown as TodaysFocusResponse;
    renderPanel({ data: malformed, isLoading: false, error: null, onRefresh: () => undefined });
    expect(screen.queryByTestId('todays-focus-evidence-600519')).not.toBeInTheDocument();
  });
});
