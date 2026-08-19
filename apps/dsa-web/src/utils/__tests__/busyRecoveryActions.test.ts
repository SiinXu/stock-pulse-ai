// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it, vi } from 'vitest';
import { createParsedApiError } from '../../api/error';
import { resolveBusyRecoveryDecision } from '../asyncTaskUx';
import { buildBusyRecoveryActions, buildLaunchErrorActions } from '../busyRecoveryActions';

const t = (key: string) => key;

describe('busyRecoveryActions', () => {
  it('invokes the shared assistant instead of inventing a second busy policy', () => {
    const error = createParsedApiError({
      title: 'busy',
      message: 'busy',
      code: 'duplicate_task',
      status: 409,
      params: { existing_task_id: 'task-1' },
    });
    expect(resolveBusyRecoveryDecision(error)).toEqual({
      kind: 'attach_or_view_tasks',
      existingTaskId: 'task-1',
      blocksLaunch: true,
    });
    const onAttachOrViewTasks = vi.fn();
    const actions = buildBusyRecoveryActions(error, t as never, { onAttachOrViewTasks });
    expect(actions).toHaveLength(1);
    expect(actions[0].label).toBe('analysisWorkbench.tasks');
    actions[0].onClick?.();
    expect(onAttachOrViewTasks).toHaveBeenCalledWith('task-1');
  });

  it('does not offer retry for wait_and_dismiss scheduler busy', () => {
    const actions = buildLaunchErrorActions(createParsedApiError({
      title: 'busy',
      message: 'busy',
      code: 'scheduler_busy',
      status: 409,
    }), t as never, {
      onAttachOrViewTasks: vi.fn(),
      onRetrySameOperation: vi.fn(),
      onRetry: vi.fn(),
    });
    expect(actions).toEqual([]);
  });

  it('offers retry-same-operation only for portfolio_busy', () => {
    const onRetrySameOperation = vi.fn();
    const actions = buildBusyRecoveryActions(createParsedApiError({
      title: 'busy',
      message: 'busy',
      code: 'portfolio_busy',
      status: 409,
    }), t as never, { onRetrySameOperation });
    expect(actions).toHaveLength(1);
    expect(actions[0].label).toBe('common.retry');
    actions[0].onClick?.();
    expect(onRetrySameOperation).toHaveBeenCalledOnce();
  });

  it('does not treat non-busy errors as launch recovery', () => {
    const error = createParsedApiError({
      title: 'invalid',
      message: 'invalid',
      code: 'validation_error',
      status: 422,
    });
    expect(resolveBusyRecoveryDecision(error).kind).toBe('none');
    expect(buildLaunchErrorActions(error, t as never, {
      onAttachOrViewTasks: vi.fn(),
      onRetry: vi.fn(),
    })).toEqual([]);
  });

  it('keeps network retry after the assistant declines the error', () => {
    const onRetry = vi.fn();
    const actions = buildLaunchErrorActions(createParsedApiError({
      title: 'net',
      message: 'net',
      category: 'upstream_network',
      status: 503,
    }), t as never, { onRetry });
    expect(actions).toHaveLength(1);
    expect(actions[0].label).toBe('common.retry');
  });
});
