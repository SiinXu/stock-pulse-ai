// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { RunFlowEvent, RunFlowSnapshot } from '../../../types/runFlow';
import { ProcessTimeline } from '../ProcessTimeline';

const agentEvent = (
  id: string,
  sequence: number,
  type: string,
  title: string,
  attrs: Record<string, unknown> = {},
): RunFlowEvent => ({
  id,
  timestamp: '2026-08-12T10:00:00Z',
  severity: 'success',
  type,
  nodeId: `node-${id}`,
  title,
  message: `${title} · step=${sequence}`,
  metadata: {
    schemaVersion: 1,
    sequence,
    eventType: type.replaceAll('_', '.'),
    status: 'success',
    duration_ms: 250,
    step: sequence,
    detailIntegrity: 'valid',
    attrs,
  },
});

const snapshot = (events: RunFlowEvent[]): RunFlowSnapshot => ({
  taskId: 'task-timeline',
  traceId: 'trace-timeline',
  stockCode: '600519',
  status: 'success',
  generatedAt: '2026-08-12T10:01:00Z',
  summary: {
    failedAttempts: 0,
    fallbackCount: 0,
    dataSourceCount: 0,
    eventCount: events.length,
  },
  lanes: [],
  nodes: [],
  edges: [],
  events,
});

describe('ProcessTimeline', () => {
  it('renders stage/tool timeline and expands real why attrs without inventing prose', () => {
    const onSelectNode = vi.fn();
    render(
      <ProcessTimeline
        snapshot={snapshot([
          agentEvent('phase', 1, 'agent_phase_end', '阶段结束: plan_execution', {
            reason: 'execution_timeout',
            success: false,
          }),
          agentEvent('tool', 2, 'agent_tool_end', '工具完成: get_daily_history', {
            success: true,
            cached: true,
          }),
        ])}
        onSelectNode={onSelectNode}
      />,
    );

    expect(screen.getByTestId('process-timeline')).toHaveAttribute('data-trace-source', 'run_flow');
    expect(screen.getAllByTestId('process-timeline-item')).toHaveLength(2);
    expect(screen.getAllByTestId('process-timeline-duration')[0]).toHaveTextContent('250');

    const items = screen.getAllByTestId('process-timeline-item');
    const firstToggle = screen.getAllByRole('button', { name: /查看详情/ })[0];
    fireEvent.click(firstToggle);

    expect(items[0].querySelector('[data-testid="process-timeline-why"]')).toHaveTextContent('execution_timeout');
    expect(items[0].querySelector('[data-testid="process-timeline-what"]')).toHaveTextContent('event_type');
    expect(screen.queryByText(/因为模型认为/)).not.toBeInTheDocument();
  });

  it('hides entirely when hideWhenEmpty and no agent events', () => {
    const { container } = render(
      <ProcessTimeline
        hideWhenEmpty
        snapshot={snapshot([{
          id: 'history',
          severity: 'info',
          type: 'history_run',
          title: '历史保存成功',
          metadata: {},
        }])}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
