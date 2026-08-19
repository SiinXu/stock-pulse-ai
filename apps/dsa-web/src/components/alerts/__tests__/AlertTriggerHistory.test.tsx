// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { AlertTriggerItem } from '../../../types/alerts';
import { AlertTriggerHistory } from '../AlertTriggerHistory';

function makeTrigger(overrides: Partial<AlertTriggerItem> = {}): AlertTriggerItem {
  return {
    id: 42,
    ruleId: 1,
    target: 'AAPL',
    status: 'triggered',
    reason: 'Price crossed threshold',
    triggeredAt: '2026-07-23T10:00:00Z',
    ...overrides,
  };
}

const triggers: AlertTriggerItem[] = [makeTrigger()];

describe('AlertTriggerHistory', () => {
  const scrollIntoView = vi.fn();

  beforeEach(() => {
    scrollIntoView.mockClear();
    HTMLElement.prototype.scrollIntoView = scrollIntoView;
  });

  it('highlights, focuses, and scrolls the deep-linked trigger row', async () => {
    render(
      <UiLanguageProvider initialLanguage="en">
        <AlertTriggerHistory triggers={triggers} selectedTriggerId={42} />
      </UiLanguageProvider>,
    );

    const row = screen.getByTestId('alert-trigger-row-42');
    expect(row).toHaveAttribute('aria-selected', 'true');
    expect(row).toHaveAttribute('data-row-selected', 'true');
    await waitFor(() => expect(screen.getByText('AAPL')).toHaveFocus());
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'center' });
  });

  it('renders localized trigger status and quality labels instead of raw codes', () => {
    render(
      <UiLanguageProvider initialLanguage="en">
        <AlertTriggerHistory
          triggers={[makeTrigger({
            status: 'degraded',
            analysisContextPackOverview: {
              packVersion: '1.0',
              subject: { code: 'AAPL', stockName: 'Apple', market: 'us' },
              blocks: [],
              counts: {
                available: 0,
                missing: 0,
                notSupported: 0,
                fallback: 0,
                stale: 0,
                estimated: 0,
                partial: 0,
                fetchFailed: 0,
              },
              dataQuality: {
                level: 'usable',
                limitations: ['fundamentals: fetch_failed'],
                blockScores: {},
              },
              warnings: [],
              metadata: {},
            },
          })]}
        />
      </UiLanguageProvider>,
    );

    expect(screen.getByText('Degraded')).toBeInTheDocument();
    expect(screen.getByText('Quality: Usable')).toBeInTheDocument();
    expect(screen.getByText('fundamentals: Fetch failed')).toBeInTheDocument();
    expect(screen.queryByText('degraded')).not.toBeInTheDocument();
    expect(screen.queryByText('usable')).not.toBeInTheDocument();
    expect(screen.queryByText('fundamentals: fetch_failed')).not.toBeInTheDocument();
  });

  it('keeps unknown status and quality codes visible', () => {
    render(
      <UiLanguageProvider initialLanguage="zh">
        <AlertTriggerHistory
          triggers={[makeTrigger({
            status: 'queued',
            analysisContextPackOverview: {
              packVersion: '1.0',
              subject: { code: 'AAPL', stockName: 'Apple', market: 'us' },
              blocks: [],
              counts: {
                available: 0,
                missing: 0,
                notSupported: 0,
                fallback: 0,
                stale: 0,
                estimated: 0,
                partial: 0,
                fetchFailed: 0,
              },
              dataQuality: {
                level: 'not_a_real_level' as never,
                limitations: ['custom_block: custom_status'],
                blockScores: {},
              },
              warnings: [],
              metadata: {},
            },
          })]}
        />
      </UiLanguageProvider>,
    );

    expect(screen.getByText('queued')).toBeInTheDocument();
    expect(screen.getByText('质量：not_a_real_level')).toBeInTheDocument();
    expect(screen.getByText('custom_block：custom_status')).toBeInTheDocument();
  });
});
