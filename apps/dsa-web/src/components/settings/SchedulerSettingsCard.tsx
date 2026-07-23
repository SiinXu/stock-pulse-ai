import { useCallback, useEffect, useState } from 'react';
import type React from 'react';
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
  const [runNowSuccess, setRunNowSuccess] = useState('');
  const [scheduleEnabledOverride, setScheduleEnabledOverride] = useState<boolean | null>(null);
  const [isAddingTime, setIsAddingTime] = useState(false);

  const refreshSchedulerStatus = useCallback(async () => {
    setStatusError(null);
    setIsRefreshingStatus(true);
    try {
      const payload = await systemConfigApi.getSchedulerStatus();
      setStatus(payload);
    } catch (error: unknown) {
      setStatusError(getParsedApiError(error));
    } finally {
      setIsRefreshingStatus(false);
    }
  }, []);

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
    >
      <div data-testid="scheduler-settings-card" className="space-y-4">
        <div className="grid grid-cols-1 gap-3">
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
              <Surface as="div" level="interactive" className="px-3 py-2">
                <dt className="text-muted-text">{t('settings.schedulerEffectiveTimes')}</dt>
                <dd className="mt-1 font-medium text-foreground">{effectiveStatusTimes.join(', ') || '-'}</dd>
              </Surface>
              <Surface as="div" level="interactive" className="px-3 py-2">
                <dt className="text-muted-text">{t('settings.schedulerNextRun')}</dt>
                <dd className="mt-1 font-medium text-foreground">
                  {formatSchedulerTimestamp(status?.nextRunAt, language)}
                </dd>
              </Surface>
              <Surface as="div" level="interactive" className="px-3 py-2">
                <dt className="text-muted-text">{t('settings.schedulerLastSuccess')}</dt>
                <dd data-testid="scheduler-last-success" className="mt-1 font-medium text-foreground">
                  {formatSchedulerTimestamp(status?.lastSuccessAt, language)}
                </dd>
              </Surface>
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
                disabled={disabled || isRunningNow}
                isLoading={isRunningNow}
                loadingText={t('settings.schedulerRunningNow')}
                onClick={() => void runSchedulerNow()}
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                {t('settings.schedulerRunNow')}
              </Button>
            </div>
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
        {!runNowError && runNowSuccess ? (
          <SettingsAlert title={t('settings.actionSuccess')} message={runNowSuccess} variant="success" />
        ) : null}
      </div>
    </SettingsSectionCard>
  );
};

export default SchedulerSettingsCard;
