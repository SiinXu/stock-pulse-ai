// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { scorecardApi } from '../../../api/scorecard';
import { UI_TEXT } from '../../../i18n/uiText';
import SignalScorecardPanel from '../SignalScorecardPanel';

vi.mock('../../../api/scorecard', () => ({
  scorecardApi: {
    getPublic: vi.fn(),
  },
}));

const t = (key: keyof typeof UI_TEXT.en, params?: Record<string, string | number>) => {
  const template = UI_TEXT.en[key] ?? String(key);
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (
    params[name] === undefined ? match : String(params[name])
  ));
};

function mockDisabledScorecard() {
  const error = Object.assign(new Error('Public scorecard is not enabled'), {
    response: {
      status: 404,
      data: { error: 'not_found', message: 'Public scorecard is not enabled' },
    },
    parsedError: {
      title: 'Not found',
      message: 'Public scorecard is not enabled',
      rawMessage: 'Public scorecard is not enabled',
      status: 404,
      category: 'http_error' as const,
      code: 'not_found',
    },
  });
  vi.mocked(scorecardApi.getPublic).mockRejectedValue(error);
}

describe('SignalScorecardPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the disabled empty state without calling the public route when the flag is off', async () => {
    render(
      <SignalScorecardPanel
        publicEnabled={false}
        minSamples={10}
        t={t}
        language="en"
      />,
    );

    expect(await screen.findByText('Public scorecard is disabled')).toBeInTheDocument();
    expect(screen.getByText(/Turn on Public Signal Scorecard/i)).toBeInTheDocument();
    expect(screen.getByText('Disabled (public route returns 404)')).toBeInTheDocument();
    expect(screen.getByText(/Min samples: 10/i)).toBeInTheDocument();
    expect(scorecardApi.getPublic).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /Refresh signal scorecard preview/i })).toBeDisabled();
  });

  it('shows enable-for-preview empty state when the public route returns 404', async () => {
    mockDisabledScorecard();

    render(
      <SignalScorecardPanel
        publicEnabled
        minSamples={10}
        t={t}
        language="en"
      />,
    );

    expect(await screen.findByText('Public scorecard is disabled')).toBeInTheDocument();
    expect(scorecardApi.getPublic).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Disabled (public route returns 404)')).toBeInTheDocument();
  });

  it('renders aggregated scorecard stats when the public route is enabled', async () => {
    vi.mocked(scorecardApi.getPublic).mockResolvedValue({
      minSamples: 5,
      overall: {
        status: 'ok',
        sampleSize: 12,
        completed: 14,
        hitRatePct: 58.3,
        avgReturnPct: 1.2,
      },
      bySignalTypeHorizon: [
        {
          signalType: 'buy',
          horizon: '5d',
          status: 'ok',
          sampleSize: 8,
          completed: 8,
          hitRatePct: 62.5,
          avgReturnPct: 2.1,
        },
      ],
      returnDistribution: [
        { band: '+2% ~ +5%', count: 3, sharePct: 25 },
      ],
      recentMisses: [
        {
          signalType: 'buy',
          horizon: '5d',
          returnPct: -3.5,
          anchorDate: '2026-07-01',
        },
      ],
    });

    render(
      <SignalScorecardPanel
        publicEnabled
        minSamples={5}
        t={t}
        language="en"
      />,
    );

    expect(await screen.findByText('Enabled (public route reachable)')).toBeInTheDocument();
    expect(screen.getByText('58.3%')).toBeInTheDocument();
    expect(screen.getAllByText('buy').length).toBeGreaterThan(0);
    expect(screen.getByText('+2% ~ +5%')).toBeInTheDocument();
    expect(screen.getByText('2026-07-01')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Refresh signal scorecard preview/i }));
    await waitFor(() => {
      expect(scorecardApi.getPublic).toHaveBeenCalledTimes(2);
    });
  });
});
