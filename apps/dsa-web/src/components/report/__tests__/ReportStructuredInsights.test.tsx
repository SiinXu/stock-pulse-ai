// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type {
  ReportCommitteeMember,
  ReportStrategySynthesisConflict,
  ReportStrategySynthesisSkill,
  ReportStructuredInsights as ReportStructuredInsightsType,
} from '../../../types/analysis';
import {
  REPORT_INSIGHT_LIST_PREVIEW_LIMIT,
  ReportStructuredInsights,
} from '../ReportStructuredInsights';
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
  committeeDeliberation: {
    status: 'split',
    outcome: 'buy',
    members: [
      {
        personaId: 'persona_value_moat',
        displayName: 'Value & Moat',
        signal: 'buy',
        confidence: 0.8,
        reasoningExcerpt: 'Moat durable',
      },
      {
        personaId: 'persona_tail_risk',
        displayName: 'Tail Risk',
        signal: 'sell',
        confidence: 0.7,
        reasoningExcerpt: 'Fragile balance sheet',
      },
    ],
    conclusion: {
      finalSignal: 'buy',
      consensusLevel: 'medium',
      conflictSeverity: 'medium',
      confidence: 0.74,
      conflictCount: 1,
    },
    dissentingOpinions: [
      {
        personaId: 'persona_tail_risk',
        displayName: 'Tail Risk',
        signal: 'sell',
        confidence: 0.7,
      },
    ],
    divergencePoints: [
      {
        source: 'strategy_conflict',
        conflictType: 'directional_opposition',
        severity: 'medium',
        participants: ['persona_value_moat', 'persona_tail_risk'],
      },
    ],
  },
};

