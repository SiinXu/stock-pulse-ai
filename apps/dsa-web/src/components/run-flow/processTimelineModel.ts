// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Process timeline view-model for run-flow agent events.
 *
 * Consumes the existing `/flow` projection (run-flow events + agent attrs).
 * Does not invent a parallel event source. When unified run-trace (#1125) lands,
 * switch TRACE_EVENT_SOURCE to 'unified_trace' and implement that branch only.
 */

import type { RunFlowEvent, RunFlowSnapshot } from '../../types/runFlow';

/** Trace source switch for #1125. Keep run_flow until unified surface is shipped. */
export type TraceEventSource = 'run_flow' | 'unified_trace';

/** Active source. Change only when #1125 provides a stable consumer contract. */
export const TRACE_EVENT_SOURCE: TraceEventSource = 'run_flow';

export type ProcessTimelineKind =
  | 'phase'
  | 'tool'
  | 'model'
  | 'decision'
  | 'other';

export type ProcessTimelineStatus =
  | 'running'
  | 'success'
  | 'failed'
  | 'warning'
  | 'info'
  | 'unknown';

export interface ProcessTimelineField {
  key: string;
  value: string;
}

export interface ProcessTimelineItem {
  id: string;
  kind: ProcessTimelineKind;
  title: string;
  /** Server-provided message only; never model-authored narrative. */
  message: string | null;
  status: ProcessTimelineStatus;
  timestamp: string | null;
  durationMs: number | null;
  step: number | null;
  nodeId: string | null;
  sequence: number | null;
  /** Observable "what" facts from the trace (name, type, phase, tool, step). */
  what: ProcessTimelineField[];
  /** Observable "why" facts from real attrs only (reason, failure_reason, plan ids, …). */
  why: ProcessTimelineField[];
}

export interface ProcessTimelineModel {
  source: TraceEventSource;
  items: ProcessTimelineItem[];
  hasAgentEvents: boolean;
}

const SENSITIVE_KEY_PATTERN = /(?:api[_-]?key|apikey|authorization|token|secret|password|prompt|system_prompt|messages|raw_response|completion|input_text|output_text|cookie|credential)/i;

const WHY_ATTR_KEYS = new Set([
  'reason',
  'failure_reason',
  'failureReason',
  'status',
  'success',
  'plan_id',
  'planId',
  'previous_plan_id',
  'previousPlanId',
  'new_plan_id',
  'newPlanId',
  'failed_step_id',
  'failedStepId',
  'observation_replans',
  'observationReplans',
  'expected_tools',
  'expectedTools',
  'tool_call_count',
  'toolCallCount',
  'cached',
  'result_length',
  'resultLength',
  'total_steps',
  'totalSteps',
  'total_tokens',
  'totalTokens',
  'goal_chars',
  'goalChars',
  'max_total_tool_calls',
  'maxTotalToolCalls',
  'step_count',
  'stepCount',
  'replan_index',
  'replanIndex',
  'error_code',
  'errorCode',
]);

const asRecord = (value: unknown): Record<string, unknown> | null => (
  value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
);

const asText = (value: unknown): string | null => (
  typeof value === 'string' && value.trim() ? value.trim() : null
);

const asNumber = (value: unknown): number | null => (
  typeof value === 'number' && Number.isFinite(value) ? value : null
);

const asNonNegativeInt = (value: unknown): number | null => {
  const n = asNumber(value);
  if (n === null || !Number.isInteger(n) || n < 0) return null;
  return n;
};

export const isSensitiveTraceKey = (key: string): boolean => {
  const normalized = key.trim().toLowerCase().replace(/-/g, '_');
  if (!normalized) return true;
  if (SENSITIVE_KEY_PATTERN.test(normalized)) return true;
  if (normalized.includes('authorization') || normalized.includes('bearer')) return true;
  return false;
};

const formatFieldValue = (value: unknown): string | null => {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'string') {
    const text = value.trim();
    if (!text) return null;
    return text.length > 160 ? `${text.slice(0, 157)}...` : text;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (Array.isArray(value)) {
    const parts = value
      .slice(0, 8)
      .map((item) => formatFieldValue(item))
      .filter((item): item is string => Boolean(item));
    if (parts.length === 0) return null;
    return parts.join(', ');
  }
  try {
    const text = JSON.stringify(value);
    if (!text || text === '{}' || text === '[]') return null;
    return text.length > 160 ? `${text.slice(0, 157)}...` : text;
  } catch {
    return null;
  }
};

/** Defense-in-depth redaction for client display of server attrs. */
export const redactTraceRecord = (
  value: Record<string, unknown> | null | undefined,
): Record<string, unknown> => {
  if (!value) return {};
  const out: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value)) {
    if (isSensitiveTraceKey(key)) {
      out[key] = '<redacted>';
      continue;
    }
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      out[key] = redactTraceRecord(item as Record<string, unknown>);
      continue;
    }
    if (typeof item === 'string' && /(?:sk-|Bearer\s|api[_-]?key\s*=)/i.test(item)) {
      out[key] = '<redacted>';
      continue;
    }
    out[key] = item;
  }
  return out;
};

