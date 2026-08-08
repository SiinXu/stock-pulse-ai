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
  packVersion: 'todays_focus/1.0',
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
    },
    {
      code: 'AAPL',
      name: 'Apple',
      reasonCode: 'high_weight_move',
      reasonDisplay: 'High portfolio weight with large move: weight 22.0%, unrealized +8.5%',
      priority: 50,
      weightPct: 22,
    },
  ],
};

const emptyFocus: TodaysFocusResponse = {
  packVersion: 'todays_focus/1.0',
  generatedAt: '2026-08-09T00:00:00Z',
  status: 'empty',
  maxItems: 5,
  itemCount: 0,
  items: [],
  emptyReason: 'no_deterministic_signals',
  emptyMessage: 'No symbols need special attention today.',
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

  it('invokes refresh and symbol select callbacks', () => {
    const onRefresh = vi.fn();
    const onSelectSymbol = vi.fn();
    renderPanel({ data: withItems, isLoading: false, error: null, onRefresh, onSelectSymbol });
    fireEvent.click(screen.getByTestId('todays-focus-refresh'));
    expect(onRefresh).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId('todays-focus-item-AAPL'));
    expect(onSelectSymbol).toHaveBeenCalledWith('AAPL');
  });
});
