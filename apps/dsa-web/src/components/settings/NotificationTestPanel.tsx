import { useEffect, useMemo, useState } from 'react';
import type React from 'react';
import { Send, Settings } from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { createParsedApiError, getParsedApiError, type ParsedApiError } from '../../api/error';
import { systemConfigApi } from '../../api/systemConfig';
import type {
  NotificationTestChannel,
  TestNotificationChannelResponse,
  SystemConfigUpdateItem,
} from '../../types/systemConfig';
import { ApiErrorAlert, Badge, Button, InlineAlert, Input, Modal, Select, Textarea } from '../common';
import { SettingsSectionCard } from './SettingsSectionCard';
import { SettingsConfigurationSummary } from './SettingsConfigurationSummary';
import {
  getNotificationChannelLabel,
  getNotificationTestHint,
  SETTINGS_NOTIFICATION_TEXT,
} from '../../locales/settingsNotifications';
import type { UiLanguage } from '../../i18n/uiText';
import { SETTINGS_CONTROL_WIDTH_CLASS } from './settingsControlLayout';
import { mapApiErrorToActionable } from '../../utils/apiReasonMapper';
import { setNotificationChannelTestRecord } from './notificationChannelTestStatus';

function getChannelOptions(language: UiLanguage): Array<{ value: NotificationTestChannel; label: string }> {
  return [
    { value: 'wechat', label: getNotificationChannelLabel('wechat', language) },
    { value: 'dingtalk', label: getNotificationChannelLabel('dingtalk', language) },
    { value: 'feishu', label: getNotificationChannelLabel('feishu', language) },
    { value: 'telegram', label: 'Telegram' },
    { value: 'email', label: getNotificationChannelLabel('email', language) },
    { value: 'pushover', label: 'Pushover' },
    { value: 'ntfy', label: 'ntfy' },
    { value: 'gotify', label: 'Gotify' },
    { value: 'pushplus', label: 'PushPlus' },
    { value: 'serverchan3', label: 'ServerChan3' },
    { value: 'custom', label: getNotificationChannelLabel('custom', language) },
    { value: 'discord', label: 'Discord' },
    { value: 'slack', label: 'Slack' },
    { value: 'astrbot', label: 'AstrBot' },
  ];
}

interface NotificationTestPanelProps {
  items: SystemConfigUpdateItem[];
  maskToken: string;
  disabled?: boolean;
}

function clampTimeout(value: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 20;
  return Math.min(120, Math.max(1, parsed));
}

function buildActionableFailureCopy(
  errorCode: string | null | undefined,
  fallbackMessage: string,
  language: UiLanguage,
): { hint: string; technicalCode?: string; technicalReason?: string } {
  const mapped = mapApiErrorToActionable(createParsedApiError({
    title: fallbackMessage,
    message: fallbackMessage,
    code: errorCode ?? undefined,
    category: errorCode === 'timeout' ? 'upstream_timeout' : 'http_error',
  }));
  const code = mapped.technicalCode ?? errorCode ?? undefined;
  return {
    hint: getNotificationTestHint(code, language),
    technicalCode: code,
    technicalReason: mapped.technicalReason,
  };
}

