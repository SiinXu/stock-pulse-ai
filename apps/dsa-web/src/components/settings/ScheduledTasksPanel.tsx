// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import type React from 'react';
import { Plus, RefreshCw } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { scheduledTasksApi } from '../../api/scheduledTasks';
import type {
  ScheduledTaskCalendarMarket,
  ScheduledTaskCreateRequest,
  ScheduledTaskDefinitionSummary,
  ScheduledTaskNonTradingDayPolicy,
  ScheduledTaskReportType,
  ScheduledTaskRunItem,
  ScheduledTaskRunStatus,
  ScheduledTaskSupportedType,
  ScheduledTaskType,
} from '../../types/scheduledTasks';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import { getUiLocale } from '../../utils/uiLocale';
import {
  ApiErrorAlert,
  Badge,
  Button,
  EmptyState,
  Field,
  IconButton,
  Input,
  Modal,
  Select,
  StatePanel,
  Switch,
} from '../common';
import { SettingsAlert } from './SettingsAlert';
import { SettingsSectionCard } from './SettingsSectionCard';
import { SettingsSwitch } from './SettingsSwitch';
import ScheduledTaskRunHistory from './ScheduledTaskRunHistory';

type ScheduledTasksPanelProps = {
  disabled?: boolean;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
  language: UiLanguage;
};

type CreateDraft = {
  name: string;
  taskType: ScheduledTaskSupportedType;
  stockCode: string;
  reportType: ScheduledTaskReportType;
  time: string;
  timezone: string;
  calendarMarket: ScheduledTaskCalendarMarket;
  nonTradingDayPolicy: ScheduledTaskNonTradingDayPolicy;
  notify: boolean;
  enabled: boolean;
  maxAttempts: string;
};

const TIME_PATTERN = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const MAX_ATTEMPTS_PATTERN = /^[1-3]$/;
const CALENDAR_MARKETS: ScheduledTaskCalendarMarket[] = ['cn', 'hk', 'us', 'jp', 'kr', 'tw'];
const REPORT_TYPES: ScheduledTaskReportType[] = ['brief', 'simple', 'detailed', 'full'];

function getBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

function emptyDraft(): CreateDraft {
  return {
    name: '',
    taskType: 'stock_analysis',
    stockCode: '',
    reportType: 'detailed',
    time: '16:30',
    timezone: getBrowserTimezone(),
    calendarMarket: 'us',
    nonTradingDayPolicy: 'skip',
    notify: true,
    enabled: true,
    maxAttempts: '1',
  };
}

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

