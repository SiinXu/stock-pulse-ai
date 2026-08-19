// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { ParsedApiError } from '../api/error';
import type { UiTextKey, UiTextParams } from '../i18n/uiText';
import {
  isOperationRetryableError,
  resolveBusyRecoveryDecision,
  type BusyRecoveryDecision,
} from './asyncTaskUx';

type Translate = (key: UiTextKey, params?: UiTextParams) => string;

/** Host-owned callbacks. The assistant never invents navigation or retry safety. */
export type BusyRecoveryHandlers = {
  onAttachOrViewTasks?: (existingTaskId: string | null) => void;
  onRetrySameOperation?: () => void;
  onReload?: () => void;
  onRetry?: () => void;
};

export type BusyRecoveryUiAction = {
  label: string;
  onClick?: () => void;
  reload?: boolean;
  disabled?: boolean;
  isLoading?: boolean;
};

export type BuildBusyRecoveryActionsOptions = {
  /** Batch surfaces that already accepted work may still offer View Tasks. */
  forceAttachOrViewTasks?: boolean;
  retryDisabled?: boolean;
  retryLoading?: boolean;
};

/**
 * Map the shared busy-recovery decision onto labeled UI actions.
 * `wait_and_dismiss` and `none` add no primary action; the host owns dismiss.
 */
export function buildBusyRecoveryActions(
  error: ParsedApiError | null | undefined,
  t: Translate,
  handlers: BusyRecoveryHandlers,
  options: BuildBusyRecoveryActionsOptions = {},
): BusyRecoveryUiAction[] {
  const decision = resolveBusyRecoveryDecision(error);
  return buildBusyRecoveryActionsFromDecision(decision, t, handlers, options);
}

export function buildBusyRecoveryActionsFromDecision(
  decision: BusyRecoveryDecision,
  t: Translate,
  handlers: BusyRecoveryHandlers,
  options: BuildBusyRecoveryActionsOptions = {},
): BusyRecoveryUiAction[] {
  const actions: BusyRecoveryUiAction[] = [];
  const offerAttach = decision.kind === 'attach_or_view_tasks'
    || Boolean(options.forceAttachOrViewTasks);

  if (offerAttach && handlers.onAttachOrViewTasks) {
    actions.push({
      label: t('analysisWorkbench.tasks'),
      onClick: () => handlers.onAttachOrViewTasks?.(decision.existingTaskId),
    });
  }

  if (decision.kind === 'retry_same_operation' && handlers.onRetrySameOperation) {
    actions.push({
      label: t('common.retry'),
      onClick: handlers.onRetrySameOperation,
      disabled: options.retryDisabled,
      isLoading: options.retryLoading,
    });
  }

  if (decision.kind === 'reload') {
    actions.push({
      label: t('routeError.reload'),
      reload: true,
      onClick: handlers.onReload,
    });
  }

  return actions;
}

/**
 * Busy recovery first; operation-owned network/rate retry only when the
 * assistant did not already claim the error.
 */
export function buildLaunchErrorActions(
  error: ParsedApiError | null | undefined,
  t: Translate,
  handlers: BusyRecoveryHandlers,
  options: BuildBusyRecoveryActionsOptions = {},
): BusyRecoveryUiAction[] {
  const recovery = buildBusyRecoveryActions(error, t, handlers, options);
  if (recovery.length > 0) return recovery;
  if (error && isOperationRetryableError(error) && handlers.onRetry) {
    return [{
      label: t('common.retry'),
      onClick: handlers.onRetry,
      disabled: options.retryDisabled,
      isLoading: options.retryLoading,
    }];
  }
  return [];
}
