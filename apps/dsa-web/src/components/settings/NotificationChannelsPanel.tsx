// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useMemo, useState } from 'react';
import type React from 'react';
import { Bell } from 'lucide-react';
import type { ConfigValidationIssue, SystemConfigItem } from '../../types/systemConfig';
import { Badge, Modal, Pressable } from '../common';
import { cn } from '../../utils/cn';
import { SettingsField } from './SettingsField';
import { isConfiguredChannelValue, NOTIFICATION_CHANNELS } from './notificationChannels';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { getNotificationChannelLabel, SETTINGS_NOTIFICATION_TEXT } from '../../locales/settingsNotifications';

interface NotificationChannelsPanelProps {
  items: SystemConfigItem[];
  disabled: boolean;
  onChange: (key: string, value: string) => void;
  issueByKey: Record<string, ConfigValidationIssue[]>;
}

function isChannelConfigured(items: SystemConfigItem[]): boolean {
  return items.some((item) => isConfiguredChannelValue(item.value));
}

export const NotificationChannelsPanel: React.FC<NotificationChannelsPanelProps> = ({
  items,
  disabled,
  onChange,
  issueByKey,
}) => {
  const { language } = useUiLanguage();
  const text = SETTINGS_NOTIFICATION_TEXT[language];
  const [openChannelId, setOpenChannelId] = useState<string | null>(null);

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

  return (
    <>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {NOTIFICATION_CHANNELS.map((channel) => {
          const channelItems = itemsByChannel.get(channel.id) ?? [];
          if (channelItems.length === 0) {
            return null;
          }
          const configured = isChannelConfigured(channelItems);
          return (
            <Pressable
              key={channel.id}
              type="button"
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
            </Pressable>
          );
        })}
      </div>

      <Modal
        isOpen={Boolean(openChannel)}
        onClose={() => setOpenChannelId(null)}
        title={openChannel ? getNotificationChannelLabel(openChannel.id, language) : undefined}
        className="max-w-2xl"
      >
        <form className="divide-y divide-transparent" onSubmit={(event) => event.preventDefault()}>
          {openChannelItems.map((item) => (
            <SettingsField
              key={item.key}
              item={item}
              value={item.value}
              disabled={disabled}
              onChange={onChange}
              issues={issueByKey[item.key] || []}
            />
          ))}
        </form>
      </Modal>
    </>
  );
};
