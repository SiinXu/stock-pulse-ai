export interface NotificationChannel {
  id: string;
  prefixes: string[];
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
  { id: 'serverchan', prefixes: ['SERVERCHAN3_'] },
  { id: 'astrbot', prefixes: ['ASTRBOT_'] },
  { id: 'custom_webhook', prefixes: ['CUSTOM_WEBHOOK_'] },
];

export function isNotificationChannelKey(key: string): boolean {
  return NOTIFICATION_CHANNELS.some((channel) => channel.prefixes.some((prefix) => key.startsWith(prefix)));
}
