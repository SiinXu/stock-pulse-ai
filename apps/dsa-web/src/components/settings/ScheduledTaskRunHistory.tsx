// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useEffect, useRef, useState } from 'react';
import type React from 'react';
import { ChevronDown, ChevronUp, RefreshCw } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { scheduledTasksApi } from '../../api/scheduledTasks';
import type { ScheduledTaskRunItem, ScheduledTaskRunStatus } from '../../types/scheduledTasks';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import { getUiLocale } from '../../utils/uiLocale';
import { ApiErrorAlert, Badge, Button, EmptyState, IconButton, StatePanel } from '../common';

type ScheduledTaskRunHistoryProps = {
  taskId: string;
  taskName: string;
  disabled?: boolean;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
  language: UiLanguage;
};

const INITIAL_LIMIT = 10;
const LIMIT_STEP = 10;
const MAX_LIMIT = 500;

function formatTimestamp(value: string | null | undefined, language: UiLanguage): string {
  if (!value) {
    return '—';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(getUiLocale(language), {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
}

function statusLabel(
  status: ScheduledTaskRunStatus,
  t: ScheduledTaskRunHistoryProps['t'],
): string {
  if (status === 'succeeded') return t('settings.scheduledTasksRunStatusSucceeded');
  if (status === 'failed') return t('settings.scheduledTasksRunStatusFailed');
  if (status === 'interrupted') return t('settings.scheduledTasksRunStatusInterrupted');
  if (status === 'skipped') return t('settings.scheduledTasksRunStatusSkipped');
  if (status === 'running' || status === 'dispatching') {
    return t('settings.scheduledTasksRunStatusRunning');
  }
  if (status === 'retry_wait') return t('settings.scheduledTasksRunStatusRetryWait');
  return status;
}

function statusVariant(
  status: ScheduledTaskRunStatus,
): 'success' | 'danger' | 'warning' | 'info' | 'default' {
  if (status === 'succeeded') return 'success';
  if (status === 'failed') return 'danger';
  if (status === 'interrupted' || status === 'retry_wait') return 'warning';
  if (status === 'running' || status === 'dispatching') return 'info';
  return 'default';
}

function valueList(values: string[] | null | undefined): string {
  return values?.length ? values.join(', ') : '—';
}

const ScheduledTaskRunHistory: React.FC<ScheduledTaskRunHistoryProps> = ({
  taskId,
  taskName,
  disabled = false,
  t,
  language,
}) => {
  const requestSequence = useRef(0);
  const [isOpen, setIsOpen] = useState(false);
  const [runs, setRuns] = useState<ScheduledTaskRunItem[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(INITIAL_LIMIT);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);

  useEffect(() => {
    requestSequence.current += 1;
    setIsOpen(false);
    setRuns([]);
    setTotal(0);
    setLimit(INITIAL_LIMIT);
    setError(null);
  }, [taskId]);

  const load = async (requestedLimit: number) => {
    const requestId = requestSequence.current + 1;
    requestSequence.current = requestId;
    setIsLoading(true);
    setError(null);
    try {
      const response = await scheduledTasksApi.listRuns(taskId, { limit: requestedLimit });
      if (requestSequence.current !== requestId) {
        return;
      }
      setRuns(response.items);
      setTotal(response.total);
      setLimit(requestedLimit);
    } catch (loadError: unknown) {
      if (requestSequence.current === requestId) {
        setError(getParsedApiError(loadError));
      }
    } finally {
      if (requestSequence.current === requestId) {
        setIsLoading(false);
      }
    }
  };

  const toggle = () => {
    const nextOpen = !isOpen;
    setIsOpen(nextOpen);
    if (nextOpen && runs.length === 0 && !isLoading && !error) {
      void load(INITIAL_LIMIT);
    }
  };

  const hasMore = runs.length < total && limit < MAX_LIMIT;

  return (
    <div className="border-t border-border/50 pt-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button
          type="button"
          variant="ghost"
          size="compact"
          disabled={disabled}
          aria-expanded={isOpen}
          aria-controls={`scheduled-task-history-${taskId}`}
          onClick={toggle}
          data-testid={`settings-scheduled-task-history-toggle-${taskId}`}
        >
          {isOpen
            ? <ChevronUp className="h-4 w-4" aria-hidden="true" />
            : <ChevronDown className="h-4 w-4" aria-hidden="true" />}
          {t('settings.scheduledTasksHistory')}
        </Button>
        {isOpen ? (
          <IconButton
            type="button"
            variant="outline"
            size="compact"
            disabled={disabled || isLoading}
            isLoading={isLoading}
            aria-label={t('settings.scheduledTasksHistoryRefresh', { name: taskName })}
            onClick={() => void load(limit)}
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          </IconButton>
        ) : null}
      </div>

      {isOpen ? (
        <div
          id={`scheduled-task-history-${taskId}`}
          className="mt-3 space-y-3 pb-2"
          data-testid={`settings-scheduled-task-history-${taskId}`}
        >
          {isLoading && runs.length === 0 ? (
            <StatePanel
              state="loading"
              title={t('settings.scheduledTasksHistoryLoading')}
              size="compact"
              titleAs="p"
            />
          ) : null}
          {error ? (
            <ApiErrorAlert
              error={error}
              actionLabel={t('common.retry')}
              onAction={() => void load(limit)}
            />
          ) : null}
          {!isLoading && !error && runs.length === 0 ? (
            <EmptyState
              compact
              title={t('settings.scheduledTasksHistoryEmpty')}
              description={t('settings.scheduledTasksHistoryEmptyDescription')}
            />
          ) : null}
          {runs.map((run) => (
            <article
              key={run.id}
              className="rounded-lg border settings-border bg-background/35 p-3"
              data-testid={`settings-scheduled-task-run-${run.id}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={statusVariant(run.status)}>
                    {statusLabel(run.status, t)}
                  </Badge>
                  <span className="font-mono text-xs text-secondary-text">{run.id}</span>
                </div>
                <span className="text-xs text-muted-text">
                  {t('settings.scheduledTasksHistoryAttempts', {
                    attempts: run.attemptCount ?? 0,
                    failures: run.dispatchFailureCount ?? 0,
                  })}
                </span>
              </div>
              <dl className="mt-3 grid grid-cols-1 gap-x-5 gap-y-2 text-xs sm:grid-cols-2">
                <div>
                  <dt className="text-muted-text">{t('settings.scheduledTasksHistoryScheduled')}</dt>
                  <dd className="mt-0.5 text-secondary-text">{formatTimestamp(run.scheduledFor, language)}</dd>
                </div>
                <div>
                  <dt className="text-muted-text">{t('settings.scheduledTasksHistoryStarted')}</dt>
                  <dd className="mt-0.5 text-secondary-text">{formatTimestamp(run.startedAt, language)}</dd>
                </div>
                <div>
                  <dt className="text-muted-text">{t('settings.scheduledTasksHistoryFinished')}</dt>
                  <dd className="mt-0.5 text-secondary-text">{formatTimestamp(run.finishedAt, language)}</dd>
                </div>
                <div>
                  <dt className="text-muted-text">{t('settings.scheduledTasksHistoryNextAttempt')}</dt>
                  <dd className="mt-0.5 text-secondary-text">{formatTimestamp(run.nextAttemptAt, language)}</dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-muted-text">{t('settings.scheduledTasksHistoryTaskId')}</dt>
                  <dd className="mt-0.5 break-all font-mono text-secondary-text">
                    {run.taskId || taskId}
                  </dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-muted-text">{t('settings.scheduledTasksHistoryExecutionIds')}</dt>
                  <dd className="mt-0.5 break-all font-mono text-secondary-text">
                    {valueList(run.executionTaskIds)}
                  </dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-muted-text">{t('settings.scheduledTasksHistoryResultRefs')}</dt>
                  <dd className="mt-0.5 break-all font-mono text-secondary-text">
                    {valueList(run.resultRefs)}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-text">{t('settings.scheduledTasksHistoryNotification')}</dt>
                  <dd className="mt-0.5 text-secondary-text">
                    {run.notificationStatus || '—'} · {valueList(run.notificationChannels)}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-text">{t('settings.scheduledTasksHistoryNotificationFailures')}</dt>
                  <dd className="mt-0.5 text-secondary-text">
                    {valueList(run.notificationFailedChannels)}
                  </dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-muted-text">{t('settings.scheduledTasksHistoryError')}</dt>
                  <dd className="mt-0.5 break-all font-mono text-secondary-text">
                    {run.errorCode || '—'}
                  </dd>
                </div>
              </dl>
            </article>
          ))}
          {runs.length ? (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs text-muted-text">
                {t('settings.scheduledTasksHistoryCount', { shown: runs.length, total })}
              </span>
              {hasMore ? (
                <Button
                  type="button"
                  variant="secondary"
                  size="compact"
                  disabled={disabled || isLoading}
                  isLoading={isLoading}
                  onClick={() => void load(Math.min(MAX_LIMIT, limit + LIMIT_STEP))}
                >
                  {t('settings.scheduledTasksHistoryLoadMore')}
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};

export default ScheduledTaskRunHistory;