describe('ReportStructuredInsights', () => {
  it('renders phase, attribution, conflict, support, and opposition as first-class sections', () => {
    render(<ReportStructuredInsights insights={completeInsights} language="en" />);

    const phaseDecision = screen.getByTestId('report-phase-decision');
    expect(phaseDecision).toHaveTextContent('Wait for confirmation');
    expect(within(phaseDecision).getByText('Market Phase').parentElement)
      .toHaveClass('sm:grid-cols-[6rem_minmax(0,1fr)]');
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

    const committee = screen.getByTestId('report-committee-deliberation');
    expect(committee).toHaveTextContent('Committee Conclusion');
    expect(screen.getByTestId('report-committee-members')).toHaveTextContent('Value & Moat');
    expect(screen.getByTestId('report-committee-dissent')).toHaveTextContent('Tail Risk');
    expect(screen.getByTestId('report-committee-divergence')).toHaveTextContent(
      'Opposing strategy directions',
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
      committee_deliberation: {
        status: 'deliberated',
        members: [
          {
            persona_id: 'persona_value_moat',
            display_name: 'Value & Moat',
            signal: 'buy',
            confidence: 0.8,
          },
          'bad',
        ],
        conclusion: {
          final_signal: 'buy',
          consensus_level: 'medium',
        },
        dissenting_opinions: [
          { persona_id: 'persona_tail_risk', signal: 'sell' },
        ],
        divergence_points: [
          {
            kind: 'directional_opposition',
            summary_key: 'disagreement.point.strategy.directional_opposition',
            participants: ['persona_value_moat', '', 9],
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
    expect(normalized?.committeeDeliberation?.members).toEqual([
      {
        personaId: 'persona_value_moat',
        displayName: 'Value & Moat',
        signal: 'buy',
        confidence: 0.8,
      },
    ]);
    expect(normalized?.committeeDeliberation?.conclusion?.finalSignal).toBe('buy');
    expect(normalized?.committeeDeliberation?.dissentingOpinions?.[0].personaId).toBe(
      'persona_tail_risk',
    );
    expect(normalized?.committeeDeliberation?.divergencePoints?.[0].participants).toEqual([
      'persona_value_moat',
    ]);
    expect(normalized?.committeeDeliberation?.divergencePoints?.[0].conflictType).toBe(
      'directional_opposition',
    );
    expect(normalized?.committeeDeliberation?.divergencePoints?.[0].descriptionKey).toBe(
      'disagreement.point.strategy.directional_opposition',
    );
  });

  it('renders a committee-only payload for Signal/History review', () => {
    render(
      <ReportStructuredInsights
        insights={{
          schemaVersion: 'report-structured-insights-v1',
          committeeDeliberation: {
            conclusion: {
              finalSignal: 'hold',
              consensusLevel: 'low',
            },
            members: [
              {
                personaId: 'persona_value_moat',
                displayName: 'Value & Moat',
                signal: 'buy',
              },
            ],
            dissentingOpinions: [
              {
                personaId: 'persona_tail_risk',
                displayName: 'Tail Risk',
                signal: 'sell',
              },
            ],
          },
        }}
        language="en"
      />,
    );

    expect(screen.getByTestId('report-committee-deliberation')).toHaveTextContent(
      'Committee Conclusion',
    );
    expect(screen.getByTestId('report-committee-members')).toHaveTextContent('Value & Moat');
    expect(screen.getByTestId('report-committee-dissent')).toHaveTextContent('Tail Risk');
    expect(screen.queryByTestId('report-phase-decision')).not.toBeInTheDocument();
  });
});

const makeSkills = (count: number): ReportStrategySynthesisSkill[] => (
  Array.from({ length: count }, (_, index) => ({
    skillId: `skill_${index + 1}`,
    signal: 'buy',
    confidence: 0.5,
  }))
);

const makeMembers = (count: number): ReportCommitteeMember[] => (
  Array.from({ length: count }, (_, index) => ({
    personaId: `persona_${index + 1}`,
    displayName: `Member ${index + 1}`,
    signal: 'hold',
  }))
);

const makeConflicts = (count: number): ReportStrategySynthesisConflict[] => (
  Array.from({ length: count }, (_, index) => ({
    conflictType: 'directional_opposition',
    descriptionKey: `conflict_${index + 1}`,
    severity: 'medium',
    participants: [`skill_${index + 1}`],
  }))
);

const insightsWithLists = ({
  skills = 0,
  opposing = 0,
  members = 0,
  dissent = 0,
  conflicts = 0,
  divergences = 0,
}: {
  skills?: number;
  opposing?: number;
  members?: number;
  dissent?: number;
  conflicts?: number;
  divergences?: number;
}): ReportStructuredInsightsType => ({
  schemaVersion: 'report-structured-insights-v1',
  phaseDecision: {
    immediateAction: 'Wait for confirmation',
    confidenceReason: 'Volume confirmation is incomplete',
  },
  signalAttribution: {
    technicalIndicators: 50,
    strongestBullishSignal: 'Volume expansion',
  },
  strategySynthesis: {
    finalSignal: 'buy',
    supportingSkills: makeSkills(skills),
    opposingSkills: makeSkills(opposing).map((skill, index) => ({
      ...skill,
      skillId: `oppose_${index + 1}`,
    })),
    conflicts: makeConflicts(conflicts),
  },
  committeeDeliberation: {
    members: makeMembers(members),
    dissentingOpinions: makeMembers(dissent).map((member, index) => ({
      ...member,
      personaId: `dissent_${index + 1}`,
      displayName: `Dissent ${index + 1}`,
    })),
    divergencePoints: makeConflicts(divergences).map((point, index) => ({
      ...point,
      descriptionKey: `divergence_${index + 1}`,
    })),
  },
});

const visibleInsightNames = (testId: string): string[] => (
  [...screen.getByTestId(testId).querySelectorAll('[data-insight-item]')]
    .filter((node) => !node.hasAttribute('hidden'))
    .map((node) => node.getAttribute('data-insight-item') ?? '')
);

const allInsightNames = (testId: string): string[] => (
  [...screen.getByTestId(testId).querySelectorAll('[data-insight-item]')]
    .map((node) => node.getAttribute('data-insight-item') ?? '')
);

describe('ReportStructuredInsights top-N list disclosure', () => {
  it('keeps Phase and Attribution fully open when insight lists overflow', () => {
    render(
      <ReportStructuredInsights
        insights={insightsWithLists({ skills: 5, members: 5, conflicts: 5 })}
        language="en"
      />,
    );

    expect(screen.getByTestId('report-phase-decision')).toHaveTextContent('Wait for confirmation');
    expect(screen.getByTestId('report-signal-attribution')).toHaveTextContent('Volume expansion');
    expect(screen.queryByTestId('report-phase-decision-disclosure')).not.toBeInTheDocument();
    expect(screen.queryByTestId('report-signal-attribution-disclosure')).not.toBeInTheDocument();
  });

  it.each([
    { section: 'skills', testId: 'report-supporting-skills', fixture: { skills: 0 }, name: 'skill_1' },
    { section: 'committee', testId: 'report-committee-members', fixture: { members: 0 }, name: 'Member 1' },
    { section: 'conflicts', testId: 'report-strategy-conflicts', fixture: { conflicts: 0 }, name: 'conflict_1' },
  ] as const)('omits the $section list and toggle when it has 0 items', ({ testId, fixture }) => {
    render(<ReportStructuredInsights insights={insightsWithLists(fixture)} language="en" />);

    expect(screen.queryByTestId(testId)).not.toBeInTheDocument();
    expect(screen.queryByTestId(`${testId}-disclosure`)).not.toBeInTheDocument();
    expect(screen.getByTestId('report-phase-decision')).toBeInTheDocument();
  });

  it.each([
    {
      count: 1,
      section: 'skills',
      testId: 'report-supporting-skills',
      fixture: { skills: 1 },
      visible: ['skill_1'],
    },
    {
      count: 3,
      section: 'skills',
      testId: 'report-supporting-skills',
      fixture: { skills: 3 },
      visible: ['skill_1', 'skill_2', 'skill_3'],
    },
    {
      count: 1,
      section: 'committee',
      testId: 'report-committee-members',
      fixture: { members: 1 },
      visible: ['Member 1'],
    },
    {
      count: 3,
      section: 'committee',
      testId: 'report-committee-members',
      fixture: { members: 3 },
      visible: ['Member 1', 'Member 2', 'Member 3'],
    },
    {
      count: 1,
      section: 'conflicts',
      testId: 'report-strategy-conflicts',
      fixture: { conflicts: 1 },
      visible: ['directional_opposition-0'],
    },
    {
      count: 3,
      section: 'conflicts',
      testId: 'report-strategy-conflicts',
      fixture: { conflicts: 3 },
      visible: [
        'directional_opposition-0',
        'directional_opposition-1',
        'directional_opposition-2',
      ],
    },
  ] as const)(
    'shows all $count $section items without a disclosure control',
    ({ testId, fixture, visible }) => {
      render(<ReportStructuredInsights insights={insightsWithLists(fixture)} language="en" />);

      expect(visibleInsightNames(testId)).toEqual([...visible]);
      expect(screen.queryByTestId(`${testId}-disclosure`)).not.toBeInTheDocument();
    },
  );

  it.each([
    {
      section: 'skills',
      testId: 'report-supporting-skills',
      fixture: { skills: 4 },
      preview: ['skill_1', 'skill_2', 'skill_3'],
      full: ['skill_1', 'skill_2', 'skill_3', 'skill_4'],
    },
    {
      section: 'committee',
      testId: 'report-committee-members',
      fixture: { members: 5 },
      preview: ['Member 1', 'Member 2', 'Member 3'],
      full: ['Member 1', 'Member 2', 'Member 3', 'Member 4', 'Member 5'],
    },
    {
      section: 'conflicts',
      testId: 'report-strategy-conflicts',
      fixture: { conflicts: 4 },
      preview: [
        'directional_opposition-0',
        'directional_opposition-1',
        'directional_opposition-2',
      ],
      full: [
        'directional_opposition-0',
        'directional_opposition-1',
        'directional_opposition-2',
        'directional_opposition-3',
      ],
    },
  ] as const)(
    'shows the first $preview.length $section items and the exact remaining count behind Show all',
    ({ testId, fixture, preview, full }) => {
      render(<ReportStructuredInsights insights={insightsWithLists(fixture)} language="en" />);

      expect(preview).toHaveLength(REPORT_INSIGHT_LIST_PREVIEW_LIMIT);
      expect(visibleInsightNames(testId)).toEqual([...preview]);
      expect(allInsightNames(testId)).toEqual([...full]);
      const toggle = screen.getByTestId(`${testId}-disclosure`);
      expect(toggle).toHaveTextContent(`Show all (${full.length})`);
      expect(toggle).toHaveAttribute('aria-expanded', 'false');
    },
  );

  it('reveals and collapses overflowing items while preserving source order', () => {
    render(
      <ReportStructuredInsights
        insights={insightsWithLists({ skills: 5 })}
        language="en"
      />,
    );

    const toggle = screen.getByTestId('report-supporting-skills-disclosure');
    expect(visibleInsightNames('report-supporting-skills')).toEqual([
      'skill_1',
      'skill_2',
      'skill_3',
    ]);

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveTextContent('Show less');
    expect(visibleInsightNames('report-supporting-skills')).toEqual([
      'skill_1',
      'skill_2',
      'skill_3',
      'skill_4',
      'skill_5',
    ]);

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveTextContent('Show all (5)');
    expect(visibleInsightNames('report-supporting-skills')).toEqual([
      'skill_1',
      'skill_2',
      'skill_3',
    ]);
  });

  it('expands Skills, Committee, and Conflicts independently', () => {
    render(
      <ReportStructuredInsights
        insights={insightsWithLists({ skills: 4, members: 4, conflicts: 4 })}
        language="en"
      />,
    );

    fireEvent.click(screen.getByTestId('report-supporting-skills-disclosure'));

    expect(visibleInsightNames('report-supporting-skills')).toEqual([
      'skill_1',
      'skill_2',
      'skill_3',
      'skill_4',
    ]);
    expect(visibleInsightNames('report-committee-members')).toEqual([
      'Member 1',
      'Member 2',
      'Member 3',
    ]);
    expect(visibleInsightNames('report-strategy-conflicts')).toEqual([
      'directional_opposition-0',
      'directional_opposition-1',
      'directional_opposition-2',
    ]);
    expect(screen.getByTestId('report-committee-members-disclosure'))
      .toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByTestId('report-strategy-conflicts-disclosure'))
      .toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(screen.getByTestId('report-committee-members-disclosure'));
    expect(visibleInsightNames('report-committee-members')).toContain('Member 4');
    expect(visibleInsightNames('report-strategy-conflicts')).not.toContain(
      'directional_opposition-3',
    );

    fireEvent.click(screen.getByTestId('report-strategy-conflicts-disclosure'));
    expect(visibleInsightNames('report-strategy-conflicts')).toContain(
      'directional_opposition-3',
    );
    expect(visibleInsightNames('report-supporting-skills')).toContain('skill_4');
  });

  it('wires keyboard-accessible shared Button disclosure controls', () => {
    render(
      <ReportStructuredInsights
        insights={insightsWithLists({ skills: 4, members: 4, conflicts: 4 })}
        language="en"
      />,
    );

    const skillsToggle = screen.getByRole('button', {
      name: 'Supporting Strategies: Show all (4)',
    });
    const committeeToggle = screen.getByRole('button', {
      name: 'Member Stances: Show all (4)',
    });
    const conflictsToggle = screen.getByRole('button', {
      name: 'Strategy Conflicts: Show all (4)',
    });

    expect(skillsToggle).toHaveAttribute('data-control', 'button');
    expect(skillsToggle).toHaveAttribute('type', 'button');
    expect(skillsToggle).not.toHaveAttribute('tabIndex', '-1');

    const skillsPanel = document.getElementById(skillsToggle.getAttribute('aria-controls')!);
    expect(skillsPanel).not.toBeNull();
    expect(screen.getByTestId('report-supporting-skills')).toContainElement(skillsPanel);

    skillsToggle.focus();
    expect(skillsToggle).toHaveFocus();
    fireEvent.keyDown(skillsToggle, { key: 'Enter', code: 'Enter' });
    fireEvent.click(skillsToggle);
    expect(skillsToggle).toHaveAttribute('aria-expanded', 'true');
    expect(skillsToggle).toHaveAccessibleName('Supporting Strategies: Show less');

    committeeToggle.focus();
    expect(committeeToggle).toHaveFocus();
    fireEvent.keyDown(committeeToggle, { key: ' ', code: 'Space' });
    fireEvent.click(committeeToggle);
    expect(committeeToggle).toHaveAttribute('aria-expanded', 'true');
    expect(conflictsToggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('localizes Show all / Show less when the report language changes', () => {
    const { rerender } = render(
      <ReportStructuredInsights
        insights={insightsWithLists({ skills: 4 })}
        language="en"
      />,
    );

    const englishToggle = screen.getByTestId('report-supporting-skills-disclosure');
    expect(englishToggle).toHaveTextContent('Show all (4)');
    fireEvent.click(englishToggle);
    expect(englishToggle).toHaveTextContent('Show less');

    rerender(
      <ReportStructuredInsights
        insights={insightsWithLists({ skills: 4 })}
        language="zh"
      />,
    );
    const chineseToggle = screen.getByTestId('report-supporting-skills-disclosure');
    expect(chineseToggle).toHaveTextContent('收起');
    expect(chineseToggle).toHaveAccessibleName('支持策略: 收起');

    rerender(
      <ReportStructuredInsights
        insights={insightsWithLists({ skills: 4 })}
        language="ko"
      />,
    );
    expect(screen.getByTestId('report-supporting-skills-disclosure')).toHaveTextContent('간략히');

    rerender(
      <ReportStructuredInsights
        insights={insightsWithLists({ skills: 4 })}
        language="zh"
      />,
    );
    fireEvent.click(screen.getByTestId('report-supporting-skills-disclosure'));
    expect(screen.getByTestId('report-supporting-skills-disclosure')).toHaveTextContent(
      '展开全部（4）',
    );
  });

  it('keeps empty, malformed, and partial fallback contracts unchanged', () => {
    const { rerender } = render(<ReportStructuredInsights language="en" />);
    expect(screen.queryByTestId('report-structured-insights')).not.toBeInTheDocument();

    rerender(
      <ReportStructuredInsights
        insights={{ schemaVersion: 'report-structured-insights-v1' }}
        language="en"
      />,
    );
    expect(screen.queryByTestId('report-structured-insights')).not.toBeInTheDocument();

    rerender(
      <ReportStructuredInsights
        insights={{
          schemaVersion: 'report-structured-insights-v1',
          strategySynthesis: { supportingSkills: makeSkills(4) },
        }}
        language="en"
      />,
    );
    expect(screen.getByTestId('report-supporting-skills-disclosure')).toHaveTextContent(
      'Show all (4)',
    );
    expect(screen.queryByTestId('report-committee-members')).not.toBeInTheDocument();
    expect(screen.queryByTestId('report-strategy-conflicts')).not.toBeInTheDocument();
  });
});
