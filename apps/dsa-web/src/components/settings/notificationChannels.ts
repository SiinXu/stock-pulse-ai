export interface NotificationChannel {
  id: string;
  prefixes: string[];
  /** Complete key groups that can independently enable this channel. */
  configurationGroups: string[][];
  /** Optional runtime-equivalent validation beyond key presence. */
  validate?: (valuesByUpperKey: Record<string, string>) => boolean;
  /** Value used by NOTIFICATION_*_CHANNELS routing fields when it differs from the config id. */
  routingValue?: string;
}

function parseHttpUrl(value: unknown): URL | null {
  const rawValue = String(value ?? '').trim();
  if (!rawValue) return null;

  try {
    const url = new URL(rawValue);
    if ((url.protocol !== 'http:' && url.protocol !== 'https:') || !url.host) return null;
    return url;
  } catch {
    return null;
  }
}

function isValidNtfyEndpoint(valuesByUpperKey: Record<string, string>): boolean {
  const url = parseHttpUrl(valuesByUpperKey.NTFY_URL);
  if (!url) return false;

  const pathSegments = url.pathname.split('/').filter(Boolean);
  if (pathSegments.length === 0) return false;

  const rawTopic = pathSegments[pathSegments.length - 1];
  try {
    return decodeURIComponent(rawTopic).trim() !== '';
  } catch {
    // Python's urllib.parse.unquote preserves malformed escapes, so they still
    // count as a non-empty runtime topic.
    return rawTopic.trim() !== '';
  }
}

function isValidGotifyServer(valuesByUpperKey: Record<string, string>): boolean {
  const url = parseHttpUrl(valuesByUpperKey.GOTIFY_URL);
  if (!url || url.search || url.hash) return false;

  const pathSegments = url.pathname.split('/').filter(Boolean);
  return pathSegments.at(-1)?.toLowerCase() !== 'message';
}

function hasCustomWebhookEndpoint(valuesByUpperKey: Record<string, string>): boolean {
  return String(valuesByUpperKey.CUSTOM_WEBHOOK_URLS ?? '')
    .split(',')
    .some((value) => value.trim() !== '');
}

export const NOTIFICATION_CHANNELS: NotificationChannel[] = [
  {
    id: 'wechat',
    prefixes: ['WECHAT_'],
    configurationGroups: [['WECHAT_WEBHOOK_URL']],
  },
  {
    id: 'feishu',
    prefixes: ['FEISHU_'],
    configurationGroups: [
      ['FEISHU_WEBHOOK_URL'],
      ['FEISHU_APP_ID', 'FEISHU_APP_SECRET', 'FEISHU_CHAT_ID'],
    ],
  },
  {
    id: 'telegram',
    prefixes: ['TELEGRAM_'],
    configurationGroups: [['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']],
  },
  {
    id: 'dingtalk',
    prefixes: ['DINGTALK_'],
    configurationGroups: [['DINGTALK_WEBHOOK_URL']],
  },
  {
    id: 'email',
    prefixes: ['EMAIL_'],
    configurationGroups: [['EMAIL_SENDER', 'EMAIL_PASSWORD']],
  },
  {
    id: 'discord',
    prefixes: ['DISCORD_'],
    configurationGroups: [
      ['DISCORD_WEBHOOK_URL'],
      ['DISCORD_BOT_TOKEN', 'DISCORD_MAIN_CHANNEL_ID'],
      ['DISCORD_BOT_TOKEN', 'DISCORD_CHANNEL_ID'],
    ],
  },
  {
    id: 'slack',
    prefixes: ['SLACK_'],
    configurationGroups: [
      ['SLACK_WEBHOOK_URL'],
      ['SLACK_BOT_TOKEN', 'SLACK_CHANNEL_ID'],
    ],
  },
  {
    id: 'pushplus',
    prefixes: ['PUSHPLUS_'],
    configurationGroups: [['PUSHPLUS_TOKEN']],
  },
  {
    id: 'pushover',
    prefixes: ['PUSHOVER_'],
    configurationGroups: [['PUSHOVER_USER_KEY', 'PUSHOVER_API_TOKEN']],
  },
  {
    id: 'ntfy',
    prefixes: ['NTFY_'],
    configurationGroups: [['NTFY_URL']],
    validate: isValidNtfyEndpoint,
  },
  {
    id: 'gotify',
    prefixes: ['GOTIFY_'],
    configurationGroups: [['GOTIFY_URL', 'GOTIFY_TOKEN']],
    validate: isValidGotifyServer,
  },
  {
    id: 'serverchan',
    prefixes: ['SERVERCHAN3_'],
    configurationGroups: [['SERVERCHAN3_SENDKEY']],
    routingValue: 'serverchan3',
  },
  {
    id: 'astrbot',
    prefixes: ['ASTRBOT_'],
    configurationGroups: [['ASTRBOT_URL']],
  },
  {
    id: 'custom_webhook',
    prefixes: ['CUSTOM_WEBHOOK_'],
    configurationGroups: [['CUSTOM_WEBHOOK_URLS']],
    validate: hasCustomWebhookEndpoint,
    routingValue: 'custom',
  },
];

export function isNotificationChannelKey(key: string): boolean {
  return NOTIFICATION_CHANNELS.some((channel) => channel.prefixes.some((prefix) => key.startsWith(prefix)));
}

/** A channel config value counts as configured when it is non-empty and not a disabled switch. */
export function isConfiguredChannelValue(value: unknown): boolean {
  const normalized = String(value ?? '').trim().toLowerCase();
  return normalized !== '' && normalized !== 'false';
}

function hasRequiredConfigurationValue(value: unknown): boolean {
  return String(value ?? '').trim() !== '';
}

/**
 * Routing values (as used by NOTIFICATION_*_CHANNELS) of every channel with a
 * complete runtime configuration group. Keys are expected in UPPERCASE.
 */
export function getConfiguredRoutingValues(valuesByUpperKey: Record<string, string>): Set<string> {
  const configured = new Set<string>();
  for (const channel of NOTIFICATION_CHANNELS) {
    const hasCompleteConfiguration = channel.configurationGroups.some(
      (group) => group.every((key) => hasRequiredConfigurationValue(valuesByUpperKey[key])),
    );
    if (hasCompleteConfiguration && (!channel.validate || channel.validate(valuesByUpperKey))) {
      configured.add(channel.routingValue ?? channel.id);
    }
  }
  return configured;
}
