// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ReportStructuredInsights as ReportStructuredInsightsType } from '../../../types/analysis';
import { ReportStructuredInsights } from '../ReportStructuredInsights';
import { normalizeReportStructuredInsights } from '../reportStructuredInsightsUtils';

const completeInsights: ReportStructuredInsightsType = {
  schemaVersion: 'report-structured-insights-v1',
  phaseDecision: {
    phaseContext: {
      phase: 'intraday',
      market: 'US',
      marketLocalTime: '2026-07-29T11:30:00-04:00',
      triggerSource: 'api',
      warnings: ['Current daily bar is partial'],
    },
    immediateAction: 'Wait for confirmation',
    actionWindow: 'Next 30 minutes',
    watchConditions: ['Price holds above VWAP'],
    confidenceReason: 'Volume confirmation is incomplete',
    dataLimitations: ['Current daily bar is partial'],
  },
  signalAttribution: {
    technicalIndicators: 50,
    newsSentiment: 20,
    fundamentals: 20,
    marketConditions: 10,
    strongestBullishSignal: 'Volume expansion',
    strongestBearishSignal: 'Weak breadth',
  },
  strategySynthesis: {
    finalSignal: 'buy',
    weightedScore: 4.2,
    confidence: 0.74,
    consensusLevel: 'medium',
    conflictCount: 1,
    conflictSeverity: 'medium',
    supportingSkills: [
      {
        skillId: 'volume_breakout',
        signal: 'buy',
        confidence: 0.83,
        reasoning: 'Breakout confirmed',
      },
    ],
    opposingSkills: [
      {
        skillId: 'box_oscillation',
        signal: 'reduce',
        confidence: 0.72,
      },
    ],
    conflicts: [
      {
        conflictType: 'directional_opposition',
        severity: 'medium',
        participants: ['volume_breakout', 'box_oscillation'],
      },
    ],
    summaryParams: {
      invalidOpinionCount: 1,
    },
  },
};

describe('ReportStructuredInsights', () => {
  it('renders phase, attribution, conflict, support, and opposition as first-class sections', () => {
    render(<ReportStructuredInsights insights={completeInsights} language="en" />);

    expect(screen.getByTestId('report-phase-decision')).toHaveTextContent('Wait for confirmation');
    const attribution = screen.getByTestId('report-signal-attribution');
    expect(within(attribution).getByText('Technical Indicators')).toBeInTheDocument();
    expect(within(attribution).getByRole('progressbar', { name: 'Technical Indicators' }))
      .toHaveAttribute('aria-valuenow', '50');
    expect(attribution).toHaveTextContent('Volume expansion');

    const synthesis = screen.getByTestId('report-strategy-synthesis');
    expect(synthesis).toHaveTextContent('Buy');
    expect(synthesis).toHaveTextContent('74%');
    expect(screen.getByTestId('report-supporting-skills')).toHaveTextContent('volume_breakout');
    expect(screen.getByTestId('report-opposing-skills')).toHaveTextContent('box_oscillation');
    expect(screen.getByTestId('report-strategy-conflicts')).toHaveTextContent(
      'Opposing strategy directions',
    );
    expect(screen.getByTestId('report-strategy-conflicts')).toHaveTextContent(
      'volume_breakout, box_oscillation',
    );
  });

  it('renders a meaningful partial payload without empty sibling cards', () => {
    render(
      <ReportStructuredInsights
        insights={{
          schemaVersion: 'report-structured-insights-v1',
          phaseDecision: { confidenceReason: 'Only phase evidence is available' },
        }}
        language="en"
      />,
    );

    expect(screen.getByTestId('report-phase-decision')).toHaveTextContent(
      'Only phase evidence is available',
    );
    expect(screen.queryByTestId('report-signal-attribution')).not.toBeInTheDocument();
    expect(screen.queryByTestId('report-strategy-synthesis')).not.toBeInTheDocument();
  });

  it('renders nothing for missing, empty, or malformed contracts', () => {
    const { rerender } = render(<ReportStructuredInsights language="en" />);
    expect(screen.queryByTestId('report-structured-insights')).not.toBeInTheDocument();

    rerender(
      <ReportStructuredInsights
        insights={{
          schemaVersion: 'report-structured-insights-v1',
        }}
        language="en"
      />,
    );
    expect(screen.queryByTestId('report-structured-insights')).not.toBeInTheDocument();

    rerender(
      <ReportStructuredInsights
        insights={
          {
            schemaVersion: 'unknown',
            phaseDecision: 'bad',
          } as unknown as ReportStructuredInsightsType
        }
        language="en"
      />,
    );
    expect(screen.queryByTestId('report-structured-insights')).not.toBeInTheDocument();
  });

  it('normalizes snake_case API fixtures and drops malformed list members', () => {
    const normalized = normalizeReportStructuredInsights({
      schema_version: 'report-structured-insights-v1',
      phase_decision: {
        phase_context: { phase: 'postmarket' },
        watch_conditions: 'Review after close',
      },
      strategy_synthesis: {
        final_signal: 'hold',
        opposing_skills: [
          { skill_id: 'event_driven', signal: 'sell' },
          'bad',
        ],
        conflicts: [
          {
            conflict_type: 'high_confidence_dissent',
            participants: ['event_driven', '', 123],
          },
        ],
      },
    });

    expect(normalized?.phaseDecision?.watchConditions).toEqual(['Review after close']);
    expect(normalized?.strategySynthesis?.opposingSkills).toEqual([
      { skillId: 'event_driven', signal: 'sell' },
    ]);
    expect(normalized?.strategySynthesis?.conflicts?.[0].participants).toEqual([
      'event_driven',
    ]);
  });
});
