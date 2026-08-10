import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { RunFlowEvent, RunFlowSnapshot } from '../../../types/runFlow';
import AgentReplayInspector from '../AgentReplayInspector';

const replayEvent = (
  id: string,
  sequence: number,
  type: string,
  nodeId: string,
  extraMetadata: Record<string, unknown> = {},
): RunFlowEvent => ({
  id,
  timestamp: '2026-08-10T10:00:00Z',
  severity: type.endsWith('error') ? 'danger' : 'success',
  type,
  nodeId,
  title: type,
  metadata: {
    schemaVersion: 1,
    sequence,
    eventType: type.replaceAll('_', '.'),
    traceId: 'trace-replay',
    spanId: `span-${sequence}`,
    status: type.endsWith('error') ? 'failed' : 'success',
    detailIntegrity: 'valid',
    ...extraMetadata,
  },
});

const snapshot = (events: RunFlowEvent[]): RunFlowSnapshot => ({
  taskId: 'task-replay',
  traceId: 'trace-replay',
  stockCode: '600519',
  status: 'success',
  generatedAt: '2026-08-10T10:01:00Z',
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

describe('AgentReplayInspector', () => {
  it('uses sequence order and moves the selected run-flow node with the cursor', () => {
    const onSelectNode = vi.fn();
    const capture = {
      originalCount: 2,
      returnedCount: 2,
      droppedCount: 0,
      truncated: false,
    };
    render(
      <AgentReplayInspector
        snapshot={snapshot([
          replayEvent('event-2', 2, 'agent_tool_end', 'tool-node', { attrs: { result: 'ok' }, capture }),
          replayEvent('event-1', 1, 'agent_phase_start', 'phase-node', { attrs: { phase: 'analysis' }, capture }),
        ])}
        onSelectNode={onSelectNode}
      />,
    );

    expect(screen.getByTestId('agent-replay-position')).toHaveTextContent('1 / 2');
    expect(screen.getByText(/"event_type": "agent_phase_start"/)).toBeInTheDocument();
    expect(screen.getByTestId('agent-replay-integrity-badge')).toHaveTextContent('完整');
    expect(screen.getByText(/"phase": "analysis"/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '下一个 Agent 事件' }));

    expect(screen.getByTestId('agent-replay-position')).toHaveTextContent('2 / 2');
    expect(screen.getByText(/"event_type": "agent_tool_end"/)).toBeInTheDocument();
    expect(onSelectNode).toHaveBeenCalledWith('tool-node');
  });

  it('marks failed or unsupported version evidence invalid', () => {
    render(
      <AgentReplayInspector
        snapshot={snapshot([
          replayEvent('event-error', 1, 'agent_error', 'error-node', {
            schemaVersion: 2,
            capture: {
              originalCount: 1,
              returnedCount: 1,
              droppedCount: 0,
              truncated: false,
            },
          }),
        ])}
      />,
    );

    expect(screen.getByTestId('agent-replay-integrity-badge')).toHaveTextContent('无效');
    expect(screen.getByText('事件的序列、版本、Trace、明细或捕获计数不一致。')).toBeInTheDocument();
    expect(screen.getByText(/"event_type": "agent_error"/)).toBeInTheDocument();
  });

  it('treats a capture-truncated sequence prefix as partial but internally consistent', () => {
    const capture = {
      originalCount: 4,
      returnedCount: 2,
      droppedCount: 2,
      truncated: true,
    };
    render(
      <AgentReplayInspector
        snapshot={snapshot([
          replayEvent('event-3', 3, 'agent_model_start', 'model-node', { capture }),
          replayEvent('event-4', 4, 'agent_model_end', 'model-node', { capture }),
        ])}
      />,
    );

    expect(screen.getByTestId('agent-replay-integrity-badge')).toHaveTextContent('部分');
    expect(screen.getByText(/有 2 条事件被丢弃/)).toBeInTheDocument();
  });

  it('reports internal sequence gaps even when capture accounting dropped none', () => {
    const capture = {
      originalCount: 2,
      returnedCount: 2,
      droppedCount: 0,
      truncated: false,
    };
    render(
      <AgentReplayInspector
        snapshot={snapshot([
          replayEvent('event-1', 1, 'agent_phase_start', 'phase-node', { capture }),
          replayEvent('event-3', 3, 'agent_phase_end', 'phase-node', { capture }),
        ])}
      />,
    );

    expect(screen.getByTestId('agent-replay-integrity-badge')).toHaveTextContent('部分');
    expect(screen.getByText(/有 1 条事件被丢弃/)).toBeInTheDocument();
  });

  it('renders an explicit empty replay state', () => {
    render(<AgentReplayInspector snapshot={snapshot([])} />);

    expect(screen.getByText('当前运行没有可回放的 Agent 事件。')).toBeInTheDocument();
    expect(screen.queryByTestId('agent-replay-position')).not.toBeInTheDocument();
  });
});
