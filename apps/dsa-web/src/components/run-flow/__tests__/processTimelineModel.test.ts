// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import type { RunFlowEvent, RunFlowSnapshot } from '../../../types/runFlow';
import {
  buildProcessTimeline,
  isSensitiveTraceKey,
  redactTraceRecord,
} from '../processTimelineModel';

const agentEvent = (
  id: string,
  sequence: number,
  type: string,
  title: string,
  extra: Record<string, unknown> = {},
): RunFlowEvent => ({
  id,
  timestamp: `2026-08-12T10:00:${String(sequence).padStart(2, '0')}Z`,
  severity: type.includes('end') || type.includes('decision') ? 'success' : 'info',
  type,
  nodeId: `node-${id}`,
  title,
  message: `${title} message`,
  metadata: {
    schemaVersion: 1,
    sequence,
    eventType: type.replaceAll('_', '.'),
    traceId: 'trace-1',
    spanId: `span-${sequence}`,
    status: type.endsWith('_start') ? 'running' : 'success',
    duration_ms: type.endsWith('_start') ? null : 120,
    step: sequence,
    detailIntegrity: 'valid',
    ...extra,
  },
});

const snapshot = (events: RunFlowEvent[]): RunFlowSnapshot => ({
  taskId: 'task-1',
  traceId: 'trace-1',
  stockCode: '600519',
  status: 'success',
  generatedAt: '2026-08-12T10:05:00Z',
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

describe('processTimeline', () => {
  it('projects agent events into ordered timeline items with real what/why fields', () => {
    const model = buildProcessTimeline(snapshot([
      agentEvent('e2', 2, 'agent_tool_end', '工具完成: get_quote', {
        tool: 'get_quote',
        attrs: {
          success: true,
          cached: false,
          result_length: 42,
          api_key: 'should-not-leak',
        },
      }),
      agentEvent('e1', 1, 'agent_phase_start', '阶段开始: plan_step', {
        phase: 'plan_step',
        attrs: {
          expected_tools: ['get_quote'],
          goal_chars: 18,
        },
      }),
      {
        id: 'non-agent',
        severity: 'info',
        type: 'history_run',
        title: '历史保存成功',
        metadata: {},
      },
    ]));

    expect(model.source).toBe('run_flow');
    expect(model.hasAgentEvents).toBe(true);
    expect(model.items).toHaveLength(2);
    expect(model.items[0].sequence).toBe(1);
    expect(model.items[0].kind).toBe('phase');
    expect(model.items[0].what.some((field) => field.key === 'phase' && field.value === 'plan_step')).toBe(true);
    expect(model.items[0].why.some((field) => field.key === 'expected_tools')).toBe(true);
    expect(model.items[1].kind).toBe('tool');
    expect(model.items[1].durationMs).toBe(120);
    expect(model.items[1].why.some((field) => field.key === 'success' && field.value === 'true')).toBe(true);
    expect(model.items[1].why.some((field) => field.value === 'should-not-leak')).toBe(false);
    expect(model.items[1].why.some((field) => field.key === 'api_key' && field.value === '<redacted>')).toBe(true);
  });

  it('returns empty when unified_trace source is selected before #1125 lands', () => {
    const model = buildProcessTimeline(snapshot([
      agentEvent('e1', 1, 'agent_phase_start', '阶段开始: agent_loop'),
    ]), 'unified_trace');
    expect(model.source).toBe('unified_trace');
    expect(model.items).toEqual([]);
    expect(model.hasAgentEvents).toBe(false);
  });

  it('redacts sensitive keys client-side', () => {
    expect(isSensitiveTraceKey('api_key')).toBe(true);
    expect(isSensitiveTraceKey('authorization')).toBe(true);
    expect(isSensitiveTraceKey('failure_reason')).toBe(false);
    const redacted = redactTraceRecord({
      failure_reason: 'timeout',
      token: 'secret-value',
      nested: { password: 'x', ok: 1 },
    });
    expect(redacted.failure_reason).toBe('timeout');
    expect(redacted.token).toBe('<redacted>');
    expect((redacted.nested as Record<string, unknown>).password).toBe('<redacted>');
    expect((redacted.nested as Record<string, unknown>).ok).toBe(1);
  });
});
