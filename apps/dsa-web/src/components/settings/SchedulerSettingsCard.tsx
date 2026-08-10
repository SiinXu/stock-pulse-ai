import { useCallback, useEffect, useRef, useState } from 'react';
import type React from 'react';
import { Clock, Play, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { scheduledTasksApi } from '../../api/scheduledTasks';
import { systemConfigApi } from '../../api/systemConfig';
import type {
  ConfigValidationIssue,
  SchedulerStatusResponse,
  SystemConfigItem,
} from '../../types/systemConfig';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import { getUiLocale } from '../../utils/uiLocale';
import {
  ApiErrorAlert,
  Button,
  IconButton,
  InlineAlert,
  Surface,
  TimePicker,
} from '../common';
import { SettingsAlert } from './SettingsAlert';
import { SettingsSectionCard } from './SettingsSectionCard';
import { SettingsSwitch } from './SettingsSwitch';
import { getConfigItem } from './settingsConfigItems';

const SCHEDULE_TIME_PATTERN = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
/** Poll interval while this process reports analysis running (run-now / schedule). */
const RUNNING_STATUS_POLL_MS = 3000;

function isEnabledConfigValue(value: unknown) {
  return String(value ?? '').trim().toLowerCase() === 'true';
}

function parseScheduleTimes(scheduleTimesValue?: string, fallbackValue?: string, defaultValue?: string | null) {
  const values = String(scheduleTimesValue ?? '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);

  if (values.length > 0) {
    return [...new Set(values)];
  }

  const fallback = String(fallbackValue ?? '').trim();
  if (fallback) {
    return [fallback];
  }

  const schemaDefault = String(defaultValue ?? '').trim();
  return schemaDefault ? [schemaDefault] : [];
}

function serializeScheduleTimes(times: string[]) {
  return times.map((time) => time.trim()).filter(Boolean).join(',');
}

function formatSchedulerTimestamp(
  value: string | null | undefined,
  language: UiLanguage,
  scheduleTimezone: string | undefined,
  t: (key: UiTextKey, params?: Record<string, string | number>) => string,
) {
  if (!value) {
    return '-';
  }

  const hasExplicitOffset = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
  if (!hasExplicitOffset) {
    return `${value} · ${t('settings.schedulerTimezoneUnknown')}`;
  }
  if (!scheduleTimezone) {
    return value;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  try {
    const locale = getUiLocale(language);
    const parts = new Intl.DateTimeFormat(locale, {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: scheduleTimezone,
      timeZoneName: 'shortOffset',
    }).formatToParts(date);

    const zone = parts.find((part) => part.type === 'timeZoneName')?.value?.replace('UTC', 'GMT');
    const body = parts
      .filter((part) => part.type !== 'timeZoneName')
      .map((part) => part.value)
      .join('')
      .trim();

    return `${body}${zone ? ` ${zone}` : ''} · ${scheduleTimezone}`;
  } catch {
    return `${value} · ${scheduleTimezone}`;
  }
}

function formatSkipReason(
  reason: string | null | undefined,
  t: (key: UiTextKey, params?: Record<string, string | number>) => string,
) {
  if (!reason) {
    return '';
  }
  const reasonKeys: Record<string, UiTextKey> = {
    analysis_already_running: 'settings.schedulerSkipReasonBusy',
    scheduler_not_attached: 'settings.schedulerReasonNotAttached',
    scheduler_disabled: 'settings.schedulerReasonDisabled',
    scheduler_state_unavailable: 'settings.schedulerReasonUnavailable',
  };
  if (reasonKeys[reason]) {
    return t(reasonKeys[reason]);
  }
  return t('settings.schedulerReasonUnknown');
}

function formatProcessMode(
  processMode: SchedulerStatusResponse['processMode'],
  t: (key: UiTextKey, params?: Record<string, string | number>) => string,
) {
  const modeKeys: Record<string, UiTextKey> = {
    serve: 'settings.schedulerProcessModeServe',
    desktop: 'settings.schedulerProcessModeDesktop',
    not_attached: 'settings.schedulerProcessModeNotAttached',
  };
  return processMode && modeKeys[processMode]
    ? t(modeKeys[processMode])
    : t('settings.schedulerProcessModeUnknown');
}

type TrackedRun = {
  id: string | null;
  state: 'running' | 'succeeded' | 'failed' | 'unknown';
};

type SchedulerSettingsCardProps = {
  items: SystemConfigItem[];
  disabled: boolean;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  statusRefreshToken: number;
  onChange: (key: string, value: string) => void;
  onSchedulerStateChange?: (payload: {
    runtimeEnabled: boolean | null;
    overrideEnabled: boolean | null;
  }) => void;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
  language: UiLanguage;
};

const SchedulerSettingsCard: React.FC<SchedulerSettingsCardProps> = ({
  items,
  disabled,
  issueByKey,
  statusRefreshToken,
  onChange,
  onSchedulerStateChange,
  t,
  language,
}) => {
  const scheduleEnabledItem = getConfigItem(items, 'SCHEDULE_ENABLED');
  const scheduleTimesItem = getConfigItem(items, 'SCHEDULE_TIMES');
  const scheduleTimeItem = getConfigItem(items, 'SCHEDULE_TIME');
  const hasSchedulerSettings = Boolean(scheduleEnabledItem || scheduleTimesItem || scheduleTimeItem);
  const [status, setStatus] = useState<SchedulerStatusResponse | null>(null);
  const [isRefreshingStatus, setIsRefreshingStatus] = useState(false);
  const [isRunningNow, setIsRunningNow] = useState(false);
  const [statusError, setStatusError] = useState<ParsedApiError | null>(null);
  const [runNowError, setRunNowError] = useState<ParsedApiError | null>(null);
  const [trackedRun, setTrackedRun] = useState<TrackedRun | null>(null);
  const [scheduleEnabledOverride, setScheduleEnabledOverride] = useState<boolean | null>(null);
  const [isAddingTime, setIsAddingTime] = useState(false);
  // Live probe: true only when list(enabled=true) succeeds with ≥1 item.
  // null = not yet known / probe failed — never invent an overlap state.
  const [hasEnabledVersionedTasks, setHasEnabledVersionedTasks] = useState<boolean | null>(null);
  const mountedRef = useRef(true);
  const statusRequestRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const refreshVersionedTaskOverlap = useCallback(async () => {
    try {
      const response = await scheduledTasksApi.list({ enabled: true, limit: 1 });
      const hasItems = (response.items?.length ?? 0) > 0;
      const hasTotal = (response.total ?? 0) > 0;
      if (mountedRef.current) {
        setHasEnabledVersionedTasks(hasItems || hasTotal);
      }
    } catch {
      // Fail soft: missing versioned-task probe must not block legacy controls.
      if (mountedRef.current) {
        setHasEnabledVersionedTasks(null);
      }
    }
  }, []);

  const refreshSchedulerStatus = useCallback(async () => {
    const requestId = ++statusRequestRef.current;
    setStatusError(null);
    setIsRefreshingStatus(true);
    try {
      const payload = await systemConfigApi.getSchedulerStatus();
      if (mountedRef.current && requestId === statusRequestRef.current) {
        setStatus(payload);
        setTrackedRun((current) => {
          if (!current) return current;
          if (current.id && payload.activeRunId === current.id) {
            return { ...current, state: 'running' };
          }
          if (current.id && payload.lastRunId === current.id) {
            return {
              ...current,
              state: payload.lastRunOutcome === 'succeeded'
                ? 'succeeded'
                : payload.lastRunOutcome === 'failed'
                  ? 'failed'
                  : 'unknown',
            };
          }
          if (!payload.running) {
            return { ...current, state: 'unknown' };
          }
          return current;
        });
      }
    } catch (error: unknown) {
      if (mountedRef.current && requestId === statusRequestRef.current) {
        setStatusError(getParsedApiError(error));
      }
    } finally {
      if (mountedRef.current && requestId === statusRequestRef.current) {
        setIsRefreshingStatus(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!hasSchedulerSettings) {
      return;
    }
    void refreshSchedulerStatus();
    void refreshVersionedTaskOverlap();
  }, [hasSchedulerSettings, refreshSchedulerStatus, refreshVersionedTaskOverlap, statusRefreshToken]);

  // While analysis is running in this process, poll status so run-now stays trackable
  // (accepted → running → idle with last success/error) without showing only a task id.
  useEffect(() => {
    if (!hasSchedulerSettings || (!status?.running && trackedRun?.state !== 'running')) {
      return;
    }
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      await refreshSchedulerStatus();
      if (!cancelled) {
        timer = window.setTimeout(() => void poll(), RUNNING_STATUS_POLL_MS);
      }
    };
    timer = window.setTimeout(() => void poll(), RUNNING_STATUS_POLL_MS);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [hasSchedulerSettings, status?.running, trackedRun?.state, refreshSchedulerStatus]);

  useEffect(() => {
    if (!onSchedulerStateChange) {
      return;
    }

    const runtimeEnabled = status?.enabled ?? null;
    onSchedulerStateChange({
      runtimeEnabled,
      overrideEnabled: scheduleEnabledOverride,
    });
  }, [onSchedulerStateChange, status?.enabled, scheduleEnabledOverride]);

  if (!hasSchedulerSettings) {
    return null;
  }

  const scheduleEnabled = isEnabledConfigValue(scheduleEnabledItem?.value);
  const scheduleTimes = parseScheduleTimes(
    String(scheduleTimesItem?.value ?? ''),
    String(scheduleTimeItem?.value ?? ''),
    scheduleTimeItem?.schema?.defaultValue,
  );
  const timeTargetKey = scheduleTimesItem ? 'SCHEDULE_TIMES' : 'SCHEDULE_TIME';
  const statusEnabled = status?.enabled ?? scheduleEnabled;
  const displayedScheduleEnabled = scheduleEnabledOverride ?? statusEnabled;
  // Directional migration notice when legacy is on; stronger copy if versioned tasks also enabled.
  const showMigrationNotice = displayedScheduleEnabled;
  const bothTracksActive = displayedScheduleEnabled && hasEnabledVersionedTasks === true;
  const effectiveStatusTimes = status?.scheduleTimes?.length ? status.scheduleTimes : scheduleTimes.filter(Boolean);
  const validationIssues = [
    ...(issueByKey.SCHEDULE_ENABLED || []),
    ...(issueByKey.SCHEDULE_TIMES || []),
    ...(issueByKey.SCHEDULE_TIME || []),
  ];
  const analysisRunning = Boolean(status?.running);
  const runNowAvailable = status?.runNowAvailable === true;
  const runNowBlocked = disabled || isRunningNow || analysisRunning || !runNowAvailable;
  const nextRunDisplay = status?.nextRunAt
    ? formatSchedulerTimestamp(status.nextRunAt, language, status.scheduleTimezone, t)
    : (statusEnabled ? t('settings.schedulerNoNextRun') : '-');
  const skipReasonText = formatSkipReason(status?.lastSkipReason, t);
  const runNowBlockReasonText = analysisRunning
    ? t('settings.schedulerSkipReasonBusy')
    : formatSkipReason(status?.runNowBlockReason, t)
      || (!runNowAvailable ? t('settings.schedulerReasonUnavailable') : '');
  const attachmentText = status?.attached === true
    ? t('settings.schedulerAttached')
    : status?.attached === false
      ? t('settings.schedulerNotAttached')
      : t('settings.schedulerAttachmentUnknown');
  const lastSkippedDisplay = status?.lastSkippedAt
    ? [
        formatSchedulerTimestamp(status.lastSkippedAt, language, status.scheduleTimezone, t),
        skipReasonText,
      ].filter(Boolean).join(' · ')
    : (skipReasonText || null);

  const updateScheduleTimes = (nextTimes: string[]) => {
    if (timeTargetKey === 'SCHEDULE_TIME') {
      onChange(timeTargetKey, nextTimes[0] || '');
      return;
    }
    onChange(timeTargetKey, serializeScheduleTimes(nextTimes));
  };

  const runSchedulerNow = async () => {
    setRunNowError(null);
    setTrackedRun(null);
    setIsRunningNow(true);
    try {
      const result = await systemConfigApi.runSchedulerNow();
      // Contract: accepted + running means work started in this process (no async task id).
      if (result.accepted) {
        setTrackedRun({
          id: result.runId ?? null,
          state: 'running',
        });
      } else if (result.running) {
        setRunNowError(getParsedApiError(new Error(t('settings.schedulerBusyReason'))));
      }
      await refreshSchedulerStatus();
    } catch (error: unknown) {
      setRunNowError(getParsedApiError(error));
      await refreshSchedulerStatus();
    } finally {
      if (mountedRef.current) {
        setIsRunningNow(false);
      }
    }
  };

  return (
    <SettingsSectionCard
      title={t('settings.schedulerTitle')}
    >
      <div data-testid="scheduler-settings-card" className="space-y-4">
        {showMigrationNotice ? (
          <InlineAlert
            variant="warning"
            data-testid="scheduler-migration-notice"
            title={t('settings.schedulerMigrationTitle')}
            message={
              bothTracksActive
                ? t('settings.schedulerMigrationNoticeBothActive')
                : t('settings.schedulerMigrationNotice')
            }
          />
        ) : null}
        <div className="grid grid-cols-1 gap-3 2xl:grid-cols-2 2xl:items-start">
          <Surface level="interactive" className="space-y-4 px-4 py-4">
            <div className="flex min-h-11 items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-foreground">{t('settings.schedulerEnable')}</p>
                <p className="text-xs leading-6 text-muted-text">{t('settings.schedulerEnableDescription')}</p>
              </div>
              <SettingsSwitch
                checked={displayedScheduleEnabled}
                disabled={disabled || !scheduleEnabledItem?.schema?.isEditable}
                onCheckedChange={(nextEnabled) => {
                  setScheduleEnabledOverride(nextEnabled);
                  onChange('SCHEDULE_ENABLED', nextEnabled ? 'true' : 'false');
                }}
                testId="scheduler-enabled-switch"
                aria-label={t('settings.schedulerEnable')}
              />
            </div>

            <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto] md:items-center md:gap-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Clock className="h-4 w-4" aria-hidden="true" />
                {t('settings.schedulerTimes')}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {scheduleTimes.map((time, index) => (
                  <div
                    key={index}
                    className="inline-flex shrink-0 items-center gap-1"
                  >
                    <TimePicker
                      data-testid={`scheduler-time-input-${index}`}
                      value={SCHEDULE_TIME_PATTERN.test(time) ? time : ''}
                      ariaLabel={t('settings.schedulerTimeInputAria', { index: index + 1 })}
                      className="w-32"
                      triggerClassName="h-9 min-h-9 text-sm font-medium"
                      disabled={disabled}
                      onChange={(nextValue) => {
                        if (SCHEDULE_TIME_PATTERN.test(nextValue)) {
                          updateScheduleTimes(scheduleTimes.map((currentTime, currentIndex) => (
                            currentIndex === index ? nextValue : currentTime
                          )));
                        }
                      }}
                    />
                    {scheduleTimes.length > 1 ? (
                      <IconButton
                        type="button"
                        variant="danger"
                        size="default"
                        aria-label={t('settings.schedulerRemoveTime')}
                        disabled={disabled}
                        onClick={() => {
                          updateScheduleTimes(scheduleTimes.filter((_, currentIndex) => currentIndex !== index));
                        }}
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </IconButton>
                    ) : null}
                  </div>
                ))}
                {isAddingTime ? (
                  <TimePicker
                    data-testid="scheduler-new-time-input"
                    value=""
                    ariaLabel={t('settings.schedulerTimeInputAria', { index: scheduleTimes.length + 1 })}
                    placeholder={t('settings.schedulerTimePlaceholder')}
                    className="w-32"
                    triggerClassName="h-9 min-h-9 text-sm font-medium"
                    disabled={disabled}
                    autoOpen
                    onOpenChange={(open) => {
                      if (!open) setIsAddingTime(false);
                    }}
                    onChange={(nextValue) => {
                      if (SCHEDULE_TIME_PATTERN.test(nextValue) && !scheduleTimes.includes(nextValue)) {
                        updateScheduleTimes([...scheduleTimes, nextValue]);
                      }
                      if (SCHEDULE_TIME_PATTERN.test(nextValue)) {
                        setIsAddingTime(false);
                      }
                    }}
                  />
                ) : null}
                {timeTargetKey === 'SCHEDULE_TIMES' && !isAddingTime ? (
                  <Button
                    type="button"
                    variant="secondary"
                    size="default"
                    className="shrink-0"
                    data-testid="scheduler-add-time-button"
                    disabled={disabled}
                    onClick={() => setIsAddingTime(true)}
                  >
                    <Plus className="h-4 w-4" aria-hidden="true" />
                    {t('settings.schedulerAddTime')}
                  </Button>
                ) : null}
              </div>
            </div>
          </Surface>

          <Surface level="interactive" className="space-y-3 px-4 py-4">
            <div>
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-foreground">{t('settings.schedulerStatus')}</p>
                <span
                  className="text-xs text-muted-text"
                  data-testid="scheduler-runtime-badge"
                >
                  {analysisRunning
                    ? t('settings.schedulerRunning')
                    : statusEnabled
                      ? t('settings.schedulerEnabled')
                      : t('settings.schedulerDisabled')}
                </span>
              </div>
              <p className="mt-1 text-xs leading-6 text-muted-text">
                {t('settings.schedulerStatusScopeNote')}
              </p>
            </div>

            <Surface
              as="div"
              level="interactive"
              className="space-y-1 px-3 py-2"
              data-testid="scheduler-process-mode"
            >
              <p className="text-xs text-muted-text">{t('settings.schedulerProcessMode')}</p>
              <p className="text-xs font-medium text-foreground" data-testid="scheduler-process-mode-value">
                {formatProcessMode(status?.processMode, t)} · {attachmentText}
              </p>
              <p
                className="text-xs leading-5 text-muted-text"
                data-testid="scheduler-owner-note"
              >
                {t('settings.schedulerOwnerNote')}
              </p>
            </Surface>

            <dl className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-2 xl:grid-cols-3">
              <Surface as="div" level="interactive" className="px-3 py-2">
                <dt className="text-muted-text">{t('settings.schedulerEffectiveTimes')}</dt>
                <dd className="mt-1 font-medium text-foreground">{effectiveStatusTimes.join(', ') || '-'}</dd>
              </Surface>
              <Surface as="div" level="interactive" className="px-3 py-2">
                <dt className="text-muted-text">{t('settings.schedulerNextRun')}</dt>
                <dd data-testid="scheduler-next-run" className="mt-1 font-medium text-foreground">
                  {nextRunDisplay}
                </dd>
              </Surface>
              <Surface as="div" level="interactive" className="px-3 py-2">
                <dt className="text-muted-text">{t('settings.schedulerLastSuccess')}</dt>
                <dd data-testid="scheduler-last-success" className="mt-1 font-medium text-foreground">
                  {formatSchedulerTimestamp(status?.lastSuccessAt, language, status?.scheduleTimezone, t)}
                </dd>
              </Surface>
              {lastSkippedDisplay ? (
                <Surface as="div" level="interactive" className="px-3 py-2 sm:col-span-2 xl:col-span-3">
                  <dt className="text-muted-text">{t('settings.schedulerLastSkipped')}</dt>
                  <dd data-testid="scheduler-last-skipped" className="mt-1 font-medium text-foreground">
                    {lastSkippedDisplay}
                  </dd>
                </Surface>
              ) : null}
            </dl>
            {status?.lastError ? (
              <InlineAlert
                variant="danger"
                title={t('settings.schedulerLastError')}
                message={status.lastError}
                data-testid="scheduler-last-error"
              />
            ) : null}
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="secondary"
                size="default"
                data-testid="scheduler-refresh-status-button"
                disabled={disabled || isRefreshingStatus}
                isLoading={isRefreshingStatus}
                loadingText={t('settings.schedulerRefreshing')}
                onClick={() => void refreshSchedulerStatus()}
              >
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                {t('settings.schedulerRefresh')}
              </Button>
              <Button
                type="button"
                variant="primary"
                size="default"
                data-testid="scheduler-run-now-button"
                disabled={runNowBlocked}
                isLoading={isRunningNow || analysisRunning}
                loadingText={t('settings.schedulerRunningNow')}
                aria-describedby={runNowBlocked && runNowBlockReasonText ? 'scheduler-run-now-busy-reason' : undefined}
                onClick={() => void runSchedulerNow()}
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                {t('settings.schedulerRunNow')}
              </Button>
            </div>
            {runNowBlocked && runNowBlockReasonText ? (
              <p
                id="scheduler-run-now-busy-reason"
                data-testid="scheduler-run-now-busy-reason"
                className="text-xs leading-5 text-muted-text"
              >
                {runNowBlockReasonText}
              </p>
            ) : null}
          </Surface>
        </div>

        {validationIssues.length ? (
          <InlineAlert
            variant="danger"
            message={(
              <ul className="space-y-1">
                {validationIssues.map((issue) => (
                  <li key={`${issue.key}-${issue.code}`}>{issue.message}</li>
                ))}
              </ul>
            )}
          />
        ) : null}
        {statusError ? <ApiErrorAlert error={statusError} /> : null}
        {runNowError ? <ApiErrorAlert error={runNowError} /> : null}
        {!runNowError && trackedRun?.state === 'running' ? (
          <SettingsAlert
            title={t('settings.actionSuccess')}
            message={t('settings.schedulerRunAccepted')}
            variant="success"
          />
        ) : null}
        {!runNowError && trackedRun?.state === 'succeeded' ? (
          <SettingsAlert
            title={t('settings.actionSuccess')}
            message={t('settings.schedulerRunSucceeded')}
            variant="success"
          />
        ) : null}
        {!runNowError && trackedRun?.state === 'failed' ? (
          <SettingsAlert
            title={t('settings.schedulerRunFailedTitle')}
            message={t('settings.schedulerRunFailed')}
            variant="error"
          />
        ) : null}
        {!runNowError && trackedRun?.state === 'unknown' ? (
          <SettingsAlert
            title={t('settings.schedulerRunOutcomeUnknownTitle')}
            message={t('settings.schedulerRunOutcomeUnknown')}
            variant="warning"
          />
        ) : null}
      </div>
    </SettingsSectionCard>
  );
};

export default SchedulerSettingsCard;
