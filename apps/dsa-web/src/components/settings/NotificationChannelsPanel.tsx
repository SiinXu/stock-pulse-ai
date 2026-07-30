// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useMemo, useState } from 'react';
import type React from 'react';
import { Bell } from 'lucide-react';
import type { ConfigValidationIssue, SystemConfigItem } from '../../types/systemConfig';
import { Badge, Modal } from '../common';
import { cn } from '../../utils/cn';
import { SettingsField } from './SettingsField';
import { isConfiguredChannelValue, NOTIFICATION_CHANNELS } from './notificationChannels';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { getNotificationChannelLabel, SETTINGS_NOTIFICATION_TEXT } from '../../locales/settingsNotifications';

interface NotificationChannelsPanelProps {
  items: SystemConfigItem[];
  configuredChannels: readonly string[] | null;
  disabled: boolean;
  onChange: (key: string, value: string) => void;
  issueByKey: Record<string, ConfigValidationIssue[]>;
}

function isChannelConfigured(items: SystemConfigItem[]): boolean {
  return items.some((item) => isConfiguredChannelValue(item.value));
}

export const NotificationChannelsPanel: React.FC<NotificationChannelsPanelProps> = ({
  items,
  configuredChannels,
  disabled,
  onChange,
  issueByKey,
}) => {
  const { language } = useUiLanguage();
  const text = SETTINGS_NOTIFICATION_TEXT[language];
  const [openChannelId, setOpenChannelId] = useState<string | null>(null);
  const configuredChannelValues = useMemo(
    () => configuredChannels === null ? null : new Set(configuredChannels),
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

  return (
    <>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {NOTIFICATION_CHANNELS.map((channel) => {
          const channelItems = itemsByChannel.get(channel.id) ?? [];
          if (channelItems.length === 0) {
            return null;
          }
          const configured = configuredChannelValues === null
            ? isChannelConfigured(channelItems)
            : configuredChannelValues.has(channel.routingValue ?? channel.id);
          return (
            <button
              key={channel.id}
              type="button"
              aria-haspopup="dialog"
              onClick={() => setOpenChannelId(channel.id)}
              className={cn(
                'flex items-center justify-between gap-2 rounded-lg border settings-border bg-background/35 px-3 py-3 text-left transition-colors hover:bg-[var(--settings-surface-hover)]',
              )}
            >
              <span className="flex min-w-0 items-center gap-2">
                <Bell className="h-4 w-4 shrink-0 text-muted-text" aria-hidden="true" />
                <span className="truncate text-sm font-medium text-foreground">{getNotificationChannelLabel(channel.id, language)}</span>
              </span>
              <Badge variant={configured ? 'success' : 'default'} size="sm" className="shrink-0">
                {configured ? text.configured : text.unconfigured}
              </Badge>
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
          <form className="divide-y divide-transparent" onSubmit={(event) => event.preventDefault()}>
            {openChannel.id === 'dingtalk' ? (
              <div className="space-y-6">
                {dingtalkGroupItems.length ? (
                  <section aria-labelledby="dingtalk-group-webhook-heading">
                    <h3 id="dingtalk-group-webhook-heading" className="text-sm font-semibold text-foreground">
                      {text.dingtalkGroupWebhook}
                    </h3>
                    <p className="mt-1 text-xs leading-5 text-secondary-text">
                      {text.dingtalkGroupWebhookDescription}
                    </p>
                    <div className="mt-2 divide-y divide-transparent">
                      {renderFields(dingtalkGroupItems)}
                    </div>
                  </section>
                ) : null}
                {dingtalkAppItems.length ? (
                  <section aria-labelledby="dingtalk-app-bot-heading">
                    <h3 id="dingtalk-app-bot-heading" className="text-sm font-semibold text-foreground">
                      {text.dingtalkAppBot}
                    </h3>
                    <p className="mt-1 text-xs leading-5 text-secondary-text">
                      {text.dingtalkAppBotDescription}
                    </p>
                    <div className="mt-2 divide-y divide-transparent">
                      {renderFields(dingtalkAppItems)}
                    </div>
                  </section>
                ) : null}
              </div>
            ) : renderFields(openChannelItems)}
          </form>
        </Modal>
      ) : null}
    </>
  );
};
