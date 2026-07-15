import type { UiLanguage } from '../i18n/uiText';

const zh = {
  configured: '已配置', unconfigured: '未配置',
  wechat: '企业微信', feishu: '飞书', telegram: 'Telegram', dingtalk: '钉钉', email: '邮件', discord: 'Discord', slack: 'Slack', pushplus: 'PushPlus', pushover: 'Pushover', ntfy: 'ntfy', gotify: 'Gotify', serverchan: 'Server酱', astrbot: 'AstrBot', custom_webhook: '自定义 Webhook',
  custom: '自定义 Webhook',
} as const;

const en: Record<keyof typeof zh, string> = {
  configured: 'Configured', unconfigured: 'Not configured',
  wechat: 'WeCom', feishu: 'Feishu', telegram: 'Telegram', dingtalk: 'DingTalk', email: 'Email', discord: 'Discord', slack: 'Slack', pushplus: 'PushPlus', pushover: 'Pushover', ntfy: 'ntfy', gotify: 'Gotify', serverchan: 'ServerChan', astrbot: 'AstrBot', custom_webhook: 'Custom Webhook',
  custom: 'Custom Webhook',
};

export const SETTINGS_NOTIFICATION_TEXT: Record<UiLanguage, Record<keyof typeof zh, string>> = { zh, en };

export function getNotificationChannelLabel(id: string, language: UiLanguage): string {
  const labels = SETTINGS_NOTIFICATION_TEXT[language] as Record<string, string>;
  return labels[id] ?? id;
}
