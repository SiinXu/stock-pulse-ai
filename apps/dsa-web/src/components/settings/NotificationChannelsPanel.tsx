// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import type React from 'react';
import { Bell, Send } from 'lucide-react';
import type {
  ConfigValidationIssue,
  NotificationTestAttempt,
  NotificationTestChannel,
  SystemConfigItem,
} from '../../types/systemConfig';
import { Badge, Button, Checkbox, InlineAlert, Modal } from '../common';
import { cn } from '../../utils/cn';
import { SettingsField } from './SettingsField';
import {
  getNotificationChannelByRoutingValue,
  getNotificationRoutingValue,
  isConfiguredChannelValue,
  NOTIFICATION_CHANNELS,
} from './notificationChannels';
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
  classifyNotificationTestOutcome,
  clearNotificationChannelTestRecord,
  clearNotificationChannelTestRecords,
  computeNotificationConfigurationFingerprint,
  getNotificationChannelTestRecord,
  getNotificationChannelTestStatusVersion,
  setNotificationChannelTestRecord,
  subscribeNotificationChannelTestStatus,
  type NotificationChannelTestOutcome,
} from './notificationChannelTestStatus';
import { systemConfigApi } from '../../api/systemConfig';
import { createParsedApiError, getParsedApiError } from '../../api/error';
import { mapApiErrorToActionable } from '../../utils/apiReasonMapper';
import type { SettingsSaveStatus } from './autosaveMachine';

interface NotificationChannelsPanelProps {
  items: SystemConfigItem[];
  configuredChannels: readonly string[] | null;
  disabled: boolean;
  onChange: (key: string, value: string) => void;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  eventRoutes?: NotificationEventRoutes | null;
  draftEventRoutes?: NotificationEventRoutes | null;
  hasPendingRoutes?: boolean;
  saveStatus?: SettingsSaveStatus;
  persistedValuesByKey?: Readonly<Record<string, string>>;
  configVersion?: string;
  onBindEvents?: (routingValue: string, kinds: readonly NotificationEventKind[]) => void;
  maskToken?: string;
}

function isChannelConfigured(items: SystemConfigItem[]): boolean {
  return items.some((item) => isConfiguredChannelValue(item.value));
}