const resolveEventType = (event: RunFlowEvent): string => {
  const metadata = asRecord(event.metadata) ?? {};
  return (
    asText(metadata.eventType)
    || asText(metadata.event_type)
    || event.type
    || ''
  );
};

const classifyKind = (eventType: string): ProcessTimelineKind => {
  const normalized = eventType.toLowerCase().replace(/\./g, '_');
  if (normalized.includes('phase')) return 'phase';
  if (normalized.includes('tool')) return 'tool';
  if (normalized.includes('model')) return 'model';
  if (normalized.includes('decision')) return 'decision';
  if (normalized.startsWith('agent_') || normalized.startsWith('agent.')) return 'other';
  return 'other';
};

const classifyStatus = (
  event: RunFlowEvent,
  metadata: Record<string, unknown>,
): ProcessTimelineStatus => {
  const raw = (
    asText(metadata.status)
    || asText(asRecord(metadata.attrs)?.status)
    || ''
  ).toLowerCase();
  if (raw === 'running' || raw === 'started' || raw === 'in_progress') return 'running';
  if (raw === 'success' || raw === 'ok' || raw === 'completed' || raw === 'done') return 'success';
  if (raw === 'failed' || raw === 'error' || raw === 'fail') return 'failed';
  if (raw === 'cancelled' || raw === 'timeout' || raw === 'degraded' || raw === 'fallback') {
    return 'warning';
  }
  if (event.severity === 'danger') return 'failed';
  if (event.severity === 'warning') return 'warning';
  if (event.severity === 'success') return 'success';
  if (event.severity === 'info') return 'info';
  return 'unknown';
};

const isAgentLikeEvent = (event: RunFlowEvent): boolean => {
  const eventType = resolveEventType(event);
  const normalized = eventType.toLowerCase();
  return normalized.startsWith('agent_')
    || normalized.startsWith('agent.')
    || Boolean(asText(asRecord(event.metadata)?.eventType)?.startsWith('agent.'))
    || Boolean(asText(asRecord(event.metadata)?.event_type)?.startsWith('agent.'));
};

const pushField = (
  fields: ProcessTimelineField[],
  key: string,
  value: unknown,
): void => {
  if (isSensitiveTraceKey(key)) {
    fields.push({ key, value: '<redacted>' });
    return;
  }
  const formatted = formatFieldValue(value);
  if (formatted === null) return;
  if (fields.some((field) => field.key === key)) return;
  fields.push({ key, value: formatted });
};

