// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import type React from 'react';
import { Bell, Send } from 'lucide-react';
import type { ConfigValidationIssue, NotificationTestChannel, SystemConfigItem } from '../../types/systemConfig';
import { Badge, Button, InlineAlert, Modal } from '../common';
import { cn } from '../../utils/cn';
import { SettingsField } from './SettingsField';
import { isConfiguredChannelValue, NOTIFICATION_CHANNELS } from './notificationChannels';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import {
  getNotificationChannelLabel,
  getNotificationTestHint,
  SETTINGS_NOTIFICATION_TEXT,
} from '../../locales/settingsNotifications';
import {
  eventsForRoutingChannel,
  type NotificationEventKind,
  type NotificationEventRoutes,
} from './notificationEventRoutes';
import {
  getNotificationChannelTestRecord,
  getNotificationChannelTestStatusVersion,
  setNotificationChannelTestRecord,
  subscribeNotificationChannelTestStatus,
} from './notificationChannelTestStatus';
import { systemConfigApi } from '../../api/systemConfig';
import { createParsedApiError, getParsedApiError } from '../../api/error';
import { mapApiErrorToActionable } from '../../utils/apiReasonMapper';

interface NotificationChannelsPanelProps {
  items: SystemConfigItem[];
  configuredChannels: readonly string[] | null;
  disabled: boolean;
  onChange: (key: string, value: string) => void;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  eventRoutes?: NotificationEventRoutes | null;
  maskToken?: string;
}

function isChannelConfigured(items: SystemConfigItem[]): boolean {
  return items.some((item) => isConfiguredChannelValue(item.value));
}

function channelRoutingValue(channelId: string, routingValue?: string): string {
  return routingValue ?? channelId;
}

function toTestChannel(channelId: string, routingValue?: string): NotificationTestChannel | null {
  const value = channelRoutingValue(channelId, routingValue);
  const allowed: NotificationTestChannel[] = [
    'wechat', 'dingtalk', 'feishu', 'telegram', 'email', 'pushover', 'ntfy',
    'gotify', 'pushplus', 'serverchan3', 'custom', 'discord', 'slack', 'astrbot',
  ];
  return (allowed as string[]).includes(value) ? (value as NotificationTestChannel) : null;
}

function eventLabel(
  kind: NotificationEventKind,
  text: (typeof SETTINGS_NOTIFICATION_TEXT)[keyof typeof SETTINGS_NOTIFICATION_TEXT],
): string {
  if (kind === 'report') return text.eventReport;
  if (kind === 'alert') return text.eventAlert;
  return text.eventSystemError;
}

function useChannelTestStatusVersion(): number {
  return useSyncExternalStore(
    subscribeNotificationChannelTestStatus,
    getNotificationChannelTestStatusVersion,
    getNotificationChannelTestStatusVersion,
  );
}

