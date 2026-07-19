import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Clock, Play, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { systemConfigApi } from '../../api/systemConfig';
import type {
  ConfigValidationIssue,
  SchedulerStatusResponse,
  SystemConfigItem,
} from '../../types/systemConfig';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import { getUiLocale } from '../../utils/uiLocale';
import { ApiErrorAlert, Button, TimePicker } from '../common';
import { SettingsAlert } from './SettingsAlert';
import { SettingsSectionCard } from './SettingsSectionCard';
import { SettingsSwitch } from './SettingsSwitch';

const SCHEDULE_TIME_PATTERN = /^(?:[01]\d|2[0-3]):[0-5]\d$/;

function getConfigItem(items: SystemConfigItem[], key: string) {
  return items.find((item) => item.key === key);
}

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

function formatSchedulerTimestamp(value: string | null | undefined, language: UiLanguage) {
  if (!value) {
    return '-';
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

type SchedulerSettingsCardProps = {
  items: SystemConfigItem[];
  disabled: boolean;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  statusRefreshToken: number;
  overrideResetToken: string;
  onChange: (key: string, value: string) => void;
  onSchedulerStateChange?: (payload: {
    runtimeEnabled: boolean | null;
    overrideEnabled: boolean | null;
  }) => void;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
  language: UiLanguage;
};

export const SchedulerSettingsCard: React.FC<SchedulerSettingsCardProps> = ({
  items,
  disabled,
  issueByKey,
  statusRefreshToken,
  overrideResetToken,
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
  const [runNowSuccess, setRunNowSuccess] = useState('');
  const [scheduleEnabledOverride, setScheduleEnabledOverride] = useState<boolean | null>(null);
  const [isAddingTime, setIsAddingTime] = useState(false);
  const statusRequestIdRef = useRef(0);

  const refreshSchedulerStatus = useCallback(async () => {
    const requestId = statusRequestIdRef.current + 1;
    statusRequestIdRef.current = requestId;
    setStatusError(null);
    setIsRefreshingStatus(true);
    try {
      const payload = await systemConfigApi.getSchedulerStatus();
      if (statusRequestIdRef.current !== requestId) {
        return;
      }
      setStatus(payload);
      setScheduleEnabledOverride((current) => current === payload.enabled ? null : current);
    } catch (error: unknown) {
      if (statusRequestIdRef.current !== requestId) {
        return;
      }
      setStatusError(getParsedApiError(error));
    } finally {
      if (statusRequestIdRef.current === requestId) {
        setIsRefreshingStatus(false);
      }
    }
  }, []);

  useEffect(() => {
    setScheduleEnabledOverride(null);
  }, [overrideResetToken]);

  useEffect(() => {
    if (!hasSchedulerSettings) {
      return;
    }
    void refreshSchedulerStatus();
  }, [hasSchedulerSettings, refreshSchedulerStatus, statusRefreshToken]);

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
  const effectiveStatusTimes = status?.scheduleTimes?.length ? status.scheduleTimes : scheduleTimes.filter(Boolean);
  const validationIssues = [
    ...(issueByKey.SCHEDULE_ENABLED || []),
    ...(issueByKey.SCHEDULE_TIMES || []),
    ...(issueByKey.SCHEDULE_TIME || []),
  ];

  const updateScheduleTimes = (nextTimes: string[]) => {
    if (timeTargetKey === 'SCHEDULE_TIME') {
      onChange(timeTargetKey, nextTimes[0] || '');
      return;
    }
    onChange(timeTargetKey, serializeScheduleTimes(nextTimes));
  };

  const runSchedulerNow = async () => {
    setRunNowError(null);
    setRunNowSuccess('');
    setIsRunningNow(true);
    try {
      await systemConfigApi.runSchedulerNow();
      setRunNowSuccess(t('settings.schedulerRunAccepted'));
      await refreshSchedulerStatus();
    } catch (error: unknown) {
      setRunNowError(getParsedApiError(error));
    } finally {
      setIsRunningNow(false);
    }
  };

  return (
    <SettingsSectionCard
      title={t('settings.schedulerTitle')}
      description={t('settings.schedulerDescription')}
      contentBordered
    >
      <div data-testid="scheduler-settings-card" className="space-y-4">
        <div className="grid grid-cols-1 gap-3">
          <div className="space-y-4 rounded-2xl border settings-border bg-background/35 px-4 py-4">
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

            <div className="space-y-2">
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
                      className="w-24"
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
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 min-w-8 text-muted-text hover:bg-danger/10 hover:text-danger"
                        aria-label={t('settings.schedulerRemoveTime')}
                        title={t('settings.schedulerRemoveTime')}
                        disabled={disabled}
                        onClick={() => {
                          updateScheduleTimes(scheduleTimes.filter((_, currentIndex) => currentIndex !== index));
                        }}
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    ) : null}
                  </div>
                ))}
                {isAddingTime ? (
                  <TimePicker
                    data-testid="scheduler-new-time-input"
                    value=""
                    ariaLabel={t('settings.schedulerTimeInputAria', { index: scheduleTimes.length + 1 })}
                    placeholder={t('settings.schedulerTimePlaceholder')}
                    className="w-24"
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
                    variant="ghost"
                    size="sm"
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
          </div>

          <div className="space-y-3 rounded-2xl border settings-border bg-background/35 px-4 py-4">
            <div>
              <p className="text-sm font-semibold text-foreground">{t('settings.schedulerStatus')}</p>
              <p className="mt-1 text-xs leading-6 text-muted-text">
                {status?.running
                  ? t('settings.schedulerRunning')
                  : statusEnabled
                    ? t('settings.schedulerEnabled')
                    : t('settings.schedulerDisabled')}
              </p>
            </div>
            <dl className="grid grid-cols-1 gap-2 text-xs">
              <div className="rounded-xl border settings-border bg-card/60 px-3 py-2">
                <dt className="text-muted-text">{t('settings.schedulerEffectiveTimes')}</dt>
                <dd className="mt-1 font-medium text-foreground">{effectiveStatusTimes.join(', ') || '-'}</dd>
              </div>
              <div className="rounded-xl border settings-border bg-card/60 px-3 py-2">
                <dt className="text-muted-text">{t('settings.schedulerNextRun')}</dt>
                <dd className="mt-1 font-medium text-foreground">
                  {formatSchedulerTimestamp(status?.nextRunAt, language)}
                </dd>
              </div>
              <div className="rounded-xl border settings-border bg-card/60 px-3 py-2">
                <dt className="text-muted-text">{t('settings.schedulerLastSuccess')}</dt>
                <dd data-testid="scheduler-last-success" className="mt-1 font-medium text-foreground">
                  {formatSchedulerTimestamp(status?.lastSuccessAt, language)}
                </dd>
              </div>
              {status?.lastError ? (
                <div className="rounded-xl border border-danger/40 bg-danger/10 px-3 py-2">
                  <dt className="text-danger">{t('settings.schedulerLastError')}</dt>
                  <dd data-testid="scheduler-last-error" className="mt-1 break-words text-danger">{status.lastError}</dd>
                </div>
              ) : null}
            </dl>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
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
                size="sm"
                data-testid="scheduler-run-now-button"
                disabled={disabled || isRunningNow}
                isLoading={isRunningNow}
                loadingText={t('settings.schedulerRunningNow')}
                onClick={() => void runSchedulerNow()}
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                {t('settings.schedulerRunNow')}
              </Button>
            </div>
          </div>
        </div>

        {validationIssues.length ? (
          <div className="space-y-1 text-xs text-danger">
            {validationIssues.map((issue) => (
              <p key={`${issue.key}-${issue.code}`}>{issue.message}</p>
            ))}
          </div>
        ) : null}
        {statusError ? <ApiErrorAlert error={statusError} /> : null}
        {runNowError ? <ApiErrorAlert error={runNowError} /> : null}
        {!runNowError && runNowSuccess ? (
          <SettingsAlert title={t('settings.actionSuccess')} message={runNowSuccess} variant="success" />
        ) : null}
      </div>
    </SettingsSectionCard>
  );
};