export const NotificationTestPanel: React.FC<NotificationTestPanelProps> = ({
  items,
  maskToken,
  disabled = false,
}) => {
  const { language, t } = useUiLanguage();
  const hubText = SETTINGS_NOTIFICATION_TEXT[language];
  const [channel, setChannel] = useState<NotificationTestChannel>('wechat');
  const [title, setTitle] = useState(t('settings.notificationTestTitleValue'));
  const [content, setContent] = useState(t('settings.notificationTestContent'));
  const [timeoutSeconds, setTimeoutSeconds] = useState('20');
  const [result, setResult] = useState<TestNotificationChannelResponse | null>(null);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [isTitleEdited, setIsTitleEdited] = useState(false);
  const [isContentEdited, setIsContentEdited] = useState(false);
  const [testModalOpen, setTestModalOpen] = useState(false);

  const normalizedItems = useMemo(
    () => items.map((item) => ({ key: item.key, value: String(item.value ?? '') })),
    [items],
  );

  useEffect(() => {
    if (!isTitleEdited) {
      setTitle(t('settings.notificationTestTitleValue'));
    }
    if (!isContentEdited) {
      setContent(t('settings.notificationTestContent'));
    }
  }, [isTitleEdited, isContentEdited, t]);

  const runTest = async () => {
    setError(null);
    setResult(null);
    setIsTesting(true);
    try {
      const payload = await systemConfigApi.testNotificationChannel({
        channel,
        items: normalizedItems,
        maskToken,
        title: title.trim() || t('settings.notificationTestTitleValue'),
        content: content.trim() || t('settings.notificationTestContent'),
        timeoutSeconds: clampTimeout(timeoutSeconds),
      });
      setResult(payload);
      setNotificationChannelTestRecord({
        channel,
        success: payload.success,
        message: payload.message,
        errorCode: payload.errorCode,
        at: Date.now(),
      });
    } catch (requestError: unknown) {
      const parsed = getParsedApiError(requestError, language);
      setError(parsed);
      setNotificationChannelTestRecord({
        channel,
        success: false,
        message: parsed.message,
        errorCode: parsed.code,
        at: Date.now(),
      });
    } finally {
      setIsTesting(false);
      setTestModalOpen(false);
    }
  };
  const selectedChannelLabel = getChannelOptions(language).find((option) => option.value === channel)?.label ?? channel;

  const failureCopy = result && !result.success
    ? buildActionableFailureCopy(result.errorCode, result.message, language)
    : null;

  return (
    <>
      <SettingsSectionCard
        title={t('settings.notificationTest')}
        description={t('settings.notificationTestDescription')}
        actions={(
          <Button
            type="button"
            variant="secondary"
            size="default"
            onClick={() => setTestModalOpen(true)}
          >
            <Settings className="h-4 w-4" />
            {t('settings.notificationTestConfigure')}
          </Button>
        )}
      >
        <SettingsConfigurationSummary
          entries={[
            {
              id: 'notification-test-channel',
              label: t('settings.notificationTestChannel'),
              value: selectedChannelLabel,
            },
            {
              id: 'notification-test-timeout',
              label: t('settings.notificationTestTimeout'),
              value: `${clampTimeout(timeoutSeconds)} s`,
            },
          ]}
        />
      </SettingsSectionCard>

      {error ? <ApiErrorAlert error={error} /> : null}

      {result ? (
        <div className="space-y-3" data-testid="notification-test-result">
          <InlineAlert
            variant={result.success ? 'success' : 'danger'}
            title={result.success ? t('settings.notificationTestSuccess') : t('settings.notificationTestFailure')}
            message={(
              <span>
                {result.success ? (
                  <>
                    {result.message}
                    {typeof result.latencyMs === 'number' ? ` · ${result.latencyMs} ms` : ''}
                    {result.errorCode ? ` · ${result.errorCode}` : ''}
                    <span className="mt-1 block text-xs leading-5 text-secondary-text">
                      {hubText.testSuccessBindHint}
                    </span>
                  </>
                ) : (
                  <>
                    {failureCopy?.hint ?? hubText.testFailureReviewHint}
                    {typeof result.latencyMs === 'number' ? ` · ${result.latencyMs} ms` : ''}
                    {result.message ? (
                      <span className="mt-1 block text-xs leading-5 text-secondary-text">
                        {result.message}
                      </span>
                    ) : null}
                    {(failureCopy?.technicalCode || result.errorCode) ? (
                      <span className="mt-1 block text-xs leading-5 text-muted-text">
                        {hubText.technicalDetails}: {failureCopy?.technicalCode ?? result.errorCode}
                        {failureCopy?.technicalReason ? ` · ${failureCopy.technicalReason}` : ''}
                      </span>
                    ) : null}
                  </>
                )}
              </span>
            )}
          />

          {result.attempts.length ? (
            <div className="space-y-2">
              {result.attempts.map((attempt, index) => {
                const attemptHint = !attempt.success
                  ? getNotificationTestHint(attempt.errorCode, language)
                  : null;
                return (
                  <div
                    key={`${attempt.channel}-${index}-${attempt.target || 'target'}`}
                    className="rounded-xl border settings-border bg-background/35 px-4 py-3"
                  >
                    <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={attempt.success ? 'success' : 'danger'}>
                            {attempt.success ? t('common.success') : t('common.failure')}
                          </Badge>
                          <span className="text-sm font-medium text-foreground">
                            {t('settings.notificationTestAttempt', { number: index + 1 })}
                          </span>
                          {typeof attempt.httpStatus === 'number' ? (
                            <span className="text-xs text-muted-text">HTTP {attempt.httpStatus}</span>
                          ) : null}
                          {typeof attempt.latencyMs === 'number' ? (
                            <span className="text-xs text-muted-text">{attempt.latencyMs} ms</span>
                          ) : null}
                        </div>
                        <p className="mt-2 break-all text-xs leading-5 text-muted-text">
                          {attempt.target || attempt.channel}
                        </p>
                      </div>
                      {attempt.errorCode ? (
                        <Badge variant={attempt.retryable ? 'warning' : 'default'}>
                          {attempt.errorCode}
                        </Badge>
                      ) : null}
                    </div>
                    <p className="mt-2 text-xs leading-5 text-secondary-text">{attempt.message}</p>
                    {attemptHint ? (
                      <p className="mt-1 text-xs leading-5 text-secondary-text" data-testid="notification-attempt-hint">
                        {attemptHint}
                      </p>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}

      <Modal
        isOpen={testModalOpen}
        onClose={() => setTestModalOpen(false)}
        title={t('settings.notificationTest')}
      >
        <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Select
          label={t('settings.notificationTestChannel')}
          value={channel}
          options={getChannelOptions(language)}
          disabled={disabled || isTesting}
          onChange={(value) => setChannel(value as NotificationTestChannel)}
          className={SETTINGS_CONTROL_WIDTH_CLASS}
        />
        <Input
          label={t('settings.notificationTestTitle')}
          value={title}
          fieldClassName={SETTINGS_CONTROL_WIDTH_CLASS}
          maxLength={80}
          disabled={disabled || isTesting}
          onChange={(event) => {
            setIsTitleEdited(true);
            setTitle(event.target.value);
          }}
        />
        <Input
          label={t('settings.notificationTestTimeout')}
          type="number"
          fieldClassName={SETTINGS_CONTROL_WIDTH_CLASS}
          min={1}
          max={120}
          value={timeoutSeconds}
          disabled={disabled || isTesting}
          onChange={(event) => setTimeoutSeconds(event.target.value)}
          onBlur={() => setTimeoutSeconds(String(clampTimeout(timeoutSeconds)))}
        />
      </div>

        <Textarea
          label={t('settings.notificationTestBody')}
          value={content}
          maxLength={1000}
          rows={4}
          fieldClassName={SETTINGS_CONTROL_WIDTH_CLASS}
          className="leading-6"
          disabled={disabled || isTesting}
          onChange={(event) => {
            setIsContentEdited(true);
            setContent(event.target.value);
          }}
        />

          <Button
            type="button"
            variant="primary"
            onClick={() => void runTest()}
            disabled={disabled || isTesting}
            isLoading={isTesting}
            loadingText={t('settings.notificationTesting')}
            className="justify-center"
          >
            <Send className="h-4 w-4" />
            {t('settings.notificationTestSend')}
          </Button>
        </div>
      </Modal>
    </>
  );
};
