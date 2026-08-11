import type { RunFlowEvent } from '../../types/runFlow';

export const SUPPORTED_AGENT_REPLAY_SCHEMA_VERSION = 1;

export type AgentReplayIntegrityStatus = 'complete' | 'warning' | 'invalid';

export interface AgentReplayCapture {
  originalCount: number;
  returnedCount: number;
  droppedCount: number;
  truncated: boolean;
}

export interface AgentReplayEntry {
  event: RunFlowEvent;
  sequence: number | null;
  schemaVersion: number | null;
  traceId: string | null;
  spanId: string | null;
  parentSpanId: string | null;
  step: number | null;
  status: string | null;
  attrs: Record<string, unknown> | null;
  payload: Record<string, unknown> | null;
  detailIntegrity: string | null;
}

export interface AgentReplayIntegrity {
  status: AgentReplayIntegrityStatus;
  gapCount: number;
  duplicateCount: number;
  missingSequenceCount: number;
  invalidVersionCount: number;
  traceMismatchCount: number;
  invalidDetailCount: number;
  capture: AgentReplayCapture | null;
  captureMismatch: boolean;
}

export interface AgentReplayModel {
  entries: AgentReplayEntry[];
  integrity: AgentReplayIntegrity;
}

const asRecord = (value: unknown): Record<string, unknown> | null => (
  value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
);

const asPositiveInteger = (value: unknown): number | null => (
  typeof value === 'number' && Number.isInteger(value) && value >= 1 ? value : null
);

const asNonNegativeInteger = (value: unknown): number | null => (
  typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null
);

const asText = (value: unknown): string | null => (
  typeof value === 'string' && value.trim() ? value.trim() : null
);

const isAgentEvent = (event: RunFlowEvent): boolean => {
  const metadata = asRecord(event.metadata);
  const eventType = asText(metadata?.eventType ?? metadata?.event_type);
  return event.type.startsWith('agent_') || Boolean(eventType?.startsWith('agent.'));
};

const readEntry = (event: RunFlowEvent): AgentReplayEntry => {
  const metadata = asRecord(event.metadata) ?? {};
  return {
    event,
    sequence: asPositiveInteger(metadata.sequence),
    schemaVersion: asPositiveInteger(metadata.schemaVersion ?? metadata.schema_version),
    traceId: asText(metadata.traceId ?? metadata.trace_id),
    spanId: asText(metadata.spanId ?? metadata.span_id),
    parentSpanId: asText(metadata.parentSpanId ?? metadata.parent_span_id),
    step: asNonNegativeInteger(metadata.step),
    status: asText(metadata.status),
    attrs: asRecord(metadata.attrs),
    payload: asRecord(metadata.payload),
    detailIntegrity: asText(metadata.detailIntegrity ?? metadata.detail_integrity),
  };
};

const readCapture = (entries: AgentReplayEntry[]): AgentReplayCapture | null => {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const metadata = asRecord(entries[index].event.metadata);
    const capture = asRecord(metadata?.capture);
    if (!capture) continue;
    const originalCount = asNonNegativeInteger(capture.originalCount ?? capture.original_count);
    const returnedCount = asNonNegativeInteger(capture.returnedCount ?? capture.returned_count);
    const droppedCount = asNonNegativeInteger(capture.droppedCount ?? capture.dropped_count);
    if (
      originalCount === null
      || returnedCount === null
      || droppedCount === null
      || typeof capture.truncated !== 'boolean'
    ) {
      return null;
    }
    return { originalCount, returnedCount, droppedCount, truncated: capture.truncated };
  }
  return null;
};

export const buildAgentReplayModel = (
  events: RunFlowEvent[],
  snapshotTraceId?: string | null,
): AgentReplayModel => {
  const entries = events
    .filter(isAgentEvent)
    .map((event, sourceIndex) => ({ ...readEntry(event), sourceIndex }))
    .sort((left, right) => (
      (left.sequence ?? Number.MAX_SAFE_INTEGER) - (right.sequence ?? Number.MAX_SAFE_INTEGER)
      || left.sourceIndex - right.sourceIndex
    ));

  const capture = readCapture(entries);
  const sequences = entries
    .map((entry) => entry.sequence)
    .filter((sequence): sequence is number => sequence !== null);
  const sequenceCounts = new Map<number, number>();
  sequences.forEach((sequence) => sequenceCounts.set(sequence, (sequenceCounts.get(sequence) ?? 0) + 1));
  const duplicateCount = [...sequenceCounts.values()].reduce(
    (count, occurrences) => count + Math.max(0, occurrences - 1),
    0,
  );
  const uniqueSequences = [...sequenceCounts.keys()].sort((left, right) => left - right);
  const expectedStart = capture ? capture.droppedCount + 1 : 1;
  let gapCount = uniqueSequences.length > 0 ? Math.max(0, uniqueSequences[0] - expectedStart) : 0;
  for (let index = 1; index < uniqueSequences.length; index += 1) {
    gapCount += Math.max(0, uniqueSequences[index] - uniqueSequences[index - 1] - 1);
  }

  const missingSequenceCount = entries.length - sequences.length;
  const invalidVersionCount = entries.filter((entry) => (
    entry.schemaVersion !== SUPPORTED_AGENT_REPLAY_SCHEMA_VERSION
  )).length;
  const normalizedSnapshotTrace = snapshotTraceId?.trim() || null;
  const traceMismatchCount = entries.filter((entry) => (
    !entry.traceId || (normalizedSnapshotTrace !== null && entry.traceId !== normalizedSnapshotTrace)
  )).length;
  const invalidDetailCount = entries.filter((entry) => entry.detailIntegrity !== 'valid').length;
  const captureMismatch = Boolean(capture && (
    capture.returnedCount !== entries.length
    || capture.originalCount !== capture.returnedCount + capture.droppedCount
    || capture.truncated !== (capture.droppedCount > 0)
  ));

  const invalid = missingSequenceCount > 0
    || duplicateCount > 0
    || invalidVersionCount > 0
    || traceMismatchCount > 0
    || invalidDetailCount > 0
    || captureMismatch;
  const warning = !capture || capture.truncated || gapCount > 0;

  return {
    entries,
    integrity: {
      status: invalid ? 'invalid' : warning ? 'warning' : 'complete',
      gapCount,
      duplicateCount,
      missingSequenceCount,
      invalidVersionCount,
      traceMismatchCount,
      invalidDetailCount,
      capture,
      captureMismatch,
    },
  };
};