function runStatusLabel(
  status: ScheduledTaskRunStatus,
  t: ScheduledTasksPanelProps['t'],
) {
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

function runStatusVariant(
  status: ScheduledTaskRunStatus,
): 'success' | 'danger' | 'warning' | 'info' | 'default' {
  if (status === 'succeeded') return 'success';
  if (status === 'failed') return 'danger';
  if (status === 'interrupted' || status === 'retry_wait') return 'warning';
  if (status === 'running' || status === 'dispatching') return 'info';
  return 'default';
}

function marketLabel(
  market: ScheduledTaskCalendarMarket,
  t: ScheduledTasksPanelProps['t'],
) {
  if (market === 'cn') return t('settings.scheduledTasksMarketCn');
  if (market === 'hk') return t('settings.scheduledTasksMarketHk');
  if (market === 'us') return t('settings.scheduledTasksMarketUs');
  if (market === 'jp') return t('settings.scheduledTasksMarketJp');
  if (market === 'kr') return t('settings.scheduledTasksMarketKr');
  return t('settings.scheduledTasksMarketTw');
}

function reportTypeLabel(
  reportType: ScheduledTaskReportType,
  t: ScheduledTasksPanelProps['t'],
) {
  if (reportType === 'brief') return t('settings.scheduledTasksReportBrief');
  if (reportType === 'simple') return t('settings.scheduledTasksReportSimple');
  if (reportType === 'full') return t('settings.scheduledTasksReportFull');
  return t('settings.scheduledTasksReportDetailed');
}

function buildCreateRequest(draft: CreateDraft): ScheduledTaskCreateRequest | { error: string } {
  const name = draft.name.trim();
  const stockCode = draft.stockCode.trim();
  const timezone = draft.timezone.trim();
  const time = draft.time.trim();
  const maxAttemptsRaw = draft.maxAttempts.trim();

  if (!name) {
    return { error: 'name' };
  }
  if (!stockCode) {
    return { error: 'stockCode' };
  }
  if (!TIME_PATTERN.test(time)) {
    return { error: 'time' };
  }
  if (!timezone) {
    return { error: 'timezone' };
  }
  if (!MAX_ATTEMPTS_PATTERN.test(maxAttemptsRaw)) {
    return { error: 'maxAttempts' };
  }
  const maxAttempts = Number.parseInt(maxAttemptsRaw, 10);

  const isResearch = draft.taskType !== 'stock_analysis';
  return {
    schemaVersion: isResearch ? 2 : 1,
    name,
    taskType: draft.taskType,
    schedule: {
      kind: 'daily',
      time,
      timezone,
      calendarMarket: draft.calendarMarket,
      nonTradingDayPolicy: draft.nonTradingDayPolicy,
    },
    payload: isResearch
      ? { stockCode, notify: draft.notify }
      : { stockCode, reportType: draft.reportType, notify: draft.notify },
    enabled: draft.enabled,
    maxAttempts,
  };
}

const ScheduledTasksPanel: React.FC<ScheduledTasksPanelProps> = ({
  disabled = false,
  t,
  language,
}) => {
  const nameFieldId = useId();
  const stockFieldId = useId();
  const timeFieldId = useId();
  const timezoneFieldId = useId();
  const maxAttemptsFieldId = useId();
  const statusRequestSeq = useRef(0);

  const [items, setItems] = useState<ScheduledTaskDefinitionSummary[]>([]);
  const [latestRuns, setLatestRuns] = useState<Record<string, ScheduledTaskRunItem | null>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);
  const [actionError, setActionError] = useState<ParsedApiError | null>(null);
  const [actionSuccess, setActionSuccess] = useState('');
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [draft, setDraft] = useState<CreateDraft>(() => emptyDraft());
  const [clientValidation, setClientValidation] = useState('');

  const taskTypeOptions = useMemo(() => ([
    { value: 'stock_analysis', label: t('settings.scheduledTasksTypeAnalysis') },
    { value: 'research_brief', label: t('settings.scheduledTasksTypeResearchBrief') },
    { value: 'risk_check', label: t('settings.scheduledTasksTypeRiskCheck') },
  ]), [t]);

  const marketOptions = useMemo(
    () => CALENDAR_MARKETS.map((value) => ({
      value,
      label: marketLabel(value, t),
    })),
    [t],
  );

  const reportTypeOptions = useMemo(
    () => REPORT_TYPES.map((value) => ({
      value,
      label: reportTypeLabel(value, t),
    })),
    [t],
  );

  const policyOptions = useMemo(() => ([
    { value: 'skip', label: t('settings.scheduledTasksPolicySkip') },
    { value: 'run', label: t('settings.scheduledTasksPolicyRun') },
  ]), [t]);

  const loadLatestRuns = useCallback(async (definitions: ScheduledTaskDefinitionSummary[]) => {
    const requestId = statusRequestSeq.current + 1;
    statusRequestSeq.current = requestId;

    if (definitions.length === 0) {
      if (statusRequestSeq.current === requestId) {
        setLatestRuns({});
      }
      return;
    }

    const results = await Promise.allSettled(
      definitions.map(async (task) => {
        const status = await scheduledTasksApi.getStatus(task.id);
        return [task.id, status.latestRun] as const;
      }),
    );
    if (statusRequestSeq.current !== requestId) {
      return;
    }

    const next: Record<string, ScheduledTaskRunItem | null> = {};
    for (const result of results) {
      if (result.status === 'fulfilled') {
        const [taskId, latestRun] = result.value;
        next[taskId] = latestRun;
      }
    }
    setLatestRuns(next);
  }, []);

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
      void loadLatestRuns(response.items);
    } catch (error: unknown) {
      setLoadError(getParsedApiError(error));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [loadLatestRuns]);

  useEffect(() => {
    void loadTasks('initial');
  }, [loadTasks]);

  const openCreate = () => {
    setDraft(emptyDraft());
    setClientValidation('');
    setActionError(null);
    setIsCreateOpen(true);
  };

  const closeCreate = () => {
    if (isCreating) return;
    setIsCreateOpen(false);
    setClientValidation('');
  };

  const handleCreate = async () => {
    if (disabled || isCreating) return;
    const built = buildCreateRequest(draft);
    if ('error' in built) {
      const messages: Record<string, string> = {
        name: t('settings.scheduledTasksValidationName'),
        stockCode: t('settings.scheduledTasksValidationStock'),
        time: t('settings.scheduledTasksValidationTime'),
        timezone: t('settings.scheduledTasksValidationTimezone'),
        maxAttempts: t('settings.scheduledTasksValidationMaxAttempts'),
      };
      setClientValidation(messages[built.error] ?? t('settings.scheduledTasksValidationGeneric'));
      return;
    }

    setClientValidation('');
    setActionError(null);
    setActionSuccess('');
    setIsCreating(true);
    try {
      const created = await scheduledTasksApi.create(built);
      setIsCreateOpen(false);
      setActionSuccess(t('settings.scheduledTasksCreatedSuccess', { name: created.name }));
      await loadTasks('refresh');
    } catch (error: unknown) {
      setActionError(getParsedApiError(error));
    } finally {
      setIsCreating(false);
    }
  };

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
      void scheduledTasksApi.getStatus(task.id).then((status) => {
        setLatestRuns((current) => ({
          ...current,
          [task.id]: status.latestRun,
        }));
      }).catch(() => {
        // Fail-soft: list and enable/disable remain authoritative.
      });
    } catch (error: unknown) {
      setActionError(getParsedApiError(error));
    } finally {
      setPendingId(null);
    }
  };

  const isResearchType = draft.taskType !== 'stock_analysis';

  return (
    <SettingsSectionCard
      title={t('settings.scheduledTasksTitle')}
      description={t('settings.scheduledTasksDescription')}
      contentBordered
      actions={(
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="secondary"
            size="default"
            onClick={openCreate}
            disabled={disabled || isLoading || isRefreshing}
            data-testid="settings-scheduled-tasks-create"
          >
            <Plus className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
            {t('settings.scheduledTasksCreate')}
          </Button>
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
        </div>
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
      {actionError && !isCreateOpen ? (
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
          action={(
            <Button
              type="button"
              variant="secondary"
              size="default"
              onClick={openCreate}
              disabled={disabled}
            >
              {t('settings.scheduledTasksCreate')}
            </Button>
          )}
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
            const latestRun = latestRuns[task.id];
            const lastRunTime = latestRun
              ? formatTimestamp(latestRun.finishedAt ?? latestRun.startedAt ?? latestRun.scheduledFor, language)
              : null;
            return (
              <div
                key={task.id}
                className="py-3"
                data-testid={`settings-scheduled-task-${task.id}`}
              >
                <div className="flex min-h-14 flex-wrap items-center justify-between gap-3">
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
                      {latestRun ? (
                        <Badge
                          variant={runStatusVariant(latestRun.status)}
                          className="shrink-0"
                          data-testid={`settings-scheduled-task-status-${task.id}`}
                        >
                          {runStatusLabel(latestRun.status, t)}
                        </Badge>
                      ) : null}
                    </div>
                    <p className="mt-1 text-xs text-secondary-text">
                      {nextRun
                        ? t('settings.scheduledTasksNextRun', { time: nextRun })
                        : t('settings.scheduledTasksNoNextRun')}
                    </p>
                    <p className="mt-0.5 text-xs text-secondary-text">
                      {latestRun && lastRunTime
                        ? t('settings.scheduledTasksLastRun', {
                            status: runStatusLabel(latestRun.status, t),
                            time: lastRunTime,
                          })
                        : t('settings.scheduledTasksNoLastRun')}
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
                <ScheduledTaskRunHistory
                  taskId={task.id}
                  taskName={task.name}
                  disabled={disabled || isRefreshing}
                  t={t}
                  language={language}
                />
              </div>
            );
          })}
        </div>
      )}

      <Modal
        isOpen={isCreateOpen}
        onClose={closeCreate}
        title={t('settings.scheduledTasksCreateTitle')}
        description={t('settings.scheduledTasksCreateDescription')}
        size="wide"
        closeDisabled={isCreating}
        footer={(
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="secondary"
              size="default"
              onClick={closeCreate}
              disabled={isCreating}
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="button"
              variant="primary"
              size="default"
              onClick={() => void handleCreate()}
              disabled={disabled || isCreating}
              isLoading={isCreating}
              data-testid="settings-scheduled-tasks-create-submit"
            >
              {t('settings.scheduledTasksCreateSubmit')}
            </Button>
          </div>
        )}
      >
        <div className="space-y-3" data-testid="settings-scheduled-tasks-create-form">
          {clientValidation ? (
            <SettingsAlert
              title={t('settings.scheduledTasksValidationTitle')}
              message={clientValidation}
              variant="error"
            />
          ) : null}
          {actionError && isCreateOpen ? (
            <ApiErrorAlert error={actionError} />
          ) : null}

          <Input
            id={nameFieldId}
            label={t('settings.scheduledTasksFieldName')}
            value={draft.name}
            onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
            disabled={isCreating}
            autoComplete="off"
          />

          <Field controlId="scheduled-task-type" label={t('settings.scheduledTasksFieldType')}>
            <Select
              id="scheduled-task-type"
              value={draft.taskType}
              onChange={(value) => setDraft((current) => ({
                ...current,
                taskType: value as ScheduledTaskSupportedType,
              }))}
              options={taskTypeOptions}
              disabled={isCreating}
              ariaLabel={t('settings.scheduledTasksFieldType')}
            />
          </Field>

          <Input
            id={stockFieldId}
            label={t('settings.scheduledTasksFieldStock')}
            value={draft.stockCode}
            onChange={(event) => setDraft((current) => ({ ...current, stockCode: event.target.value }))}
            disabled={isCreating}
            autoComplete="off"
            placeholder={t('settings.scheduledTasksFieldStockPlaceholder')}
          />

          {!isResearchType ? (
            <Field controlId="scheduled-task-report-type" label={t('settings.scheduledTasksFieldReportType')}>
              <Select
                id="scheduled-task-report-type"
                value={draft.reportType}
                onChange={(value) => setDraft((current) => ({
                  ...current,
                  reportType: value as ScheduledTaskReportType,
                }))}
                options={reportTypeOptions}
                disabled={isCreating}
                ariaLabel={t('settings.scheduledTasksFieldReportType')}
              />
            </Field>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              id={timeFieldId}
              label={t('settings.scheduledTasksFieldTime')}
              value={draft.time}
              onChange={(event) => setDraft((current) => ({ ...current, time: event.target.value }))}
              disabled={isCreating}
              placeholder="16:30"
              autoComplete="off"
              hint={t('settings.scheduledTasksFieldTimeHint')}
            />
            <Input
              id={timezoneFieldId}
              label={t('settings.scheduledTasksFieldTimezone')}
              value={draft.timezone}
              onChange={(event) => setDraft((current) => ({ ...current, timezone: event.target.value }))}
              disabled={isCreating}
              autoComplete="off"
              hint={t('settings.scheduledTasksFieldTimezoneHint')}
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field controlId="scheduled-task-market" label={t('settings.scheduledTasksFieldMarket')}>
              <Select
                id="scheduled-task-market"
                value={draft.calendarMarket}
                onChange={(value) => setDraft((current) => ({
                  ...current,
                  calendarMarket: value as ScheduledTaskCalendarMarket,
                }))}
                options={marketOptions}
                disabled={isCreating}
                ariaLabel={t('settings.scheduledTasksFieldMarket')}
              />
            </Field>
            <Field controlId="scheduled-task-policy" label={t('settings.scheduledTasksFieldPolicy')}>
              <Select
                id="scheduled-task-policy"
                value={draft.nonTradingDayPolicy}
                onChange={(value) => setDraft((current) => ({
                  ...current,
                  nonTradingDayPolicy: value as ScheduledTaskNonTradingDayPolicy,
                }))}
                options={policyOptions}
                disabled={isCreating}
                ariaLabel={t('settings.scheduledTasksFieldPolicy')}
              />
            </Field>
          </div>

          <Input
            id={maxAttemptsFieldId}
            label={t('settings.scheduledTasksFieldMaxAttempts')}
            type="number"
            min={1}
            max={3}
            value={draft.maxAttempts}
            onChange={(event) => setDraft((current) => ({
              ...current,
              maxAttempts: event.target.value,
            }))}
            disabled={isCreating}
            hint={t('settings.scheduledTasksFieldMaxAttemptsHint')}
          />

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border/70 px-3 py-2">
            <div>
              <p className="text-xs font-medium text-foreground">
                {t('settings.scheduledTasksFieldNotify')}
              </p>
              <p className="mt-0.5 text-xs text-secondary-text">
                {t('settings.scheduledTasksFieldNotifyHint')}
              </p>
            </div>
            <Switch
              checked={draft.notify}
              onCheckedChange={(checked) => setDraft((current) => ({ ...current, notify: checked }))}
              disabled={isCreating}
              aria-label={t('settings.scheduledTasksFieldNotify')}
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border/70 px-3 py-2">
            <div>
              <p className="text-xs font-medium text-foreground">
                {t('settings.scheduledTasksFieldEnabled')}
              </p>
              <p className="mt-0.5 text-xs text-secondary-text">
                {t('settings.scheduledTasksFieldEnabledHint')}
              </p>
            </div>
            <Switch
              checked={draft.enabled}
              onCheckedChange={(checked) => setDraft((current) => ({ ...current, enabled: checked }))}
              disabled={isCreating}
              aria-label={t('settings.scheduledTasksFieldEnabled')}
            />
          </div>
        </div>
      </Modal>
    </SettingsSectionCard>
  );
};

export default ScheduledTasksPanel;
