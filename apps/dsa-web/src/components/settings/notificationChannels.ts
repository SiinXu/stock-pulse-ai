export interface NotificationChannel {
  id: string;
  label: string;
  prefixes: string[];
}

export const NOTIFICATION_CHANNELS: NotificationChannel[] = [
  { id: 'wechat', label: '企业微信', prefixes: ['WECHAT_'] },
  { id: 'feishu', label: '飞书', prefixes: ['FEISHU_'] },
  { id: 'telegram', label: 'Telegram', prefixes: ['TELEGRAM_'] },
  { id: 'dingtalk', label: '钉钉', prefixes: ['DINGTALK_'] },
  { id: 'email', label: '邮件', prefixes: ['EMAIL_'] },
  { id: 'discord', label: 'Discord', prefixes: ['DISCORD_'] },
  { id: 'slack', label: 'Slack', prefixes: ['SLACK_'] },
  { id: 'pushplus', label: 'PushPlus', prefixes: ['PUSHPLUS_'] },
  { id: 'pushover', label: 'Pushover', prefixes: ['PUSHOVER_'] },
  { id: 'ntfy', label: 'ntfy', prefixes: ['NTFY_'] },
  { id: 'gotify', label: 'Gotify', prefixes: ['GOTIFY_'] },
  { id: 'serverchan', label: 'Server酱', prefixes: ['SERVERCHAN3_'] },
  { id: 'astrbot', label: 'AstrBot', prefixes: ['ASTRBOT_'] },
  { id: 'custom_webhook', label: '自定义 Webhook', prefixes: ['CUSTOM_WEBHOOK_'] },
];

export function isNotificationChannelKey(key: string): boolean {
  return NOTIFICATION_CHANNELS.some((channel) => channel.prefixes.some((prefix) => key.startsWith(prefix)));
}
