// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useState } from 'react';
import type React from 'react';
import { RefreshCw } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { scheduledTasksApi } from '../../api/scheduledTasks';
import type {
  ScheduledTaskDefinitionSummary,
  ScheduledTaskType,
} from '../../types/scheduledTasks';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import { getUiLocale } from '../../utils/uiLocale';
import {
  ApiErrorAlert,
  Badge,
  EmptyState,
  IconButton,
  StatePanel,
} from '../common';
import { SettingsAlert } from './SettingsAlert';
import { SettingsSectionCard } from './SettingsSectionCard';
import { SettingsSwitch } from './SettingsSwitch';

type ScheduledTasksPanelProps = {
  disabled?: boolean;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
  language: UiLanguage;
};

function formatTimestamp(value: string | null | undefined, language: UiLanguage) {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(getUiLocale(language), {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

function taskTypeLabel(
  taskType: ScheduledTaskType | undefined,
  t: ScheduledTasksPanelProps['t'],
) {
  if (taskType === 'stock_analysis') return t('settings.scheduledTasksTypeAnalysis');
  if (taskType === 'research_brief') return t('settings.scheduledTasksTypeResearchBrief');
  if (taskType === 'risk_check') return t('settings.scheduledTasksTypeRiskCheck');
  return t('settings.scheduledTasksTypeUnknown');
}

const ScheduledTasksPanel: React.FC<ScheduledTasksPanelProps> = ({
  disabled = false,
  t,
  language,
}) => {
  const [items, setItems] = useState<ScheduledTaskDefinitionSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);
  const [actionError, setActionError] = useState<ParsedApiError | null>(null);
  const [actionSuccess, setActionSuccess] = useState('');
  const [pendingId, setPendingId] = useState<string | null>(null);

  const loadTasks = useCallback(async (mode: 'initial' | 'refresh' = 'initial') => {
    setLoadError(null);
    setActionError(null);
    if (mode === 'initial') {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }
    try {
      const response = await scheduledTasksApi.list({ limit: 200 });
      setItems(response.items);
    } catch (error: unknown) {
      setLoadError(getParsedApiError(error));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadTasks('initial');
  }, [loadTasks]);

  const handleToggle = async (task: ScheduledTaskDefinitionSummary, nextEnabled: boolean) => {
    if (disabled || task.compatibility !== 'supported' || pendingId) {
      return;
    }
    setActionError(null);
    setActionSuccess('');
    setPendingId(task.id);
    try {
      const updated = nextEnabled
        ? await scheduledTasksApi.enable(task.id)
        : await scheduledTasksApi.disable(task.id);
      setItems((current) => current.map((item) => (
        item.id === task.id
          ? {
              ...item,
              ...updated,
              // Preserve list-only fields when the enable/disable body is sparse.
              taskType: updated.taskType ?? item.taskType,
            }
          : item
      )));
      setActionSuccess(
        nextEnabled
          ? t('settings.scheduledTasksEnabledSuccess', { name: task.name })
          : t('settings.scheduledTasksDisabledSuccess', { name: task.name }),
      );
    } catch (error: unknown) {
      setActionError(getParsedApiError(error));
    } finally {
      setPendingId(null);
    }
  };

  return (
    <SettingsSectionCard
      title={t('settings.scheduledTasksTitle')}
      description={t('settings.scheduledTasksDescription')}
      contentBordered
      actions={(
        <IconButton
          type="button"
          variant="outline"
          size="compact"
          onClick={() => void loadTasks('refresh')}
          disabled={disabled || isLoading || isRefreshing}
          isLoading={isRefreshing}
          aria-label={t('settings.scheduledTasksRefresh')}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
        </IconButton>
      )}
    >
      <p className="mb-3 text-xs leading-5 text-secondary-text">
        {t('settings.scheduledTasksProcessLocalNote')}
      </p>

      {loadError ? (
        <div className="mb-3">
          <ApiErrorAlert error={loadError} />
        </div>
      ) : null}
      {actionError ? (
        <div className="mb-3">
          <ApiErrorAlert error={actionError} />
        </div>
      ) : null}
      {!actionError && actionSuccess ? (
        <div className="mb-3">
          <SettingsAlert
            title={t('settings.actionSuccess')}
            message={actionSuccess}
            variant="success"
          />
        </div>
      ) : null}

      {isLoading ? (
        <StatePanel
          state="loading"
          title={t('common.loading')}
          size="compact"
          titleAs="p"
        />
      ) : items.length === 0 ? (
        <EmptyState
          compact
          title={t('settings.scheduledTasksEmptyTitle')}
          description={t('settings.scheduledTasksEmptyDescription')}
        />
      ) : (
        <div
          role="region"
          aria-label={t('settings.scheduledTasksListLabel')}
          data-testid="settings-scheduled-tasks-list"
          className="divide-y divide-border/70"
        >
          {items.map((task) => {
            const nextRun = formatTimestamp(task.nextRunAt, language);
            const unsupported = task.compatibility !== 'supported';
            const busy = pendingId === task.id;
            return (
              <div
                key={task.id}
                className="flex min-h-14 flex-wrap items-center justify-between gap-3 py-3"
                data-testid={`settings-scheduled-task-${task.id}`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-medium text-foreground">
                      {task.name}
                    </span>
                    <Badge variant={unsupported ? 'warning' : 'default'} className="shrink-0">
                      {unsupported
                        ? t('settings.scheduledTasksUnsupported')
                        : taskTypeLabel(task.taskType, t)}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-secondary-text">
                    {nextRun
                      ? t('settings.scheduledTasksNextRun', { time: nextRun })
                      : t('settings.scheduledTasksNoNextRun')}
                  </p>
                </div>
                <SettingsSwitch
                  checked={task.enabled}
                  disabled={disabled || unsupported || busy || isRefreshing}
                  onCheckedChange={(checked) => {
                    void handleToggle(task, checked);
                  }}
                  aria-label={t('settings.scheduledTasksToggleAria', { name: task.name })}
                />
              </div>
            );
          })}
        </div>
      )}
    </SettingsSectionCard>
  );
};

export default ScheduledTasksPanel;
