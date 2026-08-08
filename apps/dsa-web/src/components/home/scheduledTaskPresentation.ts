// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiTextKey, UiTextParams } from '../../i18n/uiText';
import type { ScheduledTaskOccurrenceStatus } from '../../types/scheduledTasks';

type UiTranslator = (key: UiTextKey, params?: UiTextParams) => string;

export type ScheduledTaskBadgeVariant =
  | 'default'
  | 'info'
  | 'success'
  | 'warning'
  | 'danger';

export function getBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

export function getScheduledTaskTypeLabel(
  taskType: string | undefined,
  t: UiTranslator,
): string {
  if (taskType === 'stock_analysis') return t('home.scheduledTaskTypeAnalysis');
  if (taskType === 'research_brief') return t('home.scheduledTaskTypeResearchBrief');
  if (taskType === 'risk_check') return t('home.scheduledTaskTypeRiskCheck');
  return t('home.scheduledTaskTypeUnknown');
}

export function getScheduledTaskStatusPresentation(
  status: ScheduledTaskOccurrenceStatus,
  t: UiTranslator,
): { label: string; variant: ScheduledTaskBadgeVariant } {
  if (status === 'succeeded') {
    return { label: t('taskPanel.completed'), variant: 'success' };
  }
  if (status === 'failed') {
    return { label: t('taskPanel.failed'), variant: 'danger' };
  }
  if (status === 'interrupted') {
    return { label: t('taskPanel.interrupted'), variant: 'warning' };
  }
  if (status === 'skipped') {
    return { label: t('home.scheduledTaskSkipped'), variant: 'default' };
  }
  if (status === 'running' || status === 'dispatching') {
    return { label: t('taskPanel.processing'), variant: 'info' };
  }
  if (status === 'retry_wait') {
    return { label: t('home.scheduledTaskRetryWait'), variant: 'warning' };
  }
  return { label: t('taskPanel.pending'), variant: 'default' };
}
