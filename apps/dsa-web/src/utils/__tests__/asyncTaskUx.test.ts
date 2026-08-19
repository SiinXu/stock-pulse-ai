// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { createParsedApiError } from '../../api/error';
import {
  extractExistingTaskId,
  isActiveTaskStatus,
  isLaunchBlockingError,
  isOperationRetryableError,
  isTaskBusyError,
  isTerminalTaskStatus,
  mapTaskStatusToClientPhase,
  normalizeTaskProgress,
  resolveBusyRecoveryDecision,
  resolveBusyRecoveryKind,
} from '../asyncTaskUx';

describe('asyncTaskUx', () => {
  describe('lifecycle mapping', () => {
    it.each([
      ['pending', 'queued'],
      ['processing', 'in_progress'],
      ['cancel_requested', 'cancel_requested'],
      ['completed', 'completed'],
      ['failed', 'failed'],
      ['cancelled', 'cancelled'],
      ['interrupted', 'interrupted'],
      [null, 'idle'],
      ['weird', 'unknown'],
    ] as const)('maps status %s to phase %s', (status, phase) => {
      expect(mapTaskStatusToClientPhase(status)).toBe(phase);
    });

    it('classifies active vs terminal wire statuses', () => {
      expect(isActiveTaskStatus('pending')).toBe(true);
      expect(isActiveTaskStatus('processing')).toBe(true);
      expect(isActiveTaskStatus('cancel_requested')).toBe(true);
      expect(isActiveTaskStatus('completed')).toBe(false);
      expect(isTerminalTaskStatus('completed')).toBe(true);
      expect(isTerminalTaskStatus('failed')).toBe(true);
      expect(isTerminalTaskStatus('cancelled')).toBe(true);
      expect(isTerminalTaskStatus('interrupted')).toBe(true);
      expect(isTerminalTaskStatus('processing')).toBe(false);
    });

    it('clamps progress into 0–100', () => {
      expect(normalizeTaskProgress(undefined)).toBe(0);
      expect(normalizeTaskProgress(NaN)).toBe(0);
      expect(normalizeTaskProgress(-5)).toBe(0);
      expect(normalizeTaskProgress(42.4)).toBe(42);
      expect(normalizeTaskProgress(150)).toBe(100);
    });
  });

  describe('busy / 409 recovery', () => {
    it('extracts existing task ids from snake or camel params', () => {
      expect(extractExistingTaskId(createParsedApiError({
        title: 'busy',
        message: 'busy',
        code: 'duplicate_task',
        status: 409,
        params: { existing_task_id: ' task-a ' },
      }))).toBe('task-a');
      expect(extractExistingTaskId(createParsedApiError({
        title: 'busy',
        message: 'busy',
        code: 'duplicate_task',
        status: 409,
        params: { existingTaskId: 'task-b' },
      }))).toBe('task-b');
      expect(extractExistingTaskId(createParsedApiError({
        title: 'busy',
        message: 'busy',
        code: 'duplicate_market_review',
        status: 409,
      }))).toBeNull();
    });

    it('treats busy as launch-blocking without classifying config conflict as task-busy', () => {
      const busy = createParsedApiError({
        title: 'busy',
        message: 'busy',
        code: 'scheduler_busy',
        status: 409,
      });
      const conflict = createParsedApiError({
        title: 'conflict',
        message: 'conflict',
        code: 'config_conflict',
        status: 409,
      });
      expect(isTaskBusyError(busy)).toBe(true);
      expect(isTaskBusyError(conflict)).toBe(false);
      expect(isLaunchBlockingError(busy)).toBe(true);
      expect(isLaunchBlockingError(conflict)).toBe(true);
    });

    it('resolves recovery kinds for representative busy codes', () => {
      expect(resolveBusyRecoveryKind(createParsedApiError({
        title: 'busy',
        message: 'busy',
        code: 'duplicate_task',
        status: 409,
        params: { existing_task_id: 't1' },
      }))).toBe('attach_or_view_tasks');
      expect(resolveBusyRecoveryKind(createParsedApiError({
        title: 'busy',
        message: 'busy',
        code: 'duplicate_market_review',
        status: 409,
      }))).toBe('attach_or_view_tasks');
      expect(resolveBusyRecoveryKind(createParsedApiError({
        title: 'busy',
        message: 'busy',
        code: 'portfolio_busy',
        status: 409,
      }))).toBe('retry_same_operation');
      expect(resolveBusyRecoveryKind(createParsedApiError({
        title: 'busy',
        message: 'busy',
        code: 'scheduler_busy',
        status: 409,
      }))).toBe('wait_and_dismiss');
      expect(resolveBusyRecoveryKind(createParsedApiError({
        title: 'conflict',
        message: 'conflict',
        code: 'config_version_conflict',
        status: 409,
      }))).toBe('reload');
    });

    it('exposes a production decision with attachable task identity', () => {
      expect(resolveBusyRecoveryDecision(createParsedApiError({
        title: 'busy',
        message: 'busy',
        code: 'duplicate_task',
        status: 409,
        params: { existing_task_id: 'live-1' },
      }))).toEqual({
        kind: 'attach_or_view_tasks',
        existingTaskId: 'live-1',
        blocksLaunch: true,
      });
      expect(resolveBusyRecoveryDecision(createParsedApiError({
        title: 'net',
        message: 'net',
        category: 'upstream_network',
        status: 503,
      }))).toEqual({
        kind: 'none',
        existingTaskId: null,
        blocksLaunch: false,
      });
    });

    it('allows operation retry only for network/rate classes', () => {
      expect(isOperationRetryableError(createParsedApiError({
        title: 'net',
        message: 'net',
        category: 'upstream_network',
        status: 503,
      }))).toBe(true);
      expect(isOperationRetryableError(createParsedApiError({
        title: 'busy',
        message: 'busy',
        code: 'duplicate_task',
        status: 409,
      }))).toBe(false);
      expect(isOperationRetryableError(createParsedApiError({
        title: 'validation',
        message: 'validation',
        code: 'validation_error',
        status: 422,
      }))).toBe(false);
    });
  });
});
