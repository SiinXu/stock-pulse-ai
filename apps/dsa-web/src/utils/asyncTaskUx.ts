// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Client async-task UX semantics for issue #885 (async half).
 *
 * Taxonomy of failure *classes* (auth, network, credential, …) stays owned by
 * `apiReasonMapper` / error catalog work (W6 / #186 / #1064). This module owns
 * **lifecycle and recovery** for long-running work: how 409/busy, queue,
 * in-progress, terminal, and retryable states present in the Web client.
 *
 * See `docs/async-task-ux-contract.md`.
 */

import type { ParsedApiError } from '../api/error';
import type { TaskLifecycleStatus } from '../types/analysis';
import {
  isBusyParsedApiError,
  mapApiErrorToActionable,
  type ActionableErrorClass,
} from './apiReasonMapper';

/** Client-facing phases for a long-running analysis/market/screening task. */
export type AsyncTaskClientPhase =
  | 'idle'
  | 'submitting'
  | 'queued'
  | 'in_progress'
  | 'cancel_requested'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'interrupted'
  | 'unknown';

/** Wire statuses that still own the primary launch control (double-submit risk). */
export const ACTIVE_TASK_STATUSES = [
  'pending',
  'processing',
  'cancel_requested',
] as const satisfies readonly TaskLifecycleStatus[];

/** Wire statuses that release progress UI and allow dismiss. */
export const TERMINAL_TASK_STATUSES = [
  'completed',
  'failed',
  'cancelled',
  'interrupted',
] as const satisfies readonly TaskLifecycleStatus[];

const ACTIVE_STATUS_SET = new Set<string>(ACTIVE_TASK_STATUSES);
const TERMINAL_STATUS_SET = new Set<string>(TERMINAL_TASK_STATUSES);

/**
 * Actionable classes where a **retry of the same operation** is generally safe
 * once the user owns the intent. Busy is intentionally excluded: recovery is
 * "view existing work / wait / dismiss", not blind resubmit.
 */
export const OPERATION_RETRYABLE_ERROR_CLASSES = new Set<ActionableErrorClass>([
  'network',
  'rate_quota',
]);

export function isActiveTaskStatus(
  status: string | null | undefined,
): status is (typeof ACTIVE_TASK_STATUSES)[number] {
  return Boolean(status && ACTIVE_STATUS_SET.has(status));
}

export function isTerminalTaskStatus(
  status: string | null | undefined,
): status is (typeof TERMINAL_TASK_STATUSES)[number] {
  return Boolean(status && TERMINAL_STATUS_SET.has(status));
}

/** Map a backend task lifecycle status to the shared client phase. */
export function mapTaskStatusToClientPhase(
  status: string | null | undefined,
): AsyncTaskClientPhase {
  switch (status) {
    case 'pending':
      return 'queued';
    case 'processing':
      return 'in_progress';
    case 'cancel_requested':
      return 'cancel_requested';
    case 'completed':
      return 'completed';
    case 'failed':
      return 'failed';
    case 'cancelled':
      return 'cancelled';
    case 'interrupted':
      return 'interrupted';
    default:
      return status ? 'unknown' : 'idle';
  }
}

/** Normalize progress to a determinate 0–100 range for Progress primitives. */
export function normalizeTaskProgress(progress: number | null | undefined): number {
  if (typeof progress !== 'number' || !Number.isFinite(progress)) return 0;
  return Math.max(0, Math.min(100, Math.round(progress)));
}

/**
 * Extract an existing in-flight task id from a 409/busy envelope.
 * Supports snake_case and camelCase params (rolling-upgrade).
 */
export function extractExistingTaskId(
  error: ParsedApiError | null | undefined,
): string | null {
  if (!error?.params) return null;
  const raw = error.params.existing_task_id ?? error.params.existingTaskId;
  if (typeof raw !== 'string') return null;
  const trimmed = raw.trim();
  return trimmed || null;
}

/** True when the error is the busy/duplicate class (not config conflict). */
export function isTaskBusyError(error: ParsedApiError | null | undefined): boolean {
  return Boolean(error && mapApiErrorToActionable(error).class === 'busy');
}

/**
 * True when a visible error should **block** another launch until dismissed
 * or recovered. Includes busy *and* config conflict (shared with analysis
 * workbench `launchBlockedByBusy`).
 */
export function isLaunchBlockingError(
  error: ParsedApiError | null | undefined,
): boolean {
  return isBusyParsedApiError(error);
}

/** True when the error class allows an operation-owned Retry control. */
export function isOperationRetryableError(
  error: ParsedApiError | null | undefined,
): boolean {
  if (!error) return false;
  return OPERATION_RETRYABLE_ERROR_CLASSES.has(mapApiErrorToActionable(error).class);
}

/**
 * Recovery kind for busy/conflict rejection surfaces.
 * - `attach_or_view_tasks`: duplicate_task (and similar) with or without id
 * - `wait_and_dismiss`: scheduler/market lock without attachable id
 * - `retry_same_operation`: ledger busy / short contention
 * - `reload`: config revision conflict
 * - `none`: not a launch-blocking error
 */
export type BusyRecoveryKind =
  | 'attach_or_view_tasks'
  | 'wait_and_dismiss'
  | 'retry_same_operation'
  | 'reload'
  | 'none';

export function resolveBusyRecoveryKind(
  error: ParsedApiError | null | undefined,
): BusyRecoveryKind {
  if (!error) return 'none';
  const mapping = mapApiErrorToActionable(error);
  if (mapping.class === 'config_conflict') return 'reload';
  if (mapping.class !== 'busy') return 'none';

  const code = (error.code || mapping.technicalCode || '').trim();
  if (
    code === 'duplicate_task'
    || code === 'duplicate_market_review'
    || Boolean(extractExistingTaskId(error))
  ) {
    return 'attach_or_view_tasks';
  }
  if (code === 'portfolio_busy') return 'retry_same_operation';
  return 'wait_and_dismiss';
}
