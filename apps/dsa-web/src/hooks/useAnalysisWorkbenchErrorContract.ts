// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback } from 'react';
import type { ParsedApiError } from '../api/error';
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  type AnalysisWorkbenchSegment,
} from '../routing/routes';
import type { TaskInfo } from '../types/analysis';
import {
  isLaunchBlockingError,
  resolveBusyRecoveryDecision,
} from '../utils/asyncTaskUx';

/** Busy/conflict launch blocking + recover-to-tasks CTA for Analysis Workbench. */
export function useAnalysisWorkbenchErrorContract(options: {
  duplicateError: ParsedApiError | null;
  duplicateTask: { stockCode: string; existingTaskId: string } | null;
  error: ParsedApiError | null;
  analysisTasks: TaskInfo[];
  openTaskRunFlow: (task: TaskInfo) => void;
  selectSegment: (segment: AnalysisWorkbenchSegment) => void;
}) {
  const {
    duplicateError,
    duplicateTask,
    error,
    analysisTasks,
    openTaskRunFlow,
    selectSegment,
  } = options;

  const duplicateRecovery = resolveBusyRecoveryDecision(duplicateError);
  const errorRecovery = resolveBusyRecoveryDecision(error);
  const launchBlockedByBusy = Boolean(duplicateError)
    || isLaunchBlockingError(error);

  const openBusyTasks = useCallback(() => {
    const attachTaskId = duplicateTask?.existingTaskId
      || duplicateRecovery.existingTaskId
      || errorRecovery.existingTaskId;
    const existing = attachTaskId
      ? analysisTasks.find((task) => task.taskId === attachTaskId)
      : undefined;
    if (existing) openTaskRunFlow(existing);
    else selectSegment(ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks);
  }, [
    analysisTasks,
    duplicateRecovery.existingTaskId,
    duplicateTask,
    errorRecovery.existingTaskId,
    openTaskRunFlow,
    selectSegment,
  ]);

  return {
    launchBlockedByBusy,
    openBusyTasks,
    duplicateRecovery,
    errorRecovery,
  };
}
