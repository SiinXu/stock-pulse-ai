export interface NotificationChannel {
  id: string;
  prefixes: string[];
  /** Value used by NOTIFICATION_*_CHANNELS routing fields when it differs from the config id. */
  routingValue?: string;
}

export const NOTIFICATION_CHANNELS: NotificationChannel[] = [
  { id: 'wechat', prefixes: ['WECHAT_'] },
  { id: 'feishu', prefixes: ['FEISHU_'] },
  { id: 'telegram', prefixes: ['TELEGRAM_'] },
  { id: 'dingtalk', prefixes: ['DINGTALK_'] },
  { id: 'email', prefixes: ['EMAIL_'] },
  { id: 'discord', prefixes: ['DISCORD_'] },
  { id: 'slack', prefixes: ['SLACK_'] },
  { id: 'pushplus', prefixes: ['PUSHPLUS_'] },
  { id: 'pushover', prefixes: ['PUSHOVER_'] },
  { id: 'ntfy', prefixes: ['NTFY_'] },
  { id: 'gotify', prefixes: ['GOTIFY_'] },
  { id: 'serverchan', prefixes: ['SERVERCHAN3_'], routingValue: 'serverchan3' },
  { id: 'astrbot', prefixes: ['ASTRBOT_'] },
  { id: 'custom_webhook', prefixes: ['CUSTOM_WEBHOOK_'], routingValue: 'custom' },
];

export function isNotificationChannelKey(key: string): boolean {
  return NOTIFICATION_CHANNELS.some((channel) => channel.prefixes.some((prefix) => key.startsWith(prefix)));
}

/** A channel config value counts as configured when it is non-empty and not a disabled switch. */
export function isConfiguredChannelValue(value: unknown): boolean {
  const normalized = String(value ?? '').trim().toLowerCase();
  return normalized !== '' && normalized !== 'false';
}

/**
 * Routing values (as used by NOTIFICATION_*_CHANNELS) of every channel that has
 * at least one configured key. Keys are expected in UPPERCASE.
 */
export function getConfiguredRoutingValues(valuesByUpperKey: Record<string, string>): Set<string> {
  const keys = Object.keys(valuesByUpperKey);
  const configured = new Set<string>();
  for (const channel of NOTIFICATION_CHANNELS) {
    const hasConfiguredKey = keys.some(
      (key) =>
        channel.prefixes.some((prefix) => key.startsWith(prefix))
        && isConfiguredChannelValue(valuesByUpperKey[key]),
    );
    if (hasConfiguredKey) {
      configured.add(channel.routingValue ?? channel.id);
    }
  }
  return configured;
}
