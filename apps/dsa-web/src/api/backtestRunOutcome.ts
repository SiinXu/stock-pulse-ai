import { getParsedApiError } from './error';
import type { ParsedApiError } from './error';

/**
 * POST /api/v1/backtest/run is synchronous. Current responses have no job /
 * task / run / idempotency identifier and no status or cancel route.
 */
export type BacktestRunClientPhase = 'idle' | 'submitting' | 'unknown_outcome';
export type BacktestRunFailureKind = 'aborted' | 'unknown_outcome' | 'terminal';

export type BacktestRunFailureClassification = {
  kind: BacktestRunFailureKind;
  error: ParsedApiError | null;
  runIdentity: string | null;
};

function readStringField(source: Record<string, unknown>, key: string): string | null {
  const value = source[key];
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed || null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' ? value as Record<string, unknown> : null;
}

/** Recover a server-issued run identity only when one is actually present. */
export function extractBacktestRunIdentity(source: unknown): string | null {
  const record = asRecord(source);
  if (!record) return null;
  const nested = [
    record,
    asRecord(record.params),
    asRecord(record.data),
    asRecord(asRecord(record.response)?.data),
  ];
  const keys = [
    'taskId',
    'task_id',
    'jobId',
    'job_id',
    'runId',
    'run_id',
    'requestId',
    'request_id',
    'existingTaskId',
    'existing_task_id',
  ];
  for (const candidate of nested) {
    if (!candidate) continue;
    for (const key of keys) {
      const value = readStringField(candidate, key);
      if (value) return value;
    }
  }
  return null;
}

export function isBacktestRunAbortError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const value = error as { code?: string; name?: string };
  return value.code === 'ERR_CANCELED'
    || value.name === 'CanceledError'
    || value.name === 'AbortError';
}

function isClientWaitTimeout(error: unknown, parsed: ParsedApiError): boolean {
  if (parsed.category === 'upstream_timeout') return true;
  if (!error || typeof error !== 'object') return false;
  const value = error as { code?: string; message?: string };
  if (value.code !== 'ECONNABORTED') return false;
  return String(value.message || '').toLowerCase().includes('timeout');
}

export function classifyBacktestRunFailure(error: unknown): BacktestRunFailureClassification {
  if (isBacktestRunAbortError(error)) {
    return { kind: 'aborted', error: null, runIdentity: extractBacktestRunIdentity(error) };
  }
  const parsed = getParsedApiError(error);
  const runIdentity = extractBacktestRunIdentity(error) ?? extractBacktestRunIdentity(parsed);
  if (typeof parsed.status === 'number' && parsed.status >= 400) {
    return { kind: 'terminal', error: parsed, runIdentity };
  }
  if (isClientWaitTimeout(error, parsed)
    || parsed.category === 'upstream_network'
    || parsed.category === 'local_connection_failed') {
    return { kind: 'unknown_outcome', error: parsed, runIdentity };
  }
  return { kind: 'terminal', error: parsed, runIdentity };
}

export function canSubmitBacktestRun(phase: BacktestRunClientPhase): boolean {
  return phase === 'idle';
}