const buildWhat = (
  event: RunFlowEvent,
  eventType: string,
  kind: ProcessTimelineKind,
  metadata: Record<string, unknown>,
  attrs: Record<string, unknown>,
): ProcessTimelineField[] => {
  const fields: ProcessTimelineField[] = [];
  pushField(fields, 'event_type', eventType);
  pushField(fields, 'kind', kind);
  pushField(fields, 'title', event.title);
  const phase = asText(metadata.phase) || asText(attrs.phase);
  if (phase) pushField(fields, 'phase', phase);
  const tool = asText(metadata.tool) || asText(attrs.tool);
  if (tool) pushField(fields, 'tool', tool);
  const model = asText(metadata.model) || asText(attrs.model);
  if (model) pushField(fields, 'model', model);
  const step = asNonNegativeInt(metadata.step) ?? asNonNegativeInt(attrs.step);
  if (step !== null) pushField(fields, 'step', step);
  const status = asText(metadata.status);
  if (status) pushField(fields, 'status', status);
  if (event.message) pushField(fields, 'message', event.message);
  return fields;
};

const buildWhy = (attrs: Record<string, unknown>): ProcessTimelineField[] => {
  const fields: ProcessTimelineField[] = [];
  for (const [key, value] of Object.entries(attrs)) {
    // Surface redacted sensitive keys so leakage is visible as <redacted>, not dropped.
    if (isSensitiveTraceKey(key)) {
      pushField(fields, key, '<redacted>');
      continue;
    }
    if (!WHY_ATTR_KEYS.has(key) && !/reason|failure|plan|replan|success|cached|error/i.test(key)) {
      continue;
    }
    if (key === 'status' && fields.some((field) => field.key === 'status')) continue;
    pushField(fields, key, value);
  }
  return fields;
};

const projectEvent = (event: RunFlowEvent): ProcessTimelineItem | null => {
  if (!isAgentLikeEvent(event)) return null;
  const metadata = asRecord(event.metadata) ?? {};
  const eventType = resolveEventType(event);
  const kind = classifyKind(eventType);
  const rawAttrs = asRecord(metadata.attrs) ?? {};
  const attrs = redactTraceRecord(rawAttrs);
  const durationRaw = metadata.duration_ms ?? metadata.durationMs ?? attrs.duration_ms ?? attrs.durationMs;
  const durationMs = asNonNegativeInt(durationRaw);

  return {
    id: event.id,
    kind,
    title: event.title || eventType || 'agent',
    message: event.message ?? null,
    status: classifyStatus(event, metadata),
    timestamp: event.timestamp ?? null,
    durationMs,
    step: asNonNegativeInt(metadata.step),
    nodeId: event.nodeId ?? null,
    sequence: asNonNegativeInt(metadata.sequence),
    what: buildWhat(event, eventType, kind, metadata, attrs),
    why: buildWhy(attrs),
  };
};

/**
 * Build a process timeline from a run-flow snapshot (or future unified trace).
 * Returns empty items when the active source has no agent events.
 */
export const buildProcessTimeline = (
  snapshot: RunFlowSnapshot | null | undefined,
  source: TraceEventSource = TRACE_EVENT_SOURCE,
): ProcessTimelineModel => {
  if (!snapshot) {
    return { source, items: [], hasAgentEvents: false };
  }

  if (source === 'unified_trace') {
    // #1125 switch point: consume unified run-trace events when available.
    // Until that contract lands, fall through is intentional (empty, not invented).
    return { source, items: [], hasAgentEvents: false };
  }

  const items = snapshot.events
    .map((event, index) => ({ item: projectEvent(event), index }))
    .filter((entry): entry is { item: ProcessTimelineItem; index: number } => entry.item !== null)
    .sort((left, right) => {
      const leftSeq = left.item.sequence ?? Number.MAX_SAFE_INTEGER;
      const rightSeq = right.item.sequence ?? Number.MAX_SAFE_INTEGER;
      if (leftSeq !== rightSeq) return leftSeq - rightSeq;
      const leftTime = left.item.timestamp ? Date.parse(left.item.timestamp) || 0 : 0;
      const rightTime = right.item.timestamp ? Date.parse(right.item.timestamp) || 0 : 0;
      if (leftTime !== rightTime) return leftTime - rightTime;
      return left.index - right.index;
    })
    .map((entry) => entry.item);

  return {
    source,
    items,
    hasAgentEvents: items.length > 0,
  };
};