export const NotificationChannelsPanel: React.FC<NotificationChannelsPanelProps> = ({
  items,
  configuredChannels,
  disabled,
  onChange,
  issueByKey,
  eventRoutes = null,
  maskToken,
}) => {
  const { language, t } = useUiLanguage();
  const text = SETTINGS_NOTIFICATION_TEXT[language];
  const testStatusVersion = useChannelTestStatusVersion();
  const [openChannelId, setOpenChannelId] = useState<string | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [modalFeedback, setModalFeedback] = useState<{
    success: boolean;
    title: string;
    message: string;
    technical?: string;
  } | null>(null);

  const configuredChannelValues = useMemo(
    () => (configuredChannels === null ? null : new Set(configuredChannels)),
    [configuredChannels],
  );

  const itemsByChannel = useMemo(() => {
    const map = new Map<string, SystemConfigItem[]>();
    for (const channel of NOTIFICATION_CHANNELS) {
      map.set(
        channel.id,
        items.filter((item) => channel.prefixes.some((prefix) => item.key.startsWith(prefix))),
      );
    }
    return map;
  }, [items]);

  const openChannel = NOTIFICATION_CHANNELS.find((channel) => channel.id === openChannelId) ?? null;
  const openChannelItems = openChannelId ? itemsByChannel.get(openChannelId) ?? [] : [];
  const dingtalkGroupKeys = new Set(['DINGTALK_WEBHOOK_URL', 'DINGTALK_SECRET']);
  const dingtalkGroupItems = openChannel?.id === 'dingtalk'
    ? openChannelItems.filter((item) => dingtalkGroupKeys.has(item.key))
    : [];
  const dingtalkAppItems = openChannel?.id === 'dingtalk'
    ? openChannelItems.filter((item) => !dingtalkGroupKeys.has(item.key))
    : [];

  useEffect(() => {
    setModalFeedback(null);
    setIsTesting(false);
  }, [openChannelId]);

  const renderFields = (fieldItems: SystemConfigItem[]) => fieldItems.map((item) => (
    <SettingsField
      key={item.key}
      item={item}
      value={item.value}
      disabled={disabled}
      onChange={onChange}
      issues={issueByKey[item.key] || []}
    />
  ));

  const formatRouteTargets = (channels: readonly string[]): string => {
    if (!channels.length) return text.eventAllConfigured;
    return channels
      .map((value) => {
        const match = NOTIFICATION_CHANNELS.find(
          (channel) => channelRoutingValue(channel.id, channel.routingValue) === value,
        );
        return match ? getNotificationChannelLabel(match.id, language) : value;
      })
      .join(', ');
  };

  const runChannelTest = async () => {
    if (!openChannel || !maskToken) return;
    const testChannel = toTestChannel(openChannel.id, openChannel.routingValue);
    if (!testChannel) return;
    setIsTesting(true);
    setModalFeedback(null);
    try {
      const payload = await systemConfigApi.testNotificationChannel({
        channel: testChannel,
        items: openChannelItems.map((item) => ({ key: item.key, value: String(item.value ?? '') })),
        maskToken,
        title: t('settings.notificationTestTitleValue'),
        content: t('settings.notificationTestContent'),
        timeoutSeconds: 20,
      });
      setNotificationChannelTestRecord({
        channel: testChannel,
        success: payload.success,
        message: payload.message,
        errorCode: payload.errorCode,
        at: Date.now(),
      });
      if (payload.success) {
        setModalFeedback({
          success: true,
          title: t('settings.notificationTestSuccess'),
          message: `${payload.message} ${text.testSuccessBindHint}`,
        });
      } else {
        const mapped = mapApiErrorToActionable(createParsedApiError({
          title: payload.message,
          message: payload.message,
          code: payload.errorCode ?? 'notification_channel_test_failed',
        }));
        setModalFeedback({
          success: false,
          title: t('settings.notificationTestFailure'),
          message: getNotificationTestHint(mapped.technicalCode ?? payload.errorCode, language),
          technical: [payload.errorCode, mapped.technicalReason].filter(Boolean).join(' · ') || undefined,
        });
      }
    } catch (requestError: unknown) {
      const parsed = getParsedApiError(requestError, language);
      const mapped = mapApiErrorToActionable(parsed);
      setNotificationChannelTestRecord({
        channel: testChannel,
        success: false,
        message: parsed.message,
        errorCode: parsed.code ?? mapped.technicalCode,
        at: Date.now(),
      });
      setModalFeedback({
        success: false,
        title: t('settings.notificationTestFailure'),
        message: getNotificationTestHint(mapped.technicalCode ?? parsed.code, language),
        technical: [parsed.code, mapped.technicalReason].filter(Boolean).join(' · ') || undefined,
      });
    } finally {
      setIsTesting(false);
    }
  };

  const openRoutingValue = openChannel ? channelRoutingValue(openChannel.id, openChannel.routingValue) : '';
  const openTestChannel = openChannel ? toTestChannel(openChannel.id, openChannel.routingValue) : null;
  void testStatusVersion;
  const openTestRecord = openTestChannel ? getNotificationChannelTestRecord(openTestChannel) : undefined;

  return (
    <div className="space-y-4" data-testid="notification-channels-hub">
      {eventRoutes ? (
        <section
          aria-labelledby="notification-event-routing-heading"
          className="rounded-lg border settings-border bg-background/25 px-3 py-3"
          data-testid="notification-event-routing"
        >
          <h3 id="notification-event-routing-heading" className="text-sm font-semibold text-foreground">
            {text.eventRoutingTitle}
          </h3>
          <p className="mt-1 text-xs leading-5 text-secondary-text">{text.eventRoutingDescription}</p>
          <dl className="mt-3 space-y-2">
            {([
              ['report', eventRoutes.report],
              ['alert', eventRoutes.alert],
              ['system_error', eventRoutes.system_error],
            ] as const).map(([kind, channels]) => (
              <div
                key={kind}
                className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:justify-between sm:gap-3"
                data-testid={`notification-event-route-${kind}`}
              >
                <dt className="shrink-0 text-xs font-medium text-secondary-text">{eventLabel(kind, text)}</dt>
                <dd className="min-w-0 text-xs leading-5 text-foreground sm:text-right">{formatRouteTargets(channels)}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {NOTIFICATION_CHANNELS.map((channel) => {
          const channelItems = itemsByChannel.get(channel.id) ?? [];
          if (channelItems.length === 0) return null;
          const routingValue = channelRoutingValue(channel.id, channel.routingValue);
          const configured = configuredChannelValues === null
            ? isChannelConfigured(channelItems)
            : configuredChannelValues.has(routingValue);
          const testChannel = toTestChannel(channel.id, channel.routingValue);
          const lastTest = testChannel ? getNotificationChannelTestRecord(testChannel) : undefined;
          const boundEvents = eventsForRoutingChannel(eventRoutes, routingValue);
          const statusLabel = !configured
            ? text.bindUnconfigured
            : lastTest?.success
              ? text.bindVerified
              : text.bindNeedsTest;
          const statusVariant = !configured
            ? 'default'
            : lastTest?.success
              ? 'success'
              : lastTest && !lastTest.success
                ? 'danger'
                : 'warning';
          const testBadge = lastTest
            ? (lastTest.success ? text.lastTestOk : text.lastTestFailed)
            : text.lastTestNever;
          return (
            <button
              key={channel.id}
              type="button"
              aria-haspopup="dialog"
              data-testid={`notification-channel-card-${channel.id}`}
              onClick={() => setOpenChannelId(channel.id)}
              className={cn(
                'flex flex-col gap-2 rounded-lg border settings-border bg-background/35 px-3 py-3 text-left transition-colors hover:bg-[var(--settings-surface-hover)]',
              )}
            >
              <span className="flex min-w-0 items-center justify-between gap-2">
                <span className="flex min-w-0 items-center gap-2">
                  <Bell className="h-4 w-4 shrink-0 text-muted-text" aria-hidden="true" />
                  <span className="truncate text-sm font-medium text-foreground">
                    {getNotificationChannelLabel(channel.id, language)}
                  </span>
                </span>
                <Badge variant={statusVariant} size="sm" className="shrink-0">{statusLabel}</Badge>
              </span>
              <span className="flex flex-wrap items-center gap-1.5">
                <Badge variant={configured ? 'success' : 'default'} size="sm">
                  {configured ? text.configured : text.unconfigured}
                </Badge>
                <Badge variant={lastTest ? (lastTest.success ? 'success' : 'danger') : 'default'} size="sm">
                  {testBadge}
                </Badge>
              </span>
              {eventRoutes ? (
                <span className="text-xs leading-5 text-muted-text">
                  <span className="font-medium text-secondary-text">{text.cardEventsLabel}: </span>
                  {boundEvents.length
                    ? boundEvents.map((kind) => eventLabel(kind, text)).join(' · ')
                    : text.eventNone}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      {openChannel ? (
        <Modal
          isOpen
          onClose={() => setOpenChannelId(null)}
          title={getNotificationChannelLabel(openChannel.id, language)}
          size="wide"
        >
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge
                variant={
                  configuredChannelValues === null
                    ? (isChannelConfigured(openChannelItems) ? 'success' : 'default')
                    : (configuredChannelValues.has(openRoutingValue) ? 'success' : 'default')
                }
                size="sm"
              >
                {configuredChannelValues === null
                  ? (isChannelConfigured(openChannelItems) ? text.configured : text.unconfigured)
                  : (configuredChannelValues.has(openRoutingValue) ? text.configured : text.unconfigured)}
              </Badge>
              {openTestRecord ? (
                <Badge variant={openTestRecord.success ? 'success' : 'danger'} size="sm">
                  {openTestRecord.success ? text.lastTestOk : text.lastTestFailed}
                </Badge>
              ) : (
                <Badge variant="default" size="sm">{text.lastTestNever}</Badge>
              )}
              {eventRoutes ? (
                <span className="text-xs text-muted-text">
                  {text.cardEventsLabel}:{' '}
                  {(() => {
                    const kinds = eventsForRoutingChannel(eventRoutes, openRoutingValue);
                    return kinds.length
                      ? kinds.map((kind) => eventLabel(kind, text)).join(' · ')
                      : text.eventNone;
                  })()}
                </span>
              ) : null}
            </div>

            <form className="divide-y divide-transparent" onSubmit={(event) => event.preventDefault()}>
              {openChannel.id === 'dingtalk' ? (
                <div className="space-y-6">
                  {dingtalkGroupItems.length ? (
                    <section aria-labelledby="dingtalk-group-webhook-heading">
                      <h3 id="dingtalk-group-webhook-heading" className="text-sm font-semibold text-foreground">
                        {text.dingtalkGroupWebhook}
                      </h3>
                      <p className="mt-1 text-xs leading-5 text-secondary-text">{text.dingtalkGroupWebhookDescription}</p>
                      <div className="mt-2 divide-y divide-transparent">{renderFields(dingtalkGroupItems)}</div>
                    </section>
                  ) : null}
                  {dingtalkAppItems.length ? (
                    <section aria-labelledby="dingtalk-app-bot-heading">
                      <h3 id="dingtalk-app-bot-heading" className="text-sm font-semibold text-foreground">
                        {text.dingtalkAppBot}
                      </h3>
                      <p className="mt-1 text-xs leading-5 text-secondary-text">{text.dingtalkAppBotDescription}</p>
                      <div className="mt-2 divide-y divide-transparent">{renderFields(dingtalkAppItems)}</div>
                    </section>
                  ) : null}
                </div>
              ) : renderFields(openChannelItems)}
            </form>

            {maskToken && openTestChannel ? (
              <div className="space-y-3 border-t border-[var(--settings-border-soft)] pt-4">
                <Button
                  type="button"
                  variant="primary"
                  onClick={() => void runChannelTest()}
                  disabled={disabled || isTesting}
                  isLoading={isTesting}
                  loadingText={text.testingChannel}
                  className="justify-center"
                  data-testid="notification-channel-send-test"
                >
                  <Send className="h-4 w-4" />
                  {text.sendChannelTest}
                </Button>
                {modalFeedback ? (
                  <InlineAlert
                    variant={modalFeedback.success ? 'success' : 'danger'}
                    title={modalFeedback.title}
                    message={(
                      <span>
                        {modalFeedback.message}
                        {modalFeedback.technical ? (
                          <span className="mt-1 block text-xs text-muted-text">
                            {text.technicalDetails}: {modalFeedback.technical}
                          </span>
                        ) : null}
                      </span>
                    )}
                  />
                ) : null}
              </div>
            ) : null}
          </div>
        </Modal>
      ) : null}
    </div>
  );
};