function toTestChannel(channelId: string, routingValue?: string): NotificationTestChannel | null {
  const channel = NOTIFICATION_CHANNELS.find((candidate) => candidate.id === channelId);
  const value = channel ? getNotificationRoutingValue(channel) : routingValue ?? channelId;
  return getNotificationChannelByRoutingValue(value)
    ? (value as NotificationTestChannel)
    : null;
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
  draftEventRoutes = null,
  hasPendingRoutes = false,
  saveStatus = 'idle',
  persistedValuesByKey = {},
  configVersion = '',
  onBindEvents,
  maskToken,
}) => {
  const { language, t } = useUiLanguage();
  const text = SETTINGS_NOTIFICATION_TEXT[language];
  const testStatusVersion = useChannelTestStatusVersion();
  const [statusNow, setStatusNow] = useState(() => Date.now());
  const [openChannelId, setOpenChannelId] = useState<string | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [configurationFingerprints, setConfigurationFingerprints] = useState<ReadonlyMap<string, string>>(new Map());
  const [selectedBindEvents, setSelectedBindEvents] = useState<NotificationEventKind[]>([]);
  const [bindFeedback, setBindFeedback] = useState<string | null>(null);
  const [modalFeedback, setModalFeedback] = useState<{
    outcome: NotificationChannelTestOutcome;
    title: string;
    message: string;
    technical?: string;
    attempts?: NotificationTestAttempt[];
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
    setSelectedBindEvents([]);
    setBindFeedback(null);
  }, [openChannelId]);

  useEffect(() => {
    let current = true;
    void Promise.all(
      NOTIFICATION_CHANNELS.map(async (channel) => {
        const testChannel = toTestChannel(channel.id, channel.routingValue);
        if (!testChannel) return null;
        const channelItems = itemsByChannel.get(channel.id) ?? [];
        const fingerprint = await computeNotificationConfigurationFingerprint(
          testChannel,
          configVersion,
          channelItems.map((item) => ({ key: item.key, value: String(item.value ?? '') })),
        );
        return [testChannel, fingerprint] as const;
      }),
    ).then((entries) => {
      if (!current) return;
      setConfigurationFingerprints(new Map(entries.filter((entry) => entry !== null)));
    }).catch(() => {
      if (current) setConfigurationFingerprints(new Map());
    });
    return () => { current = false; };
  }, [configVersion, itemsByChannel]);

  useEffect(() => {
    if (saveStatus === 'failed' || saveStatus === 'conflicted') {
      clearNotificationChannelTestRecords();
    }
  }, [saveStatus]);

  useEffect(() => {
    const timer = globalThis.setInterval(() => setStatusNow(Date.now()), 30_000);
    return () => globalThis.clearInterval(timer);
  }, []);

  const renderFields = (fieldItems: SystemConfigItem[]) => fieldItems.map((item) => (
    <SettingsField
      key={item.key}
      item={item}
      value={item.value}
      disabled={disabled}
      onChange={(key, value) => {
        if (openChannel) {
          const testChannel = toTestChannel(openChannel.id, openChannel.routingValue);
          if (testChannel) clearNotificationChannelTestRecord(testChannel);
        }
        onChange(key, value);
      }}
      issues={issueByKey[item.key] || []}
    />
  ));

  const formatRouteTargets = (route: NotificationEventRoutes[NotificationEventKind]): string => {
    if (route.effective === null) return text.routeAuthorityUnknown;
    if (route.usesDefaultFanout) return text.eventAllConfigured;
    if (!route.effective.length) return text.eventNone;
    return route.effective
      .map((value) => {
        const match = getNotificationChannelByRoutingValue(value);
        return match ? getNotificationChannelLabel(match.id, language) : value;
      })
      .join(', ');
  };

  const runChannelTest = async () => {
    if (!openChannel || !maskToken) return;
    const testChannel = toTestChannel(openChannel.id, openChannel.routingValue);
    if (!testChannel) return;
    const testItems = openChannelItems.map((item) => ({ key: item.key, value: String(item.value ?? '') }));
    setIsTesting(true);
    setModalFeedback(null);
    let configFingerprint: string | null = null;
    try {
      configFingerprint = await computeNotificationConfigurationFingerprint(
        testChannel,
        configVersion,
        testItems,
      );
      const payload = await systemConfigApi.testNotificationChannel({
        channel: testChannel,
        items: testItems,
        maskToken,
        title: t('settings.notificationTestTitleValue'),
        content: t('settings.notificationTestContent'),
        timeoutSeconds: 20,
      });
      const outcome = classifyNotificationTestOutcome(payload);
      setNotificationChannelTestRecord({
        channel: testChannel,
        outcome,
        message: payload.message,
        errorCode: payload.errorCode,
        attempts: payload.attempts,
        configVersion,
        configFingerprint,
        at: Date.now(),
      });
      if (outcome === 'verified') {
        setModalFeedback({
          outcome,
          title: t('settings.notificationTestSuccess'),
          message: `${payload.message} ${text.testSuccessBindHint}`,
          attempts: payload.attempts,
        });
      } else {
        const mapped = mapApiErrorToActionable(createParsedApiError({
          title: payload.message,
          message: payload.message,
          code: payload.errorCode ?? 'notification_channel_test_failed',
        }));
        setModalFeedback({
          outcome,
          title: outcome === 'degraded' ? text.lastTestPartial : t('settings.notificationTestFailure'),
          message: outcome === 'degraded'
            ? text.testPartialHint
            : getNotificationTestHint(mapped.technicalCode ?? payload.errorCode, language),
          technical: [payload.errorCode, mapped.technicalReason].filter(Boolean).join(' · ') || undefined,
          attempts: payload.attempts,
        });
      }
    } catch (requestError: unknown) {
      const parsed = getParsedApiError(requestError, language);
      const mapped = mapApiErrorToActionable(parsed);
      if (configFingerprint) {
        setNotificationChannelTestRecord({
          channel: testChannel,
          outcome: 'failed',
          message: parsed.message,
          errorCode: parsed.code ?? mapped.technicalCode,
          attempts: [],
          configVersion,
          configFingerprint,
          at: Date.now(),
        });
      }
      setModalFeedback({
        outcome: 'failed',
        title: t('settings.notificationTestFailure'),
        message: getNotificationTestHint(mapped.technicalCode ?? parsed.code, language),
        technical: [parsed.code, mapped.technicalReason].filter(Boolean).join(' · ') || undefined,
      });
    } finally {
      setIsTesting(false);
    }
  };

  const openRoutingValue = openChannel ? getNotificationRoutingValue(openChannel) : '';
  const openTestChannel = openChannel ? toTestChannel(openChannel.id, openChannel.routingValue) : null;
  void testStatusVersion;
  const openFingerprint = openTestChannel ? configurationFingerprints.get(openTestChannel) : undefined;
  const openTestRecord = openTestChannel && openFingerprint
    ? getNotificationChannelTestRecord(openTestChannel, {
      configVersion,
      configFingerprint: openFingerprint,
    }, statusNow)
    : undefined;
  const openChannelHasPendingConfig = openChannelItems.some(
    (item) => String(item.value ?? '') !== String(persistedValuesByKey[item.key] ?? ''),
  );
  const openChannelIsConfigured = configuredChannelValues?.has(openRoutingValue) ?? false;
  const openBoundEvents = eventsForRoutingChannel(eventRoutes, openRoutingValue);
  const openDraftBoundEvents = eventsForRoutingChannel(draftEventRoutes, openRoutingValue);
  const openUnboundEvents = (['report', 'alert', 'system_error'] as const)
    .filter((kind) => !openBoundEvents.includes(kind));

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
            ] as const).map(([kind, route]) => (
              <div
                key={kind}
                className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:justify-between sm:gap-3"
                data-testid={`notification-event-route-${kind}`}
              >
                <dt className="shrink-0 text-xs font-medium text-secondary-text">{eventLabel(kind, text)}</dt>
                <dd className="min-w-0 text-xs leading-5 text-foreground sm:text-right">
                  <span>{formatRouteTargets(route)}</span>
                  {route.invalid.length ? (
                    <span className="block text-danger">
                      {text.routeInvalid}: {route.invalid.join(', ')}
                    </span>
                  ) : null}
                  {route.unconfigured.length ? (
                    <span className="block text-warning">
                      {text.routeUnconfigured}: {route.unconfigured.join(', ')}
                    </span>
                  ) : null}
                </dd>
              </div>
            ))}
          </dl>
          {hasPendingRoutes ? (
            <InlineAlert
              variant={saveStatus === 'failed' || saveStatus === 'conflicted' ? 'danger' : 'warning'}
              title={text.routePendingDraft}
              message={saveStatus === 'failed' || saveStatus === 'conflicted'
                ? text.routePendingFailed
                : text.routePendingDescription}
            />
          ) : null}
        </section>
      ) : null}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {NOTIFICATION_CHANNELS.map((channel) => {
          const channelItems = itemsByChannel.get(channel.id) ?? [];
          if (channelItems.length === 0) return null;
          const routingValue = getNotificationRoutingValue(channel);
          const configured = configuredChannelValues === null
            ? isChannelConfigured(channelItems)
            : configuredChannelValues.has(routingValue);
          const hasPendingConfiguration = channelItems.some(
            (item) => String(item.value ?? '') !== String(persistedValuesByKey[item.key] ?? ''),
          );
          const testChannel = toTestChannel(channel.id, channel.routingValue);
          const fingerprint = testChannel ? configurationFingerprints.get(testChannel) : undefined;
          const lastTest = testChannel && fingerprint
            ? getNotificationChannelTestRecord(testChannel, {
              configVersion,
              configFingerprint: fingerprint,
            }, statusNow)
            : undefined;
          const boundEvents = eventsForRoutingChannel(eventRoutes, routingValue);
          const statusLabel = !configured
            ? text.bindUnconfigured
            : hasPendingConfiguration && lastTest
              ? text.testDraftOnly
            : lastTest?.outcome === 'verified'
              ? text.bindVerified
              : lastTest?.outcome === 'degraded'
                ? text.bindDegraded
              : text.bindNeedsTest;
          const statusVariant = !configured
            ? 'default'
            : hasPendingConfiguration && lastTest
              ? 'warning'
            : lastTest?.outcome === 'verified'
              ? 'success'
              : lastTest?.outcome === 'failed'
                ? 'danger'
                : 'warning';
          const testBadge = lastTest
            ? (lastTest.outcome === 'verified'
              ? text.lastTestOk
              : lastTest.outcome === 'degraded'
                ? text.lastTestPartial
                : text.lastTestFailed)
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
                <Badge
                  variant={lastTest
                    ? (lastTest.outcome === 'verified'
                      ? 'success'
                      : lastTest.outcome === 'degraded' ? 'warning' : 'danger')
                    : 'default'}
                  size="sm"
                >
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
                <Badge
                  variant={openTestRecord.outcome === 'verified'
                    ? 'success'
                    : openTestRecord.outcome === 'degraded' ? 'warning' : 'danger'}
                  size="sm"
                >
                  {openTestRecord.outcome === 'verified'
                    ? text.lastTestOk
                    : openTestRecord.outcome === 'degraded'
                      ? text.lastTestPartial
                      : text.lastTestFailed}
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

            {openTestRecord ? (
              <p className="text-xs leading-5 text-muted-text" data-testid="notification-test-evidence-scope">
                {text.lastTestAt}:{' '}
                {new Intl.DateTimeFormat(language === 'zh' ? 'zh-CN' : language, {
                  dateStyle: 'short',
                  timeStyle: 'medium',
                }).format(new Date(openTestRecord.at))}
                {' · '}{text.testEvidenceSession}
                {openTestRecord.message ? ` · ${openTestRecord.message}` : ''}
              </p>
            ) : null}

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
                    variant={modalFeedback.outcome === 'verified'
                      ? 'success'
                      : modalFeedback.outcome === 'degraded' ? 'warning' : 'danger'}
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
                {modalFeedback?.attempts?.length ? (
                  <div className="space-y-2" data-testid="notification-channel-test-attempts">
                    {modalFeedback.attempts.map((attempt, index) => (
                      <div
                        key={`${attempt.channel}-${attempt.target ?? index}`}
                        className="rounded-md border settings-border bg-background/35 px-3 py-2 text-xs"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={attempt.success ? 'success' : 'danger'} size="sm">
                            {attempt.success ? t('common.success') : t('common.failure')}
                          </Badge>
                          <span className="break-all text-secondary-text">
                            {attempt.target || attempt.channel}
                          </span>
                        </div>
                        {!attempt.success ? (
                          <p className="mt-1 text-muted-text">
                            {getNotificationTestHint(attempt.errorCode, language)}
                          </p>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

            {openTestRecord?.outcome === 'verified'
              && openChannelIsConfigured
              && eventRoutes
              && onBindEvents ? (
              <section
                className="space-y-3 border-t border-[var(--settings-border-soft)] pt-4"
                aria-labelledby="notification-bind-events-heading"
              >
                <div>
                  <h3 id="notification-bind-events-heading" className="text-sm font-semibold text-foreground">
                    {text.bindEventsTitle}
                  </h3>
                  <p className="mt-1 text-xs leading-5 text-secondary-text">
                    {text.bindEventsDescription}
                  </p>
                </div>
                {openChannelHasPendingConfig ? (
                  <InlineAlert
                    variant="warning"
                    title={text.testDraftOnly}
                    message={text.testDraftOnlyDescription}
                  />
                ) : openUnboundEvents.length ? (
                  <>
                    <div className="grid gap-2 sm:grid-cols-3">
                      {openUnboundEvents.map((kind) => (
                        <Checkbox
                          key={kind}
                          checked={selectedBindEvents.includes(kind)}
                          disabled={disabled || hasPendingRoutes}
                          label={eventLabel(kind, text)}
                          onChange={(event) => {
                            setSelectedBindEvents((current) => event.target.checked
                              ? [...current, kind]
                              : current.filter((value) => value !== kind));
                          }}
                        />
                      ))}
                    </div>
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={disabled || hasPendingRoutes || selectedBindEvents.length === 0}
                      onClick={() => {
                        onBindEvents(openRoutingValue, selectedBindEvents);
                        setBindFeedback(text.bindingPending);
                        setSelectedBindEvents([]);
                      }}
                      data-testid="notification-channel-bind-events"
                    >
                      {text.bindSelectedEvents}
                    </Button>
                  </>
                ) : (
                  <p className="text-xs text-success">{text.noEligibleEvents}</p>
                )}
                {hasPendingRoutes || bindFeedback ? (
                  <InlineAlert
                    variant={saveStatus === 'failed' || saveStatus === 'conflicted' ? 'danger' : 'warning'}
                    title={text.routePendingDraft}
                    message={saveStatus === 'failed' || saveStatus === 'conflicted'
                      ? text.routePendingFailed
                      : `${bindFeedback ?? text.bindingPending} ${openDraftBoundEvents.length
                        ? openDraftBoundEvents.map((kind) => eventLabel(kind, text)).join(' · ')
                        : ''}`}
                  />
                ) : null}
              </section>
            ) : null}
          </div>
        </Modal>
      ) : null}
    </div>
  );
};
