// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { analysisApi } from '../api/analysis';
import {
  createParsedApiError,
  getParsedApiError,
  type ParsedApiError,
} from '../api/error';
import type { UiTextKey } from '../i18n/uiText';
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  buildAnalysisWorkbenchHref,
  RUN_FLOW_ROUTE_QUERY_VALUES,
} from '../routing/routes';
import { extractExistingTaskId, isTaskBusyError } from './asyncTaskUx';

type Translate = (key: UiTextKey, params?: Record<string, string | number>) => string;

/** Analysis Workbench tasks deep link, optionally focusing a known task RunFlow. */
export function buildAnalysisTasksHref(taskId?: string | null): string {
  const trimmed = typeof taskId === 'string' ? taskId.trim() : '';
  if (trimmed) {
    return buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
      runFlow: RUN_FLOW_ROUTE_QUERY_VALUES.task,
      runFlowTaskId: trimmed,
    });
  }
  return buildAnalysisWorkbenchHref({
    segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
  });
}

export type SetupSmokeOutcome =
  | { status: 'blocked'; error: ParsedApiError }
  | { status: 'accepted'; successMessage: string; tasksHref: string }
  | { status: 'failed'; error: ParsedApiError; tasksHref: string | null };

/**
 * Run the first-run brief analysis smoke check without embedding task-id-only UX.
 * Callers own React state; this function only performs the request + outcome shape.
 */
export async function runSetupSmokeAnalysis(options: {
  readyForSmoke: boolean;
  stockCode: string;
  t: Translate;
}): Promise<SetupSmokeOutcome> {
  const { readyForSmoke, stockCode, t } = options;

  if (!readyForSmoke) {
    return {
      status: 'blocked',
      error: createParsedApiError({
        title: t('settings.setupGuideSmokeUnavailableTitle'),
        message: t('settings.setupGuideSmokeNotReady'),
        rawMessage: t('settings.setupGuideSmokeNotReady'),
        category: 'missing_params',
      }),
    };
  }

  if (!stockCode) {
    return {
      status: 'blocked',
      error: createParsedApiError({
        title: t('settings.setupGuideSmokeUnavailableTitle'),
        message: t('settings.setupGuideSmokeNeedsStock'),
        rawMessage: t('settings.setupGuideSmokeNeedsStock'),
        category: 'missing_params',
      }),
    };
  }

  try {
    const result = await analysisApi.analyzeAsync({
      stockCode,
      reportType: 'brief',
      asyncMode: true,
      notify: false,
      originalQuery: stockCode,
      selectionSource: 'manual',
    });
    const taskId = 'taskId' in result ? result.taskId : result.accepted?.[0]?.taskId;
    return {
      status: 'accepted',
      // Primary copy never surfaces a bare task id (#885 / #879 A6).
      successMessage: t('settings.setupGuideSmokeAccepted', { stock: stockCode }),
      tasksHref: buildAnalysisTasksHref(taskId),
    };
  } catch (error: unknown) {
    const parsed = getParsedApiError(error);
    return {
      status: 'failed',
      error: parsed,
      tasksHref: isTaskBusyError(parsed)
        ? buildAnalysisTasksHref(extractExistingTaskId(parsed))
        : null,
    };
  }
}
